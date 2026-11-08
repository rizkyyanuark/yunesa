"""Rehearse Airflow resource and release operations with eight isolated core services."""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from airflow_operations import (
    AIRFLOW_SECRETS, AirflowOperations, configuration_digest, deployment_architecture, require_open,
)

SOURCE = Path(__file__).resolve().parents[1]
ROOT = Path('/opt/yunesa-app')
SERVICES = ('postgres', 'redis', 'graph', 'vector', 'minio', 'api', 'worker', 'web')


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


local = module('local_checks', SOURCE / 'scripts/airflow-local-check.py')
probe = module('readiness', SOURCE / 'scripts/deployment-readiness.py')


def command(*arguments: str, timeout: int = 600, data: bytes | None = None) -> bytes:
    completed = subprocess.run(arguments, input=data, capture_output=True, timeout=timeout)
    if completed.returncode:
        raise RuntimeError('Command failed ' + ' '.join(arguments[:3]))
    return completed.stdout


def observe(arguments: list[str], identifiers: list[str]) -> bytes:
    completed = subprocess.run(arguments, capture_output=True, timeout=60)
    if completed.returncode and completed.stderr.strip() == b'EOF' and arguments[1] == 'stats':
        snapshot = observe(['docker', 'inspect', *identifiers], identifiers)
        alive = [item['Id'] for item in json.loads(snapshot) if item['State']['Running']]
        if set(alive) != set(identifiers):
            print('OBSERVATION_RETRY=container-removed-or-stopped', flush=True)
            if not alive:
                return b''
            completed = subprocess.run([*arguments[:-len(identifiers)], *alive],
                                       capture_output=True, timeout=60)
    if completed.returncode:
        expected = {prefix + identifier for identifier in identifiers for prefix in (
            'error: no such object: ', 'error: no such container: ',
            'error response from daemon: no such container: ',
        )}
        errors = set(completed.stderr.decode().strip().casefold().splitlines())
        if not errors or not errors.issubset(expected):
            raise RuntimeError('Docker observation failed ' + ' '.join(arguments[:3])
                               + ' ' + completed.stderr.decode()[-500:])
    return completed.stdout


def inspect(project: str) -> list[dict]:
    identifiers = command('docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=' + project).split()
    workers = command('docker', 'ps', '-aq', '--filter', 'label=io.yunesa.etl.project=' + project).split()
    identifiers = list(dict.fromkeys(identifiers + workers))
    if not identifiers:
        return []
    identifiers = [item.decode() for item in identifiers]
    return json.loads(observe(['docker', 'inspect', *identifiers], identifiers))


def identities(project: str) -> dict[str, str]:
    return {item['Config']['Labels']['com.docker.compose.service']: item['Id']
            for item in inspect(project) if item['Config']['Labels'].get('com.docker.compose.service') in SERVICES}


