# Airflow ETL profile: local implementation evidence

## Takeover verification update

Verified local completion is 23/28 tasks. The five open tasks are 4.4, 5.4, 5.5, 6.2 and 6.3, with their acceptance boundaries listed below.

The owner authorized localhost registry publication and continuation without provider/chat credentials. Production activation and Git publication are excluded. Task tracking was audited against runtime evidence. Completed local work covers tasks 2.2, 3.3, 3.4, 5.1, 5.3 and 6.4 in addition to the previously verified seventeen tasks. The earlier colleague summary is superseded by this update and the current task checklist.

The failed-worker cleanup propagates inspection and diagnostic-write errors, preserves failed/OOM containers and treats missing containers idempotently. The first Docker race run admitted one launch and rejected nineteen. The latest twenty-race run rejected twenty after gate closure, with separate positive create/start and running-worker completion checks. Successful cleanup removed its container, exit-7 cleanup retained its diagnostic, a real filesystem write failure propagated while preserving the container, and positional force removal worked. Linux lifecycle/release contracts passed seventeen tests, including actual image architecture rejection and acceptance.

The final ARM64 Airflow image is `sha256:cb3744c8dea74c6d0ef82836f2a7a1ddacd6df11feadcabe2696feb22bd432fc`. Its DagBag imported three DAGs and rendered forty-eight commands. Embedded DAG SHA-256 values matched the working source. The existing ARM64 worker `sha256:fc08a0952ee7fb9c0af9a0f71bed4d4b7e27451b709f1cdcac47422669c85216` accepted all forty-eight commands through its actual parser and registry and completed CLI task listing. Native Airflow cleanup checks used `sha256:4f05c521130c0426032faf05078eda9cfae168be9e94c4817deabab2c8a9ab62`. These image identities supersede the older image index in `.cache/airflow-final-proof/` for takeover verification.

Actual API/web/MinIO/Airflow build metadata matched the five-image localhost digest/dotenv contract, with the retained worker identity established through actual image inspection. The real `production-request.py deploy --validate-only` accepted all required variable names. CI rules retained protected-main publication, builder serialization and placeholder-only MR credentials. `bash -n scripts/ci-build.sh` passed. The GitLab pipeline itself remains unrun. Reports reside in ignored `.cache/airflow-takeover-proof/`, including `images.json`, `dags-arm64.json`, `worker-arm64.json` and `release-inputs.json`.

The eight-core rehearsal initially failed on local dependency architecture and emulation boundaries. Docker Desktop stopped during an interruption and was restored. ARM64 emulation registration was restored, and Windows reserved the previous registry port. The retained registry moved to loopback port 54765. Redis ARM64 rejected the emulated kernel with `ARM64-COW-BUG`; Memgraph ARM64 aborted under QEMU. Subsequent fixture configuration uses real native Redis/Memgraph, ARM64 MinIO with a fixture-only 384 MiB allocation, and extended worker probe timing. A fixture username rejected by the real initialization API was corrected from `integration-owner` to `integration_owner`. Diagnostic volumes and failure reports were retained.

The wrapper's nested backup bind mounts require the controller's `/opt/yunesa-app` to resolve to the same data in the local Docker daemon. After verifying the Docker VM path was absent, a reversible alias was created to the labeled fixture root volume. Its cleanup is recorded at the end of this report. The complete ARM64 emulated run later reached healthy components but failed on Execution API/read polling timeouts. That run produced no successful managed worker execution. Target-class native ARM64 acceptance is pending.

### Completed native full-core phases

The root installer supports an explicit staging project, readiness endpoints and expected Linux architecture. Production defaults select ARM64. The fixture used `--architecture amd64`; deployment requests cannot override it, and the normal image guard verified actual native images. These settings enabled the real wrapper on local hardware without substituting services or disabling provider gates.

Project `yunesa-airflow-it-73e9a2c6` used real PostgreSQL, Redis, Memgraph, Qdrant, MinIO, API, queue worker and Nginx alongside Airflow. Native source memory limits and readiness commands were exercised. Local-only immutable image references are recorded in `.cache/airflow-core-native-proof/registry-images.json`. Native Airflow and worker digests are `4f05c521130c0426032faf05078eda9cfae168be9e94c4817deabab2c8a9ab62` and `51349fd9d6b8dc03e2f07e8d0f895ea6f8b346cd56137887a285f99e4af1ab98`. Embedded worker KG/registry/Memgraph source hashes matched the workspace in both architectures.

