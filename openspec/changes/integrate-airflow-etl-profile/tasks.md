# Tasks

Local implementation and isolated verification were authorized on 7 November 2026. Production deployment, commit and push remain excluded. Checkboxes record verified completion, not code presence. Use [design.md](design.md) and [airflow-operations](specs/airflow-operations/spec.md) as the implementation contract.

The 9 November local follow-up adds persistent adopted log-volume selection, the mandatory Airflow CI gate and focused next-release/rollback verification. Evidence is recorded in [the log and CI rehearsal](../../../docs/evidence/airflow-log-ci-2026-11-09.md). Outstanding production, provider/chat and target-capacity checkboxes below retain their separate acceptance boundaries.

## 1. Integrated topology and persistent state

- [x] 1.1 Add init/API-server/scheduler/DAG-processor services behind `etl` in `docker-compose.prod.yml`, preserving the eight core services; verify rendered core-only and ETL-enabled configurations and a real isolated Compose startup, including the cross-container Execution API URL.
- [x] 1.2 Extend the administrative bootstrap for the separate Airflow metadata database/role, restricted secret delivery, stable log storage and idempotent init; verify real PostgreSQL initialization twice, existing run/history preservation, non-superuser grants and explicit failure on invalid credentials without changing academic tables.
- [x] 1.3 Add local component checks and combined readiness that parse required component state and DAG import errors; verify healthy operation and nonzero readiness when the scheduler or DAG processor stops despite HTTP 200 from the API server.
- [x] 1.4 Document topology, metadata/log/key ownership, localhost-only UI and required secret names in `docs/operations/airflow.md`; verify authentication over an SSH tunnel and refusal of direct public-port access without exposing secret values.

## 2. Versioned Airflow and worker release assets

- [x] 2.1 Update the Airflow/ETL Dockerfiles for constrained providers, pinned build tooling, embedded DAG/code and required KG dependencies; verify Linux ARM64 image metadata, actual DAG imports and `python -m yunesa.etl.run_worker` command listing from built images.
- [x] 2.2 Extend `scripts/ci-build.sh` and `.gitlab-ci.yml` to publish Airflow/ETL-worker digests from the release revision under existing builder serialization; verify manifest/dotenv identity consistency and that MR checks require no production secrets or publication.
- [x] 2.3 Update `scripts/production-request.py`, `scripts/install-deployment-host.py` and `scripts/deploy-production.py` for the two digest inputs, explicit environment/secret allowlists and aligned trusted checksum inputs; verify rejection of mutable tags, wrong registry prefixes, unsupported fields and bootstrap/source mismatches before service mutations.
- [x] 2.4 Extend worker-command coverage from the actual lecturer/paper/KG DAGs, including separate graph/vector writes, and review the untracked KG handlers and environment forwarding; verify rendered task commands dispatch through the real built worker registry and unrelated credentials are absent from worker configuration.
- [x] 2.5 Document image provenance, protected-variable delivery and reviewed bootstrap refresh in `docs/deployment.md`; verify the documented release identities match a built integration release with no host source-code mount or production build dependency.

## 3. Resource limits and launch admission

- [x] 3.1 Implement shared launch admission/reservations and release/run/task labels through the common operator path used by every managed DAG; verify on real Docker that gate closure racing a container launch cannot leave an untracked worker, and that stale reservations fail closed after interrupted creation.
- [x] 3.2 Assign all lecturer/paper/KG tasks to one shared pool, use initial LocalExecutor parallelism one, and enforce explicit service/worker memory/swap and CPU allocation settings; verify two eligible DAGs never execute more than one heavy worker and Docker inspection shows actual allocation controls.
- [x] 3.3 Add bounded startup/worker resource sampling and configure measured budgets; verify a representative task with core application traffic, capture available memory/swap/peak/OOM/restart deltas, and verify an isolated memory-exhaustion case reports a real task failure rather than success. Measure and reduce duplicate job-handler imports in the core queue-worker probe while preserving real ARQ heartbeat success and failure behavior.
- [x] 3.4 Document the selected resource values, host-budget check, CPU-share semantics and workload-size limits in the operations guide; verify documented values match rendered configuration and evidence from task 3.3 rather than the previous idle snapshot.

## 4. SSH on/off lifecycle

