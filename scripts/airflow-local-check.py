"""Bounded lifecycle checks with real Airflow, PostgreSQL and Docker workers."""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone
from pathlib import Path

from airflow_operations import AirflowOperations, OperationError, RUNTIME_SERVICES, lifecycle_lock
from yunesa_airflow.admission import atomic_json, require_open, set_gate

ROOT = Path('/opt/yunesa-app')
SOURCE = Path(__file__).resolve().parents[1]
API_TOKENS: dict[str, tuple[float, str]] = {}


def docker(*arguments: str, timeout=180) -> str:
    result = subprocess.run(['docker', *arguments], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Docker check failed: ' + ' '.join(arguments[:3]))
    return result.stdout


def prepare(project: str, airflow_image='yunesa-airflow:local-check',
            worker_image='yunesa-etl-worker:lifecycle-check', component_memory='512m', component_swap='1g',
            internal_network=False) -> AirflowOperations:
    release = ROOT / 'releases/integration-a'
    release.mkdir(parents=True)
    ROOT.chmod(0o700)
    environment = {
        'GLOBAL_PASSWORD': secrets.token_hex(16), 'JWT_SECRET_KEY': secrets.token_hex(32),
        'GEMINI_API_KEY': 'integration-unavailable', 'SILICONFLOW_API_KEY': 'integration-unavailable',
        'YUNESA_API_IMAGE': 'unused:local', 'YUNESA_WEB_IMAGE': 'unused:local', 'YUNESA_MINIO_IMAGE': 'unused:local',
        'YUNESA_AIRFLOW_IMAGE': airflow_image,
        'YUNESA_ETL_WORKER_IMAGE': worker_image,
        'AIRFLOW_DB_PASSWORD': secrets.token_hex(16), 'AIRFLOW_ADMIN_PASSWORD': secrets.token_hex(16),
        'AIRFLOW_API_SECRET': secrets.token_hex(32), 'AIRFLOW_JWT_SECRET': secrets.token_hex(32),
        'AIRFLOW_FERNET_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        'YUNESA_STATE_ROOT': str(ROOT / 'shared'), 'YUNESA_RELEASE_ID': release.name,
        'YUNESA_COMPOSE_PROJECT': project, 'DOCKER_NETWORK': project + '_app-network',
        'YUNESA_DOCKER_GID': str(Path('/var/run/docker.sock').stat().st_gid),
        'YUNESA_AIRFLOW_LOG_VOLUME': project + '-logs', 'ETL_DATA_VOLUME': project + '-data',
        'AIRFLOW_COMPONENT_MEMORY': component_memory, 'AIRFLOW_COMPONENT_MEMORY_SWAP': component_swap,
    }
    (ROOT / 'bin').mkdir()
    shutil.copyfile(SOURCE / 'scripts/airflow_operations.py', ROOT / 'bin/airflow_operations.py')
    (ROOT / 'bin/airflow_operations.py').chmod(0o700)
    shutil.copytree(SOURCE / 'orchestration/yunesa_airflow', ROOT / 'orchestration/yunesa_airflow')
    for name in ('data', 'saves', 'models', 'airflow/control'):
        (ROOT / 'shared' / name).mkdir(parents=True, exist_ok=True)
    (release / '.env').write_text(''.join(f"{key}='{value}'\n" for key, value in environment.items()))
    (release / '.env').chmod(0o600)
    override = release / 'override.yml'
    override.write_text(f'''services:
  airflow-api-server:
    ports: !reset []
  airflow-scheduler:
    volumes: !override
      - airflow-logs:/opt/airflow/logs
      - integration-control:/opt/airflow/control
      - /var/run/docker.sock:/var/run/docker.sock
volumes:
  integration-control:
    external: true
    name: {project}-control
''')
    rendered = docker('compose', '--project-name', project, '--env-file', str(release / '.env'),
                      '-f', str(SOURCE / 'docker-compose.prod.yml'), '-f', str(override),
                      '--profile', 'etl', 'config', '--format', 'json')
    configuration = json.loads(rendered)
    if internal_network:
        configuration['networks']['app-network']['internal'] = True
    (release / 'docker-compose.prod.yml').write_text(json.dumps(configuration))
    manifest = {'project': project, 'airflow_version': '3.1.7',
                'airflow_image': environment['YUNESA_AIRFLOW_IMAGE'],
                'etl_worker_image': environment['YUNESA_ETL_WORKER_IMAGE']}
    (release / 'manifest.json').write_text(json.dumps(manifest))
    (release / 'manifest.json').chmod(0o600)
    (ROOT / 'current').symlink_to(release)
    operation = AirflowOperations(ROOT)
    operation.compose('up', '-d', '--wait', 'postgres', 'graph', timeout=180)
    docker('network', 'connect', project + '_app-network', project + '-controller')
    operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'postgres',
                      '-v', 'ON_ERROR_STOP=1', data=b"""
CREATE TABLE lecturers (nip TEXT PRIMARY KEY, nama_dosen TEXT, nama_norm TEXT, nidn TEXT, prodi TEXT, scopus_id TEXT, scholar_id TEXT, sinta_id TEXT);
CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, abstract TEXT, tldr TEXT, keywords TEXT, year INTEGER, journal TEXT, document_type TEXT, authors TEXT, author_ids TEXT, doi TEXT, link TEXT);
INSERT INTO lecturers VALUES ('integration-author','Integration Fixture','integration fixture','','Computer Science','','','');
INSERT INTO papers VALUES ('integration-paper','Graph retrieval integration fixture','Synthetic academic metadata for the graph fixture.','Graph retrieval fixture.','graph retrieval',2026,'Integration Journal','article','Integration Fixture','integration-author','','');
""")
    return operation