def host_memory() -> dict[str, int]:
    rows = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    return {name: int(rows[name].split()[0]) * 1024
            for name in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree')}


def emulated_healthchecks(configuration: dict, architecture: str) -> None:
    if architecture != 'arm64':
        return
    services = configuration['services']
    for name in ('redis', 'graph'):
        services[name]['platform'] = 'linux/amd64'
    services['worker']['healthcheck'].update(timeout='180s', start_period='120s')
    services['minio'].update(mem_limit='384m', memswap_limit='1g')
    services['minio']['healthcheck'].update(timeout='20s', start_period='120s', retries=20)
    for name in ('airflow-api-server', 'airflow-dag-processor', 'airflow-scheduler'):
        health = configuration['services'][name]['healthcheck']
        health['start_period'] = '600s'
        health['retries'] = 10
        if name != 'airflow-api-server':
            health['timeout'] = '120s'


class Sampling:
    def __init__(self, operation: AirflowOperations, base_url: str = 'http://web'):
        self.operation = operation
        self.base_url = base_url
        self.stop = threading.Event()
        self.samples: list[dict] = []
        self.traffic: list[dict] = []
        self.errors: list[str] = []
        self.threads: list[threading.Thread] = []

    def run(self, work) -> None:
        try:
            while not self.stop.is_set():
                work()
                self.stop.wait(5)
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError, probe.ReadinessError) as error:
            self.errors.append(type(error).__name__ + ' ' + str(error))
            self.stop.set()

    def sample(self) -> None:
        containers = inspect(self.operation.project)
        running = [item for item in containers if item['State']['Running']]
        identifiers = [item['Id'] for item in running]
        stats = observe(['docker', 'stats', '--no-stream', '--format', '{{json .}}', *identifiers],
                        identifiers).decode().splitlines()
        kernels = {}
        kernel_errors = {}
        for item in running:
            measured = subprocess.run(['docker', 'exec', item['Id'], 'sh', '-c',
                'cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.peak /sys/fs/cgroup/memory.swap.current'],
                capture_output=True, text=True, timeout=20)
            values = measured.stdout.split()
            if measured.returncode == 0 and len(values) == 3:
                kernels[item['Id']] = dict(zip(('current', 'peak_so_far', 'swap_current'), map(int, values), strict=True))
            else:
                kernel_errors[item['Id']] = {'exit_code': measured.returncode}
        self.samples.append({'at': datetime.now(UTC).isoformat(), 'host': host_memory(),
            'stats': [json.loads(row) for row in stats], 'cgroup_v2': kernels, 'cgroup_errors': kernel_errors,
            'states': [{'id': item['Id'], 'service': item['Config']['Labels'].get('com.docker.compose.service'),
                        'worker': item['Config']['Labels'].get('io.yunesa.etl.task'),
                        'oom': item['State']['OOMKilled'], 'restarts': item['RestartCount']}
                       for item in containers]})
        Path('/proof/core-resource-samples.json').write_text(json.dumps(self.samples, indent=2))

    def request(self) -> None:
        self.traffic.append({'at': datetime.now(UTC).isoformat(),
            'result': probe.http_probe(self.base_url, ROOT / 'shared/admin-credentials.json', False, False)})
        Path('/proof/core-traffic.json').write_text(json.dumps(self.traffic, indent=2))

    def __enter__(self):
        for work in (self.sample, self.request):
            thread = threading.Thread(target=self.run, args=(work,), daemon=True)
            thread.start()
            self.threads.append(thread)
        return self

    def __exit__(self, error_type, error, traceback):
        self.stop.set()
        for thread in self.threads:
            thread.join(120)
            if thread.is_alive():
                raise RuntimeError('Bounded core sampling thread did not stop')
        if self.errors:
            message = 'Core sampling failed ' + '; '.join(self.errors)
            if error is None:
                raise RuntimeError(message)
            error.add_note(message)
        if error_type is None:
            assert self.samples and self.traffic


