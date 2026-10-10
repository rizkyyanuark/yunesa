from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, UTC
from pathlib import Path

ROOT = Path("/opt/yunesa-app")
PROJECT = "yunesa-app"
SERVICES = ("postgres", "redis", "graph", "vector", "minio", "api", "worker", "web")
SECRET_NAMES = ("GLOBAL_PASSWORD", "JWT_SECRET_KEY", "GEMINI_API_KEY", "SILICONFLOW_API_KEY")
OPTIONAL_NAMES = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")


class DeployError(RuntimeError):
    pass


def run(arguments: list[str], *, label: str, data: bytes | None = None, timeout: int = 300, output_file=None) -> bytes:
    try:
        result = subprocess.run(
            arguments,
            input=data,
            stdout=output_file or subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DeployError(f"{label}: command unavailable or deadline exceeded") from error
    if result.returncode:
        raise DeployError(f"{label}: exit {result.returncode}; raw output suppressed")
    return result.stdout or b""


def secure_write(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
    path.chmod(0o600)


def checked_config(path: Path) -> dict:
    if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
        raise DeployError("Trusted configuration must be root-owned and not group/world writable")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_request(payload: dict, operation: str, registry: dict) -> None:
    allowed = set(
        SECRET_NAMES
        + OPTIONAL_NAMES
        + (
            "ADMIN_PASSWORD",
            "CI_COMMIT_SHA",
            "CI_REGISTRY",
            "CI_REGISTRY_IMAGE",
            "CI_REGISTRY_USER",
            "CI_REGISTRY_PASSWORD",
            "YUNESA_API_IMAGE",
            "YUNESA_WEB_IMAGE",
        )
    )
    allowed.add("YUNESA_MINIO_IMAGE")
    allowed.add("YUNESA_CONFIG_SHA256")
    if (
        not isinstance(payload, dict)
        or set(payload) - allowed
        or any(not isinstance(value, str) for value in payload.values())
    ):
        raise DeployError("Request contains unsupported fields")
    if not re.fullmatch(r"[a-f0-9]{40}", payload.get("CI_COMMIT_SHA", "")):
        raise DeployError("Request must identify a full commit SHA")
    if (
        payload.get("CI_REGISTRY") != registry["registry"]
        or payload.get("CI_REGISTRY_IMAGE") != registry["image_prefix"]
    ):
        raise DeployError("Registry/project differs from root-installed configuration")
    if not payload.get("CI_REGISTRY_USER") or not payload.get("CI_REGISTRY_PASSWORD"):
        raise DeployError("Registry job credentials missing")
    if operation == "deploy":
        if payload.get("YUNESA_CONFIG_SHA256") != registry.get("config_sha256"):
            raise DeployError("Trusted host configuration differs from the pipeline source; refresh host bootstrap")
        for name in (*SECRET_NAMES, "ADMIN_PASSWORD"):
            if not payload.get(name) or any(char in payload[name] for char in "\r\n\x00"):
                raise DeployError(f"Required variable {name} missing or multiline")
        # Database URL interpolation requires this alphabet; rotating existing state is a separate operation.
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,}", payload["GLOBAL_PASSWORD"]):
            raise DeployError("GLOBAL_PASSWORD must be a URL-safe value of at least 8 characters")
        for kind in ("API", "WEB", "MINIO"):
            image = payload.get(f"YUNESA_{kind}_IMAGE", "")
            prefix = re.escape(registry["image_prefix"] + "/" + kind.lower() + "@sha256:")
            if not re.fullmatch(prefix + r"[a-f0-9]{64}", image):
                raise DeployError(f"{kind} image must use a digest from the configured project")


def compose(release: Path, *arguments: str, label: str, output_file=None, timeout: int = 600) -> bytes:
    return run(
        [
            "docker",
            "compose",
            "--project-name",
            PROJECT,
            "--project-directory",
            str(release),
            "--env-file",
            str(release / ".env"),
            "-f",
            str(release / "docker-compose.prod.yml"),
            *arguments,
        ],
        label=label,
        output_file=output_file,
        timeout=timeout,
    )


def image_platform(image: str) -> None:
    info = json.loads(run(["docker", "image", "inspect", image, "--format", "{{json .}}"], label="Inspect image"))
    if info["Architecture"] != "arm64" or info["Os"] != "linux":
        raise DeployError("Release image is not Linux ARM64")


def create_release(payload: dict) -> Path:
    release = ROOT / "releases" / (payload["CI_COMMIT_SHA"] + "-" + datetime.now(UTC).strftime("%Y%m%d%H%M%S"))
    release.mkdir(mode=0o700, parents=True)
    for name in ("docker-compose.prod.yml", "deployment-readiness.py"):
        source = ROOT / "config" / name
        if source.is_symlink() or source.stat().st_uid != 0 or source.stat().st_mode & 0o022:
            raise DeployError("Release source must come from root-installed trusted configuration")
        shutil.copy2(source, release / name)
    env = {name: payload[name] for name in SECRET_NAMES}
    env.update({name: payload.get(name, "") for name in OPTIONAL_NAMES})
    env.update(
        {
            "YUNESA_API_IMAGE": payload["YUNESA_API_IMAGE"],
            "YUNESA_WEB_IMAGE": payload["YUNESA_WEB_IMAGE"],
            "YUNESA_MINIO_IMAGE": payload["YUNESA_MINIO_IMAGE"],
            "YUNESA_STATE_ROOT": str(ROOT / "shared"),
            "MINIO_PUBLIC_BASE_URL": "https://yunesa.tugasakhir.space",
        }
    )
    for name, value in env.items():
        if any(char in value for char in "\r\n\x00'\\"):
            raise DeployError(f"Unsupported dotenv characters in {name}")
    secure_write(release / ".env", "".join(f"{name}='{value}'\n" for name, value in env.items()))
    secure_write(
        release / "manifest.json",
        json.dumps(
            {
                "commit": payload["CI_COMMIT_SHA"],
                "api_image": payload["YUNESA_API_IMAGE"],
                "web_image": payload["YUNESA_WEB_IMAGE"],
                "minio_image": payload["YUNESA_MINIO_IMAGE"],
                "config_sha256": payload["YUNESA_CONFIG_SHA256"],
                "project": PROJECT,
                "created_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
        + "\n",
    )
    compose(release, "config", "--quiet", label="Validate production Compose")
    return release


def pointed_release(name: str) -> Path | None:
    link = ROOT / name
    if not link.exists():
        return None
    target = link.resolve()
    if not target.is_relative_to(ROOT / "releases") or not target.is_dir():
        raise DeployError("Release link points outside trusted releases")
    return target


def set_release_link(name: str, release: Path) -> None:
    temporary = ROOT / ("." + name + "-" + secrets.token_hex(4))
    temporary.symlink_to(release, target_is_directory=True)
    temporary.replace(ROOT / name)


def backup(release: Path) -> Path:
    run(["docker", "pull", "alpine:3.22"], label="Prepare backup helper image")
    compose(release, "stop", "web", label="Stop accepting public application requests")
    active = compose(
        release,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-tAc",
        "SELECT count(*) FROM agent_runs WHERE status IN ('queued','running')",
        label="Check active runs",
    ).strip()
    if active != b"0":
        raise DeployError("Queued/running application work must finish before backup/cutover")
    directory = ROOT / "backups" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    directory.mkdir(mode=0o700, parents=True)
    compose(release, "stop", "web", "api", "worker", label="Quiesce application writers")
    with (directory / "postgres.dump").open("wb") as stream:
        compose(
            release,
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-Fc",
            label="Backup PostgreSQL",
            output_file=stream,
        )
    compose(release, "stop", "graph", "vector", "redis", "minio", label="Stop storage for consistent snapshots")
    for service in ("memgraph", "qdrant", "redis", "minio"):
        volume = f"{PROJECT}_{service}-data"
        labels = json.loads(
            run(
                ["docker", "volume", "inspect", volume, "--format", "{{json .Labels}}"],
                label="Check backup volume ownership",
            )
        )
        if labels.get("com.docker.compose.project") != PROJECT:
            raise DeployError("Backup volume does not belong to the new deployment")
        run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--mount",
                f"type=volume,src={volume},dst=/source,readonly",
                "--mount",
                f"type=bind,src={directory},dst=/backup",
                "alpine:3.22",
                "tar",
                "-czf",
                f"/backup/{service}.tar.gz",
                "-C",
                "/source",
                ".",
            ],
            label=f"Backup {service}",
        )
    with tarfile.open(directory / "shared.tar.gz", "w:gz") as archive:
        for name in ("data", "saves", "models"):
            archive.add(ROOT / "shared" / name, arcname=name)
    shutil.copy2(release / ".env", directory / "production.env")
    shutil.copy2(release / "manifest.json", directory / "manifest.json")
    for archive_path in directory.glob("*.tar.gz"):
        with tarfile.open(archive_path, "r:gz") as archive:
            for _ in archive:
                pass
    run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--mount",
            f"type=bind,src={directory},dst=/backup,readonly",
            "postgres:16-alpine",
            "pg_restore",
            "--list",
            "/backup/postgres.dump",
        ],
        label="Check PostgreSQL dump",
    )
    checksums = {}
    for item in directory.iterdir():
        with item.open("rb") as stream:
            checksums[item.name] = hashlib.file_digest(stream, "sha256").hexdigest()
    secure_write(directory / "checksums.json", json.dumps(checksums, sort_keys=True) + "\n")
    for item in directory.iterdir():
        item.chmod(0o600)
    return directory


