"""Measure the actual ARM64 stack inside the RAM-constrained local guest."""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import importlib.util
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from airflow_operations import AirflowOperations
from airflow_capacity_session import Session, instance_identity, native_hardware

SOURCE = Path('/source')
ROOT = Path('/opt/yunesa-app')
PROOF = Path('/proof')
PROJECT = 'yunesa-arm64-capacity'
BASE = 'http://127.0.0.1:8088'
TARGET_MEM_KIB = 1_879_024
SESSION: Session | None = None
IDENTITY: dict | None = None


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


core = module('core_capacity', SOURCE / 'scripts/check-airflow-core-release.py')
kernel = module('kernel_capacity', SOURCE / 'scripts/check-airflow-kernel-guest.py')


def engine_get(path: str) -> dict | list | None:
    connection = http.client.HTTPConnection('localhost', timeout=30)
    connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.sock.settimeout(30)
    try:
        connection.sock.connect('/var/run/docker.sock')
        connection.request('GET', path)
        response = connection.getresponse()
        if response.status == 404:
            return None
        if response.status != 200:
            raise RuntimeError(f'Docker observation failed with HTTP {response.status}')
        return json.load(response)
    finally:
        connection.close()


def observed_containers() -> list[dict]:
    records = engine_get('/containers/json?all=1')
    if not isinstance(records, list):
        raise RuntimeError('Docker container listing is unavailable')
    observed = []
    for record in records:
        labels = record.get('Labels') or {}
        if PROJECT not in (labels.get('com.docker.compose.project'), labels.get('io.yunesa.etl.project')):
            continue
        inspected = engine_get('/containers/' + record['Id'] + '/json')
        if isinstance(inspected, dict):
            observed.append(inspected)
        elif inspected is not None:
            raise RuntimeError('Docker inspection returned an invalid container record')
    return observed


def service_url(name: str, port: int) -> str:
    container = next((item for item in observed_containers()
                      if item['Config']['Labels'].get('com.docker.compose.service') == name), None)
    if container is None:
        raise RuntimeError(f'Expected fixture service {name} is missing')
    network = container['NetworkSettings']['Networks'][PROJECT + '_app-network']
    return f"http://{network['IPAddress']}:{port}"


class Sampling(core.Sampling):
    def run(self, work) -> None:
        super().run(work)
        if self.errors:
            (PROOF / 'sampling-failure.json').write_text(json.dumps({
                'at': datetime.now(timezone.utc).isoformat(), 'observer': work.__name__,
                'errors': self.errors, 'samples': len(self.samples), 'application_cycles': len(self.traffic),
            }, indent=2))

    def sample(self) -> None:
        containers = observed_containers()
        groups = {}
        for item in containers:
            pid = item['State']['Pid']
            if not pid:
                continue
            try:
                relative = next(line.split(':', 2)[2] for line in Path(f'/proc/{pid}/cgroup').read_text().splitlines()
                                if line.startswith('0::'))
                directory = Path('/sys/fs/cgroup') / relative.lstrip('/')
                values = {name: int((directory / filename).read_text()) for name, filename in (
                    ('current', 'memory.current'), ('peak_so_far', 'memory.peak'), ('swap_current', 'memory.swap.current'))}
                values['events'] = dict(line.split() for line in (directory / 'memory.events').read_text().splitlines())
                values['service'] = item['Config']['Labels'].get('com.docker.compose.service')
                values['task'] = item['Config']['Labels'].get('io.yunesa.etl.task')
                groups[item['Id']] = values
            except FileNotFoundError:
                groups[item['Id']] = {'observation': 'process or cgroup removed during sample'}
        zram = list(map(int, Path('/sys/block/zram0/mm_stat').read_text().split()))
        swap_io = dict(line.split() for line in Path('/proc/vmstat').read_text().splitlines()
                       if line.startswith(('pswpin ', 'pswpout ')))
        self.samples.append({'at': datetime.now(timezone.utc).isoformat(), 'host': core.host_memory(),
            'zram': dict(zip(('original_bytes', 'compressed_bytes', 'physical_bytes', 'limit_bytes', 'physical_peak_bytes'), zram[:5], strict=True)),
            'swap_io_pages': {name: int(value) for name, value in swap_io.items()},
            'pressure': Path('/proc/pressure/memory').read_text(), 'cgroup_v2': groups,
            'states': [{'id': item['Id'], 'service': item['Config']['Labels'].get('com.docker.compose.service'),
                        'task': item['Config']['Labels'].get('io.yunesa.etl.task'),
                        'oom': item['State']['OOMKilled'], 'restarts': item['RestartCount'],
                        'allocation': {key: item['HostConfig'][key] for key in ('Memory', 'MemorySwap', 'CpuShares', 'NanoCpus')}}
                       for item in containers]})
        (PROOF / 'core-resource-samples.json').write_text(json.dumps(self.samples, indent=2))