def cli(action: str, deadline=180):
    return subprocess.run([sys.executable, str(ROOT / 'bin/airflow_operations.py'), action,
                           '--deadline', str(deadline)], capture_output=True, text=True,
                          timeout=max(400, deadline * 3 + 60))


def success(action: str, deadline=600):
    result = cli(action, deadline)
    if result.returncode:
        raise RuntimeError(action + ' failed: ' + result.stderr[-500:])


def request_json(request, retryable=False):
    attempts = 3 if retryable else 1
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError:
            raise
        except (URLError, TimeoutError) as error:
            if attempt + 1 == attempts:
                raise
            print(f'API_NETWORK_RETRY={attempt + 1} error={type(error).__name__}', flush=True)
            time.sleep(2)


def api(operation, path, method='GET', body=None):
    base = 'http://airflow-api-server:8080'
    credentials = {'username': 'admin', 'password': operation.environment()['AIRFLOW_ADMIN_PASSWORD']}
    expires, token = API_TOKENS.get(operation.project, (0, ''))
    if time.monotonic() >= expires:
        response = request_json(urllib.request.Request(base + '/auth/token', data=json.dumps(credentials).encode(),
                                headers={'Content-Type': 'application/json'}), retryable=True)
        token = response['access_token']
        API_TOKENS[operation.project] = (time.monotonic() + 60, token)
    request = urllib.request.Request(base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
    return request_json(request, retryable=method == 'GET')


def wait_until(check, seconds=300):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        result = check()
        if result:
            return result
        time.sleep(2)
    raise TimeoutError('Lifecycle condition deadline exceeded')


def closed(operation, release):
    try:
        require_open(operation.control, release)
    except RuntimeError:
        return
    raise AssertionError('Admission unexpectedly open')


def bootstrap(operation):
    success('on')
    success('off')
    environment_path = operation.release / '.env'
    compose_path = operation.release / 'docker-compose.prod.yml'
    environment_before = environment_path.read_bytes()
    compose_before = compose_path.read_bytes()
    password = operation.environment()['AIRFLOW_DB_PASSWORD']
    fingerprint_sql = (
        "SELECT md5(string_agg(row_to_json(t)::text,',' ORDER BY nip)) FROM lecturers t; "
        "SELECT md5(string_agg(row_to_json(t)::text,',' ORDER BY paper_id)) FROM papers t;"
    )
    before = operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'postgres',
                               '-tAc', fingerprint_sql)
    try:
        replacement = secrets.token_hex(16)
        environment_path.write_bytes(environment_before.replace(password.encode(), replacement.encode()))
        configuration = json.loads(compose_before)
        for service in (*RUNTIME_SERVICES, 'airflow-init'):
            values = configuration['services'][service]['environment']
            values['AIRFLOW__DATABASE__SQL_ALCHEMY_CONN'] = values['AIRFLOW__DATABASE__SQL_ALCHEMY_CONN'].replace(
                password, replacement)
        compose_path.write_text(json.dumps(configuration))
        rejected = cli('on')
        assert rejected.returncode, 'Wrong metadata password was accepted'
        closed(operation, operation.release.name)
        postgres = operation.compose('ps', '-q', 'postgres').decode().strip()
        logs = subprocess.run(['docker', 'logs', '--tail', '100', postgres], capture_output=True,
                              text=True, check=True, timeout=30)
        assert 'password authentication failed for user "airflow"' in logs.stdout + logs.stderr
    finally:
        environment_path.write_bytes(environment_before)
        compose_path.write_bytes(compose_before)
    success('on')
    assert operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'postgres',
                              '-tAc', fingerprint_sql) == before
    role = operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'postgres', '-tAc',
                              "SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname='airflow'").strip()
    assert role == b'f|f|f', role
    admin = operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'airflow', '-tAc',
                               "SELECT count(*) FROM ab_user WHERE username='admin'").strip()
    assert admin == b'1', admin
    assert environment_path.stat().st_mode & 0o077 == 0
    return {'repeat_init': 'passed', 'wrong_metadata_password': 'rejected_by_postgres',
            'role_privileges': 'non_superuser', 'admin_accounts': 1, 'academic_rows': 'unchanged'}