def readiness(release: Path, *, providers: bool) -> dict:
    probe = release / "deployment-readiness.py"
    api = compose(release, "ps", "-q", "api", label="Locate API container").decode().strip()
    if not re.fullmatch(r"[a-f0-9]{12,64}", api):
        raise DeployError("API container unavailable for dependency probes")
    run(["docker", "cp", str(probe), api + ":/tmp/yunesa-readiness.py"], label="Install runtime probe")
    run(
        ["docker", "exec", "-i", api, "python", "/tmp/yunesa-readiness.py", "--initialize-admin"],
        label="Initialize admin through the internal auth API",
        data=(ROOT / "shared" / "admin-credentials.json").read_bytes(),
    )
    storage = json.loads(
        compose(
            release,
            "exec",
            "-T",
            "api",
            "python",
            "/tmp/yunesa-readiness.py",
            "--inside-storage",
            label="Check real storage dependencies",
        )
    )
    http = json.loads(
        run(
            [
                sys.executable,
                str(probe),
                "--base-url",
                "http://127.0.0.1:8088",
                "--credentials",
                str(ROOT / "shared" / "admin-credentials.json"),
                *(["--chat"] if providers else []),
            ],
            label="Check auth and persistence",
            timeout=600,
        )
    )
    public = json.loads(
        run(
            [
                sys.executable,
                str(probe),
                "--base-url",
                "https://yunesa.tugasakhir.space",
                "--credentials",
                str(ROOT / "shared" / "admin-credentials.json"),
            ],
            label="Check public domain path",
        )
    )
    result = {"storage": storage, "http_local": http, "http_public": public}
    if providers:
        result["providers"] = json.loads(
            compose(
                release,
                "exec",
                "-T",
                "api",
                "python",
                "/tmp/yunesa-readiness.py",
                "--inside-provider",
                label="Check configured providers",
            )
        )
    return result


