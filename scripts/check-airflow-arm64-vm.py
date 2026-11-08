"""Transfer local ARM64 artifacts and run the capacity check in its own VM."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import tarfile
from pathlib import Path

from airflow_capacity_session import Session, capacity_result

SOURCE = Path(__file__).resolve().parents[1]
PROOF = Path('/proof')


def native(lease_path: Path, bundle: Path, proof: Path) -> None:
    lease = json.loads(lease_path.read_text())
    session = Session.read(lease)
    session.remaining(20)
    manifest = json.loads((bundle / 'bundle.json').read_text())
    for name in ('images.tar.gz', 'source.tar.gz'):
        path = bundle / name
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != manifest['artifacts'][name]['sha256']:
            raise ValueError('Native transfer bundle checksum mismatch')
    for name, expected in manifest['source_files'].items():
        path = (SOURCE / name).resolve()
        if not path.is_relative_to(SOURCE):
            raise ValueError('Native bundle source path is outside this checkout')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError('Native bundle source changed; refresh and verify it before use')
    proof.mkdir(parents=True, exist_ok=True)
    ssh = ['ssh', '-F', os.devnull, '-i', lease['ssh']['key'],
        '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
        '-o', 'UserKnownHostsFile=' + lease['ssh']['known_hosts'], 'ubuntu@' + lease['ssh']['host']]

    def remote(command: str, minute: int, input_path: Path | None = None, data: bytes | None = None) -> None:
        with (proof / 'native-runner.log').open('ab') as log:
            source = input_path.open('rb') if input_path else None
            try:
                result = subprocess.run([*ssh, command], input=data, stdin=source, stdout=log,
                    stderr=subprocess.STDOUT, timeout=session.remaining(minute))
            finally:
                if source:
                    source.close()
        if result.returncode:
            raise RuntimeError('Native SSH phase failed; inspect native-runner.log')

    session_value = {key: lease[key] for key in Session.__dataclass_fields__}
    identity_check = (SOURCE / 'scripts/airflow_capacity_session.py').read_text() + '\n' + f"""
import os
session=Session.read({session_value!r})
total=int(next(x for x in open('/proc/meminfo') if x.startswith('MemTotal:')).split()[1])
native_hardware({{'architecture':os.uname().machine,'cpu_count':os.cpu_count(),
'mem_total_kib':total}},session,instance_identity())
"""
    remote('sudo python3 -', 20, data=identity_check.encode())
    failure = None
    monitor = None
    monitor_log = None
    try:
        remote('sudo mkdir -p /source /proof', 20)
        remote('sudo tar --no-same-owner -xzf - -C /source', 20, input_path=bundle / 'source.tar.gz')
        remote('sudo sh -c "umask 077; cat > /proof/native-lease.json"', 20, data=lease_path.read_bytes())
        remote("sudo python3 - <<'PY'\nfrom pathlib import Path\n"
               "p=Path('/etc/apt/sources.list.d/ubuntu.sources')\n"
               "p.write_text(p.read_text().replace('http://','https://'))\nPY\n"
               'sudo apt-get update && sudo apt-get install -y --no-install-recommends '
               'docker.io docker-compose-v2 && sudo systemctl start docker', 20)
        remote('sudo docker load', 20, input_path=bundle / 'images.tar.gz')
        monitor_code = f"""import json,pathlib,time
while time.time() < {session.started_at + 51 * 60!r}:
 for name in ['core-resource-samples.json','core-traffic.json','baseline-progress.json']:
  path=pathlib.Path('/proof')/name
  try:
   value=json.loads(path.read_text())
   print(json.dumps({{'file':name,'value':value[-1] if isinstance(value,list) and value else value}}),flush=True)
  except (OSError,ValueError):pass
 time.sleep(5)
"""
        monitor_log = (proof / 'observations.jsonl').open('wb')
        monitor = subprocess.Popen([*ssh, 'sudo python3 -u -'], stdin=subprocess.PIPE,
            stdout=monitor_log, stderr=subprocess.STDOUT)
        monitor.stdin.write(monitor_code.encode())
        monitor.stdin.close()
        for phase, minute in (('prepare', 27), ('measure', 51)):
            remote('sudo python3 /source/scripts/check-airflow-arm64-capacity.py ' + phase
                   + ' --mode native --lease /proof/native-lease.json', minute)
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        failure = error
        raise
    finally:
        if monitor and monitor.poll() is None:
            monitor.terminate()
            monitor.wait(timeout=10)
        if monitor_log:
            monitor_log.close()
        export_error = None
        try:
            code = """import pathlib,sys,tarfile