| Executed path | Concrete result | Evidence file under `.cache/airflow-core-native-proof/` |
| --- | --- | --- |
| Managed DAG with core traffic | `manual__core_47d5a646` succeeded, independent Memgraph reads returned four nodes and five relationships matching the worker artifact, 36 resource observations and 70 authentication/CRUD cycles passed. | `core-measurement-recovery.json`, `resource-summary.json`, `core-resource-samples.json`, `core-traffic.json` |
| Normal off | Eight core IDs were preserved, active workers reached zero and authenticated CRUD passed after off. | `core-measurement-recovery.json` |
| Full wrapper ON/OFF rollback | Both operations exited zero, ON reopened only after readiness, and OFF retained stopped orchestration. | `core-recovery-progress.json` |
| Real failed cutover recovery | Changing the request's admin password failed after backup and triggered `automatic_rollback`; expected wrapper exit was one and requested ON recovered. | `core-recovery-progress.json` |
| Active full-wrapper drain | `manual__wrapper_drain_33506e05` was blocked by a real PostgreSQL lock. Deadline failure preserved the worker and all eight running core IDs. A competing off returned busy. After releasing the lock, Docker events placed worker exit 20.9498723 seconds before the first core stop, rollback exited zero, queued work succeeded and core IDs were preserved. | `core-drain.json` |
| Actual worker controls | Worker inspection showed 512 MiB RAM, 1 GiB combined memory/swap, 1024 shares, zero hard CPU quota and embedded code. | `core-worker-allocation.json` |
| Resumed worker provenance | A resumed task's worker reference and release label matched the active admission release's manifest, with unrelated credentials and source mounts absent. | `core-resumed-worker-allocation.json` |
| Real OOM visibility | `manual__oom_da1c710d` enforced 32 MiB memory/combined swap, Docker reported OOM and exit 137, Airflow reported `up_for_retry`, status exposed failure, five successful runs were preserved and core IDs/authentication survived. | `core-oom.json` |
| Source Compose contract | Eight core/twelve ETL-enabled services, localhost UI, cross-container Execution API, component controls and a 3296 MiB configured cap sum passed rendering checks. Shell syntax checks passed. | `compose-contract.json` |

The phased receipt `final-local-proof.json` joins individually completed executions. Historical verifier failures are retained separately. Initial sampling hit Docker's real `EOF` when an automatically removed worker disappeared during stats collection. The observer checks that a container stopped/disappeared before one bounded retry, which passed five actual removal regressions. Another verifier correction normalized short container IDs against full Docker event IDs. An independent observer records the current link, admission release and worker identity before checking the active admission manifest. These corrections affected verification tooling, and both earlier native KG runs are persisted as successful history.

Inside the configured disposable controller, the executed integration entrypoint was `/source/scripts/checks/airflow/check-airflow-core-release.py` with `--architecture amd64`, project `yunesa-airflow-it-73e9a2c6`, registry `127.0.0.1:54765`, images `/proof/registry-images.json` and source base revision `b6924e196f6728c73dd70864c20b1c655db9f50f`. The resource/recovery pass used `--resume`. Final focused invocations used `--resume --phase drain` and `--resume --phase oom`, each exiting zero. The full entrypoint had previously stopped on the documented verifier failures after its earlier phases completed. The combined receipt keeps those phases explicit.

The selected resource controls passed this one-paper/one-lecturer native workload. Observed worker cgroup peaks reached 396.43 MiB, and DAG processor/scheduler used swap under their 384 MiB resident limits. Peak readings are bounded by observation time. The VM had 7.556 GiB RAM and 2 GiB swap, with minimum observed available memory 4.604 GiB and maximum observed swap use 467.43 MiB. Larger batches, GLiNER, vector writes and target-host capacity have separate acceptance boundaries in the operations guide.

### Requirement coverage and boundaries