def drain(operation, deployment, check_shared_pool=False):
    success('on')
    dag = '/api/v2/dags/unesa_kg_construction'
    api(operation, dag, 'PATCH', {'is_paused': False})
    core = operation.compose('ps', '-q', 'postgres').decode().strip()
    latch = subprocess.Popen(['docker', 'exec', '-i', core, 'psql', '-U', 'postgres', '-d', 'postgres', '-At'],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        latch.stdin.write("BEGIN;\nLOCK TABLE papers IN ACCESS EXCLUSIVE MODE;\nSELECT 'LOCKED';\n")
        latch.stdin.flush()
        while latch.stdout.readline().strip() != 'LOCKED':
            if latch.poll() is not None:
                raise RuntimeError('PostgreSQL fixture lock failed')
        runs = []
        for _ in range(2):
            run_id = 'manual__drain_' + secrets.token_hex(4)
            api(operation, dag + '/dagRuns', 'POST', {'dag_run_id': run_id,
                'logical_date': datetime.now(timezone.utc).isoformat(), 'conf': {
                    'mode': 'sample', 'sample_size': 1, 'use_gliner': False,
                    'write_neo4j': True, 'write_milvus': False, 'graph_name': operation.project}})
            runs.append(run_id)
        worker = wait_until(lambda: operation.workers())[0]['id']
        def waiting_on_database():
            workers = operation.workers(include_exited=True)
            failed = [row for row in workers if row['status'] == 'exited' and row['exit_code'] != 0]
            if failed:
                raise RuntimeError('ETL worker exited before the SQL lock: ' + json.dumps(failed))
            return operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'postgres',
                       '-tAc', "SELECT count(*) FROM pg_stat_activity WHERE datname='postgres' AND wait_event_type='Lock'").strip() != b'0'
        wait_until(waiting_on_database)
        pool_result = None
        if check_shared_pool:
            other_dag = '/api/v2/dags/unesa_lecturers_etl'
            api(operation, other_dag, 'PATCH', {'is_paused': False})
            other_run = 'manual__pool_' + secrets.token_hex(4)
            api(operation, other_dag + '/dagRuns', 'POST', {'dag_run_id': other_run,
                'logical_date': datetime.now(timezone.utc).isoformat(), 'conf': {'mode': 'sample'}})
            canceled_schedules = set()
            def eligible():
                schedules = operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'airflow',
                    '-tAc', "SELECT run_id FROM dag_run WHERE dag_id='unesa_lecturers_etl' "
                    "AND run_type='scheduled' AND state IN ('queued','running')").decode().splitlines()
                for scheduled in schedules:
                    api(operation, other_dag + '/dagRuns/' + scheduled, 'PATCH', {'state': 'failed'})
                    canceled_schedules.add(scheduled)
                return operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'airflow',
                    '-tAc', "SELECT count(*) FROM task_instance WHERE dag_id='unesa_lecturers_etl' "
                    f"AND run_id='{other_run}' AND state IN ('scheduled','queued')").strip() != b'0'
            wait_until(eligible)
            for _ in range(15):
                assert [row['id'] for row in operation.workers()] == [worker]
                time.sleep(1)
            pool = operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'airflow',
                '-tAc', "SELECT slots FROM slot_pool WHERE pool='yunesa-etl'").strip()
            assert pool == b'1'
            set_gate(operation.control, False, operation.release.name)
            api(operation, other_dag, 'PATCH', {'is_paused': True})
            api(operation, other_dag + '/dagRuns/' + other_run, 'PATCH', {'state': 'failed'})
            assert not any(row['id'] != worker for row in operation.workers())
            pool_result = {'contending_dag': 'unesa_lecturers_etl', 'run': other_run,
                           'eligible': True, 'observations': 15, 'maximum_workers': 1,
                           'canceled_fixture_schedules': sorted(canceled_schedules),
                           'contending_run': 'canceled_before_external_extraction'}
        inspected = json.loads(docker('inspect', worker))[0]
        allocation = inspected['HostConfig']
        assert allocation['Memory'] == 512 * 1024 * 1024
        assert allocation['MemorySwap'] == 1024 * 1024 * 1024
        assert allocation['CpuShares'] == 1024
        assert not any(mount['Destination'].startswith('/app/package') for mount in inspected['Mounts'])
        resources = operation.status()['resources']
        usage = [row for row in resources if row.get('ID', row.get('Container', ''))[:12] == worker[:12]]
        assert len(usage) == 1, 'Status must expose active ETL worker resource usage'
        runtime = {'image': inspected['Image'], 'labels': inspected['Config']['Labels'],
                   'memory': allocation['Memory'], 'memory_swap': allocation['MemorySwap'],
                   'cpu_shares': allocation['CpuShares'], 'usage': usage[0],
                   'mounts': [{'type': mount['Type'], 'destination': mount['Destination']}
                              for mount in inspected['Mounts']]}
        result = cli('off', 1)
        assert result.returncode and 'Drain deadline exceeded' in result.stderr, result.stderr
        assert any(row['id'] == worker and row['status'] == 'running' for row in operation.workers())
        assert operation.state()['requested'] == 'off' and operation.state()['phase'] == 'draining'
        closed(operation, operation.release.name)
        os.environ['YUNESA_AIRFLOW_DRAIN_DEADLINE'] = '1'
        try:
            with lifecycle_lock(ROOT):
                deployment.backup(operation.release)
        except deployment.QuiescenceError:
            pass
        else:
            raise AssertionError('Backup interrupted an active worker')
        finally:
            os.environ.pop('YUNESA_AIRFLOW_DRAIN_DEADLINE', None)
        assert operation.compose('ps', '-q', 'postgres').decode().strip() == core
        assert any(row['id'] == worker for row in operation.workers())
        latch.stdin.write('COMMIT;\n\\q\n')
        latch.stdin.flush()
        latch.communicate(timeout=30)
        success('off', 180)
        assert not operation.workers()
        assert not set(RUNTIME_SERVICES).intersection(operation.compose('ps', '--status', 'running', '--services').decode().split())
        success('off')
        success('on')
        assert api(operation, '/api/v2/dags/unesa_lecturers_etl')['is_paused']
        assert not api(operation, dag)['is_paused']
        for run_id in runs:
            def terminal():
                state = api(operation, dag + '/dagRuns/' + run_id)['state']
                return state if state in ('success', 'failed') else None
            assert wait_until(terminal, 900) == 'success', run_id
        code = (
            "import json; from pathlib import Path; "
            "from yunesa.knowledge.graphs.storage_neo4j import inspect_neo4j_graph; "
            "summary=json.loads(Path('/app/data/kg/output/kg_build_summary.json').read_text()); "
            "stored=inspect_neo4j_graph(uri='bolt://graph:7687',username='',password='',database='memgraph',"
            f"backend='memgraph',graph_name={operation.project!r}); "
            "assert stored['nodes']==summary['validation']['total_nodes']; "
            "assert stored['relationships']==summary['validation']['total_edges']; "
            "assert stored['sample_publications'][0]['title']=='Graph retrieval integration fixture'; "
            "print('DESTINATION='+json.dumps(stored))"
        )
        output = docker('run', '--rm', '--network', operation.project + '_app-network', '--memory', '512m',
                        '-e', 'GEMINI_API_KEY=integration-unavailable', '-e', 'SILICONFLOW_API_KEY=integration-unavailable',
                        '--mount', f'type=volume,src={operation.project}-data,dst=/app/data,readonly',
                        '--entrypoint', 'python', operation.environment()['YUNESA_ETL_WORKER_IMAGE'],
                        '-c', code, timeout=300)
        stored = json.loads(next(line.removeprefix('DESTINATION=') for line in output.splitlines()
                                 if line.startswith('DESTINATION=')))
        assert operation.compose('ps', '-q', 'postgres').decode().strip() == core
        return {'runs': runs, 'timeout': 'nonzero', 'active_worker': 'preserved',
                'queued_work': 'resumed_successfully', 'backup': 'aborted_before_core_stop', 'postgres_id': core,
                'memgraph_destination': stored, 'worker_runtime': runtime, 'shared_pool': pool_result}
    finally:
        if latch.poll() is None:
            latch.communicate('ROLLBACK;\n\\q\n', timeout=30)


