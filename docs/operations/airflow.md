# Airflow operations

Implementation verification is in progress. No production activation or migration is implied by this document. The existing separate installation remains retained until its authorized cutover passes acceptance.

## Topology and release

`docker-compose.prod.yml` contains the eight core Yunesa services and optional `etl` services: init, API server, DAG processor and LocalExecutor scheduler. Core-only startup does not activate Airflow. Airflow and worker images are built for ARM64 by CI and recorded by registry digest with the corresponding source revision. Production DAGs are embedded in the Airflow image; worker code is embedded in the ETL image.

The scheduler alone receives the Docker socket and the shared launch-control directory. Its UID remains 50000 and its supplementary group uses the actual socket GID. Docker access grants powerful host authority; only trusted DAGs belong in this deployment.

## Credentials and persistence

The release environment must contain `AIRFLOW_DB_PASSWORD`, `AIRFLOW_ADMIN_PASSWORD`, `AIRFLOW_FERNET_KEY`, `AIRFLOW_API_SECRET` and `AIRFLOW_JWT_SECRET`, delivered through protected production variables. The metadata password is URL-safe with at least 16 characters. Preserve existing Fernet/signing keys when adopting metadata; generating replacement keys is not a migration procedure.

The metadata database is `airflow` on the existing PostgreSQL service, owned by a non-superuser role named `airflow`. Administrative bootstrap provisions the role/database; the init service applies `airflow db migrate` and creates the admin account only if absent. Ordinary start does not create application academic tables. Changing the initial UI-password variable does not reset an existing account.

Logs use the stable named volume selected by `YUNESA_AIRFLOW_LOG_VOLUME`. Before adoption, inventory the actual old volume and explicitly preserve its mapping. Off/on does not remove the log volume or metadata. Lifecycle intent and launch control live below `/opt/yunesa-app/shared/airflow`, outside the release directories. Keep these paths restricted; the scheduler only needs group access to its control subdirectory.

Select an adopted volume during the first administrative bootstrap with `--airflow-log-volume <inventoried-volume>`. The installer stores its name in root-owned `config/registry.json`. Subsequent installer refreshes preserve it when the flag is omitted. New release environments and manifests inherit the stored name. Existing installations without this setting inherit the current release mapping, or use `<project>_airflow-logs` on a fresh installation. Changing an established mapping fails and requires an explicit offline migration. CI request payloads cannot select a log volume. Rollback validates the target mapping before enabling Airflow.

## Airflow release gate

Protected-main releases run `integration-airflow` after `build-baseline`. The job consumes the built Airflow and ETL-worker digests, starts isolated PostgreSQL and Memgraph plus the packaged Airflow services, and runs one managed KG DAG through the authenticated API, scheduler and Docker worker. It checks persisted graph counts, component readiness, rejection while the DAG processor is stopped, recovery and OFF with no remaining managed workers. The fixture uses synthetic academic records and an internal network. Provider/chat acceptance remains separate.

The gate emits `artifacts/integration-airflow.json` and removes its disposable containers, volumes, network and tooling image. It shares `yunesa-build-host` serialization with the existing core gate. Automatic production deployment requires both integration jobs to succeed. The local AMD64 rehearsal exercises this entrypoint; execution on the actual ARM64 GitLab runner requires a subsequent authorized pipeline.

## SSH controls

After the trusted bootstrap is installed and activation is authorized:

```sh
sudo -n /opt/yunesa-app/bin/airflow status
sudo -n /opt/yunesa-app/bin/airflow on
sudo -n /opt/yunesa-app/bin/airflow off
sudo -n /opt/yunesa-app/bin/airflow logs --service airflow-scheduler --lines 50
```

From Windows:

```powershell
.\scripts\yunesa-airflow.ps1 status
.\scripts\yunesa-airflow.ps1 on
.\scripts\yunesa-airflow.ps1 off
.\scripts\yunesa-airflow.ps1 on
.\scripts\yunesa-airflow.ps1 logs 50
.\scripts\yunesa-airflow.ps1 tunnel
```

The helper supports explicit `-Server`, `-SshKey`, `-SshPort` and `-KnownHostsFile` for an isolated host. It propagates SSH/remote failures and requires a known host key. UI access is at `http://localhost:8080` through the tunnel and still requires Airflow login. The server binds that port only to loopback.

On keeps worker admission closed until required components and DAG imports pass. Default readiness deadline is 180 seconds; the host command accepts `--deadline` for a different positive deadline. A failed start returns nonzero.

