# ARM64 capacity rehearsal

Task 6.3 remains open. The two-vCPU and owner-authorized eight-vCPU full-system ARM64 rehearsals did not reach a successful managed KG execution. OpenSpec progress remains 25 of 28 tasks. Production deployment, Git commit and Git push were excluded. Provider/chat remained deferred.

## Verified target reference

Read-only SSH and EC2 IMDSv2 checks on 8 November 2026 identified the Yunesa host as instance `i-04ba2d1b2dcd7f757`, public IP `23.20.126.187`, `t4g.small`, ARM64, two vCPUs, in `us-east-1c`. Linux reported 1,879,024 KiB MemTotal, 654.77 MiB MemAvailable and 1,285.84 MiB swap used at that snapshot. Its swap devices were a 4 GiB disk swapfile and approximately 917.49 MiB zram.

The host had eight healthy `yunesa-app` services, API, web, queue worker, PostgreSQL, Redis, Memgraph, Qdrant and MinIO. A separate healthy `yunesa-airflow:3.1.7` container was also running. The integrated fixture includes those eight core services and the proposed replacement orchestration. It does not duplicate the legacy scheduler installation.

The colleague's audit addressed `34.196.37.78`, instance `i-0571d58c00a33db88` in `us-east-1a`. That instance runs Personal-agentic, Matrix, GitLab runners, JupyterLab, MLflow and a GitHub MCP container. Its 6 GiB disk swap and approximately 2.63 GiB swap usage belong to that separate host. The two instances had distinct SSH host fingerprints. The earlier report's shared-workload inventory does not describe the Yunesa host.

## Local environment and boundaries

The local controller was `yunesa-arm64-capacity`, labeled `io.yunesa.arm64-capacity=local`, with its own disk volume `yunesa-arm64-capacity-data`. It had no host Docker socket mount. The guest ran Ubuntu 24.04.5, kernel `6.8.0-147-generic`, PID 1 systemd and its own Docker daemon. Every application and dependency image was ARM64. Image identities are retained in the ignored proof directory.

QEMU used full-system ARM64 TCG on an AMD64 laptop, `virt` and `neoverse-n1`. The eight-vCPU retry retained the 1,926 MiB QEMU memory allocation. Linux exposed 1,876,196 KiB, or 1,832.22 MiB, which is 2.76 MiB below the measured Yunesa MemTotal. Swap totaled 5,012.11 MiB, with a 4 GiB disk swapfile and zstd zram sized at approximately half guest RAM. Zram had priority 100. The kernel assigned the local disk swap priority -2.

Application memory/swap limits were retained. The fixture extended healthcheck timeouts to 600 seconds, startup grace to 1,800 seconds and intervals to 120 seconds while preserving each original probe command. Baseline Compose readiness had a 3,600-second wait and a 3,900-second subprocess deadline. The two-vCPU Airflow ON attempt used a 3,600-second initialization deadline. These are emulator-specific timing exceptions.

Eight emulated CPUs change scheduling and automatic thread counts. They cannot certify the CPU capacity, latency or concurrency characteristics of the production two-vCPU instance. The fixture uses synthetic academic rows and synthetic credentials. It does not reproduce production dataset size, caches, historical traffic or provider usage.

## Two-vCPU result

The initial baseline passed frontend HTML, login, authorization rejection and conversation write/read/delete through the actual Nginx/API/PostgreSQL path. During the subsequent Airflow ON attempt, 198 resource observations and 136 successful application cycles were captured over approximately 61 minutes.

| Observation | Value |
| --- | --- |
| Minimum observed MemAvailable | 562.93 MiB |
| Maximum observed total swap used | 1,061.23 MiB |
| Maximum observed physical zram use | 234.62 MiB |
| Observed OOM kills and container restarts | 0 |
| Managed workers at failure | 0 |
| Airflow startup result | Initialization exceeded 3,600 seconds |

Total swap includes disk swap and compressed zram. It cannot be treated as disk I/O volume. Cgroup peak counters include the startup history of surviving containers. The intended run identifier `manual__arm64_capacity_a52d36c3` was generated before ON, but the DAG submission was never reached.

A subsequent real OFF command returned requested/observed OFF with no managed workers or launch reservations. The one-shot `airflow-init` container remained running. Available memory did not demonstrate release from a completed orchestration workload. This failed-start shutdown observation needs a lifecycle review before production acceptance. It is retained in `two-vcpu/failed-start-off.json`.

