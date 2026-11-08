# Local Airflow fixture diagnosis

This follows the failed ARM64 capacity rehearsals in the [capacity report](airflow-arm64-capacity-2026-11-08.md). Production, Git commit and Git push remain excluded. Task 6.3 stays open until the corrected ARM64 baseline, managed KG run, destination query and post-OFF resource checks pass. Provider/chat remains deferred.

## Startup probe scheduling

The earlier fixture changed `interval` to 120 seconds and `start_period` to 1,800 seconds while leaving `start_interval` unset. Docker 29.1.3 defaults the interval during startup to five seconds. This kept failed startup probes frequent during the extended grace period. The intended reduction in probe frequency was therefore incomplete.

Docker also applies a separate fixed 30-second limit while starting the exec process, before applying the configured probe-command timeout. This explains the observed `timed out starting health check` failures despite a 600-second command timeout. The implementation confirms both mechanisms. [Docker 29.1.3 health implementation](https://raw.githubusercontent.com/moby/moby/docker-v29.1.3/daemon/health.go)

The corrected fixture sets `start_interval` and `interval` to 120 seconds explicitly, preserves actual probe commands from the current production Compose source, starts core services sequentially and restores their normal `unless-stopped` restart policy before acceptance. These remain local emulator timing/setup exceptions. Service memory/swap limits retain their source values.

Read-only resource sampling now uses the actual guest Engine API directly. This avoids repeatedly starting Docker CLI processes solely for observation. Actual lifecycle operations still run through the managed CLI and Compose path.

## Controlled Docker observations

The existing guest was booted with eight emulated vCPUs and 1,926 MiB QEMU memory. Linux exposed approximately 1,832.22 MiB, conservatively below the measured Yunesa total of 1,834.98 MiB. Systemd and Docker run inside the isolated ARM64 kernel, with the guest's own Docker socket.

Guest Docker autostart was disabled for diagnosis, and the existing core containers were stopped through the guest Engine API. Their restart policies were temporarily set to `no` during isolation. A first daemon-start diagnostic exceeded its 180-second wait. After Docker completed initialization, a resumed diagnostic verified the actual API and exec paths.

| Controlled operation | Observed duration |
| --- | --- |
| Engine `/_ping` | 0.063 seconds |
| Individual container inspection requests | Approximately 0.02 to 0.39 seconds |
| Redis container start | 22.92 seconds |
| First `/bin/true` exec start | 4.94 seconds |
| Actual Redis `PING` exec start | 5.71 seconds, returned `PONG` |
| Second `/bin/true` exec start | 4.15 seconds |

The daemon reported version 29.1.3. These results establish that the isolated Docker paths can work once startup load is controlled. Full-stack readiness and native EC2 latency require separate evidence. Logs also showed exec-start failures for light Redis, Nginx, PostgreSQL and Qdrant probes while the guest still had approximately 1.3 GiB available memory. The observations suggest exec-start scheduling pressure alongside queue-worker paging.

Several ARQ process names appeared during shutdown. A subsequent argument/cgroup inspection found zero remaining `arq --check` processes. The evidence does not establish a persistent orphan-probe leak.

## Queue-worker probe correction

The old Compose probe, `arq --check server.worker_main.WorkerSettings`, imported the application job-handler module on each invocation. The import profile showed `yunesa.services.chat_service` and its tracing/LLM dependencies. The replacement, `python -m server.worker_health`, calls the same upstream `arq.worker.async_check_health` with Redis settings parsed from the worker's `REDIS_URL`. The worker runs `arq server.worker_main.WorkerSettings`.

The comparison used native AMD64 containers with real PostgreSQL and Redis, no published ports, an internal diagnostic network and the worker's 256 MiB memory / 1 GiB combined memory-and-swap limits. Python import profiling was enabled for both probes. Measurements are Linux child-process peak RSS and wall time. They are separate from cgroup aggregate memory and ARM64 capacity.

| Probe with no running worker | Peak child RSS | Duration | Result |
| --- | --- | --- | --- |
| Original | 276.56 MiB | 14.72 seconds | Exit 1, missing heartbeat, chat handlers imported |
| Replacement | 44.08 MiB | 0.58 seconds | Exit 1, missing heartbeat, chat handlers absent |

The same packaged image then ran the actual ARQ worker entrypoint against those dependencies. Docker health reached healthy and a direct replacement probe returned exit 0. After graceful worker shutdown, the probe returned exit 1 for the absent heartbeat. An invalid Redis URI returned exit 1 with a redacted error and no password disclosure. Heartbeats came from the actual worker. Provider/chat was deferred.

The native build is `yunesa-api:health-diagnosis-native`. The ARM64 diagnostic image was built inside the guest from its retained API image with the new module copied into the normal package location. Its inspected identity was `sha256:17578891faa0a11e2a1b8c7c32e595913b42e068b8c552458c13546b4a4c515c`, architecture `arm64`. Reading the module back from its image filesystem matched source SHA-256 `13d5b1edbfbf440a6c0b486c51db0ed2980fd9bc11cec36c926cc94e692bd02a`.

The guest initially lacked the Buildx plugin and its legacy build client stalled. That diagnostic client was terminated. Installing Ubuntu's ARM64 `docker-buildx` package enabled the thin BuildKit build. The image build completed successfully, including its final 29.1-second export/unpack stage. This changes local guest tooling only. No image was published.

## Residual initialization correction

The earlier OFF path checked only the three runtime services and could report OFF while `airflow-init` remained active. The updated lifecycle includes active initialization in pending shutdown. It closes admission, waits within the deadline and reports draining on timeout. ON recovery waits before replacing an active init container, backup rejects active initialization, and bounded logs accept `airflow-init`.

Regression project `yunesa-airflow-it-f5d4e79e` used native AMD64 Airflow and a real PostgreSQL lock on `alembic_version` to hold an actual migration. PostgreSQL activity confirmed the Airflow connection was waiting for a lock. During that wait, status reported degraded with an initialization reason. OFF and ON each returned exit 1 with draining state and a closed gate. The same init container remained running, and backup was rejected even when replaying the historical persisted OFF state.

After terminating only the fixture lock-holder backend, the real initialization completed with exit 0. OFF and repeated OFF succeeded, workers were empty, the PostgreSQL container identity was preserved and metadata schema remained `cc92b33c6709`. The actual init log command returned its requested bounded output. The separate lifecycle/trust contract suite passed all 17 tests.

## Proof and current acceptance boundary

Native regression entrypoints are `scripts/check-airflow-init.py` and `scripts/check-worker-health.py`, run in the existing local checker image. Their synthetic PostgreSQL/Redis/container/network resources were removed after verification. Proof remains under `.cache/airflow-init-diagnosis/` and `.cache/worker-health-diagnosis/`.

ARM64 diagnostic scripts, results, builder logs and source/image identities remain under `.cache/airflow-arm64-capacity/`. The original failed measurements are retained. `--refresh-baseline` explicitly archives the previous baseline, installs the corrected local lifecycle bootstrap, validates every image as ARM64 and captures new core identities after intentional setup changes. The measurement phase continues to require identity preservation, actual application traffic, observed managed-worker cgroup peaks, no observed OOM/restart increase, positive post-OFF memory release and zero remaining managed workers.

The corrected ARM64 baseline completed with exit 0. All eight core services passed startup with their normal restart policies restored. The actual Nginx/application path passed frontend, login, authorization rejection and conversation write/read/delete checks. The guest exposed 1,876,196 KiB RAM, 2,828 KiB below the audited Yunesa total. The baseline records all core container and ARM64 image identities in `.cache/airflow-arm64-capacity/baseline.json`.

The subsequent measurement failed. Airflow initialization exceeded its 3,600-second Compose deadline. The same init container eventually completed successfully with exit 0, starting at 13:03:00 UTC and finishing at 14:07:26 UTC on 8 November, approximately 64 minutes 26 seconds. Its log records metadata head `cc92b33c6709`, FAB schema creation and completed migration. The planned run `manual__arm64_capacity_f72a8e7a` was never submitted. There is no workload peak or KG destination evidence from this attempt.

The resource observer stopped after three samples and the traffic observer recorded two successful application cycles. The final exception from the sampling context obscured the original init timeout. The verification helper now preserves the original exception and attaches sampling errors as notes. ARM64 sampling also writes its failure immediately, including the observer name and collected counts. These changes improve the next diagnostic's failure evidence. This attempt's sparse samples cannot establish peak capacity.

A separate read-only Engine request timed out at 30 seconds during initialization. A later controlled request returned `/_ping` in 0.137 seconds and the container list in 6.239 seconds. Availability varied during this emulated startup. The evidence supports intermittent observer/Engine latency, with no basis for treating every timeout as memory exhaustion.

After init completed, the actual OFF command returned exit 0 with observed/requested OFF, an exited init service, no runtime Airflow services and zero managed workers. The command took 163.5 seconds including status/resource collection, despite a ten-second drain deadline. That deadline bounds drain waiting, and does not bound the full command's observation overhead. The final failure snapshot showed all eight core services healthy, OOM false and restart count zero. This is separate from continuous resource coverage, which was lost early.

The post-OFF real application probe passed frontend, login, authorization and conversation write/read/delete again. All core IDs matched the corrected baseline, no Airflow service was active and managed workers were empty. Available memory at that observation was 807,632,896 bytes. This snapshot cannot replace the missing workload/OFF peak-and-release comparison. The helper's exception preservation was also exercised directly in the native Linux checker, covering original-error preservation and standalone sampling failure. Both checks passed. No services were substituted in application verification.

No further QEMU retry was started. Task 6.3 remains open at 25/28 tracked tasks. A native ARM64 isolated environment with the audited RAM/swap baseline is the next capacity acceptance path. The AMD64 fixture allowed by design line 104 remains valid for functional DAG/wrapper verification, with capacity/ARM64 acceptance tracked separately. Native completion time is unmeasured. Eight emulated vCPUs cannot establish production two-vCPU throughput, CPU credits or latency. The planned workload uses one synthetic paper/lecturer with GLiNER and vector writes disabled. Provider/chat is deferred.

## Fixture closure

Airflow OFF and the post-OFF application proof completed before emulator shutdown. The guest `systemctl poweroff` SSH command exceeded 120 seconds, and the emulator remained active after an additional wait. Cleanup sent SIGTERM only to the verified fixture QEMU PID 17, then confirmed its exit. This establishes emulator termination, without clean guest shutdown proof. The controller was stopped and its named disk `yunesa-arm64-capacity-data` retained. Evidence is recorded in `.cache/airflow-arm64-capacity/diagnosis-shutdown.json`. The two unrelated Personal-agentic controllers retained their original start timestamps.