allowed={'baseline.json','baseline-progress.json','guest-images.json','native-timing.json',
'core-resource-samples.json','core-traffic.json','sampling-failure.json','result.json',
'failure.json','prepare-failure.json','measure-failure.json'}
files=[p for p in pathlib.Path('/proof').iterdir() if p.name in allowed and p.is_file() and not p.is_symlink()]
assert sum(p.stat().st_size for p in files) <= 95*1024**2, 'Proof exceeds transfer budget'
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as t:
 for p in files:t.add(p,arcname=p.name)
"""
            with (proof / 'guest-proof.tar.gz').open('wb') as target:
                result = subprocess.run([*ssh, 'sudo python3 -'], input=code.encode(),
                    stdout=target, stderr=subprocess.PIPE, timeout=session.remaining(51))
            if result.returncode:
                raise RuntimeError('Native guest proof export failed')
            if failure is None:
                with tarfile.open(proof / 'guest-proof.tar.gz') as archive:
                    capacity_result(json.load(archive.extractfile('result.json')), session)
            with (proof / 'guest-proof.tar.gz').open('rb') as stream:
                exported = hashlib.file_digest(stream, 'sha256').hexdigest()
            (proof / 'guest-proof.sha256').write_text(exported + '\n')
        except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            export_error = error
            if failure is not None:
                failure.add_note('Proof export failed: ' + str(error))
            else:
                raise
        finally:
            (proof / 'native-driver-result.json').write_text(json.dumps({
                'session': session.session, 'completed': failure is None and export_error is None,
                'error': str(failure) if failure else None,
                'export_error': str(export_error) if export_error else None}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=('swap', 'import', 'prepare', 'baseline', 'measure'))
    parser.add_argument('--refresh-baseline', action='store_true')
    parser.add_argument('--native-lease', type=Path)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--proof', type=Path)
    args = parser.parse_args()
    if args.native_lease:
        if not args.bundle or not args.proof or args.phase or args.refresh_baseline:
            parser.error('Native mode requires --bundle and --proof and runs the complete rehearsal')
        native(args.native_lease, args.bundle, args.proof)
        return
    if args.refresh_baseline and args.phase != 'baseline':
        parser.error('--refresh-baseline requires --phase baseline')
    spec = importlib.util.spec_from_file_location('vm', SOURCE / 'scripts/check-airflow-kernel-vm.py')
    vm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vm)
    archive = PROOF / 'capacity-source.tar'
    with tarfile.open(archive, 'w') as stream:
        for name in ('docker-compose.prod.yml', 'scripts/airflow_operations.py', 'scripts/yunesa-airflow.sh',
                     'scripts/airflow_capacity_session.py',
                     'scripts/check-airflow-arm64-capacity.py', 'scripts/check-airflow-core-release.py',
                     'scripts/airflow-local-check.py', 'scripts/check-airflow-kernel-guest.py',
                     'scripts/deployment-readiness.py', 'backend/server/worker_health.py', 'orchestration/yunesa_airflow'):
            stream.add(SOURCE / name, arcname=name, filter=lambda item: None if '__pycache__' in item.name else item)
    vm.copy_to_guest(archive, '/tmp/capacity-source.tar')
    vm.ssh('sudo mkdir -p /source && sudo tar -xf /tmp/capacity-source.tar -C /source')
    try:
        for phase in (args.phase,) if args.phase else ('swap', 'import', 'prepare', 'measure'):
            if phase == 'import':
                vm.copy_to_guest(PROOF / 'tagged-images.tar', '/tmp/images.tar')
                vm.ssh('sudo docker load -i /tmp/images.tar >/tmp/image-load.log && sudo rm /tmp/images.tar', timeout=7200)
                continue
            option = ' --refresh-baseline' if args.refresh_baseline else ''
            output = vm.ssh('sudo python3 /source/scripts/check-airflow-arm64-capacity.py ' + phase + option, timeout=7200)
            marker = 'CAPACITY_RESULT='
            if marker not in output:
                raise RuntimeError('Capacity guest returned no structured result')
            value = json.loads(output.rsplit(marker, 1)[1])
            (PROOF / (phase + '-result.json')).write_text(json.dumps(value, indent=2))
            print('ARM64_CAPACITY_PHASE=' + phase, flush=True)
    finally:
        result = subprocess.run(['scp', '-i', '/vm/client', '-P', '2222', '-o', 'BatchMode=yes',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no',
            '-o', 'UserKnownHostsFile=/vm/known_hosts', '-r', 'ubuntu@127.0.0.1:/proof/.', str(PROOF)],
            capture_output=True, text=True, timeout=300)
        if result.returncode:
            raise RuntimeError('Guest proof export failed: ' + result.stderr[-400:])


if __name__ == '__main__':
    main()