The deployment wrapper accepts `YUNESA_AIRFLOW_READINESS_DEADLINE` in its administrative process environment, defaulting to 180 seconds, and `YUNESA_AIRFLOW_DRAIN_DEADLINE`, defaulting to 600 seconds. Both accept 1–3600 seconds and reject malformed values with an explicit error. These are host-controlled settings. The native lifecycle fixture uses a 600-second readiness override after a cold local startup exceeded 180 seconds.

Off closes new worker admission and preserves existing pause choices. It waits for executing task attempts, pending launches and labeled workers to finish, then stops only the Airflow runtime services. Tasks still queued remain recoverable. Default drain deadline is 600 seconds; timeout returns nonzero and leaves admission closed while existing work finishes. Inspect status and retry off afterward. Do not remove an unresolved launch reservation until it has been reconciled against Docker and task state.

Lifecycle records include a transition identifier. Status reads the desired mode, component health and admission record without changing files. A stale boot/release admission record reports degraded health even when containers are running. Reconciliation uses the desired mode and opens admission only after current-release readiness. Requested OFF can remain OFF when rolling back to a legacy core-only release; activating that release rejects missing Airflow assets.

Status includes allocation usage for running Compose containers and labeled ETL workers, plus retained worker exit/OOM state. A failed resource sample is reported as `resource_error`. A worker that Docker has already removed is omitted from subsequent observations.

Local restart/recovery verification uses `scripts/check-airflow-restart.py` on the retained eight-core fixture. It covers SSH on/off/on, OFF after core restart, selected bounded logs, stale-boot admission rejection through an actual managed task, targeted API retry, missing processor, scheduler process crash, corrupt-state checkpoint recovery and interrupted startup. The [8 November recovery evidence](../evidence/airflow-restart-recovery-2026-11-08.md) records results and remaining systemd/kernel-boot, provider/chat and ARM64 boundaries. A simultaneous local core restart exposed one worker DNS failure requiring normal Compose startup recovery. This remains an observed recovery limit.

The subsequent [kernel/systemd evidence](../evidence/airflow-kernel-systemd-2026-11-08.md) closes the local boot boundary for task 4.4. A dedicated Ubuntu KVM guest underwent four kernel reboots with the original enabled reconciliation unit. OFF persisted, a real worker launch was rejected before ON reconciliation, and systemd recovered automatically after a deliberate release-identity failure. The fixture used a test-only pre-start timing barrier and preserved owner pause choices plus actual history/log samples. Provider/chat, ARM64 capacity and production cutover retain their separate acceptance boundaries.

