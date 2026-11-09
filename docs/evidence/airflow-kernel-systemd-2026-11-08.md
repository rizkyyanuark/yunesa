# Airflow kernel reboot and systemd verification

Task 4.4 of `integrate-airflow-etl-profile` completed local acceptance on 8 November 2026. The verifier exited zero after four actual guest kernel reboots. Provider/chat, target-class ARM64 capacity and production migration remain separate tasks. No production connection, Git commit or Git push was performed.

## Isolated Linux environment

The disposable QEMU/KVM guest ran Ubuntu 24.04 with kernel `6.8.0-147-generic`, systemd PID 1, its own Docker daemon, 4 GiB RAM and 2 GiB persistent swap. The outer controller received `/dev/kvm`, a dedicated disk volume, read-only repository source and an ignored proof directory. The guest received selected source files and locally exported images over SSH. The host Docker socket was excluded from the controller and guest. SSH publication was restricted to Windows loopback.

The Ubuntu cloud image was downloaded over HTTPS and matched the published SHA-256 value `04e8f2461a16a44e78a370284471f29616cdd9baf1893df25807b71f985b6c94`. The fixture used QEMU KVM acceleration and user networking with SSH forwarding. [Ubuntu image directory](https://cloud-images.ubuntu.com/noble/current/), [QEMU invocation documentation](https://www.qemu.org/docs/master/system/invocation.html)

The actual production Compose configuration supplied PostgreSQL and the optional Airflow services. The guest ran API server, DAG processor, LocalExecutor scheduler and a real managed worker. The seven other core services were outside this boot-specific fixture. Their local restart/authenticated application proof remains in the [preceding recovery report](airflow-restart-recovery-2026-11-08.md).

The database image used its locally loaded immutable image identity because image archive import can change available repository-digest associations. Airflow and worker inputs came from the previously built native local images. The exported image archive SHA-256 was `c98a7b9d6d35a0bd50f31d81bdafd363c80fd16d87a755522d7a40c1b19992c1`.

The installed reconciliation unit matched repository bytes, SHA-256 `f0aefb80844cb89926201dee9e2377a0709c878fef0ab90f358777b60bf083dd`. Installed lifecycle/admission modules also matched their source. Admission and operator files read directly from the loaded Airflow image matched the working-tree source. These comparisons are recorded in `source-identity.json`.

## Execution

The host helper is `scripts/checks/airflow/check-airflow-kernel-vm.py`. The in-guest assertions are `scripts/checks/airflow/check-airflow-kernel-guest.py`. The helper ran inside a disposable controller with QEMU, cloud-image-utils, SSH client and CA certificates installed. VM files were isolated under `/vm`, source was read-only under `/source`, and proof was written under `/proof`.

```sh
python /source/scripts/checks/airflow/check-airflow-kernel-vm.py setup
python /source/scripts/checks/airflow/check-airflow-kernel-vm.py verify
```

`setup` verifies the official image checksum, generates disposable SSH client/host keys, creates a fresh QCOW2 overlay and cloud-init seed, boots with KVM and waits for actual guest Docker installation. Existing guest disks are rejected to preserve prior state. `verify` transfers selected source and exported local images, installs the original unit, enables it through systemd and drives the reboot scenarios. Every boot reads `/proc/sys/kernel/random/boot_id` inside the guest.

The unit retained its original `ExecStart`, Docker dependency, 900-second timeout and `Restart=on-failure` / 30-second retry. A test-only drop-in added an `ExecStartPre` barrier for the ON boot. This held the unit before its real lifecycle command while the actual Docker services started. Removing the fixture hold file allowed the original command to execute. The boot ID was never rewritten.

## Observed boot sequence

| Boot | Actual kernel boot ID | Outcome |
| --- | --- | --- |
| Initial | `5e42a1b8-c86a-4ac2-be4c-ac7934639348` | Real bounded DAG completed, history/log baseline captured, requested OFF saved |
| OFF reboot | `89cd7a3e-426b-4d3f-8ced-c703a4a2d997` | Enabled unit ran automatically, `Result=success`, `ExecMainStatus=0`, requested/observed OFF, current-boot closed gate |
| ON reboot | `86e7e9e7-4645-4ac6-a703-47f2b4e9dac3` | Before reconciliation, desired ON / observed degraded, old gate boot ID, unit `start-pre`, worker creation rejected. After barrier release, original unit completed successfully and opened current-boot admission |
| Failure/retry reboot | `610a3573-c7ff-4db2-ab89-72d8cfed3acb` | Deliberate manifest identity mismatch caused unit exit 1, `Result=exit-code`, desired ON / observed error and closed admission. Correcting the manifest allowed automatic systemd retry to recover healthy ON without a manual unit start |
| Final OFF reboot | `1116bb28-4549-43fa-9877-dc5ae91405b4` | Requested/observed OFF, gate closed with final boot ID, no running Airflow runtime services and zero managed workers |

During the ON barrier, the actual scheduler's `AdmissionClient.create_container` path rejected worker creation with `release/boot reconciliation required`. Docker contained zero probe workers. The old gate referenced the preceding real kernel boot ID. `ExecMainStartTimestampMonotonic=0` and unit `SubState=start-pre` established that reconciliation had not started yet.

After release, readiness and admission passed with the new boot ID. KG remained owner-unpaused, while lecturer and paper DAGs remained owner-paused. The same choices survived failure recovery. The failed unit showed `NRestarts=1`; successful automatic recovery showed `NRestarts=2`, `Result=success` and `ExecMainStatus=0`. Successful oneshot completion left the unit inactive/dead with its execution result and invocation ID retained.

## Persistence and independent evidence

Run `manual__kernel_4efd8b7d` executed the actual KG DAG through authenticated API, scheduler, managed Docker operator, built worker and real PostgreSQL. Its sample used one synthetic paper/lecturer, GLiNER disabled and graph/vector writes disabled. All five tasks succeeded. The run state, metadata schema revision and all five task-log hashes remained verifiable after OFF reboot, ON reboot, automatic failure recovery and the final OFF reboot.

The QEMU serial console independently recorded five Linux kernel banners, four `reboot: Restarting system` messages and one final power-down message. Selected kernel/unit events and counts are retained in `serial-kernel-events.log` and `serial-counts.json`.

The outer Docker/WSL kernel boot ID remained `c351305e-a831-4b4f-93a2-2cfa6f0eeb4b`. Two unrelated Personal-agentic containers retained the same IDs, start timestamps and healthy state. `isolation-before.json` and `isolation-after.json` capture this comparison.

Ignored proof is under `.cache/airflow-kernel-proof/`. It includes `result.json`, `verify-exit.txt` containing `0`, per-phase JSON results, source/image identities, cloud-image checksum, serial events, isolation comparison and cleanup receipt. Recovery keys/passwords were excluded from exported proof.

## Verification scope and cleanup

Read-only status, bounded service-selected logs, invalid-tail rejection, partial-health observation and interrupted/corrupt-state recovery remain covered by the preceding local recovery report. This kernel/systemd run closes its outstanding task 4.4 boot boundary. The fixture used real kernel, systemd, Docker, PostgreSQL, Airflow and worker execution. Synthetic academic data, the timing barrier and the deliberately invalid release identity were explicit test inputs.

During bootstrap, persistent guest swap was enabled before the accepted reboot sequence. The final helper performs this setup before initializing Airflow. The VM used native AMD64 and generous guest resources. Target-class ARM64 workload acceptance remains task 6.3. Task 6.2 retains the owner-deferred provider/chat and provider-gated release boundaries. Task 5.5 retains the authorized production cutover window.

The guest was powered off through systemd. After confirming QEMU stopped, the owned controller, fresh guest disk volume, SSH keys and temporary image/source export archives were removed. Structured evidence and reproducible helpers remain. Existing host images and unrelated containers were preserved.

Python compilation, Ruff, strict OpenSpec validation and diff checks passed. Git HEAD remained `b6924e196f6728c73dd70864c20b1c655db9f50f` on `main`.