## Eight-vCPU result

The owner authorized eight emulated vCPUs while retaining equivalent RAM. Guest boot ID was `4e6134f2-eff4-4d7d-a31d-b77168ee708b`. Core container IDs survived the reboot. Baseline Compose exceeded its 3,900-second subprocess deadline and returned exit 1. At the failure snapshot, eight core containers were running. Seven reported unhealthy and PostgreSQL remained starting. OOM and restart counters in that snapshot were zero.

An independent request through the current Nginx address returned HTTP 200 from `/api/system/health`, with status `ok` and version `0.6.0`. The bridge IP changed across reboot. An earlier diagnostic used the stale address and received connection refusal. The corrected address was obtained from the running container's network namespace. Authenticated CRUD was not completed on the eight-vCPU baseline.

The diagnostic snapshot reported 559.39 MiB MemAvailable and 519.42 MiB total swap used. These are single observations. They are not workload peaks.

| Service | Cgroup memory peak since reboot, MiB |
| --- | --- |
| API | 384.01 |
| Queue worker | 256.01 |
| Memgraph | 129.39 |
| MinIO | 128.02 |
| Qdrant | 86.77 |
| PostgreSQL | 55.13 |
| Web | 23.98 |
| Redis | 19.74 |

The queue worker had 469.87 MiB cgroup swap and 77 PIDs at that snapshot. Its memory PSI `some avg60` was 68.80 and `full avg60` was 26.87. All observed core cgroup OOM-kill counters were zero. Direct Docker Engine container-list requests also timed out after 30 and 60 seconds, including the attempt after Compose had ended.

The outer controller reached its 4 GiB memory boundary and had approximately 65.54 MiB swapped at the captured diagnostic. Its peak and event counters cover the controller's cumulative lifetime, including prior setup and the two-vCPU attempt. This additional emulator boundary and the guest's per-service paging prevent attributing the outcome solely to CPU emulation or solely to target RAM capacity.

The managed KG DAG, destination query, steady Airflow component peaks, post-workload OFF release and complete worker-lifecycle acceptance were not reached. A successful liveness GET cannot close these boundaries.

## Commands and retained proof

The controller ran `python /source/scripts/rehearsal/arm64/check-airflow-arm64-vm.py --phase baseline`. The two-vCPU attempt also ran its `measure` phase. Guest startup used `start_guest('arm64', 1926, 8, 'yunesa-arm64-capacity')`. Diagnostics read actual cgroup v2 files, kernel memory/swap/PSI, container network namespaces and the Docker Engine API. No service or application response was mocked.

Proof is retained under `.cache/airflow-arm64-capacity/`, including `yunesa-reference.json`, `two-vcpu/`, `two-vcpu-analysis.json`, `eight-vcpu-baseline.log`, `eight-vcpu-baseline-exit.txt`, `baseline-failure.json`, `eight-vcpu-diagnostic.json`, `eight-vcpu-analysis.json` and `eight-vcpu-controller.json`. Exported proof excludes fixture environment files and credential values.

The final helper adds the exact verified Yunesa MemTotal reference and a conservative maximum 4 MiB guest shortfall, bounded SSH connection handling, resumable baseline capture with identity guards and failure persistence before optional Docker inspection. These helper edits pass static verification. Their complete path remains blocked by the local runtime outcome described above.

## Fixture shutdown and verification

The guest poweroff SSH request exceeded its 90-second deadline. Only the verified owned QEMU process was then terminated with SIGTERM, and its stopped state was confirmed before stopping the controller. This shutdown does not provide successful Airflow OFF or clean guest-filesystem shutdown evidence. The controller is stopped, with its restricted synthetic disk volume retained for diagnosis. The redundant 2.47 GB host image export was removed. The two unrelated Personal-agentic containers retained their IDs and original start timestamps.

Ruff, Python compilation, strict OpenSpec validation and diff whitespace checks passed after the final helper edits. Git HEAD remained `b6924e196f6728c73dd70864c20b1c655db9f50f` on `main`. Existing and concurrent unrelated workspace changes were preserved.

The smallest remaining capacity proof requires a responsive isolated native ARM64 environment with equivalent RAM and the Yunesa core workload, followed by the real managed DAG and independent destination/off checks. The retained emulator disk can support further diagnosis. Task 5.5 still requires a separately authorized production window. Task 6.2 retains its provider/chat boundaries.
