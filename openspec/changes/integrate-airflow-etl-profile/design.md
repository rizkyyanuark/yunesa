# Design

## Context

See [proposal.md](proposal.md) for motivation and [airflow-operations](specs/airflow-operations/spec.md) for the behavior contract. This document records a proposed design, not an implemented or verified deployment.

Observed source on 7 November 2026:

- `docker-compose.prod.yml` defines eight core services in `yunesa-app`; production requests and root-installed configuration are coupled by `YUNESA_CONFIG_SHA256`.
- `scripts/deploy-production.py` validates three image digests, selects eight services explicitly, checks nonterminal `agent_runs`, dumps the application PostgreSQL database, and stops storage for backup. It does not quiesce Airflow or back up its separate database.
- The untracked `docker-compose.airflow.yml` runs Airflow 3.1.7 API server, scheduler and DAG processor in one root container, with a 640 MiB memory limit and host Docker socket. API execution currently uses loopback because all processes share a container.
- The untracked host switch uses `/home/ubuntu/yunesa`, creates application tables during `on`, lacks a failing readiness deadline, and uses separate-project `down` for `off`.
- Lecturer, paper and KG DAGs use DockerOperator without explicit worker memory limits. Two extraction sources can become runnable together. Worker task handlers are discovered dynamically from pipeline modules; the current dispatch test's KG command list does not cover the two separate graph/vector write commands in the untracked KG DAG.
- `openspec list --specs` returns no promoted capability specs. DEP-001 acceptance deliberately excludes ETL; ING-001/KG-001 remain separate product contracts. Existing dirty/untracked changes are not automatically accepted implementations.

The preceding exploration observed Airflow installed on the server, but this proposal does not revalidate server state or infer peak capacity from its idle readings. Implementation must refresh the relevant inventory before migration.

## Goals / Non-Goals

**Goals:** make optional Airflow part of the existing release contract; retain simple SSH operations; preserve metadata/logs and queued work; maintain core availability during ordinary on/off; obtain measured capacity and real execution proof on the existing host.

**Non-Goals:** changing the executor to Celery/Kubernetes; upgrading Airflow as part of this integration; fixing all ING/KG semantics; rebuilding production indexes; replaying historical schedules; publishing a public Airflow endpoint; introducing a force-kill operation; activating production during planning.

## Decisions

### 1. One Compose project with separate Airflow services

Add `airflow-init`, `airflow-api-server`, `airflow-scheduler`, and `airflow-dag-processor` to `docker-compose.prod.yml`, all behind `profiles: [etl]`. Keep the eight core services unprofiled. Use the same internal application network and stable project identity. Initialization is a one-shot prerequisite; its completion is not a continuously running health requirement.

Use LocalExecutor and the current Airflow 3.1.7/Python 3.12 baseline. The scheduler executes operator tasks locally; heavy ETL code still runs in separate DockerOperator containers. No additional Celery worker, Flower, or Redis broker for Airflow is needed. A triggerer is outside this initial topology because the inspected managed DAGs do not use deferrable tasks.

The API server's Execution API URL must become `http://airflow-api-server:8080/execution/` for callers in other Airflow containers, with matching stable API/JWT authentication settings. Reusing the old loopback URL would break the split-process deployment.

Alternatives: retain separate Compose (rejected by the owner); copy the official Celery quick-start (adds unnecessary components); retain the multiprocess shell container (hides process failures and complicates shutdown).

### 2. Immutable release assets and constrained configuration

Extend `docker/airflow.Dockerfile` from the pinned Airflow version with constrained providers and embedded DAGs. Use `docker/etl-worker.Dockerfile` with the required KG dependency group and actual worker entrypoint. Pin build tooling references rather than `uv:latest`. Publish ARM64 `/airflow@sha256:...` and `/etl-worker@sha256:...` images from the same source revision as the release.