When recovery requires initialization while runtime components are still present, it reuses the drain/stop routine and preserves pause choices before running metadata migration. This follows the requirement to execute migrations while Airflow components are stopped. [Airflow 3.1.7 database setup](https://airflow.apache.org/docs/apache-airflow/3.1.7/installation/setting-up-the-database.html)

Do not use `docker compose --profile etl down` as the switch: it can also remove core services. No force-kill operation is provided.

## Graph backend

The integrated Compose selects `YUNESA_GRAPH_BACKEND=memgraph`, `NEO4J_DATABASE=memgraph` and the internal Bolt URI. The legacy command/task name `kg_write_neo4j` remains valid; it writes the explicitly selected backend. Existing standalone callers default to `neo4j` and retain its schema/fulltext setup. Unsupported backend values fail before writing.

Memgraph in the existing Compose has no configured database users. An empty `NEO4J_USERNAME` therefore selects empty Bolt credentials; the application-wide password does not configure Memgraph authentication. An authenticated installation must explicitly supply its actual username/password. No connection failure triggers an unauthenticated fallback.

Memgraph uses its own constraint/index statements and does not receive Neo4j fulltext DDL. The node identity is `(graph_name, id)` and relationship matching is scoped to the same graph name. Retry merges existing nodes/edges; `clear_existing` deletes only the selected namespace. Changing an existing database's schema or adopting legacy nodes requires a separately reviewed migration; this writer does not remove existing constraints or move historical nodes.

These choices follow the official [Memgraph Python client](https://memgraph.com/docs/client-libraries/python), [constraints](https://memgraph.com/docs/fundamentals/constraints) and [indexes](https://memgraph.com/docs/fundamentals/indexes) documentation, checked against the fixture's actual pinned Memgraph 3.6.0 rather than assuming all newer syntax is available.

## Schedules and capacity

All managed tasks use one shared ETL pool slot and initial LocalExecutor parallelism one. Existing lecturer/paper weekly schedules and `catchup=False` remain unchanged. Off pauses execution; on restores lifecycle-owned pause choices rather than unpausing DAGs the owner intentionally paused. Missed intervals do not trigger a replay of the entire history; trigger a bounded manual run where needed.

Unpausing a scheduled DAG can create its latest missed interval. That scheduled run can occupy the DAG's one active-run slot before a manual run. The isolated pool check cancels this fixture-only scheduled run through the Airflow API while the KG worker holds the shared slot, then observes the eligible manual lecturer run and cancels it before external scraping starts.

### Resource configuration and measurement boundaries

Component defaults are 384 MiB memory, 768 MiB combined memory/swap and 256 CPU shares per service. Worker defaults are 512 MiB memory, 1 GiB combined memory/swap and 1024 CPU shares. These settings passed the bounded full-core native rehearsal. The older lifecycle fixture used 512 MiB memory and 1 GiB combined memory/swap per component. Target-class ARM64 capacity acceptance is tracked separately in task 6.3.

Run `manual__core_47d5a646` completed with one paper and one lecturer, independent Memgraph reads matching four nodes and five relationships, thirty-six resource samples and seventy successful authentication/conversation CRUD cycles. Core container IDs survived on/off. Sampling recorded zero OOM flags and restart counts. Each collector sleeps five seconds after finishing its work; recorded timestamps provide actual spacing.

| Component or task | Highest observed cgroup peak, MiB | Highest observed cgroup swap, MiB |
| --- | --- | --- |
| Airflow init | 210.41 | 0 |
| Airflow API server | 292.88 | 0 |
| Airflow DAG processor | 384.00 | 71.46 |
| Airflow scheduler | 384.01 | 79.10 |
| ETL load data | 351.84 | 0 |
| ETL extract entities | 311.93 | 0 |
| ETL build graph | 396.43 | 0 |
| ETL write graph | 294.27 | 0 |
| ETL vector command with writes disabled | 370.84 | 0 |

These values are kernel `memory.peak` readings collected while each container existed. Raw bytes and observation errors are retained in the ignored reports. Container lifetime after its last observation falls outside the captured peak window. The Docker VM had 7.556 GiB RAM and 2 GiB swap. Minimum observed available memory was 4.604 GiB, maximum observed VM swap use was 467.43 MiB, and available memory after off was 5.535 GiB. Core API and queue-worker cgroups also used swap during the rehearsal.

Run `manual__oom_da1c710d` enforced 32 MiB memory and 32 MiB combined memory/swap on an actual managed worker. Docker recorded `OOMKilled=true` and exit 137, while Airflow recorded `up_for_retry`. Status exposed the failed container. The fixture canceled that run after observing failure, then verified five successful historical runs, unchanged core IDs and authenticated access after off. The operational defaults above were restored afterward.

CPU shares are relative weights under contention. Actual worker inspection returned 1024 shares and `NanoCpus: 0`. The one-slot ETL pool bounds concurrent heavy workers. The eight core services have a combined configured cap of 1632 MiB. Three Airflow runtimes add 1152 MiB and one worker adds 512 MiB, for a configured total of 3296 MiB. Init runs in its separate startup phase. Caps apply per container, and the guide records observed peaks per container.

Before enabling ETL on the target host, record available RAM, configured swap and the existing core footprint, then compare them with the additional runtime/worker budgets and the bounded workload measurement. Repeat authentication and queue acceptance during the run, check OOM/restart deltas and record memory after off. The local VM supplies functional evidence, and target-host acceptance requires its own bounded execution.

```bash
free -m
swapon --show
docker stats --no-stream
```

Sample mode defaults to five records and accepts configurable positive sample sizes. The verified full-core KG workload used one paper and one lecturer with GLiNER, vector writes and external model calls disabled. The sample-size setting applies to sample mode. Scraping, larger samples and incremental/full workloads require their own measured budgets before target-host acceptance. Current resource conclusions use the full-core reports described here, with the earlier single `worker-status.json` snapshot retained as historical data.

## Migration and recovery

Use the change's design migration checklist before production cutover. Record database/run identifiers, actual log-volume ownership, current keys and image identities; drain and stop the old scheduler before starting the integrated one. Rehearse metadata/log restore on isolated resources before retiring the old Compose entrypoint. Keep old volumes and image references recoverable.

### Legacy adoption prerequisites

The read-only audit on 8 November 2026 found the separate `yunesa-airflow` project/container running Airflow 3.1.7 on ARM64. Its Compose file is `/home/ubuntu/yunesa/docker-compose.airflow.yml`, metadata database is `airflow`, and log volume is `yunesa-airflow_airflow-logs`. All 63 public tables and 28 sequences belonged to `postgres`; the dedicated `airflow` role was absent. Three managed DAGs were paused, with zero retained DAG runs/task instances and zero import errors at that snapshot.

The effective Fernet key came from `/opt/airflow/airflow.cfg` in the container writable layer. The file is outside persistent mounts. Preserve the effective configuration securely before replacing the old container. An absent Fernet environment variable does not establish an absent key. Preserve the effective API/JWT keys and existing admin credential as well. Initialization preserves an existing admin account and does not reset its password from the initial-password variable.

Use this checklist in a separately authorized production window.

- Refresh the inventory, pending/running attempts, owner-selected mode, exact image IDs, log mapping and effective key sources. Stop for unexpected metadata ownership or schema differences.
- Drain the old installation, close its operational entrypoint and disable its restart path before starting integrated orchestration. Confirm zero executing attempts/workers and no running old scheduler. Retain its container configuration and image references for rollback.
- Back up the Airflow database with `pg_dump -Fc`, the complete legacy log volume, effective key/config recovery material and role/grant inventory. Restrict recovery material to administrators. Record SHA-256 values and verify archive readability. Preserve application recovery coverage separately.
- Create the dedicated URL-safe metadata credential and non-superuser `airflow` role. While both scheduler installations are stopped, change only the `airflow` database, public schema and inventoried metadata table/sequence owners. The rehearsal uses explicit schema-qualified `ALTER TABLE` and `ALTER SEQUENCE` statements. Avoid cluster-wide ownership reassignment from the application's shared `postgres` role. Review any views/routines or other unexpected object kinds separately.
- Deliver the recovered Fernet/API/JWT material to the restricted release environment, preserve the actual existing admin credential, and map `YUNESA_AIRFLOW_LOG_VOLUME` to the inventoried legacy volume. Give UID 50000/GID 0 the necessary access while preserving file contents. Key rotation requires a separate operation.
- Install the reviewed root-owned bootstrap and matching checksum inputs, immutable ARM64 release images and dedicated secrets. Confirm the request wrapper and installed bootstrap agree before service changes. The legacy user-owned helper is outside the new trust model.
- Start through the trusted lifecycle entrypoint with admission closed until readiness. Verify matching schema revision, retained run/task IDs and statuses, ciphertext/decryption, one admin, pause choices, historical task-log hashes and preserved parser-log prefixes. Only one scheduler installation may be running. Check the core application independently.
- Before acceptance, rollback stops integrated orchestration first and confirms zero workers/schedulers. Restore only the Airflow-specific dump when required, recover the old key/config and log mapping, and re-enable only the old installation if the prior owner mode was ON. Recheck known rows, decryption, admin authentication and log samples. Keep the new entrypoint inactive while the old scheduler is selected.

Native local adoption verification uses `scripts/check-airflow-adoption.py` with the existing controller image and disposable project namespace. It recreates the audited ownership/key/log boundaries using synthetic metadata and a real BashOperator task. Production backup transfer and target-class capacity remain separate acceptance boundaries. Its controller requires the same named control volume mounted at `/opt/yunesa-app/shared/airflow/control` that the scheduler mounts at `/opt/airflow/control`.

The accepted run, recovery results and reproduction command are recorded in the [8 November adoption evidence](../evidence/airflow-adoption-2026-11-08.md).

Deploy/rollback must use the same lifecycle lock and drain operation before storage interruption. Airflow metadata, role recovery material, logs, release environment and shared control state join the backup set. The owner-selected OFF state must survive deploy; ON resumes only after matching release readiness. Airflow-version incompatibility requires a verified metadata restore, not an image-only rollback. Historical DEP-001 acceptance does not certify ingestion or KG correctness.

## Isolated verification

The root installer accepts `--project`, `--local-base-url`, `--public-base-url` and `--architecture` for an independently installed staging host. It stores these settings in restricted, root-owned `config/registry.json`. Deployment requests cannot override them. The defaults select the existing production project, endpoints and Linux ARM64 images. A separately installed native AMD64 staging host uses `--architecture amd64`; image inspection still rejects any image that differs from its installed architecture. Refresh the trusted bootstrap and checksum together when adopting this version.

The eight-service local rehearsal uses `scripts/check-airflow-core-release.py`, dedicated labeled volumes and an internal Docker network. Its registry is loopback-only and image publication is limited to that registry under the owner's explicit authorization. The controller shares the registry's network namespace so local registry references remain valid inside the deployment wrapper. It records real authentication and conversation CRUD without provider/chat requests. Successful provider-gated deployment remains a separate acceptance step.

Select `--architecture amd64` with independently built native image digests for the native functional rehearsal. This path uses production component memory limits and readiness commands. The ARM64 variant records its emulation-specific overrides explicitly. Sampling persists each completed measurement/traffic cycle to `/proof`, including progress before a failure. The full phase exercises a managed KG run, independent destination reads, ON/OFF rollback, failed-cutover recovery, active-task drain and deliberate worker OOM. `--resume --phase drain` repeats the active drain scenario on a retained initialized fixture, and `--resume --phase oom` repeats the memory-exhaustion case. Each invocation has a ninety-minute overall deadline. Test root volumes contain synthetic recovery secrets and remain restricted.

Docker Desktop restarted during the rehearsal. ARM64 emulator registration was restored and the registry moved from an excluded Windows port to `127.0.0.1:54765`. The local fixture uses native AMD64 Redis and Memgraph after their ARM64 variants rejected the emulated kernel or aborted under QEMU. ARM64 MinIO receives a fixture-only 384 MiB limit and extended startup grace. These overrides exclude this rehearsal from target-host capacity and all-ARM64 acceptance. Docker documents emulator registration for cross-platform execution. [Docker multi-platform documentation](https://docs.docker.com/build/building/multi-platform/)

The bounded local lifecycle runner is `scripts/airflow-local-check.py`, executed in the image built from `docker/airflow-check.Dockerfile`. Use a fresh `yunesa-airflow-it-<eight hex digits>` project, dedicated root/control/data volumes, a read-only repository mount at `/source`, an output directory at `/proof`, and the local Docker socket. It creates synthetic credentials and academic rows in real PostgreSQL, uses real Memgraph and removes its project containers in `finally`. Volumes remain available for diagnosis. The controller publishes no ports and has a 60-minute overall deadline.

The runner caches its short-lived API token for 60 seconds. Token issuance and GET requests have at most three attempts for network timeouts, with each retry printed. Application mutations use one request. A resumable fixture records interrupted runs explicitly and cancels them through the real Airflow API before starting new acceptance runs. Use `--resume` only with its retained project volumes and `initial-http-failure.json`; `--postflight` requires an existing successful `result.json` and verifies scheduler restart, allocation controls and retained run history.

Build `yunesa-airflow:local-check` and `yunesa-etl-worker:lifecycle-check` for the native architecture before running the lifecycle runner. Build the worker with `ETL_INSTALL_KG_DEPS=true` and `ETL_INSTALL_TEST_DEPS=false`. Final ARM64 compatibility is checked separately through `scripts/check-airflow-dags.py` in the ARM64 Airflow image and the actual command parser/registry in the ARM64 worker. Docker Desktop requires ARM64 emulation when its host architecture differs. QEMU timing is excluded from target-host capacity measurements.

`scripts/check-airflow-contracts.py` covers real process locks, filesystem trust and release/admission failure states. `scripts/check-airflow-launch-race.py` uses actual disposable Docker workers and removes its random project workers afterward. Historical SSH/backup verification used a separate fixture that has since been removed; retain its recorded evidence without assuming that controller remains available.

This verification uses real containers and the actual operational/worker entrypoints. Record unavailable providers explicitly. Full production activation, external image publication and production capacity acceptance require separate evidence and authorization.

### ARM64 capacity rehearsal boundary

The 8 November 2026 read-only identity audit confirmed Yunesa as instance `i-04ba2d1b2dcd7f757` at `23.20.126.187`. The `ec2` SSH alias at `34.196.37.78` selects a separate Personal-agentic/infra instance. Use the Yunesa instance identity and eight core services when constructing its capacity baseline.

Full-system ARM64 TCG rehearsals exposed 1,833.49 MiB guest RAM with two vCPUs and 1,832.22 MiB with eight vCPUs, against the measured Yunesa total of 1,834.98 MiB. They retained the target disk-swap/zram arrangement. The two-vCPU run passed 136 application cycles during initialization but exceeded the Airflow startup deadline. The eight-vCPU retry exceeded core Compose readiness before DAG submission. Task 6.3 remains open. The evidence report records timing exceptions, resource observations and the emulator's own memory boundary. [ARM64 capacity evidence](../evidence/airflow-arm64-capacity-2026-11-08.md)

The earlier failed-start OFF case exposed a missing initialization guard. The updated lifecycle waits for active initialization, reports draining on timeout, rejects backup and replacement while it runs, and exposes `logs --service airflow-init`. A real blocked-migration regression verified failure during the wait and successful OFF after completion. The queue-worker probe also uses the existing ARQ heartbeat through `python -m server.worker_health`, avoiding repeated chat-handler imports. The diagnostic report separates native regressions, emulator setup corrections and the remaining ARM64 workload acceptance. [Local fixture diagnosis](../evidence/airflow-diagnosis-2026-11-08.md)
