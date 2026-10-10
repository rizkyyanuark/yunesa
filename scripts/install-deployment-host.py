from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

ROOT = Path("/opt/yunesa-app")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install trusted deployment code/config; does not start services.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--registry", default="registry.tugasakhir.space:443")
    parser.add_argument("--image-prefix", default="registry.tugasakhir.space:443/rizkyyanuark/yunesa")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Run the host installer as root through the administrative session")
    source = args.source.resolve(strict=True)
    files = {
        "scripts/deploy-production.py": "bin/deploy-production.py",
        "scripts/deploy-wrapper.sh": "bin/deploy",
        "scripts/deployment-readiness.py": "config/deployment-readiness.py",
        "docker-compose.prod.yml": "config/docker-compose.prod.yml",
    }
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
    for name, destination in files.items():
        target = ROOT / destination
        if target.is_symlink():
            raise SystemExit(f"Refusing symlink target: {destination}")
        shutil.copyfile(source / name, target)
        target.chmod(0o700 if destination.startswith("bin/") else 0o600)
    digest = hashlib.sha256()
    for name in ("docker-compose.prod.yml", "scripts/deployment-readiness.py"):
        digest.update(name.encode() + b"\0" + (source / name).read_bytes() + b"\0")
    registry = {"registry": args.registry, "image_prefix": args.image_prefix, "config_sha256": digest.hexdigest()}
    path = ROOT / "config" / "registry.json"
    if path.is_symlink():
        raise SystemExit("Refusing registry config symlink")
    path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    print(
        json.dumps(
            {
                "installed": list(files.values()) + ["config/registry.json"],
                "config_sha256": digest.hexdigest(),
                "services_started": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
