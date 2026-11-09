# Local Airflow restart and recovery

Additional local verification for tasks 4.4 and 6.2 ran on 8 November 2026. Both tasks remain open for the acceptance boundaries described below. Production, Git commits and Git pushes were excluded. Existing implementation files and historical DEP-001 results were preserved.

## Environment and entrypoints

The retained native AMD64 project is `yunesa-airflow-it-73e9a2c6`. It uses eight real core services, Airflow 3.1.7 API server/DAG processor/LocalExecutor scheduler, the actual managed Docker operator and built ETL worker. Metadata, application data, log and control volumes were retained from the preceding release/drain rehearsal.

`scripts/checks/airflow/check-airflow-restart.py` reuses the existing core fixture, lifecycle CLI, authenticated Airflow API and application readiness implementation. Preparation verifies that the installed lifecycle module matches the working-tree source and that the fixture selects AMD64. The final baseline guards reject a different project or changed core container identity before lifecycle mutations.

A temporary OpenSSH server ran inside the local controller, published only at `127.0.0.1:63597`. A disposable SSH key authenticated user `rehearsal`, with sudo access to the trusted Airflow operation. The test known-host file was pinned from that container's public host key. No production SSH identity or connection was used.

The actual Windows helper invocation used explicit local connection arguments.

```powershell
pwsh -NoProfile -File scripts/yunesa-airflow.ps1 on `
  -Server rehearsal@127.0.0.1 -SshPort 63597 `
  -SshKey .cache/airflow-restart-proof/ssh_identity `
  -KnownHostsFile .cache/airflow-restart-proof/known_hosts
