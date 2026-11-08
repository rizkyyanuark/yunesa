"""Run boot assertions inside the independently booted disposable Ubuntu guest."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, '/source/scripts')
from airflow_operations import AirflowOperations, RUNTIME_SERVICES  # noqa: E402
from yunesa_airflow.admission import boot_id  # noqa: E402

ROOT = Path('/opt/yunesa-app')
PROJECT = 'yunesa-kernel-proof'
UNIT = 'yunesa-airflow-reconcile.service'
HOLD = Path('/var/lib/yunesa-kernel-proof/hold')
CHOICES = {'unesa_lecturers_etl': True, 'unesa_papers_etl': True, 'unesa_kg_construction': False}


def run(*args: str, timeout=240) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Guest command failed: ' + ' '.join(args[:2]) + '\n' + result.stderr[-800:])
    return result.stdout


def wait(check, seconds=600):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = check()
        if value:
            return value
        time.sleep(2)
    raise TimeoutError('Guest assertion deadline exceeded')


def cli(action: str) -> dict:
    return json.loads(run(str(ROOT / 'bin/airflow'), action, '--deadline', '600', timeout=1000))


def query(operation: AirflowOperations, statement: str) -> str:
    return operation.compose('exec', '-T', 'postgres', 'psql', '-X', '-U', 'postgres', '-d', 'airflow',
                             '-At', '-v', 'ON_ERROR_STOP=1', data=statement.encode()).decode().strip()


def api(operation: AirflowOperations, path: str, method='GET', body=None,
        base_url='http://127.0.0.1:8080') -> dict:
    def request(path, method='GET', body=None, token=''):
        value = urllib.request.Request(base_url + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(value, timeout=30) as response:
            return json.load(response)
    token = request('/auth/token', 'POST', {'username': 'admin',
                    'password': operation.environment()['AIRFLOW_ADMIN_PASSWORD']})['access_token']
    return request(path, method, body, token)


def unit() -> dict:
    content = run('systemctl', 'show', UNIT, '--no-pager',
                  '--property=Result,ExecMainStatus,NRestarts,ActiveState,SubState,InvocationID,ExecMainStartTimestampMonotonic')
    return dict(line.split('=', 1) for line in content.splitlines())


def settled(operation: AirflowOperations, mode: str) -> dict:
    def finished():
        state = unit()
        if (state.get('Result') == 'success' and state.get('ExecMainStatus') == '0'
                and state.get('ActiveState') == 'inactive' and state.get('InvocationID')
                and int(state.get('ExecMainStartTimestampMonotonic', '0')) > 0):
            return state
        return None
    state = wait(finished, 900)
    status = operation.status()
    assert status['lifecycle']['requested'] == mode
    assert status['observed_health'] == ('healthy' if mode == 'on' else 'off')
    gate = json.loads((operation.control / 'gate.json').read_text())
    assert gate['boot_id'] == boot_id() and gate['open'] == (mode == 'on')
    return {'boot_id': boot_id(), 'kernel': os.uname().release, 'unit': state,
            'requested': mode, 'observed': status['observed_health'], 'gate': gate}


def history(operation: AirflowOperations) -> dict:
    postgres = operation.compose('ps', '-q', 'postgres').decode().strip()
    wait(lambda: json.loads(run('docker', 'inspect', postgres))[0]['State'].get('Health', {}).get('Status') == 'healthy')
    reference = json.loads((ROOT / 'kernel-baseline.json').read_text())
    run_id = reference['run']
    assert query(operation, f"SELECT state FROM dag_run WHERE run_id='{run_id}'") == 'success'
    assert query(operation, "SELECT version_num FROM alembic_version") == reference['schema']
    log_root = Path(run('docker', 'volume', 'inspect', PROJECT + '-logs', '--format', '{{.Mountpoint}}').strip())
    for name, checksum in reference['logs'].items():
        assert hashlib.sha256((log_root / name).read_bytes()).hexdigest() == checksum
    assert not operation.workers()
    return {'run': run_id, 'state': 'success', 'retained_log_files': len(reference['logs']), 'workers': []}


def prepare() -> dict:
    assert not ROOT.exists(), 'Fresh isolated guest root required'
    if not Path('/swapfile').exists():
        run('fallocate', '-l', '2G', '/swapfile')
        Path('/swapfile').chmod(0o600)
        run('mkswap', '/swapfile')
    if '/swapfile' not in Path('/proc/swaps').read_text():
        run('swapon', '/swapfile')
    fstab = Path('/etc/fstab')
    if '/swapfile' not in fstab.read_text():
        with fstab.open('a') as stream:
            stream.write('\n/swapfile none swap sw 0 0\n')
    release = ROOT / 'releases/kernel-local'
    release.mkdir(parents=True)
    ROOT.chmod(0o700)
    for name in ('bin', 'shared/data', 'shared/models', 'shared/saves', 'shared/airflow/control'):
        (ROOT / name).mkdir(parents=True, exist_ok=True)
    shutil.copytree('/source/orchestration', ROOT / 'orchestration')
    shutil.copyfile('/source/scripts/airflow_operations.py', ROOT / 'bin/airflow_operations.py')
    shutil.copyfile('/source/scripts/yunesa-airflow.sh', ROOT / 'bin/airflow')
    (ROOT / 'bin/airflow').chmod(0o755)
    environment = {
        'GLOBAL_PASSWORD': secrets.token_hex(16), 'JWT_SECRET_KEY': secrets.token_hex(32),
        'GEMINI_API_KEY': 'provider-unavailable', 'SILICONFLOW_API_KEY': 'provider-unavailable',
        'YUNESA_API_IMAGE': 'unused:local', 'YUNESA_WEB_IMAGE': 'unused:local', 'YUNESA_MINIO_IMAGE': 'unused:local',
        'YUNESA_AIRFLOW_IMAGE': 'yunesa-airflow:local-check',
        'YUNESA_ETL_WORKER_IMAGE': 'yunesa-etl-worker:lifecycle-check',
        'AIRFLOW_DB_PASSWORD': secrets.token_hex(16), 'AIRFLOW_ADMIN_PASSWORD': secrets.token_hex(16),
        'AIRFLOW_FERNET_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        'AIRFLOW_API_SECRET': secrets.token_hex(32), 'AIRFLOW_JWT_SECRET': secrets.token_hex(32),
        'YUNESA_STATE_ROOT': str(ROOT / 'shared'), 'YUNESA_RELEASE_ID': release.name,
        'YUNESA_COMPOSE_PROJECT': PROJECT, 'DOCKER_NETWORK': PROJECT + '_app-network',
        'YUNESA_DOCKER_GID': str(Path('/var/run/docker.sock').stat().st_gid),
        'YUNESA_AIRFLOW_LOG_VOLUME': PROJECT + '-logs',
    }
    env_file = release / '.env'
    env_file.write_text(''.join(f"{key}='{value}'\n" for key, value in environment.items()))
    env_file.chmod(0o600)
    configuration = run('docker', 'compose', '--project-name', PROJECT, '--env-file', str(env_file),
                        '-f', '/source/docker-compose.prod.yml', '--profile', 'etl', 'config', '--format', 'json')
    rendered = json.loads(configuration)
    rendered['services']['postgres']['image'] = run(
        'docker', 'image', 'inspect', 'postgres:16-alpine', '--format', '{{.Id}}').strip()
    (release / 'docker-compose.prod.yml').write_text(json.dumps(rendered))
    manifest = {'project': PROJECT, 'airflow_version': '3.1.7',
                'airflow_image': environment['YUNESA_AIRFLOW_IMAGE'],
                'etl_worker_image': environment['YUNESA_ETL_WORKER_IMAGE']}
    (release / 'manifest.json').write_text(json.dumps(manifest))
    (ROOT / 'current').symlink_to(release)
    operation = AirflowOperations(ROOT)
    operation.compose('up', '-d', '--wait', 'postgres', timeout=180)
    operation.compose('exec', '-T', 'postgres', 'psql', '-X', '-U', 'postgres', '-d', 'postgres',
                      '-v', 'ON_ERROR_STOP=1', data=b"""