| Requirement | Verified evidence | Outstanding boundary |
| --- | --- | --- |
| Optional integrated orchestration | Rendered 8/12 topology and real native core/Airflow startup. | Production activation excluded. |
| Authorized SSH lifecycle operations | Earlier real isolated SSH/Windows helper evidence plus current normal CLI/wrapper paths and process-lock contracts. | Target production authorization/bootstrap refresh pending. |
| Successful start requires component readiness | Prior stopped-component rejection and current actual metadata/API/processor/scheduler readiness before managed execution. | Native target host pending. |
| Drain before normal shutdown | Actual SQL-blocked worker, timeout, busy rejection, Docker event ordering and resumed run success. | Production workload sizing pending. |
| Persist requested state and scheduling intent | ON/OFF rollback and pause restoration, five retained successful runs. | Full host/systemd boot acceptance in 4.4 pending. |
| Persistent metadata and logs | Earlier actual metadata/log restore and checksums, current real backups and retained native history. | Exact separate-installation inventory/adoption in 5.4 pending. |
| Bounded execution resources | Startup/task samples, independent allocation inspection, normal zero OOM/restarts and deliberate real OOM failure. | Target-class measurements in 6.3 pending. |
| Coordinate lifecycle with release and backup | Normal full wrapper, common lock, timeout before core interruption and worker exit before backup stops. | Production window in 5.5 excluded. |
| Release provenance and secret boundaries | ARM64/native immutable assets, actual worker/source comparisons, forbidden credential checks, source/installed checksum and input contracts. | GitLab pipeline execution excluded by Git publication restriction. |
| KG writer supports deployed graph backend | Real managed-DAG Memgraph persistence plus previous idempotence/scoped-clear/rejection proof. | ING-001/KG-001 feature acceptance is separate. |
| Operational acceptance uses real path | Actual scheduler/operator/worker, graph destination, storage, authentication and rollback. | Provider-gated successful deploy and queued chat in 6.2 deferred by owner, target ARM64 in 6.3 pending. |

All application integration phases use actual dependencies. No integration mocks, provider stubs or fake authentication were used. The older 33-test worker unit suite contains its documented I/O fakes and establishes unit evidence only. Release directories used the same compatible Airflow version and immutable image pair. An Airflow metadata version upgrade was outside the rehearsal. Production activation, Git commit/push and external registry publication were excluded throughout.

### Final checks and cleanup

After the implementation edits, final ARM64 DagBag validation exited zero with three DAGs and forty-eight rendered commands, each bound to the immutable worker digest. The ARM64 worker accepted every command through its actual parser/registry and completed CLI listing. Final Linux contracts passed seventeen tests. The real release request's validate-only path, image/dotenv/source consistency and protected/MR rule checks passed. Production Compose rendering and shell syntax passed, as did Ruff over `scripts`/`orchestration`, AST parsing of twenty-one Python files, `git diff --check` and strict OpenSpec validation.

The temporary localhost registry container was removed after verifying its ownership label. The exact Docker VM backup alias was checked against the owned native fixture volume and unlinked. Native fixture service/worker container counts reached zero. Restricted diagnostic volumes, metadata, historical logs and backups were retained. The stale latest-failure artifact was removed only after its SHA-256 matched the explicitly archived historical verifier failure. `cleanup.json` records this teardown. Unrelated application containers were preserved.

Takeover source changes are in `orchestration/dags/etl_operator.py`, `scripts/airflow_operations.py`, `scripts/install-deployment-host.py`, `scripts/deploy-production.py`, `scripts/checks/airflow/check-airflow-contracts.py`, `scripts/checks/airflow/check-airflow-dags.py`, `scripts/checks/airflow/check-airflow-launch-race.py` and the new `scripts/checks/airflow/check-airflow-core-release.py`. Operations/evidence/handoff documents and the change's design/task records were updated. Existing dirty integration work and the pre-existing deletion of `docs/database/supabase-schema.sql` were preserved. `git-status.txt` records the workspace inventory, with HEAD at `b6924e196f6728c73dd70864c20b1c655db9f50f`.

Outstanding acceptance covers real host/systemd restart in 4.4, exact existing-installation inventory/adoption in 5.4, the separately authorized production window in 5.5, provider-gated deployment/queued chat in 6.2 and target-class native ARM64 resource evidence in 6.3. The change stays open for those boundaries.