Extend `scripts/ci-build.sh`, `.gitlab-ci.yml`, request validation, release manifests/environment, platform inspection, pull logic and readiness for the two image identities. Validate digests and registry prefixes even when ETL is off so a later SSH `on` needs no mutable tag or production build. Production DAG/code bind mounts from `/home/ubuntu/yunesa` are removed; shared data remains at `/opt/yunesa-app/shared/data`.

Install the operational entrypoint through `scripts/install-deployment-host.py` under the existing root-owned trust model, with a compatibility entrypoint at `/usr/local/bin/yunesa-airflow`. Use the currently selected trusted release and its restricted environment rather than a mutable home checkout. Keep the install/request/runtime checksum calculation aligned and versioned together; do not bypass digest validation to make deployment pass.

Keep new environment inputs explicitly allowlisted. Review the existing untracked dynamic environment forwarding in `etl_common.py`; do not automatically forward unrelated AWS, Telegram, or other credentials into every worker. Provider credentials required by a task stay at their intended execution boundary.

Alternative: building images on `on` would consume production capacity and disconnect execution from verified release assets.

### 3. Metadata, credentials and logs survive lifecycle changes

Reuse PostgreSQL 16 with database `airflow` and a dedicated non-superuser metadata role. Administrative bootstrap creates the role/database and grants required schema rights; Airflow init runs `airflow db migrate` and idempotent admin initialization. Ordinary `on` never creates or changes application academic tables. Missing academic schema is an explicit prerequisite error, not permission to install a parallel schema.

Use separate metadata and UI passwords, stable Fernet/API/JWT keys, and the existing FAB provider. Extend protected secret delivery without reusing `GLOBAL_PASSWORD` as the Airflow UI password. Inventory and preserve existing encryption/signing material during adoption; rotation is a separate operation. Runtime services receive only their required credentials; secrets do not appear in status, logs, manifests, or examples.

Use a stable persistent log volume explicitly named or marked external to avoid project-name-dependent replacement. Preserve/adopt the existing `yunesa-airflow` log volume after inspecting actual labels and ownership. Metadata backup includes `airflow` in addition to the existing application dump, plus restricted role/grant recovery material and the required key/config backup reference. Restore must be rehearsed on an isolated database. Ordinary off never removes logs, metadata or shared artifacts.

The administrative installer records the adopted log-volume name in root-owned `config/registry.json` through `--airflow-log-volume`. Refreshes preserve this setting, and release creation records it in both the environment and manifest. An existing release mapping is the fallback for older bootstrap configurations. Conflicting mappings fail and require explicit offline migration. Deployment payloads cannot select a volume.

The protected-main `integration-airflow` job consumes the Airflow and ETL-worker build digests and exercises one managed KG run against isolated PostgreSQL and Memgraph. It requires persisted output, combined readiness, rejection of a stopped DAG processor, recovery and completed OFF. The job shares builder serialization with the core integration gate. Automatic deployment waits for both integration jobs. Provider/chat and target-class capacity retain their separate acceptance boundaries.

Alternative: a new PostgreSQL container wastes capacity and creates another persistence lifecycle; a fresh empty database would silently discard existing history.

### 4. Persistent lifecycle state and serialized launch admission

Store lifecycle state under `/opt/yunesa-app/shared/airflow/`, outside versioned release directories. Record requested mode, observed phase, prior DAG pause choices, transition identifier, release identities and redacted failure details. Use atomic writes and the root-owned permissions pattern already used by deployment. A fresh missing state means OFF; corrupt or interrupted state means admission closed, with explicit recovery reporting.

Serialize `on`, `off`, deploy, rollback and backup using the existing deployment lock, refactoring reusable internal routines to avoid recursive lock acquisition. A second operation fails as busy rather than modifying services concurrently.

Add one shared operator launch-admission mechanism used by every managed DAG through `etl_common.py`. A short common launch lock synchronizes gate checks, launch reservations, labeled container creation and gate closure; the long-running ETL task does not hold this lock. The host operation and scheduler-side launch path share a narrowly scoped control directory. Labels identify project, release, DAG, run and task so Docker inventory can be reconciled with Airflow state. Stale launch reservations after a crash require reconciliation and cannot be ignored as zero workers.

