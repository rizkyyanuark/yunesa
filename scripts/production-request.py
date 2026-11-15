from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from airflow_operations import IMAGE_KINDS, configuration_digest


class RequestError(RuntimeError):
    pass


def wrapper_timeout(protocol: object) -> int:
    if (not isinstance(protocol, dict) or type(protocol.get('release_evidence_protocol')) is not int
            or protocol.get('release_evidence_protocol') != 2
            or set(protocol) != {'release_evidence_protocol', 'operation_seconds', 'recovery_seconds'}):
        raise RequestError('Refresh the trusted host bootstrap to support release evidence protocol 2')
    budgets = (protocol['operation_seconds'], protocol['recovery_seconds'])
    if any(type(value) is not int or value <= 0 for value in budgets) or sum(budgets) > 3000:
        raise RequestError('Wrapper deadlines exceed the supported CI execution budget')
    return sum(budgets) + 120


def wrapper_failure(stderr: bytes) -> dict:
    stages = {'preflight', 'prepare', 'quiescence', 'activation', 'verification', 'finalization', 'recovery'}
    categories = {'guard', 'invalid_state', 'command_failed', 'deadline', 'cancelled', 'quiescence',
                  'recovery_failed', 'recovery_deadline'}
    recoveries = {'not_started', 'quiescence_closed', 'passed', 'failed', 'deadline_exceeded'}
    for line in reversed(stderr.splitlines()):
        try:
            record = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            continue
        if not isinstance(record, dict) or record.get('status') != 'failed':
            continue
        reference = record.get('diagnostic_reference')
        if (any(not isinstance(record.get(key), str) for key in ('stage', 'category', 'recovery_status'))
                or record.get('stage') not in stages or record.get('category') not in categories
                or record.get('recovery_status') not in recoveries
                or (reference is not None and (not isinstance(reference, str)
                    or not re.fullmatch(r'release-[0-9a-f]{32}', reference)))):
            continue
        return {key: record[key] for key in ('stage', 'category', 'diagnostic_reference', 'recovery_status')}
    return {}


def require_latest_commit(environment: dict[str, str]) -> None:
    branch = environment.get("CI_DEFAULT_BRANCH", "main")
    if environment.get("CI_COMMIT_BRANCH") != branch or environment.get("CI_COMMIT_REF_PROTECTED") != "true":
        raise RequestError("Deployment requires the protected default branch")
    revision = environment.get("CI_COMMIT_SHA", "")
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise RequestError("Deployment requires a full commit SHA")
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "origin", "refs/heads/" + branch],
        capture_output=True, check=False, timeout=30,
    )
    if result.returncode or result.stdout.decode().split() != [revision, "refs/heads/" + branch]:
        raise RequestError("Deployment refused because the latest default-branch SHA could not be confirmed")


def verify_release(proof: object, payload: dict[str, str], operation: str) -> dict:
    if not isinstance(proof, dict) or proof.get("operation") != operation or proof.get("status") != "passed":
        raise RequestError("The wrapper did not confirm a successful release")
    if not isinstance(proof.get("commit"), str) or not re.fullmatch(r"[a-f0-9]{40}", proof["commit"]):
        raise RequestError("Release evidence has no valid commit identity")
    if (not re.fullmatch(r"[a-f0-9]{64}", str(proof.get("config_sha256", "")))
            or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", str(proof.get("project", "")))
            or not re.fullmatch(re.escape(proof["commit"]) + r"-[0-9]{14}", str(proof.get("release", "")))):
        raise RequestError("Release evidence has an invalid release identity")
    images = proof.get("images")
    kinds = IMAGE_KINDS
    if not isinstance(images, dict) or set(images) != set(kinds):
        raise RequestError("Release evidence must identify all three images")
    for kind in kinds:
        prefix = re.escape(payload["CI_REGISTRY_IMAGE"] + "/" + kind.lower().replace("_", "-") + "@sha256:")
        if not isinstance(images[kind], str) or not re.fullmatch(prefix + r"[a-f0-9]{64}", images[kind]):
            raise RequestError("Release evidence contains an invalid image identity")
        if operation == "deploy" and images[kind] != payload[f"YUNESA_{kind}_IMAGE"]:
            raise RequestError("Release evidence differs from the tested images")
    if operation == "deploy" and (proof["commit"] != payload["CI_COMMIT_SHA"]
                                   or proof.get("config_sha256") != payload["YUNESA_CONFIG_SHA256"]):
        raise RequestError("Release evidence differs from the requested commit or configuration")
    readiness = proof.get("readiness")
    if not isinstance(readiness, dict):
        raise RequestError("Release readiness evidence is missing")
    checks = {
        "storage": ("postgres", "redis_write_read", "memgraph_query", "qdrant", "minio_upload_download_delete",
                    "public_object_bytes", "private_bucket_proxy_denied", "public_bucket_listing_denied"),
        "http_local": ("frontend", "login", "authorization", "conversation_write_read_delete"),
        "http_public": ("frontend", "login", "authorization", "conversation_write_read_delete"),
    }
    if operation == "deploy":
        checks["http_local"] += ("async_chat", "assistant_response_persisted")
        checks["providers"] = ("chat", "embedding")
    for group, names in checks.items():
        values = readiness.get(group)
        if not isinstance(values, dict) or any(values.get(name) != "passed" for name in names):
            raise RequestError("Release readiness evidence is incomplete")
    return {**{key: proof[key] for key in ("operation", "status", "release", "project", "commit",
                                         "images", "config_sha256")},
            "readiness": {group: {name: readiness[group][name] for name in names}
                          for group, names in checks.items()}}