def rollback(operation, deployment):
    original = operation.release
    candidate = ROOT / 'releases/integration-b'
    shutil.copytree(original, candidate)
    path = candidate / '.env'
    path.write_text(path.read_text().replace("YUNESA_RELEASE_ID='integration-a'", "YUNESA_RELEASE_ID='integration-b'"))
    config_path = candidate / 'docker-compose.prod.yml'
    config = json.loads(config_path.read_text())
    for service in (*RUNTIME_SERVICES, 'airflow-init'):
        config['services'][service]['environment']['YUNESA_RELEASE_ID'] = candidate.name
    config_path.write_text(json.dumps(config))
    with lifecycle_lock(ROOT):
        state_before = operation.state_path.read_bytes()
        busy = cli('off', 1)
        assert busy.returncode and 'Lifecycle busy' in busy.stderr
        assert operation.state_path.read_bytes() == state_before
    for release in (candidate, original):
        with lifecycle_lock(ROOT):
            AirflowOperations(ROOT).off(preserve_requested=True)
            deployment.restore_airflow(release)
            deployment.set_release_link('current', release)
        current = AirflowOperations(ROOT)
        require_open(current.control, release.name)
        assert current.state()['requested'] == 'on'
        current.component('ready')
    with lifecycle_lock(ROOT):
        operation.off(preserve_requested=True)
        manifest_path = candidate / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest_path.write_text(json.dumps({**manifest, 'etl_worker_image': 'invalid-release-identity'}))
        try:
            deployment.restore_airflow(candidate)
        except deployment.DeployError:
            pass
        else:
            raise AssertionError('Mismatched release admitted')
        closed(operation, candidate.name)
        deployment.restore_airflow(original)
        manifest_path.write_text(json.dumps(manifest))
    success('off')
    with lifecycle_lock(ROOT):
        deployment.restore_airflow(candidate)
        deployment.set_release_link('current', candidate)
    assert AirflowOperations(ROOT).state()['requested'] == 'off'
    assert not set(RUNTIME_SERVICES).intersection(operation.compose('ps', '--status', 'running', '--services').decode().split())
    legacy = ROOT / 'releases/legacy-core'
    shutil.copytree(candidate, legacy)
    (legacy / 'manifest.json').write_text(json.dumps({'project': operation.project}))
    configuration = json.loads((legacy / 'docker-compose.prod.yml').read_text())
    for service in (*RUNTIME_SERVICES, 'airflow-init'):
        configuration['services'].pop(service)
    (legacy / 'docker-compose.prod.yml').write_text(json.dumps(configuration))
    with lifecycle_lock(ROOT):
        deployment.restore_airflow(legacy)
        deployment.set_release_link('current', legacy)
    current = AirflowOperations(ROOT)
    assert current.state()['requested'] == 'off'
    rejected = cli('on')
    assert rejected.returncode and 'Airflow release is unavailable' in rejected.stderr
    closed(current, legacy.name)
    return {'on_forward_and_back': 'passed', 'mismatched_release': 'rejected',
            'prior_release_recovery': 'passed', 'off_release_change': 'stayed_off',
            'legacy_core_release_off': 'preserved', 'legacy_core_activation': 'rejected',
            'scope': 'Airflow release functions; full core deploy/rollback remains separate'}