The gate supplements the one-slot Airflow pool: pool state alone cannot prove that an already-dispatched operator will not create a container after shutdown checks. Only trusted, versioned managed DAGs have access to the Docker launch path.

### 5. SSH operation contract

Retain `on`, `off`, `status`, `logs` and the local helper's `tunnel`. The Windows helper propagates nonzero exits and supports configurable SSH target/key. Host operations accept allowlisted arguments and use existing administrative SSH/sudo authorization; they do not expose arbitrary root commands.

`on` transitions through STARTING with admission closed. It verifies trusted release inputs and core dependency health, runs necessary metadata initialization without swallowing errors, starts the three runtime services, checks component health/import errors, restores lifecycle-owned pause choices/pool capacity, then opens admission and reports ON. Initial readiness deadline is configurable with a documented default of 180 seconds. Repeated healthy `on` is idempotent; a deadline failure returns nonzero and leaves admission closed.

`off` records requested OFF and transitions to DRAINING. Under the launch lock it closes admission, saves pause choices, pauses managed DAGs, and sets the shared ETL pool to zero. It keeps API/scheduler services alive while checking executing task attempts, pending launch reservations and labeled worker containers. New launch attempts fail or defer visibly without writing outputs. Queued tasks and partially completed DAG runs are preserved for later resumption; off does not promise to finish an entire DAG after pausing it.

When all executing tasks, reservations and workers are absent, stop only the three runtime services with an explicit service list and shutdown timeout. Never use project-wide `down`, `down -v`, or container-name pattern deletion. Default drain deadline is configurable at 600 seconds. On timeout return nonzero, retain the closed gate and live services for in-flight work, report active identifiers, and allow a later `off` to finish. Do not kill active work or silently reopen admission.

Initialization left running after an interrupted startup also prevents completed OFF. Wait for the one-shot initialization container within the drain deadline and preserve its process on timeout. Status exposes pending initialization, logs may select `airflow-init`, backup rejects active initialization, and ON recovery must wait before recreating that container. The local diagnostic verification uses a real PostgreSQL lock to hold an actual Airflow migration, then releases it and verifies successful completion and OFF.

`status` is read-only and reports desired mode, actual service/heartbeat state, transition/failure, running/queued work, launch reservations, worker resource usage and release identities. `logs` is service-selectable with a bounded tail. Bind UI at `127.0.0.1:8080`; preserve login and SSH tunneling. Protect Docker socket access at the scheduler execution boundary using its required host group rather than exposing it to API/DAG processor containers.

Reboot preserves requested OFF and does not auto-activate ETL. Requested ON may recover its components using restart policy, but admission stays closed until a boot reconciliation/readiness step validates the persisted transition and release. Restore only pauses introduced by lifecycle operations. Keep existing weekly schedules and `catchup=False`; document manual triggering for work missed while offline.

### 6. Resource bounds and meaningful health

Set one global ETL pool slot across lecturer, paper and KG DAGs, LocalExecutor parallelism one initially, and one active run per managed DAG. Configure explicit per-service memory/swap budgets and per-worker memory plus CPU allocation controls. DockerOperator `cpus` is a CPU share setting, not a hard host CPU ceiling; document actual enforced semantics rather than claiming hard isolation.

The current 640 MiB Airflow limit is not evidence that three services plus a worker fit safely. Proposed sizing inputs are separately configurable; final MiB values are selected from bounded workload measurements, recorded in the runbook and verification evidence, and must pass an aggregate host-budget check. No unlimited worker default is permitted. Insufficient measured capacity keeps ETL disabled or constrains workload size instead of silently raising limits.

Use local component liveness checks and a combined readiness check for database/API/scheduler/DAG processor status and DAG import errors. Parse health JSON; HTTP 200 alone is insufficient. Initialization errors cannot be hidden by `|| true`. Treat intentionally absent triggerer as absent rather than unhealthy. Capture host RAM, available memory, swap growth, worker peaks and OOM/restart counters while exercising actual core application behavior.