Date: 7 November 2026 (Asia/Jakarta). Change: `integrate-airflow-etl-profile`.

Implementation is incomplete. Production deployment, commit and push were excluded by the owner. Initial verification targeted Docker Desktop project `yunesa-airflow-it-5e693c74`; follow-up projects are identified below. Existing unrelated containers and the separate Airflow Compose file were retained. The pre-existing deletion of `docs/database/supabase-schema.sql` was not changed.

## Verified paths

| Requirement area | Execution and result | Limit |
| --- | --- | --- |
| Optional topology (1.1) | Actual production Compose rendered eight core services and twelve with `etl`; init exited zero; API server, processor and scheduler became healthy. | Only PostgreSQL and Memgraph core dependencies ran in this fixture. |
| Meaningful readiness (1.3) | Stopping scheduler and processor separately made `python -m yunesa_airflow.component ready` exit nonzero, despite the API monitor returning HTTP 200. | No production health claim. |
| SSH/authentication (1.4) | Windows helper performed on/off/on against a real SSH server with a pinned host key. Tunnel `localhost:18080` returned version HTTP 200 and unauthenticated DAG API HTTP 401. Harness authenticated with the actual FAB token endpoint. | Fixture removed host port publication; production model binds only 127.0.0.1. |
| Release validation (2.3) | Eight real-process/filesystem contract checks passed, including digest/registry/field rejection, installed/source checksum agreement, authorization, busy lock without state mutation, corrupt state and stale admission. | No publication or production installer execution. |
| Startup recovery (4.2) | Real CLI rejected an invalid metadata password, stopped PostgreSQL and a one-second deadline. Recovery and repeated `on` succeeded with the same PostgreSQL container ID and completed successful DAG history. | A pending retry may legitimately change state after restart; successful history was compared separately. |
| Backup/restore (5.2) | `--backup-restore` verified five backup checksums, restored PostgreSQL metadata into a fresh database, compared two DAG history rows, restored sixteen actual log files into another volume and compared all file SHA-256 values. | Full application rollback/cutover remains unverified. |

## Actual DAG execution

Run `manual__integration_9a065aa5` reached `success` through the actual Airflow API, scheduler, Docker operator, worker CLI and real PostgreSQL fixture. One paper, one lecturer and one relationship produced persisted Parquet/JSON graph artifacts with five nodes and six edges. Task history retained an initial failed build attempt; after fixing missing public package exports, the real retry succeeded.

GLiNER and external model providers were disabled for this bounded run. Both store-writing tasks were configured to skip destination writes. This proves worker orchestration and local graph artifacts, not graph/vector database persistence, scraping correctness or ING-001/KG-001 acceptance.

Run `manual__integration_57abc5df` initially enabled graph persistence against actual Memgraph 3.6.0. Load, extract and graph build succeeded; graph writing failed with `Set NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD first.` Source inspection also found Neo4j-specific constraint/index statements. The owner subsequently approved the Memgraph compatibility extension; the successful follow-up below supersedes that blocker without rewriting the failed run.

## Approved Memgraph follow-up

The writer now accepts explicit `YUNESA_GRAPH_BACKEND=memgraph` with the existing worker command name. Integrated Compose sets the backend/database/username explicitly. The Memgraph path uses its schema dialect and graph-scoped identity; the default Neo4j path remains available. Both paths consume every write result so rejected operations propagate before a successful result is returned. No new package dependency was added.

Run `manual__integration_885d9387` succeeded through the actual managed DAG with graph persistence enabled. Independent destination reads returned five nodes and six relationships, matching the artifact counts. Labels included Concept (2), Lecturer (1), Publication (1), Venue (1) and ResearchTopic (2 secondary labels). Relationships included HAS_TOPIC (2), HAS_AUTHOR (1), HAS_KEYWORD (1), PUBLISHED_IN_VENUE (1) and PUBLISHES (1). The stored publication title was `Graph retrieval integration fixture`.

