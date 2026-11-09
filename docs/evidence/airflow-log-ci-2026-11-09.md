# Persistent Airflow logs and CI gate rehearsal

## Scope

Local work on 9 November 2026 Asia/Jakarta adds the persistent adopted-volume setting and the protected-main Airflow integration gate. The checkout remains dirty at HEAD `b6924e196f6728c73dd70864c20b1c655db9f50f`. Production, AWS resources, Git commits and Git pushes remain outside this execution.

The local registry is `127.0.0.1:57566/yunesa-integration`. Registry pushes are localhost-only under the owner's earlier authorization. The rehearsal consumes cached native AMD64 application, Airflow and worker images. Their digests identify the tested local artifacts. They do not establish a fresh build from this dirty checkout or execution on the ARM64 GitLab runner.

## Implementation

- The root installer accepts `--airflow-log-volume` and stores `airflow_log_volume` in `config/registry.json`. Reinstallation without the flag preserves the setting. Existing release environments provide the backward-compatible fallback. Conflicting mappings and CI payload overrides are rejected.
- Release creation writes the selected name to `.env` and `manifest.json`. Rollback checks the target environment against the root-installed selection before enabling Airflow.
- `integration-airflow` consumes the build job's immutable Airflow and ETL-worker references. It exercises authenticated DAG execution through the real scheduler and Docker worker, checks Memgraph output, verifies component degradation/recovery, completes OFF and cleans up its isolated resources. Automatic deployment depends on the core and Airflow integration gates.
- The focused verifier uses an explicitly labeled legacy log volume and the actual installer, release functions and root rollback wrapper. A fixture-only Docker argument adapter translates backup bind paths from the sibling controller to its named volume's daemon path. Storage operations still use real Docker volumes and real archives.

## Verification record

### Adopted logs, next release and rollback

`log-release.json` reports `status=passed` for project `yunesa-airflow-it-90b2241e` with legacy-labeled volume `yunesa-airflow-it-90b2241e-adopted-logs`.

- Installer refresh preserved the configured name and a conflicting explicit replacement was rejected without rewriting its configuration.
- The real managed DAG run `manual__persistent_logs_8baa3426` completed successfully. Initial release `b6924e196f6728c73dd70864c20b1c655db9f50f-20261108174946` and next release `b6924e196f6728c73dd70864c20b1c655db9f50f-20261108175448` used the same actual Docker log mounts, environment mapping and manifest field.
- The next release passed core storage and HTTP/auth checks, resumed requested ON, and retained the successful DAG run. Its provider boundary is recorded explicitly in the report.
- Both ON and OFF rollback completed through the root wrapper with exit 0. ON retained the historical run. OFF retained requested OFF and had zero managed workers. Post-OFF frontend, login, authorization and conversation write/read/delete all passed on application version 0.6.0.
- The historical marker SHA-256 remained `dc836443c923f66b054cca873c634879a72750f3776c9e2b060846ec04a9362e`. Five actual task-log files retained their recorded SHA-256 values across rollback. Checksums for all five Airflow recovery files were independently verified in each of three real backup directories. `log-files-and-backups.json` and `task-log-samples.json` retain these observations.

Two earlier fixture attempts failed before the next release. The first volume lacked the legacy Compose ownership label. The second controller used a bind source visible only inside its container. The successful fresh run used the correct ownership label and the documented fixture path adapter. A separate real Docker write/read/remove probe printed `BACKUP_BIND_TRANSLATION_OK` before the successful backup.

### Final positive Airflow CI gate

`ci-gate-positive-final.json` reports `status=passed` and `cleanup=passed` for `yunesa-airflow-it-44e8b10c`. Run `manual__ci_gate_485ebfd24ead` succeeded and independent Memgraph queries returned four nodes and five relationships. Readiness reported zero import errors, zero queued work and no running tasks. The stopped-processor case was rejected, readiness recovered, and OFF completed with an empty worker list. The final gate source SHA-256 is `1dd53d4d8f4e3afbd52f785780da4392885c16397e02a30ab1c18748cfcdf55e`.

The actual localhost image references used by this gate were

```text
127.0.0.1:57566/yunesa-integration/airflow@sha256:4f05c521130c0426032faf05078eda9cfae168be9e94c4817deabab2c8a9ab62
127.0.0.1:57566/yunesa-integration/etl-worker@sha256:51349fd9d6b8dc03e2f07e8d0f895ea6f8b346cd56137887a285f99e4af1ab98
```

