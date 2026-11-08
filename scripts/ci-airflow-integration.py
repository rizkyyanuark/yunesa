"""Gate deployment on packaged Airflow readiness and one isolated managed KG run."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from airflow_operations import AIRFLOW_SECRETS, AirflowOperations
from yunesa_airflow.admission import set_gate

SOURCE = Path(__file__).resolve().parents[1]
OWNER = 'io.yunesa.airflow-gate'
SECRET_NAMES = (*AIRFLOW_SECRETS, 'GLOBAL_PASSWORD', 'JWT_SECRET_KEY', 'ADMIN_PASSWORD',
                'GEMINI_API_KEY', 'SILICONFLOW_API_KEY', 'SUPABASE_SERVICE_ROLE_KEY')


def docker(*args: str, timeout: int = 180, data: bytes | None = None) -> bytes:
    result = subprocess.run(['docker', *args], input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'Docker {args[0]} failed with exit {result.returncode}; raw output suppressed')
    return result.stdout


def inside(project: str, airflow: str, worker: str, readiness_deadline: int) -> dict:
    spec = importlib.util.spec_from_file_location('local', SOURCE / 'scripts/airflow-local-check.py')
    local = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(local)
    print('AIRFLOW_GATE_PHASE=prepare', flush=True)
    operation = local.prepare(project, airflow, worker, '384m', '768m', internal_network=True)
    print('AIRFLOW_GATE_PHASE=on', flush=True)
    operation.on(deadline=readiness_deadline)
    path = '/api/v2/dags/unesa_kg_construction'
    local.api(operation, path, 'PATCH', {'is_paused': False})
    run_id = 'manual__ci_gate_' + secrets.token_hex(6)
    local.api(operation, path + '/dagRuns', 'POST', {'dag_run_id': run_id,
        'logical_date': datetime.now(timezone.utc).isoformat(), 'conf': {'mode': 'sample', 'sample_size': 1,
            'use_gliner': False, 'write_neo4j': True, 'write_milvus': False, 'graph_name': project}})
    def completed():
        state = local.api(operation, path + '/dagRuns/' + run_id)['state']
        if state == 'failed':
            raise RuntimeError('Managed KG DAG failed')
        return state == 'success'
    local.wait_until(completed, 600)
    print('AIRFLOW_GATE_PHASE=destination', flush=True)
    cypher = (f"MATCH (n {{graph_name:'{project}'}}) RETURN count(n);\n"
              f"MATCH (n {{graph_name:'{project}'}})-[r]->() RETURN count(r);\n")
    destination = operation.compose('exec', '-T', 'graph', 'mgconsole', '--host', '127.0.0.1',
        '--port', '7687', '--use-ssl=false', data=cypher.encode()).decode()
    counts = list(map(int, re.findall(r'\|\s*(\d+)\s*\|', destination)))
    if counts != [4, 5]:
        raise RuntimeError('Managed DAG destination counts differ from the fixture contract')
    readiness = operation.component('ready')
    print('AIRFLOW_GATE_PHASE=degraded_readiness', flush=True)
    operation.compose('stop', '--timeout', '30', 'airflow-dag-processor')
    def rejects_degraded():
        try:
            operation.component('ready')
            return False
        except local.OperationError:
            return True
    local.wait_until(rejects_degraded, 90)
    operation.compose('up', '-d', '--no-deps', 'airflow-dag-processor')
    def ready_again():
        try:
            operation.component('ready')
            return True
        except local.OperationError:
            return False
    local.wait_until(ready_again, 180)
    print('AIRFLOW_GATE_PHASE=off', flush=True)
    operation.off(deadline=120)
    if operation.workers() or operation.status()['observed_health'] != 'off':
        raise RuntimeError('CI Airflow did not complete OFF')
    return {'project': project, 'run_id': run_id, 'run_state': 'success',
        'destination': {'backend': 'memgraph', 'nodes': counts[0], 'relationships': counts[1]},
        'readiness': readiness, 'off': 'passed', 'workers': [], 'provider_chat': 'not invoked',
        'degraded_readiness_rejected': True,
        'readiness_deadline_seconds': readiness_deadline}


def execute(architecture: str, readiness_deadline: int, report: dict) -> None:
    revision = os.getenv('CI_COMMIT_SHA', '')
    prefix = os.getenv('CI_REGISTRY_IMAGE', '')
    registry = os.getenv('CI_REGISTRY', '')
    if not re.fullmatch(r'[a-f0-9]{40}', revision) or not registry or not prefix.startswith(registry + '/'):
        raise ValueError('Validated CI revision and project registry are required')
    images = {}
    for kind in ('AIRFLOW', 'ETL_WORKER'):
        image = os.getenv('YUNESA_' + kind + '_IMAGE', '')
        name = kind.lower().replace('_', '-')
        if not re.fullmatch(re.escape(prefix + '/' + name + '@sha256:') + r'[a-f0-9]{64}', image):
            raise ValueError(kind + ' must use its built project image digest')
        images[kind] = image
    project = 'yunesa-airflow-it-' + secrets.token_hex(4)
    controller = project + '-controller'
    tooling = project + '-tools:local'
    report.update(project=project, revision=revision, images=images, architecture=architecture,
                  gate_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    volumes = []
    created_controller = False
    try:
        print('AIRFLOW_GATE_PHASE=pull project=' + project, flush=True)
        for image in images.values():
            docker('pull', '--platform', 'linux/' + architecture, image, timeout=600)
            record = json.loads(docker('image', 'inspect', image))[0]
            if record['Architecture'] != architecture or record['Os'] != 'linux':
                raise ValueError('Gate image platform differs from the selected runner architecture')
        with tempfile.TemporaryDirectory(prefix='airflow-gate-') as temporary:
            context = Path(temporary)
            files = ['ci-airflow-integration.py', 'airflow-local-check.py', 'airflow_operations.py']
            (context / 'source/scripts').mkdir(parents=True)
            for name in files:
                shutil.copyfile(SOURCE / 'scripts' / name, context / 'source/scripts' / name)
            shutil.copyfile(SOURCE / 'docker-compose.prod.yml', context / 'source/docker-compose.prod.yml')
            shutil.copytree(SOURCE / 'orchestration', context / 'source/orchestration', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copyfile(shutil.which('docker'), context / 'docker')
            shutil.copyfile('/usr/local/libexec/docker/cli-plugins/docker-compose', context / 'docker-compose')
            (context / 'docker').chmod(0o755)
            (context / 'docker-compose').chmod(0o755)
            (context / 'Dockerfile').write_text(f'''FROM {images['AIRFLOW']}
USER root
COPY docker /usr/local/bin/docker
COPY docker-compose /root/.docker/cli-plugins/docker-compose
COPY source /source
ENTRYPOINT ["python", "/source/scripts/ci-airflow-integration.py"]
''')
            docker('build', '--platform', 'linux/' + architecture, '--network', 'none',
                   '--label', OWNER + '=' + project, '-t', tooling, str(context), timeout=600)
        for suffix in ('root', 'control', 'data'):
            name = project + '-' + suffix
            docker('volume', 'create', '--label', OWNER + '=' + project, name)
            volumes.append(name)
        docker('create', '--name', controller, '--label', OWNER + '=' + project, '--user', '0',
               '--memory', '256m', '--memory-swap', '512m',
               '-v', project + '-root:/opt/yunesa-app',
               '-v', project + '-control:/opt/yunesa-app/shared/airflow/control',
               '-v', '/var/run/docker.sock:/var/run/docker.sock', tooling,
               '--inside', '--project', project, '--airflow-image', images['AIRFLOW'], '--worker-image', images['ETL_WORKER'],
               '--readiness-deadline', str(readiness_deadline))
        created_controller = True
        docker('start', controller)
        print('AIRFLOW_GATE_PHASE=controller project=' + project, flush=True)
        code = docker('wait', controller, timeout=1500).decode().strip()
        with tempfile.TemporaryDirectory(prefix='airflow-gate-result-') as temporary:
            path = Path(temporary) / 'result.json'
            docker('cp', controller + ':/proof/airflow-gate.json', str(path))
            result = json.loads(path.read_text())
        report['gate_result'] = result
        report.update(result)
        if code != '0' or result.get('status') != 'passed':
            raise RuntimeError('Airflow gate rejected release: ' + result.get('error_type', 'unknown failure'))
    finally:
        identifiers = set()
        identifiers.update(docker('ps', '-aq', '--filter', 'label=com.docker.compose.project=' + project).decode().split())
        if created_controller:
            identifiers.add(controller)
        for identifier in identifiers:
            docker('rm', '-fv', identifier)
        for identifier in docker('ps', '-aq', '--filter', 'label=io.yunesa.etl.project=' + project).decode().split():
            docker('rm', '-fv', identifier)
        for kind in ('network', 'volume'):
            for identifier in docker(kind, 'ls', '-q', '--filter', 'label=com.docker.compose.project=' + project).decode().split():
                docker(kind, 'rm', identifier)
        for volume in volumes:
            docker('volume', 'rm', volume)
        if docker('image', 'ls', '-q', tooling).strip():
            docker('image', 'rm', tooling)
        report['cleanup'] = 'passed'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--architecture', choices=('arm64', 'amd64'), default='arm64')
    parser.add_argument('--inside', action='store_true')
    parser.add_argument('--project')
    parser.add_argument('--airflow-image')
    parser.add_argument('--worker-image')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--readiness-deadline', type=int, default=600)
    args = parser.parse_args()
    if not 1 <= args.readiness_deadline <= 600:
        parser.error('CI readiness deadline must be between 1 and 600 seconds')
    def expired(signum, frame):
        raise TimeoutError('Airflow integration gate deadline exceeded')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(1200 if args.inside else 2100)
    report = {'status': 'failed'}
    target = Path('/proof/airflow-gate.json') if args.inside else (args.report or SOURCE / 'artifacts/integration-airflow.json')
    try:
        if args.inside:
            if not args.project or not re.fullmatch(r'yunesa-airflow-it-[a-f0-9]{8}', args.project):
                raise ValueError('Disposable CI project required')
            target.parent.mkdir(exist_ok=True)
            report.update(inside(args.project, args.airflow_image, args.worker_image, args.readiness_deadline))
        else:
            if os.getenv('CI_ENVIRONMENT_NAME') == 'production' or any(os.getenv(key) for key in SECRET_NAMES):
                raise ValueError('Airflow CI must not receive production/application secrets')
            with tempfile.TemporaryDirectory(prefix='airflow-gate-auth-') as directory:
                previous = os.environ.get('DOCKER_CONFIG')
                os.environ['DOCKER_CONFIG'] = directory
                try:
                    registry = os.getenv('CI_REGISTRY', '')
                    username = os.getenv('CI_REGISTRY_USER', '')
                    password = os.getenv('CI_REGISTRY_PASSWORD', '')
                    if not registry or not username or not password:
                        raise ValueError('CI registry credentials required')
                    docker('login', registry, '--username', username, '--password-stdin', data=password.encode())
                    execute(args.architecture, args.readiness_deadline, report)
                finally:
                    if previous is None:
                        os.environ.pop('DOCKER_CONFIG', None)
                    else:
                        os.environ['DOCKER_CONFIG'] = previous
        report['status'] = 'passed'
    except (RuntimeError, OSError, ValueError, AssertionError, subprocess.SubprocessError) as error:
        report['status'] = 'failed'
        report['error_type'] = type(error).__name__
        report['error'] = str(error)
        if args.inside and Path('/opt/yunesa-app/current').exists():
            try:
                operation = AirflowOperations(Path('/opt/yunesa-app'))
                count = operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'airflow',
                    '-tAc', 'SELECT count(*) FROM import_error', timeout=30)
                report['dag_import_errors'] = int(count.strip())
            except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as diagnostic_error:
                report['import_error_probe'] = type(diagnostic_error).__name__
        raise
    finally:
        try:
            if args.inside and Path('/opt/yunesa-app/current').exists():
                operation = AirflowOperations(Path('/opt/yunesa-app'))
                set_gate(operation.control, False, operation.release.name)
        finally:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