def reconcile(operation):
    before = (operation.state_path.read_bytes(), (operation.control / 'gate.json').read_bytes())
    observed = cli('status')
    assert observed.returncode == 0
    assert json.loads(observed.stdout)['observed_health'] == 'healthy'
    assert before == (operation.state_path.read_bytes(), (operation.control / 'gate.json').read_bytes())
    gate = json.loads((operation.control / 'gate.json').read_text())
    atomic_json(operation.control / 'gate.json', {**gate, 'boot_id': 'prior-boot-fixture'})
    degraded = json.loads(cli('status').stdout)
    assert degraded['observed_health'] == 'degraded'
    assert degraded['lifecycle']['requested'] == 'on'
    closed(operation, operation.release.name)
    success('reconcile')
    require_open(operation.control, operation.release.name)
    success('off')
    success('reconcile')
    assert operation.state()['requested'] == 'off'
    assert not set(RUNTIME_SERVICES).intersection(operation.compose('ps', '--status', 'running', '--services').decode().split())
    success('on')
    return {'status_read_only': 'passed', 'stale_boot_health': 'degraded',
            'on_reconcile': 'ready_before_open', 'off_reconcile': 'stayed_off',
            'boot_boundary': 'prior boot record fixture; host systemd boot not executed'}


def reopen_fixture(project, deployment):
    operation = AirflowOperations(ROOT, ROOT / 'releases/integration-a', project)
    shutil.copyfile(SOURCE / 'scripts/airflow_operations.py', ROOT / 'bin/airflow_operations.py')
    shutil.copytree(SOURCE / 'orchestration/yunesa_airflow', ROOT / 'orchestration/yunesa_airflow', dirs_exist_ok=True)
    release = operation.release
    rendered = docker('compose', '--project-name', operation.project, '--env-file', str(release / '.env'),
                      '-f', str(SOURCE / 'docker-compose.prod.yml'), '-f', str(release / 'override.yml'),
                      '--profile', 'etl', 'config', '--format', 'json')
    (release / 'docker-compose.prod.yml').write_text(rendered)
    with lifecycle_lock(ROOT):
        deployment.set_release_link('current', release)
        state = {key: value for key, value in operation.state().items() if key != 'error'}
        operation.save({**state, 'requested': 'off', 'phase': 'off'})
    operation.compose('up', '-d', '--wait', 'postgres', 'graph', timeout=180)
    networks = json.loads(docker('inspect', operation.project + '-controller'))[0]['NetworkSettings']['Networks']
    if operation.project + '_app-network' not in networks:
        docker('network', 'connect', operation.project + '_app-network', operation.project + '-controller')
    return operation