- [x] 4.1 Replace the home-checkout switch path with a trusted current-release operation and persistent atomic desired/observed state; verify valid/invalid arguments, authorization, lock contention, corrupted/missing state, interrupted transitions and fresh-install OFF behavior with focused lifecycle checks.
- [x] 4.2 Implement `on` with admission closed until initialization, component readiness and DAG imports pass; verify idempotent success, missing-dependency/migration failure, the configurable 180-second readiness default and nonzero timeout without altering core container identities.
- [x] 4.3 Implement `off` by closing admission, preserving pause choices, pausing managed DAGs and zeroing the pool, draining executing attempts/reservations/labeled workers, then stopping only explicit Airflow services; verify idle off, active-task/queued-task off, resumable queued work, idempotence and the configurable 600-second timeout without killing active tasks. Include residual initialization in pending shutdown, reject backup and replacement while it runs, and verify deadline failure followed by successful completion using a real blocked migration.
- [x] 4.4 Implement read-only `status`, bounded service-selectable `logs`, and reboot reconciliation; verify desired mode differs visibly from failed/partial health, requested OFF survives restart, requested ON cannot admit work before reconciliation, and only lifecycle-induced pauses are restored.
- [x] 4.5 Update `scripts/yunesa-airflow.ps1` for the trusted SSH operation, bounded failures, exit propagation and tunnel usage; document on/off/on and missed-schedule/manual-run behavior, then verify the documented Windows commands through a real SSH session against the isolated deployment.

## 5. Deployment, migration and recovery

- [x] 5.1 Reuse one lifecycle lock and quiescence routine across deploy/rollback/backup and switches without recursive locking; verify ETL drain completes before core/storage backup interruption, a competing operation fails as busy, and drain failure aborts before core services stop.
- [x] 5.2 Extend backup/recovery coverage for the Airflow database, log volume, lifecycle state and required role/key recovery references; verify checksums and an actual isolated restore with matching known run IDs, metadata counts and readable historical log samples.
- [x] 5.3 Preserve requested ON/OFF through release/rollback and validate compatible metadata before restart; verify OFF remains OFF, ON resumes only with matching DAG/worker release identities and readiness, and failed cutover restores a coherent prior state without admitting mixed-version work.
- [x] 5.4 Refresh the separate installation's exact project/container/database/log/key inventory and produce the migration/rollback evidence checklist; rehearse adoption on isolated resources, verifying unchanged history and only one scheduler installation, and document explicit production-window prerequisites without activating production implicitly.
- [ ] 5.5 In a separately authorized production window, perform the rehearsed cutover and retire the separate Compose entrypoint only after acceptance; verify known metadata/log samples, no duplicate scheduler, preserved owner mode and recoverable old assets. Update `README.md`, `docs/deployment.md` and the operations guide with the accepted behavior, leaving DEP-001 historical results intact.

## 6. End-to-end acceptance

- [x] 6.5 Owner-approved Memgraph extension: add explicit backend selection to the existing graph writer and worker environment while preserving Neo4j support; verify real managed-DAG destination counts/properties, repeated-write idempotence, graph-scoped clear and explicit failure for invalid backend or rejected schema/data writes. Keep production, commit and push excluded.

- [x] 6.1 Extend `scripts/ci-integration.py` or a narrowly scoped companion integration entrypoint to run one bounded managed DAG through the actual Airflow API/scheduler/DockerOperator/worker path against real isolated PostgreSQL and the relevant graph/vector destination; query persisted output and record run IDs, release digests and actual external provider usage or named unavailable boundaries without mocking the system under test.
- [ ] 6.2 Exercise SSH on/off/on, active-task shutdown, drain timeout, launch race, concurrent deploy, OFF/ON deploy and rollback, and restart recovery; record core container identities plus application health, authenticated API and queued chat results, and confirm resumed work and retained history/logs. Run destructive failure cases only in isolated resources.
- [ ] 6.3 Capture bounded workload resource evidence on the target-class host, successful core behavior during the run, post-off memory release and zero remaining managed worker execution; record actual peak values and any unsupported workload rather than claiming capacity from health status alone.
- [x] 6.4 Run relevant DAG/worker/deployment checks, lint, Compose validation and OpenSpec validation after the final implementation edit; inspect the diff and deliver an evidence report mapping each requirement to commands, outputs and remaining risks, with ING-001/KG-001 acceptance explicitly separate.