def hardware() -> dict:
    fields = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    total = int(fields['MemTotal'].split()[0])
    return {'architecture': os.uname().machine, 'kernel': os.uname().release, 'mem_total_kib': total,
            'target_instance_id': 'i-04ba2d1b2dcd7f757', 'target_mem_total_kib': TARGET_MEM_KIB,
            'target_cpu_count': 2, 'mem_shortfall_kib': TARGET_MEM_KIB - total,
            'swap_total_kib': int(fields['SwapTotal'].split()[0]), 'cpu_count': os.cpu_count(),
            'emulation': 'none; native EC2 Graviton' if SESSION else
                'QEMU full-system ARM64 TCG on AMD64; CPU timing is outside native EC2 acceptance',
            'fixture_identity': IDENTITY}


def validate_hardware() -> None:
    value = hardware()
    if SESSION:
        native_hardware(value, SESSION, IDENTITY)
    else:
        assert 0 <= value['mem_shortfall_kib'] <= 4096, value


def phase_timeout(minute: int, emulated_seconds: int) -> int:
    return SESSION.remaining(minute) if SESSION else emulated_seconds


def configure_swap() -> dict:
    if not Path('/swapfile').exists():
        kernel.run('fallocate', '-l', '4G', '/swapfile')
        Path('/swapfile').chmod(0o600)
        kernel.run('mkswap', '/swapfile')
    assert Path('/swapfile').stat().st_size == 4 * 1024**3
    if '/swapfile' not in Path('/proc/swaps').read_text():
        kernel.run('swapon', '--priority=-1', '/swapfile')
    if not Path('/sys/block/zram0').exists():
        available = subprocess.run(['modinfo', 'zram'], capture_output=True, check=False)
        if available.returncode:
            print('CAPACITY_BOOTSTRAP=install-zram-module', flush=True)
            kernel.run('apt-get', 'install', '-y', '--no-install-recommends',
                       'linux-modules-extra-' + os.uname().release, timeout=1200)
        kernel.run('modprobe', 'zram', 'num_devices=1')
    size = 939_508 * 1024 if SESSION else hardware()['mem_total_kib'] * 1024 // 2
    if int(Path('/sys/block/zram0/disksize').read_text()) == 0:
        Path('/sys/block/zram0/comp_algorithm').write_text('zstd')
        Path('/sys/block/zram0/disksize').write_text(str(size))
        kernel.run('mkswap', '/dev/zram0')
    assert abs(int(Path('/sys/block/zram0/disksize').read_text()) - size) < 4096
    assert '[zstd]' in Path('/sys/block/zram0/comp_algorithm').read_text()
    if '/dev/zram0' not in Path('/proc/swaps').read_text():
        kernel.run('swapon', '--priority=100', '/dev/zram0')
    if SESSION:
        swaps = {row.split()[0]: row.split() for row in Path('/proc/swaps').read_text().splitlines()[1:]}
        assert abs(int(swaps['/swapfile'][2]) - 4_194_300) <= 4, swaps
        assert abs(int(swaps['/dev/zram0'][2]) - 939_508) <= 4, swaps
        assert int(swaps['/dev/zram0'][4]) == 100, swaps
    return hardware()