def prepare(project: str, registry: str, images: dict[str, str], revision: str, architecture: str,
            log_volume: str | None = None):
    ROOT.chmod(0o700)
    assert not (ROOT / 'current').exists(), 'Fresh release fixture root required'
    interpreter = Path('/usr/bin/python3')
    if not interpreter.exists():
        interpreter.symlink_to(sys.executable)
    volume_args = ['--airflow-log-volume', log_volume] if log_volume else []
    command(sys.executable, str(SOURCE / 'scripts/install-deployment-host.py'), '--source', str(SOURCE),
            '--registry', registry, '--image-prefix', registry + '/yunesa-integration', '--project', project,
            '--local-base-url', 'http://web', '--public-base-url', 'http://web', '--architecture', architecture,
            *volume_args)
    payload = {'CI_COMMIT_SHA': revision, 'CI_REGISTRY': registry,
               'CI_REGISTRY_IMAGE': registry + '/yunesa-integration',
               'CI_REGISTRY_USER': 'integration', 'CI_REGISTRY_PASSWORD': 'local-only',
               'GLOBAL_PASSWORD': secrets.token_hex(16), 'JWT_SECRET_KEY': secrets.token_hex(32),
               'ADMIN_PASSWORD': 'Ci!Aa1-' + secrets.token_urlsafe(24),
               'GEMINI_API_KEY': 'unavailable-gemini', 'SILICONFLOW_API_KEY': 'unavailable-siliconflow',
               **{name: secrets.token_hex(32) for name in AIRFLOW_SECRETS}, **images}
    payload['AIRFLOW_FERNET_KEY'] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    prior = sorted((ROOT / 'releases').glob('*/manifest.json'))
    if prior:
        previous = AirflowOperations(ROOT, prior[-1].parent)
        assert previous.project == project, 'Cannot reuse another fixture project'
        environment = previous.environment()
        for name in (*AIRFLOW_SECRETS, 'GLOBAL_PASSWORD', 'JWT_SECRET_KEY',
                     'GEMINI_API_KEY', 'SILICONFLOW_API_KEY'):
            payload[name] = environment[name]
        payload['ADMIN_PASSWORD'] = json.loads((ROOT / 'shared/admin-credentials.json').read_text())['password']
    seed = {**payload, 'YUNESA_STATE_ROOT': str(ROOT / 'shared'), 'YUNESA_RELEASE_ID': 'fixture-template-only',
            'YUNESA_COMPOSE_PROJECT': project, 'DOCKER_NETWORK': project + '_app-network',
            'YUNESA_DOCKER_GID': str(Path('/var/run/docker.sock').stat().st_gid),
            'YUNESA_AIRFLOW_LOG_VOLUME': log_volume or project + '_airflow-logs',
            'ETL_DATA_VOLUME': project + '_ci-data', 'YUNESA_CI_RUN_ID': project,
            'MINIO_PUBLIC_BASE_URL': 'http://web'}
    override = ROOT / 'config/isolation.yml'
    override.write_text(f'''services:
  airflow-api-server:
    ports: !reset []
  airflow-scheduler:
    volumes: !override
      - airflow-logs:/opt/airflow/logs
      - integration-control:/opt/airflow/control
      - /var/run/docker.sock:/var/run/docker.sock
networks:
  app-network: !override
    external: true
    name: {project}_app-network
volumes:
  integration-control:
    external: true
    name: {project}-control
''')
    with tempfile.NamedTemporaryFile(mode='w') as environment:
        environment.write(''.join(f"{name}='{value}'\n" for name, value in seed.items()))
        environment.flush()
        rendered = command('docker', 'compose', '--project-name', project, '--env-file', environment.name,
            '-f', str(SOURCE / 'docker-compose.prod.yml'), '-f', str(SOURCE / 'docker-compose.ci.yml'),
            '-f', str(override), '--profile', 'etl', 'config', '--format', 'json')
    substitutions = {name: seed[name] for name in (*AIRFLOW_SECRETS, 'GLOBAL_PASSWORD', 'JWT_SECRET_KEY',
        'GEMINI_API_KEY', 'SILICONFLOW_API_KEY', *images, 'YUNESA_RELEASE_ID')}
    def symbolic(value):
        if isinstance(value, dict):
            return {key: symbolic(item) for key, item in value.items()}
        if isinstance(value, list):
            return [symbolic(item) for item in value]
        if isinstance(value, str):
            for name, actual in substitutions.items():
                value = value.replace(actual, '${' + name + '}')
        return value
    configuration = symbolic(json.loads(rendered))
    configuration['volumes']['airflow-logs']['name'] = '${YUNESA_AIRFLOW_LOG_VOLUME}'
    emulated_healthchecks(configuration, architecture)
    (ROOT / 'config/docker-compose.prod.yml').write_text(json.dumps(configuration))
    installed = json.loads((ROOT / 'config/registry.json').read_text())
    installed['config_sha256'] = configuration_digest(ROOT, installed=True)
    (ROOT / 'config/registry.json').write_text(json.dumps(installed))
    payload['YUNESA_CONFIG_SHA256'] = installed['config_sha256']
    deployment = module('deployment', ROOT / 'bin/deploy-production.py')
    deployment.PROJECT = project
    deployment.ARCHITECTURE = architecture
    deployment.validate_request(payload, 'deploy', installed)
    for image in images.values():
        command('docker', 'pull', '--platform', 'linux/' + architecture, image)
        deployment.image_platform(image)
    deployment.secure_write(ROOT / 'shared/deployment-owner.json', json.dumps({'project': project}))
    deployment.secure_write(ROOT / 'shared/admin-credentials.json',
                            json.dumps({'username': 'integration_owner', 'password': payload['ADMIN_PASSWORD']}))
    first = deployment.create_release(payload)
    configuration = json.loads(deployment.compose(first, 'config', '--format', 'json',
                                                  label='Read isolated dependency references'))
    for service in ('postgres', 'redis', 'graph', 'vector'):
        dependency = configuration['services'][service]
        command('docker', 'pull', '--platform', dependency.get('platform', 'linux/' + architecture), dependency['image'])
    deployment.compose(first, 'up', '-d', '--no-build', '--wait', '--wait-timeout', '900', *SERVICES,
                       label='Start isolated eight-service baseline', timeout=1200)
    baseline = deployment.readiness(first, providers=False)
    deployment.set_release_link('current', first)
    time.sleep(1)
    second = deployment.create_release(payload)
    deployment.compose(second, 'up', '-d', '--no-build', '--wait', '--wait-timeout', '900', *SERVICES,
                       label='Start isolated second core release', timeout=1200)
    deployment.set_release_link('previous', first)
    deployment.set_release_link('current', second)
    operation = AirflowOperations(ROOT)
    assert set(identities(project)) == set(SERVICES)
    operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'postgres',
                      '-v', 'ON_ERROR_STOP=1', data=b"""
CREATE TABLE IF NOT EXISTS lecturers (nip TEXT PRIMARY KEY, nama_dosen TEXT, nama_norm TEXT, nidn TEXT, prodi TEXT, scopus_id TEXT, scholar_id TEXT, sinta_id TEXT);
CREATE TABLE IF NOT EXISTS papers (paper_id TEXT PRIMARY KEY, title TEXT, abstract TEXT, tldr TEXT, keywords TEXT, year INTEGER, journal TEXT, document_type TEXT, authors TEXT, author_ids TEXT, doi TEXT, link TEXT);
INSERT INTO lecturers VALUES ('integration-author','Integration Fixture','integration fixture','','Computer Science','','','');
INSERT INTO papers VALUES ('integration-paper','Graph retrieval integration fixture','Synthetic academic metadata.','Graph retrieval fixture.','graph retrieval',2026,'Integration Journal','article','Integration Fixture','integration-author','','');
""")
    return operation, payload, baseline