def worker_oom(operation):
    success('off')
    path = operation.release / 'docker-compose.prod.yml'
    original = path.read_bytes()
    try:
        configuration = json.loads(original)
        for service in (*RUNTIME_SERVICES, 'airflow-init'):
            environment = configuration['services'][service]['environment']
            environment['ETL_WORKER_MEMORY'] = '32m'
            environment['ETL_WORKER_SWAP_BYTES'] = str(32 * 1024 * 1024)
        path.write_text(json.dumps(configuration))
        success('on')
        dag = '/api/v2/dags/unesa_kg_construction'
        api(operation, dag, 'PATCH', {'is_paused': False})
        run_id = 'manual__oom_' + secrets.token_hex(4)
        api(operation, dag + '/dagRuns', 'POST', {'dag_run_id': run_id,
            'logical_date': datetime.now(timezone.utc).isoformat(), 'conf': {
                'mode': 'sample', 'sample_size': 1, 'use_gliner': False,
                'write_neo4j': False, 'write_milvus': False}})
        def failed_worker():
            identifiers = docker('ps', '-aq', '--filter', 'label=io.yunesa.etl.project=' + operation.project,
                                 '--filter', 'label=io.yunesa.etl.run=' + run_id).split()
            if not identifiers:
                return None
            for identifier in identifiers:
                inspected = json.loads(docker('inspect', identifier))[0]
                assert inspected['HostConfig']['Memory'] == 32 * 1024 * 1024
                assert inspected['HostConfig']['MemorySwap'] == 32 * 1024 * 1024
                if inspected['State']['Status'] != 'exited':
                    continue
                assert inspected['State']['OOMKilled'] and inspected['State']['ExitCode'] == 137
                return {'id': inspected['Id'], 'state': inspected['State']}
            return None
        worker = wait_until(failed_worker)
        def failed_attempt():
            state = operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'airflow',
                '-tAc', f"SELECT state FROM task_instance WHERE run_id='{run_id}' AND task_id='load_data'").decode().strip()
            assert state != 'success', 'OOM attempt was reported successful'
            return state if state in ('failed', 'up_for_retry') else None
        state = wait_until(failed_attempt)
        observed = cli('status')
        assert observed.returncode == 0, observed.stderr
        status = json.loads(observed.stdout)
        assert any(row['id'] == worker['id'][:12] and row['oom'] and row['exit_code'] == 137
                   for row in status['workers'])
        api(operation, dag + '/dagRuns/' + run_id, 'PATCH', {'state': 'failed'})
        success('off')
        return {'run': run_id, 'memory_bytes': 32 * 1024 * 1024, 'swap_total_bytes': 32 * 1024 * 1024,
                'worker': worker, 'attempt_state': state, 'oom_visible_in_status': True,
                'run_cleanup': 'canceled_after_observing_failed_attempt'}
    finally:
        path.write_bytes(original)


