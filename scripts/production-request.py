from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from airflow_operations import AIRFLOW_SECRETS, configuration_digest


def main() -> int:
    parser = argparse.ArgumentParser(description="Send an allowlisted deployment request to the trusted local wrapper.")
    parser.add_argument("operation", choices=("deploy", "rollback"))
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    required = ("CI_COMMIT_SHA", "CI_REGISTRY", "CI_REGISTRY_IMAGE", "CI_REGISTRY_USER", "CI_REGISTRY_PASSWORD")
    if args.operation == "deploy":
        required += (
            "YUNESA_API_IMAGE",
            "YUNESA_WEB_IMAGE",
            "YUNESA_MINIO_IMAGE",
            "YUNESA_AIRFLOW_IMAGE",
            "YUNESA_ETL_WORKER_IMAGE",
            "GLOBAL_PASSWORD",
            "JWT_SECRET_KEY",
            "GEMINI_API_KEY",
            "SILICONFLOW_API_KEY",
            "ADMIN_PASSWORD",
        )
        required += AIRFLOW_SECRETS
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print("Missing deployment variables: " + ", ".join(missing), file=sys.stderr)
        return 1
    payload = {name: os.environ[name] for name in required}
    if args.operation == "deploy":
        root = Path(__file__).resolve().parents[1]
        payload["YUNESA_CONFIG_SHA256"] = configuration_digest(root)
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        if os.environ.get(name):
            payload[name] = os.environ[name]
    if args.validate_only:
        print(json.dumps({"operation": args.operation, "variables_present": sorted(payload)}, sort_keys=True))
        return 0
    result = subprocess.run(
        ["sudo", "-n", "/opt/yunesa-app/bin/deploy", args.operation], input=json.dumps(payload).encode(), check=False
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
