from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
SERVICES = ("postgres", "redis", "graph", "vector", "minio", "api", "worker", "web")
APP_SECRET_NAMES = (
    "GLOBAL_PASSWORD",
    "JWT_SECRET_KEY",
    "ADMIN_PASSWORD",
    "GEMINI_API_KEY",
    "SILICONFLOW_API_KEY",
    "SUPABASE_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "GROQ_API_KEY",
)
OWNER_LABEL = "io.yunesa.ci.run"


class IntegrationError(RuntimeError):
    pass


def run(
    arguments: list[str], *, env: dict[str, str], label: str, data: bytes | None = None, timeout: int = 120
) -> bytes:
    try:
        result = subprocess.run(
            arguments, env=env, input=data, capture_output=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise IntegrationError(f"{label}: command unavailable or deadline exceeded") from error
    if result.returncode:
        raise IntegrationError(f"{label}: exit {result.returncode}; raw output suppressed")
    return result.stdout


def secure_write(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
    path.chmod(0o600)


class IntegrationRun:
    def __init__(self, directory: Path):
        if any(name in os.environ for name in APP_SECRET_NAMES) or os.getenv("CI_ENVIRONMENT_NAME") == "production":
            raise IntegrationError("Integration job must not receive application secrets or the production environment")
        job = os.getenv("CI_JOB_ID", "")
        commit = os.getenv("CI_COMMIT_SHA", "")
        if not re.fullmatch(r"[1-9][0-9]{0,19}", job) or not re.fullmatch(r"[a-f0-9]{40}", commit):
            raise IntegrationError("Validated CI_JOB_ID and full CI_COMMIT_SHA required")
        prefix = os.getenv("CI_REGISTRY_IMAGE", "")
        registry = os.getenv("CI_REGISTRY", "")
        if not prefix.startswith(registry + "/") or not registry:
            raise IntegrationError("Project registry configuration missing")
        self.images = {}
        for kind in ("API", "WEB", "MINIO"):
            image = os.getenv(f"YUNESA_{kind}_IMAGE", "")
            if not re.fullmatch(re.escape(prefix + "/" + kind.lower() + "@sha256:") + r"[a-f0-9]{64}", image):
                raise IntegrationError(f"{kind} must be a built project image pinned by digest")
            self.images[f"YUNESA_{kind}_IMAGE"] = image
        self.nonce = secrets.token_hex(6)
        self.project = f"yunesa-ci-{job}-{self.nonce}"
        self.directory = directory
        self.claimed = False
        self.anonymous_volumes: set[str] = set()
        self.initial_volumes: set[str] = set()
        self.env = {
            name: value
            for name, value in os.environ.items()
            if name
            in (
                "PATH",
                "SystemRoot",
                "SYSTEMROOT",
                "TEMP",
                "TMP",
                "HOME",
                "USERPROFILE",
                "LANG",
                "LC_ALL",
                "DOCKER_HOST",
                "DOCKER_TLS_VERIFY",
                "DOCKER_CERT_PATH",
                "DOCKER_CONTEXT",
                "DOCKER_API_VERSION",
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "NO_PROXY",
                "http_proxy",
                "https_proxy",
                "no_proxy",
            )
        }
        self.env.update(
            {"DOCKER_CONFIG": str(directory / "docker-config"), "COMPOSE_PROFILES": "", "COMPOSE_DISABLE_ENV_FILE": "1"}
        )
        (directory / "docker-config").mkdir(mode=0o700)
        app_env = {
            **self.images,
            "GLOBAL_PASSWORD": secrets.token_urlsafe(24),
            "JWT_SECRET_KEY": secrets.token_urlsafe(48),
            "GEMINI_API_KEY": "ci-placeholder-never-invoked",
            "SILICONFLOW_API_KEY": "ci-placeholder-never-invoked",
            "MINIO_PUBLIC_BASE_URL": "http://web",
            "YUNESA_STATE_ROOT": "/ci-placeholder-never-mounted",
            "YUNESA_CI_RUN_ID": self.nonce,
        }
        secure_write(directory / ".env", "".join(f"{name}={value}\n" for name, value in app_env.items()))
        self.credentials = directory / "admin.json"
        secure_write(
            self.credentials,
            json.dumps({"username": f"ciadmin{job}", "password": "Ci!Aa1-" + secrets.token_urlsafe(24)}),
        )
        for filename in ("docker-compose.prod.yml", "docker-compose.ci.yml"):
            shutil.copyfile(SOURCE / filename, directory / filename)
        self.command = [
            "docker",
            "compose",
            "--project-name",
            self.project,
            "--project-directory",
            str(directory),
            "--env-file",
            str(directory / ".env"),
            "-f",
            str(directory / "docker-compose.prod.yml"),
            "-f",
            str(directory / "docker-compose.ci.yml"),
        ]
        self.report = {"project": self.project, "commit": commit, "images": self.images}

    def docker(self, *arguments: str, label: str, timeout: int = 120, data: bytes | None = None) -> bytes:
        return run(["docker", *arguments], env=self.env, label=label, timeout=timeout, data=data)

    def compose(self, *arguments: str, label: str, timeout: int = 120) -> bytes:
        return run([*self.command, *arguments], env=self.env, label=label, timeout=timeout)

    def resources(self, kind: str) -> list[str]:
        args = [kind, "ls", "--quiet", "--filter", "label=com.docker.compose.project=" + self.project]
        if kind == "container":
            args.append("--all")
        return self.docker(*args, label=f"Inventory CI {kind}s", timeout=20).decode().split()

    def validate(self) -> None:
        version = self.docker("compose", "version", "--short", label="Check Compose compatibility").decode().strip()
        match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", version)
        if not match or tuple(map(int, match.groups())) < (2, 24, 4):
            raise IntegrationError("Docker Compose 2.24.4+ required for isolated volume overrides")
        model = json.loads(self.compose("config", "--format", "json", label="Validate isolated Compose model"))
        if model.get("name") != self.project or set(model.get("services", {})) != set(SERVICES):
            raise IntegrationError("CI Compose project or service set differs from the isolated baseline")
        for service in model["services"].values():
            if (
                service.get("ports")
                or service.get("container_name")
                or service.get("network_mode")
                or service.get("build")
            ):
                raise IntegrationError("CI services must use built images and an isolated network without host ports")
            if service.get("env_file") or service.get("labels", {}).get(OWNER_LABEL) != self.nonce:
                raise IntegrationError("CI services must have isolated ownership and no inherited environment files")
            if set(service.get("networks", {})) != {"app-network"}:
                raise IntegrationError("CI services must use only the isolated app network")
            if any(volume.get("type") != "volume" for volume in service.get("volumes", [])):
                raise IntegrationError("Host binds are forbidden in CI integration")
        expected = {"/app/data": "ci-data", "/app/saves": "ci-saves", "/models": "ci-models"}
        for name in ("api", "worker", "web"):
            mounts = {item["target"]: item["source"] for item in model["services"][name].get("volumes", [])}
            if mounts != (expected if name != "web" else {"/app/data": "ci-data"}):
                raise IntegrationError("Application state must use only the new CI named volumes")
        for kind in ("volumes", "networks"):
            for name, resource in model.get(kind, {}).items():
                if resource.get("external") or resource.get("name") != self.project + "_" + name:
                    raise IntegrationError("CI resources must use their unique project namespace")
                if resource.get("labels", {}).get(OWNER_LABEL) != self.nonce:
                    raise IntegrationError("CI resource ownership label missing")
        if model["networks"]["app-network"].get("internal") is not True:
            raise IntegrationError("CI application network must deny external provider access")
        for kind in ("container", "network", "volume"):
            names = self.docker(
                kind,
                "ls",
                "--format",
                "{{.Name}}" if kind != "container" else "{{.Names}}",
                "--filter",
                "name=" + self.project,
                *(["--all"] if kind == "container" else []),
                label=f"Check fresh CI {kind} namespace",
            )
            if names.strip() or self.resources(kind):
                raise IntegrationError("CI namespace already exists; refusing to reuse or remove it")
        self.initial_volumes = set(
            self.docker("volume", "ls", "--quiet", label="Record preexisting volume names").decode().split()
        )
        self.report["compose_version"] = version

    def metadata(self) -> list[dict]:
        ids = self.resources("container")
        if not ids:
            return []
        template = (
            '{"name":"{{.Name}}","service":"{{index .Config.Labels "com.docker.compose.service"}}",'
            '"state":{"status":"{{.State.Status}}","exitCode":{{.State.ExitCode}},'
            '"OOMKilled":{{.State.OOMKilled}}},"restartCount":{{.RestartCount}},'
            '"health":{"status":"{{if .State.Health}}{{.State.Health.Status}}{{end}}"}}'
        )
        output = self.docker(
            "container", "inspect", *ids, "--format", template, label="Capture safe CI state", timeout=30
        )
        for identifier in ids:
            mounts = json.loads(
                self.docker(
                    "container",
                    "inspect",
                    identifier,
                    "--format",
                    "{{json .Mounts}}",
                    label="Track CI image-declared volumes",
                    timeout=10,
                )
            )
            for mount in mounts:
                name = mount.get("Name", "")
                if mount.get("Type") == "volume" and not name.startswith(self.project + "_"):
                    if not re.fullmatch(r"[a-f0-9]{64}", name) or name in self.initial_volumes:
                        raise IntegrationError("CI container unexpectedly reused an unrelated volume")
                    self.anonymous_volumes.add(name)
        return [json.loads(line) for line in output.decode().splitlines()]

    def execute(self) -> None:
        self.validate()
        platform = (
            self.docker("info", "--format", "{{.OSType}}/{{.Architecture}}", label="Check build host platform")
            .decode()
            .strip()
        )
        if platform not in {"linux/arm64", "linux/aarch64"}:
            raise IntegrationError("Real Linux ARM64 Docker host required for integration")
        self.claimed = True
        username, password = os.getenv("CI_REGISTRY_USER", ""), os.getenv("CI_REGISTRY_PASSWORD", "")
        if not username or not password:
            raise IntegrationError("Registry job credentials required; application keys must remain absent")
        self.docker(
            "login",
            os.environ["CI_REGISTRY"],
            "--username",
            username,
            "--password-stdin",
            label="Authenticate project registry",
            data=password.encode(),
        )
        for path in (self.directory / "docker-config").rglob("*"):
            if path.is_file():
                path.chmod(0o600)
        self.compose("pull", "--quiet", *SERVICES, label="Pull exact integration images", timeout=900)
        for image in self.images.values():
            actual = (
                self.docker(
                    "image",
                    "inspect",
                    image,
                    "--format",
                    "{{.Os}}/{{.Architecture}}",
                    label="Verify built image architecture",
                )
                .decode()
                .strip()
            )
            if actual != "linux/arm64":
                raise IntegrationError("Built integration image is not Linux ARM64")
        self.compose(
            "up",
            "--wait",
            "--wait-timeout",
            "300",
            "--no-build",
            "--pull",
            "never",
            *SERVICES,
            label="Wait for eight real integration services",
            timeout=360,
        )
        states = self.metadata()
        if set(item["service"] for item in states) != set(SERVICES) or any(
            item["state"]["status"] != "running" or item["health"]["status"] != "healthy" or item["state"]["OOMKilled"]
            for item in states
        ):
            raise IntegrationError("All eight integration services must be healthy without OOM")
        api = self.compose("ps", "--quiet", "api", label="Locate isolated API").decode().strip()
        if not re.fullmatch(r"[a-f0-9]{12,64}", api):
            raise IntegrationError("Isolated API container unavailable")
        probe, credentials = f"/tmp/ci-{self.nonce}-readiness.py", f"/tmp/ci-{self.nonce}-admin.json"
        self.docker(
            "cp",
            str(SOURCE / "scripts" / "deployment-readiness.py"),
            api + ":" + probe,
            label="Install unchanged application readiness probe",
        )
        self.docker("cp", str(self.credentials), api + ":" + credentials, label="Copy synthetic CI credentials")
        self.docker("exec", api, "chmod", "600", credentials, label="Protect synthetic credentials inside API")
        initialized = self.docker(
            "exec",
            "-i",
            api,
            "python",
            probe,
            "--initialize-admin",
            label="Initialize real application admin internally",
            data=self.credentials.read_bytes(),
        )
        self.report["admin"] = json.loads(initialized)
        self.report["storage"] = json.loads(
            self.docker(
                "exec", api, "python", probe, "--inside-storage", label="Exercise real application storage", timeout=180
            )
        )
        self.report["http"] = json.loads(
            self.docker(
                "exec",
                api,
                "python",
                probe,
                "--base-url",
                "http://web",
                "--credentials",
                credentials,
                label="Exercise frontend, login, authorization and conversation persistence",
                timeout=360,
            )
        )
        final_states = self.metadata()
        if set(item["service"] for item in final_states) != set(SERVICES) or any(
            item["state"]["status"] != "running"
            or item["health"]["status"] != "healthy"
            or item["state"]["OOMKilled"]
            or item["restartCount"]
            for item in final_states
        ):
            raise IntegrationError("An integration service failed during the real application probes")
        self.report["containers"] = final_states

    def cleanup(self) -> None:
        for kind in ("container", "network", "volume"):
            ids = self.resources(kind)
            if ids:
                labels = (
                    self.docker(
                        kind,
                        "inspect",
                        *ids,
                        "--format",
                        '{{index .Config.Labels "' + OWNER_LABEL + '"}}'
                        if kind == "container"
                        else '{{index .Labels "' + OWNER_LABEL + '"}}',
                        label=f"Verify ownership before CI {kind} cleanup",
                        timeout=30,
                    )
                    .decode()
                    .splitlines()
                )
                if any(label != self.nonce for label in labels):
                    raise IntegrationError("Refusing cleanup of resources without this CI run's ownership label")
        self.compose(
            "down",
            "--volumes",
            "--remove-orphans",
            "--timeout",
            "15",
            label="Remove only isolated CI resources",
            timeout=180,
        )
        remaining = any(self.resources(kind) for kind in ("container", "network", "volume"))
        names = set(
            self.docker("volume", "ls", "--quiet", label="Confirm anonymous CI volume cleanup").decode().split()
        )
        if remaining or names.intersection(self.anonymous_volumes):
            raise IntegrationError("Isolated CI resources remain after cleanup")


def interrupted(signum: int, _frame) -> None:
    raise IntegrationError(f"Integration interrupted by signal {signum}")


def main() -> int:
    os.umask(0o077)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, interrupted)
    report: dict = {"status": "failed"}
    failure = ""
    with tempfile.TemporaryDirectory(prefix="yunesa-ci-") as temporary:
        instance = None
        try:
            instance = IntegrationRun(Path(temporary))
            report = instance.report
            instance.execute()
        except (IntegrationError, OSError, ValueError) as error:
            failure = (
                str(error)
                if isinstance(error, IntegrationError)
                else f"Integration validation failed ({type(error).__name__})"
            )
        finally:
            if instance and instance.claimed:
                try:
                    report["containers"] = instance.metadata()
                except (IntegrationError, ValueError):
                    report["diagnostics"] = "Safe container metadata unavailable"
                try:
                    instance.cleanup()
                    report["cleanup"] = "passed"
                except (IntegrationError, ValueError) as error:
                    report["cleanup"] = "failed"
                    report["cleanup_error"] = (
                        str(error) if isinstance(error, IntegrationError) else "Cleanup state invalid"
                    )
                    failure = failure or "Integration resource cleanup failed"
            else:
                report["cleanup"] = "not-started"
    report["status"] = "failed" if failure else "passed"
    if failure:
        report["error"] = failure
    destination = SOURCE / "artifacts" / "integration-baseline.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if failure:
        print(failure, file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