```

The recorded sequence was `status`, `on`, `off`, `on`. All four returned zero with the expected OFF/healthy observations. SSH setup and keys belonged exclusively to the disposable local controller.

The controller mounted the retained root volume at `/opt/yunesa-app`, its named control volume at `/opt/yunesa-app/shared/airflow/control`, the log volume read-only at `/airflow-logs`, repository source read-only at `/source`, and ignored evidence at `/proof`. Its Docker socket referred to the local Desktop daemon. The controller temporarily installed OpenSSH server and sudo in its own filesystem.

```sh
python /source/scripts/checks/airflow/check-airflow-restart.py --project yunesa-airflow-it-73e9a2c6 --phase prepare
python /source/scripts/checks/airflow/check-airflow-restart.py --project yunesa-airflow-it-73e9a2c6 --phase verify
```

Preparation is repeatable on this retained fixture. A new unrelated project requires the original core-fixture installation first. The verify phase has a 45-minute bound. Preserve its evidence, then explicitly stop/remove its owned containers and network after review.

The retained fixture requires its internal external network named `yunesa-airflow-it-73e9a2c6_app-network`, labeled `io.yunesa.integration=yunesa-airflow-it-73e9a2c6`. Cleanup removed that empty network. Recreate the owned network and controller mounts, and generate a fresh test SSH identity/known-host mapping, before repeating these historical commands.

## Accepted execution

The main verifier completed with exit `0`, recorded in ignored `.cache/airflow-restart-proof/verify-exit.txt`. Its receipt is `verify-result.json`. The final baseline-guard addition was checked separately through a fresh import of the current script and real Docker inspection after the main run. Both negative cases preserved lifecycle/gate bytes and container start times. `baseline-guards.json` records the current script SHA-256 and results.

| Scenario | Observed result |
| --- | --- |
| Core restart while Airflow OFF | All eight existing core IDs restarted. Reconciliation preserved OFF and zero Airflow runtime services. Application checks passed afterward. The accepted run needed one core-start attempt. |
| Read-only status | Healthy and stale-boot observations preserved lifecycle and gate file bytes. |
| Bounded selected logs | Each of three selected services returned three lines. Tail 1001 was rejected. Lifecycle/gate bytes were preserved. |
| Stale boot with healthy components | Real Airflow container restarts reached component readiness. Status reported desired ON / observed degraded. A gate check inside the actual scheduler rejected admission. |
| Managed task before reconciliation | `manual__restart_fdb248ec`, `load_data` attempt 1, reached `up_for_retry`. Its task log contained `release/boot reconciliation required`. No worker container was created for the run. |
| Resume after reconciliation | Reconciliation restored readiness and opened admission. The authenticated `clearTaskInstances` API targeted exactly this run's `load_data` task, with exactly one returned entry. The same managed DAG completed successfully. |
| Pause ownership | KG remained unpaused. Lecturer and paper DAGs remained owner-paused after recovery. KG uses `schedule=None`; the bounded manual run disabled GLiNER and graph/vector writes. |
| Missing DAG processor | Stopping the actual processor produced desired ON / observed degraded. Reconciliation restored healthy operation. |
| Scheduler crash | SIGKILL targeted the scheduler process beneath PID 1, leaving Docker's restart policy active. The same container restarted, with `RestartCount` increasing from 0 to 1. |
| Corrupt state | Reconciliation returned 1, closed admission and exposed unknown intent / error health. An administrator restored the captured valid checkpoint, then reconciliation recovered health. |
| Interrupted startup | The real `on` process was killed during STARTING, exit `-9`. Intent remained ON, admission remained closed and status reported STARTING. Reconciliation recovered health and the original pause choices. |
| Retained history/logs | Seven successful DAG runs remained. All 32 pre-existing historical task-log SHA-256 values matched. |
| Final OFF | Requested OFF, zero active managed workers, application checks passed. |

Independent SQL after the accepted run returned the following rows.

```text
build_graph|success|1
extract_entities|success|1
load_data|success|2
write_milvus|success|1
write_neo4j|success|1
```

`final-task-rows.json` retains that query result. Core identities were compared throughout all recovery scenarios against the prepared eight-ID baseline. The application checks exercised frontend HTML, login, authenticated profile, unauthorized-request rejection and conversation create/list/delete through the real proxy/API/persistence path. All recorded checkpoints passed at application version 0.6.0.

## Corrected verifier paths and observed recovery limit

The first attempt used a Docker restart flag unsupported by the controller's Docker client 26.1.4. The Desktop daemon was 29.9.2. The command now uses the supported `-t` spelling.

The initial bounded-date CLI clear left the task waiting for retry. Recovery now uses the actual Airflow API request model with explicit `dag_run_id` and `task_ids`, and checks the returned selection. The response's rendered fields are excluded from evidence because they can contain runtime configuration.

An initial `docker kill` injection marked the scheduler container manually stopped. The corrected injection kills the actual scheduler child process inside its namespace, allowing the real restart policy to run. The earlier phased run needed manual application of these corrections. Its receipt/log are retained separately as historical diagnostic evidence.

One full-repeat attempt encountered a real core-worker failure during simultaneous restart. ARQ exited 1 with `redis.exceptions.ConnectionError` and `Temporary failure in name resolution` for Redis. The other core services subsequently became healthy. Repeating normal Compose startup recovered the worker. The verifier permits one recorded retry only for this observed worker DNS failure with healthy dependencies and no worker OOM. Other failures propagate. The accepted final run used one attempt, so it does not establish seamless core-worker recovery from every boot-time DNS race. No core application behavior was changed to mask this finding.

The baseline guards were subsequently tightened and verified separately against wrong-project and changed-container-ID files. Both failed before changing lifecycle state, admission or container start times. Static syntax/lint validation passed on that final script.

## Remaining acceptance

The later [kernel/systemd verification](airflow-kernel-systemd-2026-11-08.md) completed task 4.4 using four actual kernel reboots. The list below records the boundaries outstanding when this earlier container-restart rehearsal finished.

- Task 4.4 retains an actual kernel reboot and installed systemd boot/retry boundary. This rehearsal used a deliberately stale persisted boot record with real service/container restarts. It exercised the actual admission code, but did not change the kernel boot ID or boot the installed host unit.
- Task 6.2 retains provider-gated successful deployment and queued chat/provider results, deferred by the owner. Conversation CRUD is recorded separately from queued chat. Historical active drain, timeout, launch race, competing wrapper operation and ON/OFF rollback evidence remains in the preceding release report.
- Task 6.3 retains target-class native ARM64 workload/capacity acceptance. This native AMD64 rehearsal provides local functional evidence.
- Task 5.5 retains the separately authorized production migration window.

All service boundaries used real dependencies. Synthetic academic data and the deliberately stale boot record are explicit fixtures. Corrupt-state recovery used an administrator-selected known checkpoint. No external provider calls or mocked services supplied successful outcomes.

## Validation

`py_compile`, Ruff and strict OpenSpec validation passed. The main verifier exited zero and the final guard checks passed separately. Git HEAD remained `b6924e196f6728c73dd70864c20b1c655db9f50f` on `main`. Global progress remains 24/28 because the outstanding acceptance boundaries are preserved.

## Cleanup

After final OFF and zero active workers, the eight core fixture services were stopped gracefully. All owned core/Airflow containers and the SSH controller were removed. The empty internal network was removed after checking its actual integration ownership label. The temporary SSH private/public key files were deleted. Recovery volumes and ignored evidence remain available for inspection. `cleanup.json` records zero owned containers, removal of the controller/network/key and two unrelated healthy Personal-agentic containers.