def wrapper(operation: str, payload: dict, deadline: int = 600) -> subprocess.Popen:
    environment = {**os.environ, 'YUNESA_AIRFLOW_DRAIN_DEADLINE': str(deadline)}
    with tempfile.TemporaryFile() as request:
        request.write(json.dumps(payload).encode())
        request.seek(0)
        return subprocess.Popen(['bash', str(ROOT / 'bin/deploy'), operation], stdin=request,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)


def finished(process: subprocess.Popen, expected: int = 0) -> dict:
    output, error = process.communicate(timeout=1800)
    if process.returncode != expected:
        raise RuntimeError('Wrapper exit ' + str(process.returncode) + ' ' + error.decode()[-600:])
    return {'exit_code': process.returncode, 'stdout': output.decode(), 'stderr': error.decode()}


def measure(operation: AirflowOperations) -> dict:
    before = identities(operation.project)
    dag = '/api/v2/dags/unesa_kg_construction'
    run_id = 'manual__core_' + secrets.token_hex(4)
    with Sampling(operation) as sampling:
        local.success('on', 900)
        local.api(operation, dag, 'PATCH', {'is_paused': False})
        local.api(operation, dag + '/dagRuns', 'POST', {'dag_run_id': run_id,
            'logical_date': datetime.now(UTC).isoformat(), 'conf': {'mode': 'sample', 'sample_size': 1,
            'use_gliner': False, 'write_neo4j': True, 'write_milvus': False, 'graph_name': operation.project}})
        def terminal():
            state = local.api(operation, dag + '/dagRuns/' + run_id)['state']
            return state if state in ('success', 'failed') else None
        assert local.wait_until(terminal, 1800) == 'success'
    Path('/proof/core-resource-samples.json').write_text(json.dumps(sampling.samples, indent=2))
    Path('/proof/core-traffic.json').write_text(json.dumps(sampling.traffic, indent=2))
    assert identities(operation.project) == before
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
    output = operation.compose('exec', '-T', 'api', 'python', '-c', code, timeout=300).decode()
    destination = json.loads(next(line.removeprefix('DESTINATION=') for line in output.splitlines()
                                  if line.startswith('DESTINATION=')))
    local.success('off')
    assert not operation.workers()
    after = probe.http_probe('http://web', ROOT / 'shared/admin-credentials.json', False, False)
    assert identities(operation.project) == before
    return {'run': run_id, 'core_ids': before, 'destination': destination, 'samples': len(sampling.samples),
            'authenticated_traffic_cycles': len(sampling.traffic), 'post_off_auth': after,
            'post_off_host_memory': host_memory(), 'sampling_interval_seconds': 5,
            'peak_method': 'maximum observed cgroup v2 peak_so_far while each container exists',
            'host_boundary': 'Docker Desktop VM; target-class host not exercised'}


