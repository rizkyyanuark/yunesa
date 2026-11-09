"""Rehearse legacy metadata, key and log adoption on disposable local resources."""

from __future__ import annotations

import argparse
import base64
import configparser
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from airflow_operations import OperationError, RUNTIME_SERVICES  # noqa: E402

SOURCE = Path(__file__).resolve().parents[3]
ROOT = Path('/opt/yunesa-app')
PROOF = Path('/proof')
spec = importlib.util.spec_from_file_location('local_check', SOURCE / 'scripts/airflow-local-check.py')
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


def sql(operation, query: str, database='airflow') -> str:
    return operation.compose('exec', '-T', 'postgres', 'psql', '-X', '-U', 'postgres', '-d', database,
                             '-At', '-v', 'ON_ERROR_STOP=1', data=query.encode()).decode().strip()


def execute(container: str, code: str) -> str:
    result = subprocess.run(['docker', 'exec', '-i', container, 'python', '-'], input=code,
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError('Container Python operation failed: ' + result.stderr[-1200:])
    return result.stdout


def call_api(base: str, password: str, path: str, method='GET', body=None):
    credentials = json.dumps({'username': 'admin', 'password': password}).encode()
    token = local.request_json(urllib.request.Request(base + '/auth/token', data=credentials,
                               headers={'Content-Type': 'application/json'}))['access_token']
    return local.request_json(urllib.request.Request(base + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token}))


def log_hashes() -> dict[str, str]:
    return {str(path.relative_to('/legacy-logs')): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in Path('/legacy-logs').rglob('*.log') if 'dag_id=adoption_probe' in str(path)}


def preserved(operation) -> dict:
    queries = {
        'runs': "SELECT dag_id,run_id,state FROM dag_run WHERE dag_id='adoption_probe' ORDER BY run_id",
        'tasks': "SELECT dag_id,run_id,task_id,state,try_number FROM task_instance WHERE dag_id='adoption_probe' ORDER BY run_id,task_id",
        'ciphertext': "SELECT password,extra FROM connection WHERE conn_id='adoption_probe' UNION ALL SELECT val,'' FROM variable WHERE key='adoption_probe'",
        'schema': 'SELECT version_num FROM alembic_version',
        'users': 'SELECT id,username,password FROM ab_user ORDER BY id',
    }
    return {name: hashlib.sha256(sql(operation, query).encode()).hexdigest() for name, query in queries.items()}


def verify_secrets(container: str) -> None:
    output = execute(container, """
from airflow import settings
from airflow.models import Connection, Variable
assert Variable.get('adoption_probe') == 'synthetic-variable-value'
with settings.Session() as session:
    connection = session.query(Connection).filter_by(conn_id='adoption_probe').one()
    assert connection.password == 'synthetic-connection-password'
    assert connection.extra_dejson == {'marker': 'synthetic-extra'}
print('DECRYPTION_PASSED')
""")
    assert 'DECRYPTION_PASSED' in output


def scheduler_inventory(project: str, legacy: str) -> list[str]:
    identifiers = local.docker('ps', '-q', '--filter', 'label=io.yunesa.adoption=' + project,
                               '--filter', 'name=^/' + legacy + '$').split()
    integrated = local.docker('ps', '-q', '--filter', 'label=com.docker.compose.project=' + project,
                              '--filter', 'label=com.docker.compose.service=airflow-scheduler').split()
    return identifiers + integrated