The built worker image used was `sha256:65bcc8bf6a4816f3f92e12e5afd29cf4738b6684ef337e9b4eee9d323d40d557`; Airflow used `sha256:3ecaf38c69e23700a307ace65f8fed345940426792dc873102b857c82b9ba762`. These are local image identities, not proof of registry publication. GLiNER and vector writes were disabled, and no external model provider was called. The exported report is `.cache/yunesa-airflow-it-5e693c74/memgraph-integration-proof.json`.

`scripts/check-memgraph-writer.py` ran against pinned real Memgraph using the final built worker code with only the test script mounted. It verified repeated-write counts, publication properties, two namespaces with identical node IDs, clear of one namespace without changing the other, invalid backend rejection and propagation of a real uniqueness-constraint violation with zero persisted nodes from the rejected batch. Its synthetic namespaces and temporary constraint were removed afterward. An earlier preliminary execution mounted the adapter source; the final verification did not.

`scripts/check-neo4j-writer.py --uri bolt://yunesa-airflow-it-5e693c74-neo4j-check:7687` ran from the same worker image against disposable Neo4j 5.26 Community (`sha256:42ef3ebfd671ebd01fdebb6dcbe80cf7b45eef2aa3d346ef4132f7ef31e67d2f`). The default backend wrote two nodes/one relationship, remained idempotent, retained the fulltext schema and rejected an invalid password. This is a bounded compatibility smoke, not an AuraDB deployment claim.

After the successful managed run, normal `off` reported no executing workers or reservations. Repeated real backup/restore recovered three DAG history rows and twenty-six log files; all five backup checksums and all restored log hashes matched. Academic fixture counts remained one lecturer and one paper, and role inspection returned `airflow|f|f` for superuser/createdb privileges.

## Historical verification commands

These commands record the initial execution. The owner subsequently requested removal of that controller and its hanging project services. Those containers were removed and this controller is no longer an available entrypoint. Current bounded checks use `scripts/airflow-local-check.py`, described below.

```powershell
docker build -f docker/airflow.Dockerfile -t yunesa-airflow:integration .
docker exec yunesa-airflow-it-5e693c74-controller python /source/scripts/checks/airflow/check-airflow-contracts.py
docker exec yunesa-airflow-it-5e693c74-controller python /source/scripts/airflow-integration.py --exercise
docker exec yunesa-airflow-it-5e693c74-controller python /opt/yunesa-app/bin/airflow_operations.py off
docker exec yunesa-airflow-it-5e693c74-controller python /source/scripts/airflow-integration.py --backup-restore
docker exec yunesa-airflow-it-5e693c74-controller python /source/scripts/airflow-integration.py --failure-checks
```

JSON reports exported to ignored `.cache/yunesa-airflow-it-5e693c74/` contain no credential values. Recovery archives include secrets and remain restricted inside the disposable controller volume, rather than becoming repository artifacts.

## Checks and boundaries

- Final x86-64 Airflow image built locally with manifest-list digest `sha256:3ecaf38c69e23700a307ace65f8fed345940426792dc873102b857c82b9ba762`. Actual image import found all three managed DAGs without errors, using the runtime DAG Python path.
- Built worker CLI listed lecturer/paper tasks and all six KG commands. Minimal provider placeholders satisfied app configuration; no provider request was made by command listing.
- The initial ARM64 Airflow result was superseded by the final pair of ARM64 builds and imports recorded below.
- Targeted worker dispatch tests passed: five tests, twenty-six deselected. Ruff and strict OpenSpec validation passed. No mocked system under test was used; the academic source rows were synthetic data persisted in real PostgreSQL.
- Startup SQL originally tried to alter existing metadata ownership and blocked on active transactions. Provisioning now creates absent objects only, checks the existing owner, and has SQL lock/statement deadlines. Existing legacy ownership requires an offline adoption procedure after backup.
- Current local samples showed API roughly 245–275 MiB, scheduler 268–350 MiB and processor 175–216 MiB. These are neither representative peaks nor target-host capacity evidence. Production limits remain provisional.
- Active-worker shutdown, launch races, OOM, queued-chat/application traffic, full deploy/rollback, legacy adoption, target-class capacity and CI integration gating remain pending. Task checkboxes stay open where the full specified behavior has not been proved. Production task 5.5 is intentionally unauthorized.