def deploy(payload: dict, operation: str) -> dict:
    current = pointed_release("current")
    previous = pointed_release("previous")
    if operation == "rollback":
        if current is None or previous is None:
            raise DeployError("Rollback requires current and previous successful releases")
        try:
            backup(current)
            compose(
                previous,
                "up",
                "-d",
                "--no-build",
                "--wait",
                "--wait-timeout",
                "300",
                *SERVICES,
                label="Start previous release",
            )
            evidence = readiness(previous, providers=False)
        except DeployError:
            compose(
                current,
                "up",
                "-d",
                "--no-build",
                "--wait",
                "--wait-timeout",
                "300",
                *SERVICES,
                label="Restore current release after rollback failure",
            )
            raise
        set_release_link("previous", current)
        set_release_link("current", previous)
        return {"operation": "rollback", "release": previous.name, "readiness": evidence}
    if current:
        old_env = (current / ".env").read_text(encoding="utf-8")
        if f"GLOBAL_PASSWORD='{payload['GLOBAL_PASSWORD']}'\n" not in old_env:
            raise DeployError("Changing GLOBAL_PASSWORD with existing volumes requires a separate rotation plan")
    release = create_release(payload)
    compose(release, "pull", *SERVICES, label="Pull release images", timeout=1200)
    image_platform(payload["YUNESA_API_IMAGE"])
    image_platform(payload["YUNESA_WEB_IMAGE"])
    image_platform(payload["YUNESA_MINIO_IMAGE"])
    try:
        if current:
            backup(current)
        admin_password = payload["ADMIN_PASSWORD"]
        credentials = ROOT / "shared" / "admin-credentials.json"
        if not credentials.exists():
            secure_write(credentials, json.dumps({"username": "rizkyyanuark", "password": admin_password}))
        elif checked_config(credentials).get("password") != admin_password:
            raise DeployError("Changing an existing app admin password requires the real account update flow")
        compose(release, "up", "-d", "--no-build", "--wait", "--wait-timeout", "300", *SERVICES, label="Start release")
        evidence = readiness(release, providers=True)
    except DeployError:
        if current:
            compose(
                current,
                "up",
                "-d",
                "--no-build",
                "--wait",
                "--wait-timeout",
                "300",
                *SERVICES,
                label="Restore current release",
            )
            readiness(current, providers=False)
            print(json.dumps({"operation": "automatic_rollback", "release": current.name, "status": "passed"}))
        else:
            compose(release, "stop", "web", "api", "worker", label="Stop failed initial application release")
        raise
    secure_write(release / "readiness.json", json.dumps(evidence, indent=2) + "\n")
    if current:
        set_release_link("previous", current)
    set_release_link("current", release)
    return {"operation": "deploy", "release": release.name, "project": PROJECT, "readiness": evidence}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("deploy", "rollback"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        print("Deployment requires the root-installed wrapper", file=sys.stderr)
        return 1
    os.umask(0o077)
    try:
        if ROOT.is_symlink() or ROOT.stat().st_uid != 0 or ROOT.stat().st_mode & 0o022:
            raise DeployError("Deployment root must be root-owned and not group/world writable")
        registry = checked_config(ROOT / "config" / "registry.json")
        installed_digest = hashlib.sha256()
        for name, target in (
            ("docker-compose.prod.yml", "docker-compose.prod.yml"),
            ("scripts/deployment-readiness.py", "deployment-readiness.py"),
        ):
            installed_digest.update(name.encode() + b"\0" + (ROOT / "config" / target).read_bytes() + b"\0")
        if installed_digest.hexdigest() != registry.get("config_sha256"):
            raise DeployError("Installed configuration checksum differs from host bootstrap manifest")
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise DeployError("Deployment request exceeds allowed size")
        payload = json.loads(raw)
        validate_request(payload, args.operation, registry)
        if shutil.disk_usage(ROOT).free < 2 * 1024**3:
            raise DeployError("At least 2 GiB free disk is required before deployment")
        for folder in ("releases", "backups", "shared/data/avatars", "shared/saves", "shared/models"):
            (ROOT / folder).mkdir(mode=0o700, parents=True, exist_ok=True)
        (ROOT / "shared" / "data" / "avatars").chmod(0o755)
        with (ROOT / ".deploy.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            ownership = ROOT / "shared" / "deployment-owner.json"
            if ownership.exists():
                if checked_config(ownership).get("project") != PROJECT:
                    raise DeployError("Shared state belongs to another deployment")
            else:
                volumes = run(
                    [
                        "docker",
                        "volume",
                        "ls",
                        "--filter",
                        f"label=com.docker.compose.project={PROJECT}",
                        "--format",
                        "{{.Name}}",
                    ],
                    label="Check new deployment volume namespace",
                ).strip()
                if volumes:
                    raise DeployError("Existing unowned project volumes require manual inventory before deployment")
                secure_write(
                    ownership, json.dumps({"project": PROJECT, "created_at": datetime.now(UTC).isoformat()}) + "\n"
                )
            with tempfile.TemporaryDirectory(prefix="yunesa-docker-", dir=ROOT) as docker_config:
                os.environ["DOCKER_CONFIG"] = docker_config
                run(
                    [
                        "docker",
                        "login",
                        registry["registry"],
                        "--username",
                        payload["CI_REGISTRY_USER"],
                        "--password-stdin",
                    ],
                    label="Registry authentication",
                    data=payload["CI_REGISTRY_PASSWORD"].encode(),
                )
                print(json.dumps(deploy(payload, args.operation), sort_keys=True))
        return 0
    except (DeployError, OSError, ValueError, KeyError) as error:
        message = str(error) if isinstance(error, DeployError) else f"Invalid deployment state ({type(error).__name__})"
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