def prepare() -> dict:
    if SESSION:
        SESSION.remaining(20)
    assert not ROOT.exists(), 'Fresh capacity fixture required'
    validate_hardware()
    configure_swap()
    release = ROOT / 'releases/capacity-local'
    release.mkdir(parents=True)
    ROOT.chmod(0o700)
    for name in ('bin', 'shared/data/avatars', 'shared/models', 'shared/saves', 'shared/airflow/control'):
        (ROOT / name).mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE / 'orchestration', ROOT / 'orchestration')
    shutil.copyfile(SOURCE / 'scripts/airflow_operations.py', ROOT / 'bin/airflow_operations.py')
    shutil.copyfile(SOURCE / 'scripts/yunesa-airflow.sh', ROOT / 'bin/airflow')
    (ROOT / 'bin/airflow').chmod(0o755)
    environment = {
        'GLOBAL_PASSWORD': secrets.token_hex(16), 'JWT_SECRET_KEY': secrets.token_hex(32),
        'GEMINI_API_KEY': 'provider-unavailable', 'SILICONFLOW_API_KEY': 'provider-unavailable',
        'YUNESA_API_IMAGE': 'yunesa-api:capacity-native-arm64' if SESSION else 'yunesa-api:integration-arm64',
        'YUNESA_WEB_IMAGE': 'yunesa-web:integration-arm64',
        'YUNESA_MINIO_IMAGE': 'yunesa-minio:integration-arm64', 'YUNESA_AIRFLOW_IMAGE': 'yunesa-airflow:integration-arm64',
        'YUNESA_ETL_WORKER_IMAGE': 'yunesa-etl-worker:integration-arm64',
        'AIRFLOW_DB_PASSWORD': secrets.token_hex(16), 'AIRFLOW_ADMIN_PASSWORD': secrets.token_hex(16),
        'AIRFLOW_API_SECRET': secrets.token_hex(32), 'AIRFLOW_JWT_SECRET': secrets.token_hex(32),
        'AIRFLOW_FERNET_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        'YUNESA_STATE_ROOT': str(ROOT / 'shared'), 'YUNESA_RELEASE_ID': release.name,
        'YUNESA_COMPOSE_PROJECT': PROJECT, 'DOCKER_NETWORK': PROJECT + '_app-network',
        'YUNESA_DOCKER_GID': str(Path('/var/run/docker.sock').stat().st_gid),
        'YUNESA_AIRFLOW_LOG_VOLUME': PROJECT + '-logs', 'MINIO_PUBLIC_BASE_URL': BASE,
    }
    identities = {}
    for image in [environment['YUNESA_' + name + '_IMAGE'] for name in ('API', 'WEB', 'MINIO', 'AIRFLOW', 'ETL_WORKER')] + [
            'yunesa-arm64-proof/' + service + ':local' for service in ('postgres', 'redis', 'graph', 'vector')]:
        inspected = json.loads(kernel.run('docker', 'image', 'inspect', image))[0]
        assert inspected['Architecture'] == 'arm64', image
        identities[image] = inspected['Id']
    (PROOF / 'guest-images.json').write_text(json.dumps(identities, indent=2))
    env_path = release / '.env'
    env_path.write_text(''.join(f"{key}='{value}'\n" for key, value in environment.items()))
    env_path.chmod(0o600)
    rendered = json.loads(kernel.run('docker', 'compose', '--project-name', PROJECT, '--env-file', str(env_path),
                         '-f', str(SOURCE / 'docker-compose.prod.yml'), '--profile', 'etl', 'config', '--format', 'json'))
    for service in ('postgres', 'redis', 'graph', 'vector'):
        rendered['services'][service]['image'] = 'yunesa-arm64-proof/' + service + ':local'
    rendered['networks']['app-network']['internal'] = True
    (release / 'docker-compose.prod.yml').write_text(json.dumps(rendered))
    (release / 'manifest.json').write_text(json.dumps({'project': PROJECT, 'airflow_version': '3.1.7',
        'airflow_image': environment['YUNESA_AIRFLOW_IMAGE'], 'etl_worker_image': environment['YUNESA_ETL_WORKER_IMAGE']}))
    (ROOT / 'current').symlink_to(release)
    credentials = {'username': 'integration_owner', 'password': 'Ci!Aa1-' + secrets.token_urlsafe(24)}
    (ROOT / 'shared/admin-credentials.json').write_text(json.dumps(credentials))
    (ROOT / 'shared/admin-credentials.json').chmod(0o600)
    return baseline()