def recovery(operation: AirflowOperations, payload: dict) -> dict:
    local.success('on', 900)
    baseline = Path(ROOT / 'current').resolve()
    first = finished(wrapper('rollback', payload))
    progress = {'on_rollback': first}
    Path('/proof/core-recovery-progress.json').write_text(json.dumps(progress, indent=2))
    restored = AirflowOperations(ROOT)
    require_open(restored.control, restored.release.name)
    assert restored.state()['requested'] == 'on' and restored.release != baseline
    wrong = {**payload, 'ADMIN_PASSWORD': 'Changed!Aa1-' + secrets.token_hex(16)}
    rejected = finished(wrapper('deploy', wrong), expected=1)
    progress['failed_cutover_recovery'] = rejected
    Path('/proof/core-recovery-progress.json').write_text(json.dumps(progress, indent=2))
    assert 'automatic_rollback' in rejected['stdout'] and 'Changing an existing app admin password' in rejected['stderr']
    assert Path(ROOT / 'current').resolve() == restored.release
    require_open(restored.control, restored.release.name)
    local.success('off')
    second = finished(wrapper('rollback', payload))
    progress['off_rollback'] = second
    Path('/proof/core-recovery-progress.json').write_text(json.dumps(progress, indent=2))
    current = AirflowOperations(ROOT)
    assert current.state()['requested'] == 'off' and not current.workers()
    assert not set(local.RUNTIME_SERVICES).intersection(current.compose('ps', '--status', 'running', '--services').decode().split())
    return {'on_rollback': first, 'failed_cutover_recovery': rejected, 'off_rollback': second,
            'provider_chat': 'not run by owner instruction', 'successful_deploy_provider_gate': 'pending'}