Verified OpenSpec progress after the approved extension: eight of twenty-eight tasks complete (1.1, 1.3, 1.4, 2.3, 4.2, 5.2, 6.1 and 6.5). Other code present in the checkout is still subject to its task's complete acceptance criteria. The Memgraph blocker is resolved; broader lifecycle, deployment and target-host acceptance remain incomplete.

## Final ARM64 and launch-admission follow-up

Both final images built with `docker buildx build --platform linux/arm64 --load` using the production Dockerfiles and frozen package lock. Worker flags were `ETL_INSTALL_KG_DEPS=true` and `ETL_INSTALL_TEST_DEPS=false`.

| Local tag | Inspected image ID | Platform |
| --- | --- | --- |
| `yunesa-airflow:integration-arm64` | `sha256:4754906d4b9239153a6ea462d4d868b5539e284735d2e927ad2d6e5828f08e08` | linux/arm64 |
| `yunesa-etl-worker:integration-arm64` | `sha256:fc08a0952ee7fb9c0af9a0f71bed4d4b7e27451b709f1cdcac47422669c85216` | linux/arm64 |

The ARM64 Airflow image ran `scripts/checks/airflow/check-airflow-dags.py` against its embedded DAGs. DagBag reported no import errors, all three managed DAGs used `yunesa-etl`, and 48 actual task commands rendered across sample/incremental/full modes. Release/run/task labels and credential exclusion passed. The ARM64 worker listed all 18 commands through `python -m yunesa.etl.run_worker`; its actual parser and callable registry accepted all 48 rendered commands. Final processes exited zero. Reports are in ignored `.cache/airflow-final-proof/dags.json` and `images.json`. Local image IDs establish tested artifacts; registry publication remains unverified.

Docker Desktop restarted during earlier builds and changed server version from 29.8.2 to 29.9.2. The interrupted builds were repeated. ARM64 binfmt registration was restored with `docker run --privileged --rm tonistiigi/binfmt --install arm64`, after which the final builds/imports completed. This changes the local Docker VM's emulation registration. A first 240-second ARM DAG check timed out after producing assertions; the accepted repeat used a 600-second bound and exited zero. QEMU timing provides no target-host resource evidence.

`scripts/checks/airflow/check-airflow-launch-race.py` ran against actual Docker with the final native Airflow operator. Twenty gate-close/start races produced three completed starts and seventeen rejected starts. A created worker was removed after closure; an already-running worker completed with exit zero after closure. Failed Docker creation and a process exiting with code 9 while holding the launch lock left durable reservations, with the process lock released. All random `yunesa-airflow-race-*` workers were removed by `finally`. The production fix inspects container state before removal, preserving workers that have already started.

`python /source/scripts/checks/airflow/check-airflow-contracts.py` completed eleven checks with `OK` against real Linux filesystems, subprocesses, flock and Docker. Coverage includes digest/registry/field rejection, trusted checksum consistency, unauthorized UID, busy operation without state mutation, absent/stale admission, manifest mismatch, interrupted reservations and corrupt lifecycle state. Transition identifiers are persisted as UUID hex values. Repeated `on` now checks that every required runtime container is running before accepting recent health heartbeats.

Final local worker tests reported `33 passed, 1 warning` in 21.37 seconds. The warning is the existing SQLAlchemy `declarative_base` deprecation. The credential-boundary test uses Docker SDK 7.1.0 as a test-only dependency. `backend/.venv/Scripts/ruff.exe check scripts orchestration` and `git diff --check` passed. An initial `uv run` lint invocation failed on sandbox cache permissions; direct execution of the installed Ruff binary passed.

### Lifecycle verification setup

The first bounded follow-up used project `yunesa-airflow-it-8b7c19d0` with an ARM64 worker under QEMU. Its worker did not reach the PostgreSQL lock within the 300-second observation deadline. Cleanup stopped it with exit 137; no OOM event was recorded. This run is a harness deadline failure, and does not prove drain or memory exhaustion. Diagnostic output is retained in ignored `.cache/airflow-local-recovery/failure-diagnostics.json`.