def save_artifact(name: str, value: dict) -> None:
    path = Path("artifacts") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
            "GLOBAL_PASSWORD",
            "JWT_SECRET_KEY",
            "GEMINI_API_KEY",
            "SILICONFLOW_API_KEY",
            "ADMIN_PASSWORD",
        )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        if not args.validate_only:
            save_artifact("production-release.json", {"operation": args.operation, "status": "failed",
                                                       "stage": "inputs", "missing_variables": missing})
            save_artifact("production-health.json", {"status": "unconfirmed", "stage": "inputs"})
        print("Missing deployment variables: " + ", ".join(missing), file=sys.stderr)
        return 1
    payload = {name: os.environ[name] for name in required}
    if args.operation == "deploy":
        root = Path(__file__).resolve().parents[1]
        payload["YUNESA_CONFIG_SHA256"] = configuration_digest(root)
    if args.validate_only:
        print(json.dumps({"operation": args.operation, "variables_present": sorted(payload)}, sort_keys=True))
        return 0
    report = {"operation": args.operation, "pipeline_commit": payload["CI_COMMIT_SHA"],
              "status": "failed", "stage": "freshness", "checked_at": datetime.now(UTC).isoformat()}
    try:
        if args.operation == "deploy":
            require_latest_commit(dict(os.environ))
        report["stage"] = "wrapper_protocol"
        protocol = subprocess.run(["sudo", "-n", "/opt/yunesa-app/bin/deploy", "deploy"],
                                  input=b'{"release_evidence_protocol":2}',
                                  capture_output=True, check=False, timeout=30)
        if protocol.returncode:
            report.update(wrapper_failure(protocol.stderr))
            raise RequestError("Refresh the trusted host bootstrap to support release evidence protocol 2")
        timeout = wrapper_timeout(json.loads(protocol.stdout))
        report["stage"] = "deployment"
        result = subprocess.run(
            ["sudo", "-n", "/opt/yunesa-app/bin/deploy", args.operation],
            input=json.dumps(payload).encode(), capture_output=True, check=False, timeout=timeout,
        )
        report["wrapper_exit_code"] = result.returncode
        if result.returncode:
            for line in result.stdout.splitlines():
                try:
                    record = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if isinstance(record, dict) and record.get("operation") == "automatic_rollback":
                    report["automatic_rollback"] = "passed" if record.get("status") == "passed" else "unconfirmed"
            report.update(wrapper_failure(result.stderr))
            reference = report.get('diagnostic_reference')
            message = ('Deployment wrapper failed at ' + report['stage']
                       + '. Diagnostic reference ' + reference) if reference else 'Deployment wrapper failed. Diagnostic journal unavailable'
            raise RequestError(message)
        report["stage"] = "release_evidence"
        proof = verify_release(json.loads(result.stdout), payload, args.operation)
        # Persist only the documented receipt fields, never raw wrapper stdout or stderr.
        receipt = {key: proof[key] for key in ("operation", "status", "release", "project", "commit",
                                              "images", "config_sha256")}
        save_artifact("production-release.json", {**report, **receipt, "stage": "verified"})
        save_artifact("production-health.json", {"status": "passed", "commit": proof["commit"],
                                                "readiness": proof["readiness"]})
        print(json.dumps({"status": "passed", "operation": args.operation, "commit": proof["commit"]}))
        return 0
    except (RequestError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        report["error"] = str(error) if isinstance(error, RequestError) else type(error).__name__
        save_artifact("production-release.json", report)
        save_artifact("production-health.json", {"status": "unconfirmed", "stage": report["stage"]})
        print(report["error"], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