The earlier positive run `manual__ci_gate_c2885c638acd` also succeeded with four nodes and five relationships. The final run above repeats the test after report and cleanup refinements.

### Import-error rejection

`ci-gate-import-rejected.json` records `status=failed`, `dag_import_errors=1` and `cleanup=passed` for project `yunesa-airflow-it-8b2fa983`. The driver exited 1 with `Airflow gate rejected release: OperationError`. Its inner result reports readiness deadline failure while the metadata contains the intentional import error. An independent PostgreSQL query found one matching `fixture_import_error.py` record, and an independent control-file read confirmed admission was closed during the failed startup.

The fault image is the positive Airflow image plus one file containing `from airflow.sdk import DAG` followed by an intentional exception. Its immutable localhost reference is `127.0.0.1:57566/yunesa-integration/airflow@sha256:52c4394a6c9b17b9c0bae3090b5c6a277d774dda300bfb868008042a2a9a13a7`. The original fault file contained only the exception and was skipped by Airflow safe mode. That first attempt was interrupted with exit 130 and completed cleanup, then the corrected image was tested on fresh resources. Only the corrected test establishes import-error rejection.

### Static and contract checks

- `check-airflow-contracts.py` passed all 18 tests in 6.258 seconds with access to real local Docker. An earlier invocation omitted the required socket and failed three Docker-dependent cases. The corrected invocation passed without changing expectations.
- Ruff passed across `scripts` and `orchestration`, Python compilation passed, and strict OpenSpec validation accepted `integrate-airflow-etl-profile`.
- Parsed CI configuration checks confirmed mandatory dependencies on both integration jobs, protected-main inheritance, failure blocking, non-interruptible Airflow integration and manual rollback.
- A separate no-network/no-socket process receiving a synthetic application secret exited 1 and recorded `Airflow CI must not receive production/application secrets` before registry access or resource creation.

## Cleanup

The temporary registry, test drivers, fault images, session registry tags, fixture containers, networks and named volumes were removed. `cleanup.json` records an empty `test_resources_remaining` list across all seven test namespaces. The two pre-existing Personal-agentic containers remained healthy with the same container IDs and `StartedAt` values recorded before this work.

## Files changed in this follow-up

- `.gitlab-ci.yml` and new `scripts/ci-airflow-integration.py`.
- `scripts/airflow_operations.py`, `scripts/install-deployment-host.py` and `scripts/deploy-production.py`.
- `scripts/airflow-local-check.py`, `scripts/checks/airflow/check-airflow-core-release.py`, `scripts/checks/airflow/check-airflow-contracts.py` and new `scripts/checks/airflow/check-airflow-log-release.py`.
- `docs/operations/airflow.md`, `docs/deployment.md` and this evidence report.
- `openspec/changes/integrate-airflow-etl-profile/design.md` and `tasks.md`.

Earlier implementation changes and unrelated dirty files were retained. In particular, this follow-up did not author the existing deletion of `docs/database/supabase-schema.sql`.

## Commands

```sh
python scripts/checks/airflow/check-airflow-contracts.py
python scripts/checks/airflow/check-airflow-log-release.py --project <isolated-project> --registry 127.0.0.1:57566 --images /proof/images.json
python scripts/ci-airflow-integration.py --architecture amd64 --report /proof/ci-gate-positive-final.json
python scripts/ci-airflow-integration.py --architecture amd64 --readiness-deadline 180 --report /proof/ci-gate-import-rejected.json
uv run --project backend ruff check scripts orchestration
openspec validate integrate-airflow-etl-profile --strict
git diff --check
```

The Linux commands run in disposable Docker controllers with a read-only repository mount. Reports stay in ignored `.cache/airflow-log-ci-proof/`. The negative import check substitutes an immutable localhost image containing one intentional failing DAG import. No provider calls or provider-success substitutes are used.

## Boundaries

- Provider/chat acceptance remains deferred by the owner. The next-release rehearsal uses the production backup, release, readiness and Airflow restore functions with `providers=False`. Full successful deploy-wrapper execution through its provider/chat gate remains unverified. The production gate keeps its provider requirement.
- AMD64 local functionality does not close target-class ARM64 workload capacity. No target-server RAM claim follows from this rehearsal.
- The actual GitLab pipeline has not run for these uncommitted changes. First production bootstrap, secret provisioning, legacy metadata/key adoption and cutover require the separately authorized window.
- OpenSpec tasks 5.5, 6.2 and 6.3 retain their outstanding production, provider/chat and capacity boundaries.