Lifecycle retries use native images built from the same source and frozen dependency lock, with final ARM64 compatibility verified independently above. The fresh project is `yunesa-airflow-it-c4a18f07`. Its bounded controller publishes no host ports, uses synthetic academic data, and removes its project services/workers in `finally`. Persistent volumes remain for diagnosis. This fixture runs PostgreSQL and Memgraph alongside Airflow. Full web/API/worker/chat acceptance and target-class capacity remain separate.

Windows SSH helper follow-up used the actual PowerShell entrypoint against isolated localhost port 1. Both status and tunnel propagated OpenSSH exit 255 after connection refusal; status took 4.87 seconds. An earlier sandbox invocation returned permission denied and was superseded by the unrestricted localhost retry. This complements the earlier pinned-host-key SSH on/off/on and authenticated tunnel proof. Production SSH was outside this check. Bounded service logs returned exactly two lines for each of the three runtime services, rejected invalid service/line values in three cases and retained identical lifecycle state bytes.

The first native lifecycle pass completed bootstrap, active-worker timeout, quiescence rejection, normal off and subsequent on. Run manual__drain_5937ab47 completed all five tasks successfully. Run manual__drain_f87a6cdb resumed into load_data, then a 30-second token-endpoint HTTP timeout ended the harness. Cleanup removed its active worker with the fixture services; this interrupted run is preserved as a failed fixture attempt, without claiming full queued-run acceptance. The snapshot recorded the worker running with OOMKilled false and all five prior-run tasks successful. Diagnostics are in ignored .cache/airflow-native-recovery/initial-http-failure.json. Polling now reuses a short-lived token and retries token/GET network failures at most three times, while application mutations remain single requests. A resumed fixture prioritizes release recovery before new drain runs. The overall fixture bound is 60 minutes to include cold KG imports and repeated startup.

After reinitialization on the retained volumes, PostgreSQL still reported manual__drain_5937ab47 as success, exactly one admin account, role privileges f|f|f and one row in each academic table. Task 1.2 is complete. A recovery startup subsequently exceeded its explicit 180-second Docker command deadline and returned nonzero with requested ON / phase error and no workers; its snapshot is .cache/airflow-native-recovery/startup-deadline-failure.json. The next fixture uses an explicit 600-second readiness override. The deployment wrapper now validates readiness/drain environment deadlines within 1–3600 seconds, retaining defaults of 180/600 seconds. The final Linux contract suite passed twelve tests, including default, configured and invalid deadline cases. Target-host capacity remains unverified.

The 600-second startup passed readiness, then stale-boot reconciliation failed during repeat initialization. Its snapshot is .cache/airflow-native-recovery/reconcile-failure.json. Source review found recovery could run metadata migration with runtime services still active. The host operation now reuses drain/stop before initialization and retains the pause snapshot. This matches the Airflow 3.1.7 database setup requirement. The specific init failure was not attributed without its missing logs; subsequent fixture failures now capture service logs with known secret values redacted. A final contract run reported thirteen tests OK, including real auto-removing Docker processes disappearing during observation. Worker enumeration tolerates confirmed disappearance while propagating other Docker errors. Status includes active worker resource metrics and an explicit resource_error if sampling fails.

### Native release identity and allocation proof

The local rehearsal uses uncommitted working-tree builds. All three Airflow runtime containers inspected as `sha256:e54fe2a7dc4d01f0a825cf961cdce3b1696c4a1e3c32a4e4ce818f8d87db9106`, referenced by `yunesa-airflow:local-check`. The actual KG worker inspected as `sha256:51349fd9d6b8dc03e2f07e8d0f895ea6f8b346cd56137887a285f99e4af1ab98`, referenced by `yunesa-etl-worker:lifecycle-check`. These match the locally built native artifacts and the integration manifest/environment references validated by the lifecycle entrypoint. Both synthetic releases A and B use this same image pair; their rehearsal does not establish a cross-version metadata downgrade.

The worker's actual labels identified release `integration-a`, DAG `unesa_kg_construction`, run `manual__drain_a7df6a11` and task `write_milvus`. Its only mount was the data volume at `/app/data`; it had no host bind mount. Code therefore came from the built image. Docker inspection reported 536870912 bytes memory, 1073741824 combined memory/swap and 1024 CPU shares. Each Airflow runtime reported the fixture's 536870912/1073741824 byte allocation and 256 shares, with NanoCpus zero. These are relative CPU weights. The production component default remains provisional at 384 MiB memory and 768 MiB combined memory/swap.

