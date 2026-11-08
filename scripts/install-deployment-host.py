from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from airflow_operations import (
    TRUSTED_FILES, AirflowOperations, configuration_digest, deployment_airflow_log_volume,
    deployment_architecture, deployment_endpoints, deployment_project, trusted_json,
)

ROOT = Path("/opt/yunesa-app")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install trusted deployment code/config; does not start services.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--registry", default="registry.tugasakhir.space:443")
    parser.add_argument("--image-prefix", default="registry.tugasakhir.space:443/rizkyyanuark/yunesa")
    parser.add_argument('--local-base-url', default='http://127.0.0.1:8088')
    parser.add_argument('--public-base-url', default='https://yunesa.tugasakhir.space')
    parser.add_argument('--project', default='yunesa-app')
    parser.add_argument('--architecture', choices=('arm64', 'amd64'), default='arm64')
    parser.add_argument('--airflow-log-volume')
    args = parser.parse_args()
    try:
        endpoints = deployment_endpoints(vars(args))
        project = deployment_project(vars(args))
        architecture = deployment_architecture(vars(args))
    except ValueError as error:
        parser.error(str(error))
    if os.geteuid() != 0:
        raise SystemExit("Run the host installer as root through the administrative session")
    source = args.source.resolve(strict=True)
    files = {
        "scripts/deploy-production.py": "bin/deploy-production.py",
        "scripts/deploy-wrapper.sh": "bin/deploy",
        "scripts/deployment-readiness.py": "config/deployment-readiness.py",
        "docker-compose.prod.yml": "config/docker-compose.prod.yml",
    }
    files.update(TRUSTED_FILES)
    files['scripts/yunesa-airflow.sh'] = 'bin/airflow'
    for name in files:
        if not (source / name).is_file() or (source / name).is_symlink():
            raise SystemExit(f"Missing regular source file: {name}")
    if not args.image_prefix.startswith(args.registry + "/"):
        raise SystemExit("Image prefix must belong to the configured registry")
    os.umask(0o077)
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if ROOT.is_symlink() or ROOT.stat().st_uid != 0 or ROOT.stat().st_mode & 0o022:
        raise SystemExit("Deployment root must be root-owned and not group/world writable")
    for name in ("bin", "config", "releases", "backups", "shared"):
        directory = ROOT / name
        if directory.is_symlink():
            raise SystemExit(f"Refusing symlink directory: {name}")
        directory.mkdir(mode=0o700, exist_ok=True)
        if directory.stat().st_uid != 0 or directory.stat().st_mode & 0o022:
            raise SystemExit(f"Directory must be root-owned and not group/world writable: {name}")
    registry_path = ROOT / 'config/registry.json'
    previous = trusted_json(registry_path) if registry_path.exists() else {}
    current_environment = AirflowOperations(ROOT).environment() if (ROOT / 'current').exists() else {}
    prior_volume = previous.get('airflow_log_volume', current_environment.get('YUNESA_AIRFLOW_LOG_VOLUME'))
    if args.airflow_log_volume is not None and prior_volume is not None and args.airflow_log_volume != prior_volume:
        raise SystemExit('Airflow log volume change requires an explicit offline migration')
    selected_volume = args.airflow_log_volume if args.airflow_log_volume is not None else prior_volume
    volume_config = {'project': project}
    if selected_volume is not None:
        volume_config['airflow_log_volume'] = selected_volume
    log_volume = deployment_airflow_log_volume(volume_config, current_environment)
    for name, destination in files.items():
        target = ROOT / destination
        if target.is_symlink():
            raise SystemExit(f"Refusing symlink target: {destination}")
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
        target.chmod(0o700 if destination.startswith("bin/") else 0o600)
    digest = configuration_digest(source)
    registry = {"registry": args.registry, "image_prefix": args.image_prefix, "config_sha256": digest,
                'project': project, 'architecture': architecture, 'airflow_log_volume': log_volume, **endpoints}
    path = ROOT / "config" / "registry.json"
    if path.is_symlink():
        raise SystemExit("Refusing registry config symlink")
    path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    unit = Path('/etc/systemd/system/yunesa-airflow-reconcile.service')
    if unit.is_symlink():
        raise SystemExit('Refusing symlink service unit')
    unit.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    shutil.copyfile(source / 'docker/yunesa-airflow-reconcile.service', unit)
    unit.chmod(0o644)
    compat = Path('/usr/local/bin/yunesa-airflow')
    if compat.is_symlink():
        raise SystemExit('Refusing symlink compatibility entrypoint')
    compat.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    shutil.copyfile(source / 'scripts/yunesa-airflow.sh', compat)
    compat.chmod(0o755)
    if shutil.which('systemctl') and Path('/run/systemd/system').exists():
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'enable', 'yunesa-airflow-reconcile.service'], check=True)
    print(
        json.dumps(
            {
                "installed": list(files.values()) + ["config/registry.json"],
                "config_sha256": digest,
                "services_started": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