The core ARQ probe invokes its existing upstream heartbeat check through a lightweight module. Loading `WorkerSettings` for every health observation also loads chat handlers and increases memory pressure in the queue-worker cgroup. Keep the actual worker entrypoint intact and verify probe success against a live worker, failure after shutdown and rejection of invalid Redis configuration. The local ARM64 sampler uses direct read-only Engine API observations to reduce CLI process overhead. Its emulator-specific setup starts core services sequentially and restores normal restart policies before acceptance.

### 7. Deploy, backup and rollback honor the same state

Before core backup or storage interruption, snapshot requested mode, acquire the common lifecycle lock and quiesce ETL through the same gate/drain routines. Existing `agent_runs` checks remain in force for application work. A drain failure aborts before core writers/storage are stopped. Extend snapshot coverage to Airflow metadata/logs and control state.

During cutover, retain admission closure until both core and, if previously requested ON, Airflow readiness pass for the new digest pair. OFF remains OFF across deploy/rollback. Update explicit service lists so core-only deploy remains valid while optional Airflow startup is deliberate. Migration/checksum failure must preserve or restore a coherent release, never accept mixed DAG and worker revisions.

Initial integration keeps the same Airflow version and must not depend on metadata schema changes. Image-only rollback is allowed only for confirmed compatible metadata. If migration changes metadata incompatibly, stop and use the verified Airflow-specific backup recovery procedure; never restore the whole shared application database just to repair Airflow.

### Local verification configuration

The trusted host installation records its Compose project, readiness endpoints and expected Linux image architecture in root-owned configuration. Production defaults select `yunesa-app`, the current local/public URLs and ARM64. Requests cannot override these values. A separately installed AMD64 staging fixture validates actual native image digests against its own installed architecture and runs the complete wrapper without provider/chat credentials. This supports local functional verification when ARM64 emulation cannot sustain the workload. Native rehearsal results have a separate scope from ARM64 compatibility and target-class capacity acceptance.

On 8 November 2026 the owner accepted local task 6.3 closure from a full-system ARM64 guest with RAM equivalent to the audited server, provided the CPU-emulation boundary is recorded. Every application/dependency image must be ARM64, measured Linux MemTotal and swap configuration must be reported, and actual core behavior, managed workload, cgroup peaks/OOM/restarts, post-off release and zero remaining workers must be verified. QEMU TCG timing cannot certify native EC2 throughput. Provider/chat remains deferred and production mutation remains excluded.

The owner subsequently authorized retrying with eight emulated vCPUs after the two-vCPU guest exceeded the 3,600-second Airflow initialization deadline. Linux-visible RAM remains equivalent to the audited server. This local configuration can establish bounded memory and functional evidence if the complete path succeeds. It cannot establish the CPU capacity or latency of the production two-vCPU server. Preserve the failed two-vCPU measurements alongside the retry.

## Risks / Trade-offs

### Approved graph-writer compatibility

The existing `kg_write_neo4j` command remains the graph-store entrypoint for compatibility. `YUNESA_GRAPH_BACKEND` explicitly selects `neo4j` (default for existing callers) or `memgraph` (integrated Compose). Memgraph uses its Bolt database/authentication and schema dialect, with no implicit downgrade after authentication or query failure. Its nodes and edges are scoped by `graph_name`; retries must not duplicate data, and clear must preserve other namespaces. Neo4j fulltext setup is not sent to Memgraph. Verify counts, labels, relationships and sample publication properties by querying the actual isolated destination after the managed DAG. Local direct writer checks cover repeated writes, namespace isolation, invalid configuration and rejected schema/data writes. This extension was explicitly approved by the owner on 7 November 2026; production activation, commit and push remain excluded.