The normal status CLI observed an active managed worker as healthy with `369MiB / 512MiB`, CPU `0.06%` and `resource_error=null`. This is one sample during a blocked database read, without representative core application traffic. Reports are ignored `.cache/airflow-native-recovery/component-allocations.json`, `worker-runtime-final.json` and `worker-status.json`. The registry digest publication contract remains pending independently of this local artifact proof.

## Completed lifecycle and component-release rehearsal

The resumed bounded controller exited zero. Runs `manual__drain_a7df6a11` and `manual__drain_fd5ced63` both reached success after active-task off, drain timeout and on. PostgreSQL ID `66022ec25df3d4ed4a181540e11b4c45f98c7c9b80070221b41a882ddaf0c904` remained identical across the switch and failed backup preflight. The one-second drain deadline returned nonzero, retained the executing worker, kept admission closed and recorded draining. Backup raised actual `QuiescenceError` before any core stop. After releasing the real academic-table lock, normal off drained all executing workers and stopped only Airflow runtime services. Repeated off succeeded; on preserved lecturer paused and KG unpaused choices.

Actual Memgraph reads after both resumed runs returned four nodes and five relationships, matching the final artifact. The publication title remained `Graph retrieval integration fixture`. GLiNER, vector persistence and external model providers were disabled. This is a bounded orchestration/persistence smoke; ING-001, full KG-001 and ANS-001 acceptance remain NOT RUN.

The shared-pool report identified lecturer run `manual__pool_b53621a0` as eligible alongside the held KG task, with fifteen observations and maximum one heavy worker. Both the pool and LocalExecutor remained at one slot. Unpausing the weekly lecturer DAG also produced `scheduled__2026-10-31T19:00:00+00:00`, which occupied its active-run slot ahead of the manual run. That fixture-only scheduled run was canceled through the actual API while KG held capacity. The manual contention run was canceled after observation, before any lecturer scraping. This was an explicit operator intervention in this execution; the helper now includes the same scheduled-run cancellation. The intervention record is `.cache/airflow-native-recovery/pool-intervention.json`.

Read-only status retained byte-identical lifecycle/admission files. A prior-boot admission record reported degraded health and rejected launch. Requested ON reconciliation drained/stopped existing runtime before migration and reopened only after readiness; requested OFF reconciliation retained OFF. This models a prior boot record and does not execute host systemd boot.

The actual Airflow release functions moved A to B and back under the shared lifecycle lock, with readiness and release-specific gate checks. A competing CLI off returned busy without modifying state. Mismatched worker identity was rejected with admission closed, and the prior release recovered. OFF stayed OFF across B and a synthetic legacy core-only release; explicit legacy activation was rejected. Releases A/B used the same native image pair and Airflow 3.1.7. Full eight-service deploy/rollback and partial core-cutover failure recovery remain separate acceptance work.

Reports are `.cache/airflow-native-recovery/result.json` and `progress.json`. Its `finally` removed all fixture services/workers and the controller used `--rm`. A separate bounded final check reopens only its retained named volumes for scheduler-stop recovery and deliberate 32 MiB worker exhaustion. All synthetic data and secret material remain within those local volumes. No production activation or image/Git publication occurred.

The supporting 33-test worker unit suite contains pre-existing monkeypatch/fake I/O tests. Those results establish unit regressions only. The managed-DAG, lifecycle, Docker race and destination proofs above use real services and processes without replacing the system under test.

## Handoff pemilik

Pekerjaan tersisa diserahkan kepada kolega atas instruksi pemilik. Progress terakhir 17/28. Postflight berakhir exit 1 pada polling container gagal, setelah assertion scheduler-stop recovery dan repeated on terlewati. Run manual__oom_6a34510f mencatat load_data failed pada try 2; konfirmasi Docker OOMKilled belum diperoleh karena provider menghapus container pada finally untuk auto_remove success. Container fixture sudah dibersihkan, volume diagnosis dipertahankan. Aturan, prasyarat dan urutan kelanjutan ada di [handoff](airflow-etl-profile-handoff-2026-11-07.md).