CREATE TABLE lecturers (nip TEXT PRIMARY KEY, nama_dosen TEXT, nama_norm TEXT, nidn TEXT, prodi TEXT, scopus_id TEXT, scholar_id TEXT, sinta_id TEXT);
CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, abstract TEXT, tldr TEXT, keywords TEXT, year INTEGER, journal TEXT, document_type TEXT, authors TEXT, author_ids TEXT, doi TEXT, link TEXT);
INSERT INTO lecturers VALUES ('kernel-author','Kernel Fixture','kernel fixture','','Computer Science','','','');
INSERT INTO papers VALUES ('kernel-paper','Kernel reboot graph fixture','Synthetic academic metadata.','Reboot fixture.','graph',2026,'Kernel Journal','article','Kernel Fixture','kernel-author','','');
""")
    cli('on')
    for dag, paused in CHOICES.items():
        api(operation, '/api/v2/dags/' + dag, 'PATCH', {'is_paused': paused})
    run_id = 'manual__kernel_' + secrets.token_hex(4)
    api(operation, '/api/v2/dags/unesa_kg_construction/dagRuns', 'POST', {
        'dag_run_id': run_id, 'logical_date': datetime.now(timezone.utc).isoformat(),
        'conf': {'mode': 'sample', 'sample_size': 1, 'use_gliner': False,
                 'write_neo4j': False, 'write_milvus': False, 'graph_name': PROJECT}})
    def complete():
        state = query(operation, f"SELECT state FROM dag_run WHERE run_id='{run_id}'")
        if state == 'failed':
            raise RuntimeError('Guest managed DAG failed')
        return state == 'success'
    wait(complete, 900)
    cli('off')
    log_root = Path(run('docker', 'volume', 'inspect', PROJECT + '-logs', '--format', '{{.Mountpoint}}').strip())
    logs = {str(p.relative_to(log_root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in log_root.rglob('*.log') if '/run_id=' + run_id + '/' in str(p)}
    assert logs
    baseline = {'run': run_id, 'logs': logs, 'schema': query(operation, 'SELECT version_num FROM alembic_version')}
    (ROOT / 'kernel-baseline.json').write_text(json.dumps(baseline))
    shutil.copyfile('/source/docker/yunesa-airflow-reconcile.service', '/etc/systemd/system/' + UNIT)
    HOLD.parent.mkdir(parents=True)
    barrier = Path('/usr/local/bin/yunesa-kernel-barrier')
    barrier.write_text('#!/bin/sh\nfor attempt in $(seq 1 600); do\n  [ -e /var/lib/yunesa-kernel-proof/hold ] || exit 0\n  sleep 1\ndone\nexit 1\n')
    barrier.chmod(0o755)
    dropin = Path('/etc/systemd/system/' + UNIT + '.d')
    dropin.mkdir()
    (dropin / 'barrier.conf').write_text('[Service]\nExecStartPre=/usr/local/bin/yunesa-kernel-barrier\n')
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', UNIT)
    return {'boot_id': boot_id(), 'kernel': os.uname().release, 'history': baseline,
            'unit_sha256': hashlib.sha256(Path('/etc/systemd/system/' + UNIT).read_bytes()).hexdigest()}


def action(name: str) -> dict:
    if name == 'prepare':
        return prepare()
    operation = AirflowOperations(ROOT)
    assert operation.project == PROJECT
    if name in ('off-boot', 'final-off-boot'):
        value = settled(operation, 'off')
        value['history'] = history(operation)
        assert not set(RUNTIME_SERVICES).intersection(operation.compose('ps', '--status', 'running', '--services').decode().split())
        return value
    if name == 'arm-on':
        cli('on')
        assert operation.component('status')['paused'] == CHOICES
        HOLD.touch()
        return {'boot_id': boot_id(), 'choices': CHOICES}
    if name == 'blocked-on-boot':
        def ready():
            try:
                operation.component('ready')
                return True
            except RuntimeError:
                return False
        wait(ready, 300)
        gate = json.loads((operation.control / 'gate.json').read_text())
        assert gate['boot_id'] != boot_id() and gate['open'] is True
        assert unit()['SubState'] == 'start-pre'
        status = operation.status()
        assert status['lifecycle']['requested'] == 'on' and status['observed_health'] == 'degraded'
        probe = """import os,sys
