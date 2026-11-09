# Airflow legacy adoption rehearsal

Task 5.4 of `integrate-airflow-etl-profile` was verified locally on 8 November 2026. Production changes, Git commits and Git pushes remain excluded. The rehearsal used synthetic recovery material and native AMD64 containers on Docker Desktop. The production backup was not transferred. ARM64 workload/resource acceptance remains task 6.3.

## Source inventory

The preceding read-only server audit found the following installation.

| Item | Observed value |
| --- | --- |
| Host architecture | `aarch64` |
| Compose project/container | `yunesa-airflow` / `yunesa-airflow` |
| Compose file | `/home/ubuntu/yunesa/docker-compose.airflow.yml` |
| Airflow version/image | `3.1.7`, `sha256:a116e6866be039e2b361d1bfacee76a3f9f707b7fc52a706d351b413afd3c889` |
| Legacy worker image | `sha256:106ea352477762c49712f156359efb9e4010a0f04dbf675732348ab5a7c81a0a` |
| Metadata | `airflow`, owner `postgres`, 63 public tables and 28 sequences owned by `postgres`, dedicated `airflow` role absent |
| Metadata revision | `cc92b33c6709` |
| Retained records | Zero DAG runs/task instances, one admin, zero import errors, three managed DAGs paused |
| Logs | `yunesa-airflow_airflow-logs`, eight files, 2,746,815 bytes |
| Effective Fernet source | `/opt/airflow/airflow.cfg`, added in the container writable layer, outside persistent mounts |
| Old entrypoint | `/usr/local/bin/yunesa-airflow`, Ubuntu-owned, mode `0775` |
| Integrated entrypoint/state/reconciliation | Absent at audit time |

The server was running the legacy installation alongside eight healthy core containers. Available RAM ranged from 630 to 489 MiB during the audit. These readings do not establish capacity for the integrated topology. Secret values were excluded from audit output.

## Real local execution

The entrypoint is `scripts/checks/airflow/check-airflow-adoption.py`. It reuses the actual Compose configuration, `AirflowOperations`, existing fixture bootstrap and API request helpers. It uses a single legacy container with API server, DAG processor and LocalExecutor scheduler, PostgreSQL-owned metadata and a writable-layer configuration file. It then adopts the same metadata and log volume into the actual split-service lifecycle.

The probe DAG runs a real BashOperator through the authenticated Airflow API and scheduler. Its output is `ADOPTION_REAL_TASK_LOG`. It supplies historical metadata/log evidence without provider calls. Connection password/extra and variable values are genuinely Fernet-encrypted through Airflow's models. The legacy Fernet/API/JWT material is generated independently from the initial integrated environment, then recovered from the backed-up configuration into that environment.

| Proof | Result |
| --- | --- |
| Accepted project | `yunesa-airflow-it-c83bf210` |
| Accepted DAG run | `manual__adoption_f52703a0`, `success` |
| Task | `adoption_probe.write_log`, `success`, try 1 |
| Controller exit | `0` from `docker wait` |
| Local Docker context | `desktop-linux` |
| Airflow image | `sha256:4f05c521130c0426032faf05078eda9cfae168be9e94c4817deabab2c8a9ab62`, AMD64 |
| PostgreSQL image | `sha256:aa6cb33cf4c19c765cefcf48d96176258800870a9a1e930ad126200f9d825139`, AMD64 |
| Legacy startup guard | Integrated `on` rejected while the labeled legacy scheduler container was running |
| Ownership preflight | Existing PostgreSQL-owned database rejected with `Existing Airflow ownership requires offline adoption after backup` |
| Adopted ownership | All 63 public tables and 28 sequences assigned to dedicated `airflow`; superuser/createdb/createrole all false |
| Preserved metadata | One DAG run, one task instance, 63 tables; run/task/ciphertext/schema/admin fingerprints equal before adoption, after adoption and after restore |
| Key proof | Connection password/extra and variable decrypt before adoption, after adoption and after rollback; a different Fernet key raises `InvalidToken` |
| Authentication | Existing admin authenticates against integrated API and reads the successful historical run; legacy admin authentication works after rollback |
| Historical task log | SHA-256 `ad55ea311480bc4a86e36c7dad3a1c4ef97947a8f67587e31c1998690a788977` retained |
| Other legacy logs | Existing content of all seven log files retained as prefixes after parser startup |
| Rollback | Integrated lifecycle OFF, Airflow-specific database dropped/recreated and restored with `pg_restore --exit-on-error`; PostgreSQL ownership restored for all 63 tables and 28 sequences |
| Log recovery | All seven archived files compared byte-for-byte; a deleted task-log sample restored from the checked archive and verified again |
| Selected installation | Legacy ON → no scheduler → integrated ON → no scheduler → legacy ON; asserted counts `1,0,1,0,1` |
| Core fixture | One lecturer and one paper retained |