def postflight(operation):
    history = operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'airflow', '-tAc',
        "SELECT run_id FROM dag_run WHERE state='success' ORDER BY run_id").decode().splitlines()
    expected = json.loads(Path('/proof/result.json').read_text())['drain']['runs']
    assert set(expected).issubset(history)
    success('on')
    allocations = {}
    for service in RUNTIME_SERVICES:
        identifier = operation.compose('ps', '-q', service).decode().strip()
        inspected = json.loads(docker('inspect', identifier))[0]['HostConfig']
        assert inspected['Memory'] == 512 * 1024 * 1024
        assert inspected['MemorySwap'] == 1024 * 1024 * 1024
        assert inspected['CpuShares'] == 256
        allocations[service] = {key: inspected[key] for key in ('Memory', 'MemorySwap', 'CpuShares')}
    print('CHECK_PHASE=stopped-scheduler-recovery', flush=True)
    operation.compose('stop', '--timeout', '30', 'airflow-scheduler')
    assert 'airflow-scheduler' not in operation.compose('ps', '--status', 'running', '--services').decode().split()
    success('on')
    assert 'airflow-scheduler' in operation.compose('ps', '--status', 'running', '--services').decode().split()
    scheduler = operation.compose('ps', '-q', 'airflow-scheduler')
    success('on')
    assert operation.compose('ps', '-q', 'airflow-scheduler') == scheduler
    print('CHECK_PHASE=isolated-worker-oom', flush=True)
    exhaustion = worker_oom(operation)
    success('on')
    retained = operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'airflow', '-tAc',
        "SELECT run_id FROM dag_run WHERE state='success' ORDER BY run_id").decode().splitlines()
    assert set(expected).issubset(retained)
    success('off')
    return {'stopped_scheduler_on': 'recovered', 'repeated_on': 'same_scheduler',
            'rollback_history_retained': expected, 'component_allocations': allocations,
            'isolated_oom': exhaustion}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--postflight', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    project = args.project
    if not re.fullmatch(r'yunesa-airflow-it-[a-f0-9]{8}', project):
        raise ValueError('A disposable project namespace is required')
    def expired(signum, frame):
        raise TimeoutError('Lifecycle check exceeded 60 minutes')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(3600)
    spec = importlib.util.spec_from_file_location('deployment', SOURCE / 'scripts/deploy-production.py')
    deployment = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deployment)
    deployment.PROJECT = project
    os.environ['YUNESA_AIRFLOW_READINESS_DEADLINE'] = '600'
    result = {}
    operation = None
    try:
        if args.postflight:
            operation = reopen_fixture(project, deployment)
            result = postflight(operation)
            Path('/proof/postflight.json').write_text(json.dumps(result, indent=2))
            print(json.dumps(result), flush=True)
            return
        if args.resume:
            operation = reopen_fixture(project, deployment)
            result = json.loads(Path('/proof/progress.json').read_text())
            success('on')
            previous = json.loads(Path('/proof/initial-http-failure.json').read_text())
            interrupted = {row.split('|')[1] for row in previous['task_states']
                           if row.split('|')[3] == 'running'}
            for run_id in interrupted:
                path = '/api/v2/dags/unesa_kg_construction/dagRuns/' + run_id
                if api(operation, path)['state'] not in ('success', 'failed'):
                    api(operation, path, 'PATCH', {'state': 'failed'})
            result['interrupted_fixture_runs_canceled'] = sorted(interrupted)
            print('CHECK_PHASE=reconcile', flush=True)
            result['reconcile'] = reconcile(operation)
            Path('/proof/progress.json').write_text(json.dumps(result, indent=2))
            print('CHECK_PHASE=rollback', flush=True)
            result['airflow_recovery'] = rollback(operation, deployment)
            Path('/proof/progress.json').write_text(json.dumps(result, indent=2))
            operation = reopen_fixture(project, deployment)
            print('CHECK_PHASE=drain-shared-pool', flush=True)
            result['drain'] = drain(operation, deployment, check_shared_pool=True)
            Path('/proof/result.json').write_text(json.dumps(result, indent=2))
            print(json.dumps(result), flush=True)
            return
        operation = prepare(project)
        print('CHECK_PHASE=bootstrap', flush=True)
        result = {'bootstrap': bootstrap(operation)}
        Path('/proof/progress.json').write_text(json.dumps(result, indent=2))
        print('CHECK_PHASE=drain', flush=True)
        result['drain'] = drain(operation, deployment)
        Path('/proof/progress.json').write_text(json.dumps(result, indent=2))
        print('CHECK_PHASE=reconcile', flush=True)
        result['reconcile'] = reconcile(operation)
        Path('/proof/progress.json').write_text(json.dumps(result, indent=2))
        print('CHECK_PHASE=rollback', flush=True)
        result['airflow_recovery'] = rollback(operation, deployment)
        Path('/proof/result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    except (RuntimeError, AssertionError, OSError, ValueError, subprocess.SubprocessError) as error:
        failure = {'error_type': type(error).__name__, 'error': str(error), 'completed': result}
        if operation is not None:
            try:
                failure['state'] = operation.state()
                failure['workers'] = operation.workers(include_exited=True)
                secrets_to_redact = [value for key, value in operation.environment().items()
                                     if 'PASSWORD' in key or 'SECRET' in key or 'KEY' in key]
                logs = {}
                for service in (*RUNTIME_SERVICES, 'airflow-init'):
                    identifier = operation.compose('ps', '--all', '-q', service).decode().strip()
                    if identifier:
                        output = subprocess.run(['docker', 'logs', '--tail', '80', identifier],
                                                capture_output=True, text=True, timeout=30)
                        content = output.stdout + output.stderr
                        for secret in secrets_to_redact:
                            if secret:
                                content = content.replace(secret, '<redacted>')
                        logs[service] = content
                failure['service_logs'] = logs
                failure['task_states'] = operation.compose(
                    'exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'airflow', '-tAc',
                    'SELECT dag_id,run_id,task_id,state,try_number FROM task_instance ORDER BY run_id,task_id LIMIT 50'
                ).decode().splitlines()
            except (OperationError, OSError, ValueError, subprocess.SubprocessError) as snapshot_error:
                failure['snapshot_error'] = str(snapshot_error)
        failure_path = '/proof/postflight-failure.json' if args.postflight else '/proof/failure.json'
        Path(failure_path).write_text(json.dumps(failure, indent=2))
        raise
    finally:
        identifiers = set()
        for label in ('com.docker.compose.project=' + project, 'io.yunesa.etl.project=' + project):
            identifiers.update(docker('ps', '-aq', '--filter', 'label=' + label).split())
        for identifier in identifiers:
            docker('rm', '-f', identifier)


if __name__ == '__main__':
    main()