sys.path.insert(0,'/opt/airflow/dags')
from etl_operator import AdmissionClient
client=AdmissionClient(base_url='unix://var/run/docker.sock',version='auto')
try:
    client.create_container(image='alpine:3.22',command=['true'],host_config=client.create_host_config(mem_limit='32m'),labels={'io.yunesa.kernel-probe':'blocked'})
except RuntimeError as error:
    assert 'release/boot reconciliation required' in str(error)
    print('REAL_BOOT_GATE_REJECTED')
else:
    raise AssertionError('Worker admitted before boot reconciliation')
"""
        output = operation.compose('exec', '-T', 'airflow-scheduler', 'python', '-c', probe).decode()
        assert 'REAL_BOOT_GATE_REJECTED' in output
        assert not run('docker', 'ps', '-aq', '--filter', 'label=io.yunesa.kernel-probe=blocked').strip()
        return {'boot_id': boot_id(), 'gate_boot_id': gate['boot_id'], 'unit': unit(),
                'desired': 'on', 'observed': 'degraded', 'worker_create': 'rejected', 'worker_count': 0}
    if name == 'release-on':
        HOLD.unlink()
        value = settled(operation, 'on')
        assert operation.component('status')['paused'] == CHOICES
        value['choices'] = CHOICES
        value['history'] = history(operation)
        return value
    if name == 'arm-failure':
        original = operation.release / 'manifest.json'
        shutil.copyfile(original, ROOT / 'manifest-recovery.json')
        manifest = json.loads(original.read_text())
        manifest['etl_worker_image'] = 'invalid-local-fixture:identity'
        original.write_text(json.dumps(manifest))
        return {'boot_id': boot_id(), 'failure': 'deliberate release identity mismatch'}
    if name == 'failed-boot':
        def failed():
            state = unit()
            return state if state.get('ExecMainStatus') == '1' and int(state.get('NRestarts', '0')) >= 1 else None
        state = wait(failed, 180)
        observed = operation.status()
        assert observed['observed_health'] == 'error' and observed['lifecycle']['requested'] == 'on'
        assert not json.loads((operation.control / 'gate.json').read_text())['open']
        return {'boot_id': boot_id(), 'unit': state, 'desired': 'on', 'observed': 'error', 'gate_open': False}
    if name == 'release-failure':
        shutil.copyfile(ROOT / 'manifest-recovery.json', operation.release / 'manifest.json')
        value = settled(operation, 'on')
        assert int(value['unit']['NRestarts']) >= 1
        assert operation.component('status')['paused'] == CHOICES
        value['history'] = history(operation)
        value['recovery'] = 'systemd Restart=on-failure without manual start'
        return value
    if name == 'arm-off':
        cli('off')
        return {'boot_id': boot_id(), 'requested': 'off'}
    raise ValueError('Unsupported guest action')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    args = parser.parse_args()
    assert os.geteuid() == 0 and socket.gethostname() == 'yunesa-kernel-proof'
    assert Path('/proc/1/comm').read_text().strip() == 'systemd'
    assert 'microsoft' not in os.uname().release
    print('KERNEL_RESULT=' + json.dumps(action(args.action)), flush=True)


if __name__ == '__main__':
    main()