def baseline(refresh: bool = False) -> dict:
    validate_hardware()
    assert hardware()['cpu_count'] == (2 if SESSION else 8), hardware()
    operation = AirflowOperations(ROOT)
    assert operation.project == PROJECT
    previous = PROOF / 'baseline.json'
    reference = json.loads(previous.read_text()) if previous.exists() else None
    existing = core.identities(PROJECT)
    if reference and not refresh:
        assert existing == reference['core_ids'], 'Existing baseline container identities changed'
    if refresh:
        if reference:
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            shutil.copyfile(previous, PROOF / ('baseline-before-refresh-' + stamp + '.json'))
        shutil.copyfile(SOURCE / 'scripts/airflow_operations.py', ROOT / 'bin/airflow_operations.py')
        shutil.copyfile(SOURCE / 'scripts/yunesa-airflow.sh', ROOT / 'bin/airflow')
        (ROOT / 'bin/airflow').chmod(0o755)
    compose_path = operation.release / 'docker-compose.prod.yml'
    configuration = json.loads(compose_path.read_text())
    source_configuration = json.loads(kernel.run('docker', 'compose', '--project-name', PROJECT,
        '--env-file', str(operation.release / '.env'), '-f', str(SOURCE / 'docker-compose.prod.yml'),
        '--profile', 'etl', 'config', '--format', 'json'))
    refs = sorted({service['image'] for service in configuration['services'].values()}
                  | {operation.environment()['YUNESA_ETL_WORKER_IMAGE']})
    images = json.loads(kernel.run('docker', 'image', 'inspect', *refs))
    assert all(item['Architecture'] == 'arm64' for item in images)
    identities = dict(zip(refs, (item['Id'] for item in images), strict=True))
    (PROOF / 'guest-images.json').write_text(json.dumps(identities, indent=2))
    timing_path = PROOF / ('native-timing.json' if SESSION else 'emulation-timing.json')
    if refresh and timing_path.exists():
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        shutil.copyfile(timing_path, PROOF / ('emulation-timing-before-refresh-' + stamp + '.json'))
    timing = {}
    for name, service in configuration['services'].items():
        if 'healthcheck' not in service:
            continue
        health = dict(source_configuration['services'][name]['healthcheck'])
        timing[name] = {'original': dict(health)}
        if not SESSION:
            health.update(timeout='600s', interval='120s', start_interval='120s', start_period='1800s')
        service['healthcheck'] = health
        timing[name]['applied'] = dict(health)
    compose_path.write_text(json.dumps(configuration))
    timing_path.write_text(json.dumps(timing, indent=2))
    if existing:
        kernel.run('docker', 'update', '--restart', 'unless-stopped', *existing.values())
    completed = []
    for service in core.SERVICES:
        (PROOF / 'baseline-progress.json').write_text(json.dumps({'completed': completed, 'starting': service}))
        wait_seconds = min(180, phase_timeout(27, 1800)) if SESSION else 1800
        operation.compose('up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout',
                          str(wait_seconds), service, timeout=phase_timeout(27, 2100))
        completed.append(service)
    (PROOF / 'baseline-progress.json').write_text(json.dumps({'completed': completed, 'starting': None}))
    for item in observed_containers():
        if item['Config']['Labels'].get('com.docker.compose.service') in core.SERVICES:
            assert item['HostConfig']['RestartPolicy']['Name'] == 'unless-stopped'
    base_url = service_url('web', 80)
    api_url = service_url('api', 5050)
    if core.probe.request(api_url + '/api/auth/check-first-run')['first_run']:
        credentials = json.loads((ROOT / 'shared/admin-credentials.json').read_text())
        core.probe.request(api_url + '/api/auth/initialize', method='POST',
                           payload={'user_id': credentials['username'], 'password': credentials['password']})
    core.probe.request(base_url + '/api/auth/initialize', method='POST', expected=(403,))
    application = core.probe.http_probe(base_url, ROOT / 'shared/admin-credentials.json', False, False)
    if reference is None:
        operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', data=b"""