The scheduler assertions count the selected legacy orchestration container or the integrated scheduler service. The legacy launcher starts one scheduler process, and a successful probe task confirms its execution. This does not test systemd boot/restart recovery, which remains task 4.4.

The accepted receipt is ignored `.cache/airflow-adoption-proof/result.json`; the intermediate adopted receipt is `adopted.json`. Sensitive database/config/log recovery archives remain inside the restricted backup directory of the disposable root volume. Their SHA-256 values are recorded in the receipt. No plaintext keys or credentials are included in this document.

### Reproduction

Use the already built `yunesa-airflow-check:local`, `yunesa-airflow:local-check` and `yunesa-etl-worker:lifecycle-check` images. Select a fresh disposable namespace. Run from the repository root on the local Docker Desktop context.

```powershell
$project = 'yunesa-airflow-it-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$source = (Get-Location).Path
$proof = Join-Path $source ".cache/$project"
New-Item -ItemType Directory -Force $proof | Out-Null
foreach ($suffix in @('root', 'control', 'logs')) {
    docker volume create --label "io.yunesa.adoption=$project" "${project}-$suffix"
}
docker run -d --name "${project}-controller" `
  --label "io.yunesa.adoption.controller=$project" `
  -v "${source}:/source:ro" -v "${proof}:/proof" `
  -v "${project}-root:/opt/yunesa-app" `
  -v "${project}-control:/opt/yunesa-app/shared/airflow/control" `
  -v "${project}-logs:/legacy-logs" `
  -v /var/run/docker.sock:/var/run/docker.sock `
  yunesa-airflow-check:local python /source/scripts/checks/airflow/check-airflow-adoption.py --project $project
docker wait "${project}-controller"
docker logs "${project}-controller"
Get-Content (Join-Path $proof 'result.json')
```

The command returned `0` for the accepted project. The entrypoint removes its legacy and integrated service containers in `finally`. Root/log/control/PostgreSQL volumes are disposable recovery artifacts and need deliberate ownership-checked cleanup after review. Remove the exited controller and its project network after collecting evidence. Do not reuse this fixture command against a production Docker context.

## Corrected fixture failures

Early attempts exposed a root-user Python import-path error and a scheduler inventory/cleanup filter that included the controller. These fixture errors were corrected before the accepted run. A subsequent attempt compared a growing parser log as an immutable sample and exited 1. The final verifier checks immutable task-log hashes and preservation of every old parser-log byte separately. The final launch also validates that controller and scheduler share the same control volume. The accepted complete run used the final script and exited zero.

## Production-window acceptance checklist

The operations guide's legacy-adoption prerequisites apply. Refresh inventory and actual owner mode, drain/disable the old startup path, secure and verify database/log/key/role backups, review targeted metadata ownership changes, deliver recovered keys and dedicated credentials, install the reviewed trusted bootstrap/checksum contract and ARM64 digests, then start only the selected installation. Require retained identifiers/decryption/log samples and independent core checks before retiring the old entrypoint. Keep Airflow-specific recovery and the old assets available until acceptance. Task 5.5 requires a separate production authorization.

## Final checks

- `python -m py_compile scripts/checks/airflow/check-airflow-adoption.py` passed.
- `backend/.venv/Scripts/ruff.exe check scripts/checks/airflow/check-airflow-adoption.py` passed.
- `openspec validate integrate-airflow-etl-profile --strict` passed.
- The accepted controller exited zero and its service containers were removed. Two unrelated Personal-agentic containers remained running and healthy.
- HEAD remained `b6924e196f6728c73dd70864c20b1c655db9f50f` on `main`. Existing unrelated working-tree changes were preserved.