def active_drain(operation: AirflowOperations, payload: dict) -> dict:
    local.success('on', 900)
    before = identities(operation.project)
    dag = '/api/v2/dags/unesa_kg_construction'
    previous_runs = operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'airflow',
        '-tAc', "SELECT run_id FROM dag_run WHERE dag_id='unesa_kg_construction' "
        "AND state IN ('queued','running') ORDER BY run_id").decode().splitlines()
    for previous_run in previous_runs:
        local.wait_until(lambda: local.api(operation, dag + '/dagRuns/' + previous_run)['state']
                         in ('success', 'failed'), 1200)
    local.api(operation, dag, 'PATCH', {'is_paused': False})
    latch = subprocess.Popen(['docker', 'exec', '-i', before['postgres'],
        'psql', '-U', 'postgres', '-d', 'postgres', '-At'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        latch.stdin.write("BEGIN;\nLOCK TABLE papers IN ACCESS EXCLUSIVE MODE;\nSELECT 'LOCKED';\n")
        latch.stdin.flush()
        while latch.stdout.readline().strip() != 'LOCKED':
            if latch.poll() is not None:
                raise RuntimeError('PostgreSQL drain fixture lock failed')
        run_id = 'manual__wrapper_drain_' + secrets.token_hex(4)
        local.api(operation, dag + '/dagRuns', 'POST', {'dag_run_id': run_id,
            'logical_date': datetime.now(UTC).isoformat(), 'conf': {'mode': 'sample', 'sample_size': 1,
                'use_gliner': False, 'write_neo4j': True, 'write_milvus': False,
                'graph_name': operation.project}})
        worker = local.wait_until(lambda: command('docker', 'ps', '-q', '--filter',
            'label=io.yunesa.etl.project=' + operation.project, '--filter',
            'label=io.yunesa.etl.run=' + run_id).decode().strip(), 600)
        details = json.loads(command('docker', 'inspect', worker))[0]
        allocation = details['HostConfig']
        assert allocation['Memory'] == 512 * 1024**2
        assert allocation['MemorySwap'] == 1024 * 1024**2
        assert allocation['CpuShares'] == 1024 and allocation['NanoCpus'] == 0
        assert details['Config']['Image'] == operation.manifest['etl_worker_image']
        assert details['Config']['Labels']['io.yunesa.etl.release'] == operation.release.name
        assert not any(mount['Destination'].startswith('/app/package') for mount in details['Mounts'])
        runtime = {'id': details['Id'], 'image': details['Config']['Image'],
            'labels': details['Config']['Labels'], 'memory': allocation['Memory'],
            'memory_swap': allocation['MemorySwap'], 'cpu_shares': allocation['CpuShares'],
            'nano_cpus': allocation['NanoCpus'], 'source_mount': 'absent'}
        Path('/proof/core-worker-allocation.json').write_text(json.dumps(runtime, indent=2))
        local.wait_until(lambda: operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres',
            '-d', 'postgres', '-tAc', "SELECT count(*) FROM pg_stat_activity WHERE datname='postgres' "
            "AND wait_event_type='Lock'").strip() != b'0', 600)
        rejected = finished(wrapper('rollback', payload, deadline=1), expected=1)
        assert 'Drain deadline exceeded' in rejected['stderr']
        assert identities(operation.project) == before and operation.workers()[0]['id'] == worker
        assert all(item['State']['Running'] for item in inspect(operation.project)
                   if item['Config']['Labels'].get('com.docker.compose.service') in SERVICES)
        process = wrapper('rollback', payload)
        local.wait_until(lambda: operation.state()['phase'] == 'draining'
            and 'error' not in operation.state(), 120)
        time.sleep(5)
        state_before = operation.state_path.read_bytes()
        busy = local.cli('off', 1)
        assert busy.returncode and 'Lifecycle busy' in busy.stderr
        assert operation.state_path.read_bytes() == state_before
        assert identities(operation.project) == before and operation.workers()[0]['id'] == worker
        with tempfile.TemporaryFile() as events:
            arguments = ['docker', 'events', '--format', '{{json .}}', '--filter', 'event=die']
            for identifier in (*before.values(), worker):
                arguments.extend(('--filter', 'container=' + identifier))
            stream = subprocess.Popen(arguments, stdout=events, stderr=subprocess.PIPE)
            try:
                time.sleep(2)
                latch.communicate('COMMIT;\n\\q\n', timeout=30)
                restored = finished(process)
            finally:
                stream.terminate()
                stream.communicate(timeout=30)
            events.seek(0)
            deaths = [json.loads(line) for line in events.read().splitlines()]
        worker_deaths = [item['timeNano'] for item in deaths if item['Actor']['ID'].startswith(worker)]
        assert worker_deaths, 'Worker completion event was not observed'
        worker_death = worker_deaths[0]
        core_deaths = [item['timeNano'] for item in deaths if item['Actor']['ID'] in before.values()]
        assert core_deaths and worker_death < min(core_deaths)
        current = AirflowOperations(ROOT)
        require_open(current.control, current.release.name)
        local.wait_until(lambda: local.api(current, dag + '/dagRuns/' + run_id)['state'] == 'success', 1800)
        local.success('off')
        return {'run': run_id, 'prior_fixture_runs_waited': previous_runs, 'worker': runtime,
                'timeout': rejected, 'busy_operation_exit': busy.returncode,
                'worker_finished_before_core_stop': True, 'die_events': deaths, 'rollback': restored,
                'core_ids_before': before, 'core_ids_after': identities(operation.project),
                'provider_chat': 'not run by owner instruction'}
    finally:
        if latch.poll() is None:
            latch.communicate('ROLLBACK;\n\\q\n', timeout=30)


def resume(project: str, images: dict, revision: str, architecture: str):
    operation = AirflowOperations(ROOT)
    assert operation.project == project
    registry = json.loads((ROOT / 'config/registry.json').read_text())
    assert deployment_architecture(registry) == architecture
    assert configuration_digest(ROOT, installed=True) == registry['config_sha256']
    installed = ROOT / 'config/docker-compose.prod.yml'
    configuration = json.loads(installed.read_text())
    emulated_healthchecks(configuration, architecture)
    installed.write_text(json.dumps(configuration))
    registry['config_sha256'] = configuration_digest(ROOT, installed=True)
    (ROOT / 'config/registry.json').write_text(json.dumps(registry))
    for link in ('current', 'previous'):
        release = AirflowOperations(ROOT, (ROOT / link).resolve(strict=True))
        assert release.project == project
        path = release.release / 'docker-compose.prod.yml'
        configuration = json.loads(path.read_text())
        emulated_healthchecks(configuration, architecture)
        path.write_text(json.dumps(configuration))
        manifest = release.manifest
        manifest['config_sha256'] = registry['config_sha256']
        (release.release / 'manifest.json').write_text(json.dumps(manifest))
    environment = operation.environment()
    payload = {name: environment[name] for name in (*AIRFLOW_SECRETS, 'GLOBAL_PASSWORD', 'JWT_SECRET_KEY',
        'GEMINI_API_KEY', 'SILICONFLOW_API_KEY')}
    payload.update(images)
    payload.update(CI_COMMIT_SHA=revision, CI_REGISTRY=registry['registry'],
        CI_REGISTRY_IMAGE=registry['image_prefix'], CI_REGISTRY_USER='integration',
        CI_REGISTRY_PASSWORD='local-only', YUNESA_CONFIG_SHA256=registry['config_sha256'],
        ADMIN_PASSWORD=json.loads((ROOT / 'shared/admin-credentials.json').read_text())['password'])
    for name, image in images.items():
        assert environment[name] == image
    deployment = module('resumed_deployment', ROOT / 'bin/deploy-production.py')
    deployment.PROJECT = project
    deployment.ARCHITECTURE = architecture
    deployment.validate_request(payload, 'deploy', registry)
    deployment.compose(operation.release, 'up', '-d', '--no-build', '--wait', '--wait-timeout', '900',
                       *SERVICES, label='Resume isolated core services', timeout=1200)
    return operation, payload, deployment.readiness(operation.release, providers=False)


def exhaustion(operation: AirflowOperations) -> dict:
    before = identities(operation.project)
    query = "SELECT run_id FROM dag_run WHERE state='success' ORDER BY run_id"
    history = operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'airflow',
                                '-tAc', query).decode().splitlines()
    result = local.worker_oom(operation)
    retained = operation.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'airflow',
                                 '-tAc', query).decode().splitlines()
    assert set(history).issubset(retained)
    assert identities(operation.project) == before
    assert not operation.workers()
    assert operation.state()['requested'] == 'off'
    result['successful_history_retained'] = history
    result['core_ids_unchanged'] = True
    result['post_off_auth'] = probe.http_probe('http://web', ROOT / 'shared/admin-credentials.json', False, False)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--registry', required=True)
    parser.add_argument('--images', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--architecture', choices=('arm64', 'amd64'), default='arm64')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--phase', choices=('full', 'drain', 'oom'), default='full')
    args = parser.parse_args()
    if not re.fullmatch(r'yunesa-airflow-it-[a-f0-9]{8}', args.project):
        raise ValueError('A disposable project namespace is required')
    if not re.fullmatch(r'127\.0\.0\.1:[0-9]{1,5}', args.registry):
        raise ValueError('Only the authorized localhost registry is supported')
    if not re.fullmatch(r'[a-f0-9]{40}', args.revision):
        raise ValueError('Full source base revision is required')
    os.environ['DOCKER_DEFAULT_PLATFORM'] = 'linux/' + args.architecture
    os.environ['YUNESA_AIRFLOW_READINESS_DEADLINE'] = '900'
    interpreter = Path('/usr/bin/python3')
    if not interpreter.exists():
        interpreter.symlink_to(sys.executable)
    def expired(signum, frame):
        raise TimeoutError('Full core rehearsal exceeded 90 minutes')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(5400)
    report = {}
    try:
        print('CORE_PHASE=prepare', flush=True)
        images = json.loads(args.images.read_text())
        if args.resume:
            operation, payload, baseline = resume(args.project, images, args.revision, args.architecture)
        else:
            operation, payload, baseline = prepare(args.project, args.registry, images, args.revision, args.architecture)
        report = {'baseline': baseline, 'project': args.project, 'source_base_revision': args.revision,
                  'working_tree': 'uncommitted local build', 'platform': 'linux/' + args.architecture,
                  'dependency_exceptions': {
                      'redis': 'Real linux/amd64 Redis because ARM64 Redis rejects the emulated kernel',
                      'graph': 'Real linux/amd64 Memgraph because its ARM64 process aborts under QEMU',
                      'minio': 'ARM64 MinIO with fixture-only 384 MiB RAM and extended startup grace',
                      'worker': 'ARM64 worker health probe with fixture-only 180 second timeout',
                      'airflow': 'Original component probes with extended fixture-only emulation deadlines',
                  }}
        if args.architecture == 'amd64':
            report['dependency_exceptions'] = {}
        Path('/proof/core-progress.json').write_text(json.dumps(report, indent=2))
        if args.phase == 'oom':
            print('CORE_PHASE=isolated-oom', flush=True)
            report['isolated_oom'] = exhaustion(operation)
            Path('/proof/core-oom.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report), flush=True)
            return
        if args.phase == 'drain':
            print('CORE_PHASE=active-wrapper-drain', flush=True)
            report['active_drain'] = active_drain(operation, payload)
            Path('/proof/core-drain.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report), flush=True)
            return
        print('CORE_PHASE=resource-and-auth', flush=True)
        report['resource_and_auth'] = measure(operation)
        Path('/proof/core-progress.json').write_text(json.dumps(report, indent=2))
        print('CORE_PHASE=wrapper-recovery', flush=True)
        report['wrapper_recovery'] = recovery(operation, payload)
        Path('/proof/core-progress.json').write_text(json.dumps(report, indent=2))
        print('CORE_PHASE=active-wrapper-drain', flush=True)
        report['active_drain'] = active_drain(AirflowOperations(ROOT), payload)
        Path('/proof/core-progress.json').write_text(json.dumps(report, indent=2))
        print('CORE_PHASE=isolated-oom', flush=True)
        report['isolated_oom'] = exhaustion(AirflowOperations(ROOT))
        Path('/proof/core-release.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    except (RuntimeError, AssertionError, OSError, ValueError, subprocess.SubprocessError) as error:
        failure = {'error': type(error).__name__ + ' ' + str(error), 'completed': report}
        containers = inspect(args.project)
        failure['containers'] = [{'name': item['Name'], 'state': item['State'],
                                  'restarts': item['RestartCount']} for item in containers]
        Path('/proof/core-failure.json').write_text(json.dumps(failure, indent=2))
        raise
    finally:
        ids = set()
        for label in ('com.docker.compose.project=' + args.project, 'io.yunesa.etl.project=' + args.project):
            ids.update(command('docker', 'ps', '-aq', '--filter', 'label=' + label).decode().split())
        for identifier in ids:
            command('docker', 'rm', '-f', identifier)


if __name__ == '__main__':
    main()