def rehearse(project: str) -> dict:
    operation = local.prepare(project)
    env = operation.environment()
    root_mount = next(m for m in json.loads(local.docker('inspect', project + '-controller'))[0]['Mounts']
                      if m['Destination'] == str(ROOT))
    assert root_mount['Type'] == 'volume'
    mounts = json.loads(local.docker('inspect', project + '-controller'))[0]['Mounts']
    assert any(m['Destination'] == str(ROOT / 'shared/airflow/control')
               and m.get('Name') == project + '-control' for m in mounts)
    legacy = project + '-legacy'
    backup = ROOT / 'backups/legacy-adoption'
    backup.mkdir(parents=True, mode=0o700)
    fixture = ROOT / 'legacy'
    fixture.mkdir(mode=0o700)
    config = configparser.ConfigParser()
    config['core'] = {'fernet_key': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}
    config['api'] = {'secret_key': secrets.token_hex(32)}
    config['api_auth'] = {'jwt_secret': secrets.token_hex(32)}
    with (fixture / 'airflow.cfg').open('w') as stream:
        config.write(stream)
    (fixture / 'airflow.cfg').chmod(0o600)
    (fixture / 'adoption_probe.py').write_text("""from datetime import datetime, timezone
from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator
with DAG('adoption_probe', schedule=None, start_date=datetime(2026, 1, 1, tzinfo=timezone.utc), catchup=False) as dag:
    BashOperator(task_id='write_log', bash_command='printf "ADOPTION_REAL_TASK_LOG\\n"')
""")
    (fixture / 'start.py').write_text("""import os, shutil, signal, subprocess, time
shutil.copyfile('/rehearsal/legacy/airflow.cfg', '/opt/airflow/airflow.cfg')
subprocess.run(['python','-m','yunesa_airflow.component','init'],check=True)
children = [subprocess.Popen(['airflow', *args]) for args in
            (['dag-processor'], ['scheduler'], ['api-server','--workers','1'])]
def stop(signum, frame):
    for child in children:
        child.terminate()
    for child in children:
        child.wait(timeout=45)
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
while all(child.poll() is None for child in children):
    time.sleep(1)
stop(None,None)
""")
    configuration = json.loads((operation.release / 'docker-compose.prod.yml').read_text())
    for service in (*RUNTIME_SERVICES, 'airflow-init'):
        configuration['services'][service]['volumes'].append({
            'type': 'volume', 'source': 'adoption-root', 'target': '/rehearsal', 'read_only': True})
        configuration['services'][service]['environment']['AIRFLOW__CORE__DAGS_FOLDER'] = '/rehearsal/dags'
    configuration['volumes']['adoption-root'] = {'external': True, 'name': root_mount['Name']}
    dags = ROOT / 'dags'
    dags.mkdir()
    for path in (SOURCE / 'orchestration/dags').glob('*.py'):
        shutil.copyfile(path, dags / path.name)
    shutil.copyfile(fixture / 'adoption_probe.py', dags / 'adoption_probe.py')
    # Read access is required for the non-root integrated components.
    ROOT.chmod(0o755)
    (operation.release / 'docker-compose.prod.yml').write_text(json.dumps(configuration))
    sql(operation, 'CREATE DATABASE airflow OWNER postgres;', 'postgres')
    legacy_env = configuration['services']['airflow-api-server']['environment'].copy()
    for key in ('AIRFLOW__CORE__FERNET_KEY', 'AIRFLOW__API__SECRET_KEY', 'AIRFLOW__API_AUTH__JWT_SECRET'):
        legacy_env.pop(key, None)
    legacy_env.update({
        'AIRFLOW__DATABASE__SQL_ALCHEMY_CONN':
            f"postgresql+psycopg2://postgres:{env['GLOBAL_PASSWORD']}@postgres:5432/airflow",
        'AIRFLOW_ADMIN_PASSWORD': env['AIRFLOW_ADMIN_PASSWORD'],
        'AIRFLOW__CORE__EXECUTION_API_SERVER_URL': f'http://{legacy}:8080/execution/',
        'AIRFLOW__CORE__PARALLELISM': '2',
        'PYTHONPATH': '/opt/airflow:/home/airflow/.local/lib/python3.12/site-packages',
    })
    arguments = ['run', '-d', '--name', legacy, '--label', 'io.yunesa.adoption=' + project,
                 '--label', 'com.docker.compose.project=yunesa-airflow',
                 '--network', project + '_app-network', '--user', '0:0',
                 '--memory', '640m', '--memory-swap', '1536m',
                 '-v', root_mount['Name'] + ':/rehearsal:ro', '-v', project + '-logs:/opt/airflow/logs']
    for key, value in legacy_env.items():
        arguments.extend(['-e', key + '=' + str(value)])
    arguments.extend(['--entrypoint', 'python', env['YUNESA_AIRFLOW_IMAGE'], '/rehearsal/legacy/start.py'])
    print('ADOPTION_PHASE=legacy-start', flush=True)
    local.docker(*arguments)
    base = f'http://{legacy}:8080'
    def ready():
        state = json.loads(local.docker('inspect', legacy))[0]['State']
        if state['Status'] != 'running':
            raise RuntimeError('Legacy fixture exited before readiness')
        try:
            result = call_api(base, env['AIRFLOW_ADMIN_PASSWORD'], '/api/v2/dags/adoption_probe')
            return result['dag_id'] == 'adoption_probe'
        except (OSError, ValueError):
            return False
    local.wait_until(ready, seconds=600)
    execute(legacy, """
from airflow import settings
from airflow.models import Connection, Variable
Variable.set('adoption_probe','synthetic-variable-value')
with settings.Session() as session:
    session.add(Connection(conn_id='adoption_probe',conn_type='http',password='synthetic-connection-password',extra={'marker':'synthetic-extra'}))
    session.commit()
""")
    call_api(base, env['AIRFLOW_ADMIN_PASSWORD'], '/api/v2/dags/adoption_probe', 'PATCH', {'is_paused': False})
    run_id = 'manual__adoption_' + secrets.token_hex(4)
    call_api(base, env['AIRFLOW_ADMIN_PASSWORD'], '/api/v2/dags/adoption_probe/dagRuns', 'POST',
             {'dag_run_id': run_id, 'logical_date': datetime.now(timezone.utc).isoformat(), 'conf': {}})
    def completed():
        state = call_api(base, env['AIRFLOW_ADMIN_PASSWORD'], '/api/v2/dags/adoption_probe/dagRuns/' + run_id)['state']
        if state == 'failed':
            raise RuntimeError('Legacy probe task failed')
        return state == 'success'
    local.wait_until(completed, seconds=600)
    verify_secrets(legacy)
    assert sql(operation, "SELECT is_encrypted,is_extra_encrypted FROM connection WHERE conn_id='adoption_probe'") == 't|t'
    assert sql(operation, "SELECT is_encrypted FROM variable WHERE key='adoption_probe'") == 't'
    assert 'WRONG_KEY_REJECTED' in execute(legacy, """
from airflow import settings
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text
with settings.Session() as session:
    ciphertext = session.execute(text("SELECT val FROM variable WHERE key='adoption_probe'")).scalar_one()
try:
    Fernet(Fernet.generate_key()).decrypt(ciphertext.encode())
except InvalidToken:
    print('WRONG_KEY_REJECTED')
else:
    raise AssertionError('Unexpected decryption with a different key')
""")
    assert len(scheduler_inventory(project, legacy)) == 1
    rejected = local.cli('on')
    assert rejected.returncode and 'Separate Airflow installation is still running' in rejected.stderr
    assert len(scheduler_inventory(project, legacy)) == 1
    call_api(base, env['AIRFLOW_ADMIN_PASSWORD'], '/api/v2/dags/adoption_probe', 'PATCH', {'is_paused': True})
    assert sql(operation, "SELECT count(*) FROM task_instance WHERE state='running'") == '0'
    local.docker('stop', '--time', '60', legacy)
    assert scheduler_inventory(project, legacy) == []
    before = preserved(operation)
    counts = sql(operation, "SELECT 'dag_run',count(*) FROM dag_run UNION ALL SELECT 'task_instance',count(*) FROM task_instance UNION ALL SELECT 'tables',count(*) FROM pg_tables WHERE schemaname='public'")
    hashes = log_hashes()
    prior_logs = {str(path.relative_to('/legacy-logs')): path.read_bytes()
                  for path in Path('/legacy-logs').rglob('*.log')}
    assert hashes
    assert any(b'ADOPTION_REAL_TASK_LOG' in p.read_bytes() for p in Path('/legacy-logs').rglob('*.log'))
    with (backup / 'airflow.dump').open('wb') as stream:
        operation.compose('exec', '-T', 'postgres', 'pg_dump', '-U', 'postgres', '-Fc', 'airflow', output_file=stream)
    local.docker('cp', legacy + ':/opt/airflow/airflow.cfg', str(backup / 'airflow.cfg'))
    (backup / 'airflow.cfg').chmod(0o600)
    with tarfile.open(backup / 'logs.tar.gz', 'w:gz') as archive:
        archive.add('/legacy-logs', arcname='logs')
    backup_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in backup.iterdir() if p.is_file()}
    assert hashlib.sha256((backup / 'airflow.cfg').read_bytes()).digest() == hashlib.sha256((fixture / 'airflow.cfg').read_bytes()).digest()
    owners_before = sql(operation, "SELECT pg_get_userbyid(relowner),relkind,count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND relkind IN ('r','p','S') GROUP BY relowner,relkind ORDER BY relkind")
    print('ADOPTION_PHASE=ownership-and-key-adoption', flush=True)
    try:
        operation.provision_database()
    except OperationError as error:
        assert 'offline adoption' in str(error)
    else:
        raise AssertionError('Legacy database ownership was silently accepted')
    sql(operation, r"""BEGIN;
ALTER DATABASE airflow OWNER TO airflow;
ALTER SCHEMA public OWNER TO airflow;
SELECT format('ALTER TABLE %I.%I OWNER TO airflow',n.nspname,c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind IN ('r','p')\gexec
SELECT format('ALTER SEQUENCE %I.%I OWNER TO airflow',n.nspname,c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind='S'\gexec
COMMIT;
""")
    assert preserved(operation) == before
    assert sql(operation, "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','S') AND pg_get_userbyid(relowner)<>'airflow'") == '0'
    assert sql(operation, "SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname='airflow'", 'postgres') == 'f|f|f'
    recovered = configparser.ConfigParser()
    recovered.read(backup / 'airflow.cfg')
    recovered_keys = {
        'AIRFLOW_FERNET_KEY': recovered['core']['fernet_key'],
        'AIRFLOW_API_SECRET': recovered['api']['secret_key'],
        'AIRFLOW_JWT_SECRET': recovered['api_auth']['jwt_secret'],
    }
    names = {'AIRFLOW_FERNET_KEY': 'AIRFLOW__CORE__FERNET_KEY',
             'AIRFLOW_API_SECRET': 'AIRFLOW__API__SECRET_KEY',
             'AIRFLOW_JWT_SECRET': 'AIRFLOW__API_AUTH__JWT_SECRET'}
    for key, value in recovered_keys.items():
        assert value != env[key]
        env[key] = value
        for service in (*RUNTIME_SERVICES, 'airflow-init'):
            configuration['services'][service]['environment'][names[key]] = value
    (operation.release / '.env').write_text(''.join(f"{key}='{value}'\n" for key, value in env.items()))
    (operation.release / 'docker-compose.prod.yml').write_text(json.dumps(configuration))
    for path in Path('/legacy-logs').rglob('*'):
        os.chown(path, 50000, 0)
    os.chown('/legacy-logs', 50000, 0)
    local.success('on')
    assert len(scheduler_inventory(project, legacy)) == 1
    assert preserved(operation) == before
    processor = operation.compose('ps', '-q', 'airflow-dag-processor').decode().strip()
    verify_secrets(processor)
    history = local.api(operation, '/api/v2/dags/adoption_probe/dagRuns/' + run_id)
    assert history['state'] == 'success'
    assert all(log_hashes().get(name) == value for name, value in hashes.items())
    assert all((Path('/legacy-logs') / name).read_bytes().startswith(content)
               for name, content in prior_logs.items())
    assert operation.state()['requested'] == 'on'
    integrated = {'metadata_fingerprints': before, 'metadata_counts': counts, 'historical_log_files': hashes,
                  'retained_log_prefixes': len(prior_logs), 'authenticated_history_read': 'passed',
                  'scheduler_count': 1, 'requested': 'on', 'decryption': 'passed'}
    (PROOF / 'adopted.json').write_text(json.dumps(integrated, indent=2))
    print('ADOPTION_PHASE=rollback-restore', flush=True)
    local.success('off')
    assert scheduler_inventory(project, legacy) == []
    for name, checksum in backup_hashes.items():
        assert hashlib.sha256((backup / name).read_bytes()).hexdigest() == checksum
    sql(operation, 'DROP DATABASE airflow; CREATE DATABASE airflow OWNER postgres;', 'postgres')
    with (backup / 'airflow.dump').open('rb') as stream:
        operation.compose('exec', '-T', 'postgres', 'pg_restore', '-U', 'postgres', '-d', 'airflow',
                          '--exit-on-error', input_file=stream)
    assert preserved(operation) == before
    assert sql(operation, "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='airflow'", 'postgres') == 'postgres'
    assert sql(operation, "SELECT pg_get_userbyid(relowner),relkind,count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND relkind IN ('r','p','S') GROUP BY relowner,relkind ORDER BY relkind") == owners_before
    with tarfile.open(backup / 'logs.tar.gz', 'r:gz') as archive:
        archive.extractall(backup / 'restored', filter='data')
    for name, content in prior_logs.items():
        assert (backup / 'restored/logs' / name).read_bytes() == content
    sample = Path('/legacy-logs') / next(iter(hashes))
    assert sample.resolve().is_relative_to(Path('/legacy-logs').resolve())
    sample.unlink()
    assert not sample.exists()
    shutil.copytree(backup / 'restored/logs', '/legacy-logs', dirs_exist_ok=True)
    assert all(log_hashes().get(name) == checksum for name, checksum in hashes.items())
    local.docker('start', legacy)
    local.wait_until(ready, seconds=600)
    verify_secrets(legacy)
    assert len(scheduler_inventory(project, legacy)) == 1
    assert preserved(operation) == before
    assert all(log_hashes().get(name) == checksum for name, checksum in hashes.items())
    assert sql(operation, 'SELECT count(*) FROM lecturers', 'postgres') == '1'
    assert sql(operation, 'SELECT count(*) FROM papers', 'postgres') == '1'
    return {'project': project, 'run_id': run_id, 'source': 'synthetic Airflow 3.1.7 legacy topology',
            'scope': 'native AMD64 local adoption; production backup and ARM64 workload not exercised',
            'legacy_guard': 'rejected_before_integrated_start', 'owners_before_and_after_rollback': owners_before,
            'adopted': integrated, 'rollback': 'metadata/key/logs/admin authentication restored',
            'wrong_fernet_key': 'rejected', 'log_recovery': 'deleted sample restored from checked archive',
            'backup_sha256': backup_hashes, 'core_academic_rows': 'unchanged',
            'scheduler_counts': [1, 0, 1, 0, 1]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'yunesa-airflow-it-[a-f0-9]{8}', args.project):
        raise ValueError('A disposable project namespace is required')
    if local.docker('ps', '-q', '--filter', 'label=com.docker.compose.project=yunesa-airflow').strip():
        raise RuntimeError('An existing legacy installation must not be touched')
    def expired(signum, frame):
        raise TimeoutError('Adoption rehearsal exceeded 40 minutes')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(2400)
    try:
        result = rehearse(args.project)
        (PROOF / 'result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    finally:
        for label in ('com.docker.compose.project=' + args.project, 'io.yunesa.adoption=' + args.project):
            for identifier in local.docker('ps', '-aq', '--filter', 'label=' + label).split():
                name = json.loads(local.docker('inspect', identifier))[0]['Name']
                if name == '/' + args.project + '-controller':
                    continue
                local.docker('rm', '-f', identifier)


if __name__ == '__main__':
    main()