- [RAM/CPU contention on the existing 2 GB host] -> one heavy task at a time, explicit caps, measured acceptance with core traffic; sizing remains unproven until executed.
- [A worker escapes off/deploy checks] -> synchronize launch admission, reconcile reservations and Docker labels, and test the in-flight launch race on real Docker.
- [Paused DAG prevents downstream work from finishing] -> drain executing attempts only and preserve queued work; never wait for an entire paused DAG run to complete.
- [Metadata/log/key loss during project migration] -> inspect actual ownership, back up both databases and logs, preserve keys, verify identifiers and isolated restore before retirement.
- [Docker socket conveys powerful host access] -> only the required scheduler execution boundary receives access; trusted DAG/image provenance remains mandatory.
- [Existing KG/ETL contract gaps prevent a full pipeline] -> report the exact failing command/schema/provider, keep affected DAG paused, and do not mark ING/KG requirements done from orchestration acceptance.
- [Broader CI artifacts consume builder capacity] -> sequential ARM64 image jobs under the existing shared resource group and bounded build resources.

## Migration Plan

1. Refresh host inventory read-only: actual Airflow version, container/project identities, metadata database/role/key sources, log volume labels, pending/running attempts, image digests, shared paths and resource usage. Capture counts and sample run/log identifiers without exposing secrets.
2. Build and validate combined release assets on the runner. Rehearse the transition and restore using isolated PostgreSQL/log volumes. Review existing untracked DAG/worker/script inputs and preserve unrelated local work.
3. In an explicitly authorized production window, close admissions and drain the separate installation before any backup/storage interruption. Stop only its orchestration container, preserve data and prevent it restarting alongside the new scheduler. Do not remove the old volumes or retained image references.
4. Capture application and Airflow backups plus key/config recovery references. Apply dedicated metadata role ownership/grants without changing historical records. Install the reviewed trusted bootstrap and matching request/wrapper checksum contract together.
5. Adopt persistent logs and metadata into the integrated project. Verify counts, known run IDs and readable retained logs. Keep admission closed until the existing instance is confirmed stopped and combined readiness passes.
6. Preserve the recorded owner mode; first activation is explicit in the authorized cutover. Exercise SSH on/off/on with one bounded DAG, including an isolated destination write and actual dependency query. Verify core service identities and authenticated behavior during ordinary switches.
7. Rehearse OFF and ON through deploy/rollback. Record digests, OOM/restart deltas, peak resources and rollback/restore outcomes. Only then retire the separate Compose operational path and update the runbook; retain recoverable backups.

Rollback before acceptance stops integrated ETL with its gate closed, verifies metadata compatibility or restores its isolated backup, restores the previous trusted config/control entrypoint and log mapping, and starts only the previous selected installation if requested ON. Never run both schedulers during rollback. Record any intentionally interrupted attempts rather than rewriting them as successes.

## Open Questions

- Exact per-component and per-task memory/swap values require the bounded measurement task; this tunes parameters without changing the one-host, one-slot contract.
- Actual legacy log volume name, credential provenance and metadata ownership must be refreshed before adoption; unexpected data/ownership conflicts stop migration for review.

## Official References

Consulted on 7 November 2026. These support the component, persistence and health choices; they do not certify this custom deployment or its capacity.

- [Airflow 3.1.7 production deployment](https://airflow.apache.org/docs/apache-airflow/3.1.7/administration-and-deployment/production-deployment.html): metadata backend, migrations, LocalExecutor, component health and task-safe maintenance.
- [Airflow 3.1.7 database backend](https://airflow.apache.org/docs/apache-airflow/3.1.7/howto/set-up-database.html): PostgreSQL support and database setup.
- [Airflow 3.1.7 health checks](https://airflow.apache.org/docs/apache-airflow/3.1.7/administration-and-deployment/logging-monitoring/check-health.html): heartbeat/JSON checks instead of HTTP status alone.
- [Extending Airflow images](https://airflow.apache.org/docs/docker-stack/build.html): constrained providers and embedded DAGs.
- [Docker Compose profiles](https://docs.docker.com/compose/how-tos/profiles/) and [targeted stop](https://docs.docker.com/reference/cli/docker/compose/stop/): optional services and explicit service shutdown.