CREATE TABLE lecturers (nip TEXT PRIMARY KEY, nama_dosen TEXT, nama_norm TEXT, nidn TEXT, prodi TEXT, scopus_id TEXT, scholar_id TEXT, sinta_id TEXT);
CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, abstract TEXT, tldr TEXT, keywords TEXT, year INTEGER, journal TEXT, document_type TEXT, authors TEXT, author_ids TEXT, doi TEXT, link TEXT);
INSERT INTO lecturers VALUES ('integration-author','Integration Fixture','integration fixture','','Computer Science','','','');
INSERT INTO papers VALUES ('integration-paper','Graph retrieval integration fixture','Synthetic academic metadata.','Graph retrieval fixture.','graph retrieval',2026,'Integration Journal','article','Integration Fixture','integration-author','','');
""")
    value = {'hardware': hardware(), 'application': application, 'base_url': base_url, 'core_ids': core.identities(PROJECT),
             'helper_sha256': hashlib.sha256((ROOT / 'bin/airflow_operations.py').read_bytes()).hexdigest(),
             'restart_counts': {item['Id']: item['RestartCount'] for item in observed_containers()},
             'swaps': Path('/proc/swaps').read_text(), 'image_ids': identities}
    (PROOF / 'baseline.json').write_text(json.dumps(value, indent=2))
    return value


def measure() -> dict:
    validate_hardware()
    assert hardware()['cpu_count'] == (2 if SESSION else 8), hardware()
    operation = AirflowOperations(ROOT)
    baseline = json.loads((PROOF / 'baseline.json').read_text())
    assert operation.project == PROJECT and core.identities(PROJECT) == baseline['core_ids']
    base_url = service_url('web', 80)
    run_id = 'manual__arm64_capacity_' + secrets.token_hex(4)
    readiness_seconds = min(180, phase_timeout(35, 3600)) if SESSION else 3600
    result = {'hardware': hardware(), 'run': run_id, 'baseline': baseline,
              'provider_chat': 'deferred by owner', 'readiness_deadline_seconds': readiness_seconds}
    starting_restarts = {item['Id']: item['RestartCount'] for item in observed_containers()}
    result['starting_restart_counts'] = starting_restarts
    sampling = Sampling(operation, base_url=base_url)
    try:
        with sampling:
            before = core.host_memory()
            result['before'] = before
            kernel.run(str(ROOT / 'bin/airflow'), 'on', '--deadline', str(readiness_seconds),
                       timeout=phase_timeout(35, 7500))
            airflow_url = service_url('airflow-api-server', 8080)
            kernel.api(operation, '/api/v2/dags/unesa_kg_construction', 'PATCH', {'is_paused': False}, base_url=airflow_url)
            kernel.api(operation, '/api/v2/dags/unesa_kg_construction/dagRuns', 'POST', {
                'dag_run_id': run_id, 'logical_date': datetime.now(timezone.utc).isoformat(),
                'conf': {'mode': 'sample', 'sample_size': 1, 'use_gliner': False,
                         'write_neo4j': True, 'write_milvus': False, 'graph_name': PROJECT}}, base_url=airflow_url)
            def completed():
                if sampling.errors:
                    raise RuntimeError('Concurrent application/resource observation failed')
                state = kernel.query(operation, f"SELECT state FROM dag_run WHERE run_id='{run_id}'")
                if state == 'failed':
                    raise RuntimeError('RAM-constrained managed DAG failed')
                return state == 'success'
            kernel.wait(completed, phase_timeout(42, 2100))
            cypher = (f"MATCH (n {{graph_name:'{PROJECT}'}}) RETURN count(n) AS nodes;\n"
                      f"MATCH (n {{graph_name:'{PROJECT}'}})-[r]->() RETURN count(r) AS relationships;\n")
            stored = operation.compose('exec', '-T', 'graph', 'mgconsole', '--host', '127.0.0.1',
                '--port', '7687', '--use-ssl=false', data=cypher.encode()).decode()
            assert list(map(int, re.findall(r'\|\s*(\d+)\s*\|', stored))) == [4, 5], stored
            result['destination'] = {'backend': 'memgraph', 'graph_name': PROJECT, 'nodes': 4, 'relationships': 5}
            on = core.host_memory()
            result['on'] = on
            if SESSION:
                kernel.run(str(ROOT / 'bin/airflow'), 'off', '--deadline',
                           str(min(120, phase_timeout(47, 600))), timeout=phase_timeout(47, 1000))
            else:
                kernel.cli('off')
            time.sleep(15)
            after = core.host_memory()
            result['after_off'] = after
        assert not sampling.errors, sampling.errors
        assert core.identities(PROJECT) == baseline['core_ids'] and not operation.workers()
        active = [item for item in observed_containers() if item['State']['Running']
                  and item['Config']['Labels'].get('com.docker.compose.service', '').startswith('airflow-')]
        assert not active and not list(operation.control.glob('reservation-*.json'))
        assert not json.loads((operation.control / 'gate.json').read_text())['open']
        restart_deltas = {}
        worker_peaks = {}
        for sample in sampling.samples:
            for state in sample['states']:
                assert not state['oom'], state
                delta = state['restarts'] - starting_restarts.get(state['id'], 0)
                restart_deltas[state['id']] = max(restart_deltas.get(state['id'], 0), delta)
            for group in sample['cgroup_v2'].values():
                assert int(group.get('events', {}).get('oom_kill', 0)) == 0, group
                if group.get('task'):
                    task = group['task']
                    worker_peaks[task] = max(worker_peaks.get(task, 0), group['peak_so_far'])
        assert not any(restart_deltas.values()), restart_deltas
        assert worker_peaks, 'No managed-worker cgroup peak was observed'
        released = after['MemAvailable'] - on['MemAvailable']
        assert released > 0, {'on': on, 'after_off': after}
        result.update(before=before, on=on, after_off=after, samples=len(sampling.samples),
                      post_off_available_increase_bytes=released, restart_deltas=restart_deltas,
                      observed_worker_peak_so_far_bytes=worker_peaks,
                      application_cycles=len(sampling.traffic), workers=operation.workers(),
                      post_off_application=core.probe.http_probe(base_url, ROOT / 'shared/admin-credentials.json', False, False),
                      run_state=kernel.query(operation, f"SELECT state FROM dag_run WHERE run_id='{run_id}'"))
        assert result['run_state'] == 'success'
        (PROOF / 'result.json').write_text(json.dumps(result, indent=2))
        return result
    except (RuntimeError, OSError, ValueError, AssertionError, subprocess.SubprocessError) as error:
        failure = {'error_type': type(error).__name__, 'error': str(error), 'partial': result,
                   'notes': getattr(error, '__notes__', []), 'sampling_errors': sampling.errors}
        failure_path = PROOF / 'failure.json'
        failure_path.write_text(json.dumps(failure, indent=2))
        try:
            failure.update(state=operation.state(), workers=operation.workers(include_exited=True))
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as snapshot_error:
            failure['snapshot_error'] = str(snapshot_error)
        failure_path.write_text(json.dumps(failure, indent=2))
        raise


def main() -> None:
    global SESSION, IDENTITY
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('swap', 'prepare', 'baseline', 'measure'))
    parser.add_argument('--refresh-baseline', action='store_true')
    parser.add_argument('--mode', choices=('emulated', 'native'), default='emulated')
    parser.add_argument('--lease', type=Path)
    args = parser.parse_args()
    if args.refresh_baseline and args.phase != 'baseline':
        parser.error('--refresh-baseline requires the baseline phase')
    assert os.uname().machine == 'aarch64' and os.geteuid() == 0
    assert Path('/proc/1/comm').read_text().strip() == 'systemd' and 'microsoft' not in os.uname().release
    if args.mode == 'native':
        if args.lease is None:
            parser.error('Native capacity requires --lease')
        if args.lease.stat().st_uid != 0 or args.lease.stat().st_mode & 0o022:
            parser.error('Native lease must be root-owned and not writable by other users')
        SESSION = Session.read(json.loads(args.lease.read_text()))
        IDENTITY = instance_identity()
        validate_hardware()
    else:
        if args.lease:
            parser.error('--lease requires --mode native')
        assert socket.gethostname() == PROJECT
    PROOF.mkdir(exist_ok=True)
    def expired(signum, frame):
        raise TimeoutError('Capacity phase deadline exceeded')
    signal.signal(signal.SIGALRM, expired)
    minute = {'swap': 20, 'prepare': 27, 'baseline': 27, 'measure': 51}[args.phase]
    signal.alarm(phase_timeout(minute, 7200))
    try:
        if args.phase == 'swap':
            value = configure_swap()
        elif args.phase == 'prepare':
            value = prepare()
        elif args.phase == 'baseline':
            value = baseline(refresh=args.refresh_baseline)
        else:
            value = measure()
    except (RuntimeError, OSError, ValueError, AssertionError, subprocess.SubprocessError) as error:
        failure = {'phase': args.phase, 'hardware': hardware(), 'error_type': type(error).__name__,
                   'error': str(error)}
        failure_path = PROOF / (args.phase + '-failure.json')
        failure_path.write_text(json.dumps(failure, indent=2))
        try:
            observed = core.inspect(PROJECT)
            failure['containers'] = [
                       {'id': item['Id'], 'service': item['Config']['Labels'].get('com.docker.compose.service'),
                        'state': item['State']['Status'], 'oom': item['State']['OOMKilled'],
                        'restarts': item['RestartCount'], 'health': item['State'].get('Health', {}).get('Status')}
                       for item in observed]
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as inspection_error:
            failure['inspection_error'] = str(inspection_error)
        failure_path.write_text(json.dumps(failure, indent=2))
        raise
    print('CAPACITY_RESULT=' + json.dumps(value), flush=True)


if __name__ == '__main__':
    main()
