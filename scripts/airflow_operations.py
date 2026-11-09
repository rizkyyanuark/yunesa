from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'orchestration'))
from yunesa_airflow.admission import atomic_json, require_open, set_gate  # noqa: E402

RUNTIME_SERVICES = ('airflow-api-server', 'airflow-dag-processor', 'airflow-scheduler')
RUNTIME_SERVICES_SET = set(RUNTIME_SERVICES)
AIRFLOW_SERVICES = ('airflow-init', *RUNTIME_SERVICES)
AIRFLOW_SECRETS = ('AIRFLOW_DB_PASSWORD', 'AIRFLOW_ADMIN_PASSWORD', 'AIRFLOW_FERNET_KEY', 'AIRFLOW_API_SECRET', 'AIRFLOW_JWT_SECRET')
IMAGE_KINDS = ('API', 'WEB', 'MINIO', 'AIRFLOW', 'ETL_WORKER')
TRUSTED_FILES = {
    'docker-compose.prod.yml': 'config/docker-compose.prod.yml',
    'scripts/deployment-readiness.py': 'config/deployment-readiness.py',
    'scripts/airflow_operations.py': 'bin/airflow_operations.py',
    'orchestration/yunesa_airflow/admission.py': 'orchestration/yunesa_airflow/admission.py',
    'orchestration/yunesa_airflow/__init__.py': 'orchestration/yunesa_airflow/__init__.py',
    'scripts/yunesa-airflow.sh': 'bin/airflow',
}


def deployment_project(configuration: dict) -> str:
    project = configuration.get('project', 'yunesa-app')
    if not isinstance(project, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,62}', project):
        raise ValueError('Invalid root-installed Compose project')
    return project


def deployment_architecture(configuration: dict) -> str:
    architecture = configuration.get('architecture', 'arm64')
    if architecture not in ('arm64', 'amd64'):
        raise ValueError('Invalid root-installed Linux architecture')
    return architecture


def deployment_airflow_log_volume(configuration: dict, current_environment: dict | None = None) -> str:
    current = (current_environment or {}).get('YUNESA_AIRFLOW_LOG_VOLUME')
    name = configuration.get('airflow_log_volume', current or deployment_project(configuration) + '_airflow-logs')
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{1,254}', name):
        raise ValueError('Invalid persistent Airflow log volume name')
    if current and current != name:
        raise ValueError('Airflow log volume change requires an explicit offline migration')
    return name


def deployment_endpoints(configuration: dict) -> dict[str, str]:
    endpoints = {}
    for name, default in (
        ('local_base_url', 'http://127.0.0.1:8088'),
        ('public_base_url', 'https://yunesa.tugasakhir.space'),
    ):
        value = configuration.get(name, default)
        if not isinstance(value, str) or any(character.isspace() for character in value):
            raise ValueError('Invalid trusted readiness endpoint ' + name)
        parsed = urlsplit(value)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment):
            raise ValueError('Invalid trusted readiness endpoint ' + name)
        if parsed.port == 0:
            raise ValueError('Invalid trusted readiness endpoint ' + name)
        endpoints[name] = value.rstrip('/')
    return endpoints


def configuration_digest(root: Path, installed: bool = False) -> str:
    digest = hashlib.sha256()
    for name, destination in TRUSTED_FILES.items():
        digest.update(name.encode() + b'\0' + (root / (destination if installed else name)).read_bytes() + b'\0')
    return digest.hexdigest()


class OperationError(RuntimeError):
    pass


def run(arguments: list[str], *, data: bytes | None = None, timeout: int = 120, input_file=None, output_file=None) -> bytes:
    try:
        result = subprocess.run(arguments, input=data, stdin=input_file, stdout=output_file or subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OperationError('Command unavailable or deadline exceeded: ' + arguments[0]) from error
    if result.returncode:
        raise OperationError(f'Operation failed (exit {result.returncode}): ' + ' '.join(arguments[:3]))
    return result.stdout or b''


def trusted_json(path: Path) -> dict:
    if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
        raise OperationError('Untrusted configuration: ' + path.name)
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise OperationError('Invalid configuration: ' + path.name)
    return value


def assert_no_legacy_scheduler() -> None:
    for selector in ('label=com.docker.compose.project=yunesa-airflow', 'name=^/yunesa-airflow$'):
        if run(['docker', 'ps', '-q', '--filter', selector]).strip():
            raise OperationError('Separate Airflow installation is still running; authorized migration must drain it first')


@contextmanager
def lifecycle_lock(root: Path) -> Iterator[None]:
    with (root / '.deploy.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise OperationError('Lifecycle busy; retry after the active operation') from error
        yield


class AirflowOperations:
    def __init__(self, root: Path, release: Path | None = None, project: str | None = None):
        self.root = root.resolve()
        self.release = (release or root / 'current').resolve(strict=True)
        if not self.release.is_relative_to(self.root / 'releases'):
            raise OperationError('Release must be inside trusted releases')
        self.manifest = trusted_json(self.release / 'manifest.json')
        self.project = project or self.manifest.get('project', 'yunesa-app')
        self.directory = self.root / 'shared' / 'airflow'
        self.control = self.directory / 'control'
        self.state_path = self.directory / 'state.json'

    def compose(self, *arguments: str, data: bytes | None = None, timeout: int = 120, input_file=None, output_file=None) -> bytes:
        try:
            return run([
                'docker', 'compose', '--project-name', self.project, '--project-directory', str(self.release),
                '--env-file', str(self.release / '.env'), '-f', str(self.release / 'docker-compose.prod.yml'),
                *arguments,
            ], data=data, timeout=timeout, input_file=input_file, output_file=output_file)
        except OperationError as error:
            targets = [argument for argument in arguments
                       if argument in RUNTIME_SERVICES_SET | {'airflow-init', 'postgres'}]
            raise OperationError(f'Compose {arguments[0]} failed for {", ".join(targets) or self.project} ({error})') from error

    def state(self) -> dict:
        if not self.state_path.exists():
            return {'requested': 'off', 'phase': 'off'}
        state = trusted_json(self.state_path)
        if state.get('requested') not in ('on', 'off') or state.get('phase') not in ('on', 'off', 'starting', 'draining', 'error'):
            raise OperationError('Invalid lifecycle state; admission recovery required')
        return state

    def save(self, state: dict) -> None:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.control.mkdir(exist_ok=True, mode=0o770)
        os.chmod(self.control, 0o770)
        state.setdefault('transition_id', uuid.uuid4().hex)
        state['release'] = self.release.name
        atomic_json(self.state_path, state, mode=0o600)

    def transition_state(self) -> dict:
        try:
            return self.state()
        except (OperationError, OSError, ValueError):
            if self.control.is_dir():
                set_gate(self.control, False, self.release.name)
            raise

    def component(self, action: str, paused: dict | None = None) -> dict:
        running = self.compose('ps', '--status', 'running', '--services').decode().split()
        prefix = ('exec', '-T', 'airflow-dag-processor') if 'airflow-dag-processor' in running else ('run', '--rm', '--no-deps', 'airflow-init')
        output = self.compose(
            *prefix, 'python', '-m', 'yunesa_airflow.component', action,
            data=json.dumps(paused or {}).encode() if action == 'resume' else None,
        ).decode()
        marker = 'YUNESA_RESULT='
        if marker not in output:
            raise OperationError('Component returned no structured result')
        return json.loads(output.rsplit(marker, 1)[1])

    def workers(self, include_exited: bool = False) -> list[dict]:
        identifiers = run([
            'docker', 'ps', '-aq', '--filter', f'label=io.yunesa.etl.project={self.project}',
        ]).decode().split()
        if not identifiers:
            return []
        fields = '{{json .State}}'
        workers = []
        for identifier in identifiers:
            try:
                state = json.loads(run(['docker', 'inspect', '--format', fields, identifier]))
            except OperationError:
                if not run(['docker', 'ps', '-aq', '--filter', f'id={identifier}']).strip():
                    continue
                raise
            if include_exited or state['Status'] in ('created', 'running', 'restarting', 'paused'):
                workers.append({'id': identifier, 'status': state['Status'], 'oom': state['OOMKilled'], 'exit_code': state['ExitCode']})
        return workers

    def status(self) -> dict:
        try:
            lifecycle = self.state()
            state_error = None
        except (OperationError, OSError, ValueError) as error:
            lifecycle = {'requested': 'unknown', 'phase': 'error', 'error': str(error)}
            state_error = str(error)
        services = self.compose('ps', '--all', '--format', 'json').decode().strip()
        records = [json.loads(line) for line in services.splitlines() if line]
        records = [{name: item.get(name) for name in ('Service', 'ID', 'State', 'Health', 'Image')} for item in records]
        activity = {'unavailable': 'DAG processor is stopped'}
        if any(item['Service'] == 'airflow-dag-processor' and item['State'] == 'running' for item in records):
            try:
                activity = self.component('status')
            except OperationError as error:
                activity = {'error': str(error)}
        running_names = {item['Service'] for item in records if item['State'] == 'running'}
        readiness_error = state_error
        if readiness_error is None and 'airflow-init' in running_names:
            readiness_error = 'Metadata initialization is still running'
        if readiness_error is None and RUNTIME_SERVICES_SET.issubset(running_names):
            try:
                self.component('ready')
            except OperationError as error:
                readiness_error = str(error)
        elif readiness_error is None and lifecycle.get('requested') == 'on':
            missing = sorted(RUNTIME_SERVICES_SET - running_names)
            readiness_error = 'Stopped runtime services: ' + ', '.join(missing)
        if readiness_error is None and lifecycle.get('requested') == 'on' and lifecycle.get('phase') == 'on':
            try:
                require_open(self.control, self.release.name)
            except RuntimeError as error:
                readiness_error = str(error)
        if state_error is not None or lifecycle.get('phase') == 'error':
            observed_health = 'error'
        elif lifecycle.get('phase') in ('starting', 'draining'):
            observed_health = lifecycle['phase']
        elif (lifecycle.get('requested') == 'off' and not RUNTIME_SERVICES_SET.intersection(running_names)
              and 'airflow-init' not in running_names):
            observed_health = 'off'
        elif readiness_error is None and RUNTIME_SERVICES_SET.issubset(running_names):
            observed_health = 'healthy'
        else:
            observed_health = 'degraded'
        identifiers = [item['ID'] for item in records if item['State'] == 'running']
        workers = self.workers(include_exited=True)
        identifiers.extend(worker['id'] for worker in workers if worker['status'] == 'running')
        metrics = []
        resource_error = None
        if identifiers:
            try:
                metrics = [json.loads(line) for line in run(['docker', 'stats', '--no-stream', '--format', '{{json .}}', *identifiers]).decode().splitlines()]
            except OperationError as error:
                resource_error = str(error)
        return {
            'lifecycle': lifecycle,
            'observed_health': observed_health,
            'readiness_error': readiness_error,
            'release': {
                'id': self.release.name,
                'commit': self.manifest.get('commit'),
                'airflow_image': self.manifest.get('airflow_image'),
                'etl_worker_image': self.manifest.get('etl_worker_image'),
                'airflow_version': self.manifest.get('airflow_version'),
            },
            'services': records,
            'activity': activity, 'resources': metrics, 'resource_error': resource_error,
            'workers': workers, 'reservations': [path.name for path in self.control.glob('reservation-*.json')],
        }

    def environment(self) -> dict[str, str]:
        path = self.release / '.env'
        if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o077:
            raise OperationError('Release environment must be restricted and root-owned')
        result = {}
        for line in path.read_text().splitlines():
            if line and not line.startswith('#'):
                name, separator, value = line.partition('=')
                if not separator or not (value.startswith("'") and value.endswith("'")):
                    raise OperationError('Invalid trusted environment format')
                result[name] = value[1:-1]
        return result

    def provision_database(self) -> None:
        environment = self.environment()
        if any(not environment.get(name) for name in AIRFLOW_SECRETS):
            raise OperationError('Required Airflow credentials are missing')
        password = environment['AIRFLOW_DB_PASSWORD']
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,}', password):
            raise OperationError('AIRFLOW_DB_PASSWORD must be URL-safe with at least 16 characters')
        script = f"""\\set ON_ERROR_STOP on
SET lock_timeout='5s';
SET statement_timeout='30s';
SELECT 'CREATE ROLE airflow LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD ''{password}''' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='airflow')\\gexec
SELECT 'CREATE DATABASE airflow OWNER airflow' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='airflow')\\gexec
"""
        self.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'postgres', data=script.encode())
        ownership = self.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'postgres', '-tAc',
                                 "SELECT count(*) FROM pg_database d JOIN pg_roles r ON d.datdba=r.oid WHERE d.datname='airflow' AND r.rolname='airflow' AND NOT r.rolsuper AND NOT r.rolcreatedb").strip()
        if ownership != b'1':
            raise OperationError('Existing Airflow ownership requires offline adoption after backup')

    def validate_release(self) -> None:
        environment = self.environment()
        if self.manifest.get('airflow_version') != '3.1.7':
            raise OperationError('Airflow release is unavailable or requires verified metadata recovery')
        for field, variable in (('airflow_image', 'YUNESA_AIRFLOW_IMAGE'),
                                ('etl_worker_image', 'YUNESA_ETL_WORKER_IMAGE')):
            if not self.manifest.get(field) or self.manifest[field] != environment.get(variable):
                raise OperationError('Release manifest and environment ETL image identities do not match')

    def on(self, deadline: int = 180) -> dict:
        state = self.transition_state()
        try:
            self.validate_release()
        except (OperationError, OSError, ValueError):
            self.save(state)
            set_gate(self.control, False, self.release.name)
            raise
        assert_no_legacy_scheduler()
        if state['phase'] == 'on':
            try:
                running = self.compose('ps', '--status', 'running', '--services').decode().split()
                if not RUNTIME_SERVICES_SET.issubset(running) or 'airflow-init' in running:
                    raise OperationError('Required Airflow components are not ready')
                self.component('ready')
                require_open(self.control, self.release.name)
                return self.status()
            except (OperationError, RuntimeError):
                pass
        self.save(state)
        set_gate(self.control, False, self.release.name)
        if self.workers():
            raise OperationError('Recovery cannot restart Airflow while an ETL worker is executing; drain it first')
        state['transition_id'] = uuid.uuid4().hex
        state.pop('error', None)
        self.save({**state, 'requested': 'on', 'phase': 'starting'})
        if list(self.control.glob('reservation-*.json')):
            raise OperationError('Unresolved worker launch reservation; inspect before restarting')
        running = self.compose('ps', '--status', 'running', '--services').decode().split()
        if RUNTIME_SERVICES_SET.intersection(running) or 'airflow-init' in running:
            self.off(deadline=deadline, preserve_requested=True)
            state = self.state()
            self.save({**state, 'phase': 'starting'})
        self.provision_database()
        self.compose('up', '--no-deps', '--force-recreate', '--exit-code-from', 'airflow-init', 'airflow-init', timeout=deadline)
        self.compose('up', '-d', '--no-deps', *RUNTIME_SERVICES, timeout=deadline)
        until = time.monotonic() + deadline
        last_error = 'Components not ready'
        while time.monotonic() < until:
            try:
                running = self.compose('ps', '--status', 'running', '--services').decode().split()
                if not RUNTIME_SERVICES_SET.issubset(running):
                    raise OperationError('Required Airflow containers are not running')
                self.component('ready')
                self.component('resume', state.get('paused', {}))
                set_gate(self.control, True, self.release.name)
                self.save({'requested': 'on', 'phase': 'on', 'transition_id': state['transition_id']})
                return self.status()
            except OperationError as error:
                last_error = str(error)
                time.sleep(2)
        self.save({**state, 'requested': 'on', 'phase': 'error', 'error': 'Readiness deadline exceeded'})
        raise OperationError('Readiness deadline exceeded: ' + last_error)

    def off(self, deadline: int = 600, preserve_requested: bool = False) -> dict:
        state = self.transition_state()
        self.save(state)
        set_gate(self.control, False, self.release.name)
        running_services = self.compose('ps', '--status', 'running', '--services').decode().split()
        until = time.monotonic() + deadline
        if 'airflow-init' in running_services:
            if state['phase'] != 'draining':
                state['transition_id'] = uuid.uuid4().hex
            state.update(phase='draining', requested=state['requested'] if preserve_requested else 'off')
            state.pop('error', None)
            self.save(state)
            while 'airflow-init' in running_services:
                if time.monotonic() >= until:
                    message = 'Drain deadline exceeded: metadata initialization is still running; inspect airflow-init logs'
                    self.save({**state, 'error': message})
                    raise OperationError(message)
                time.sleep(2)
                running_services = self.compose('ps', '--status', 'running', '--services').decode().split()
        if not set(RUNTIME_SERVICES).intersection(running_services) and not self.workers() and not list(self.control.glob('reservation-*.json')):
            cleaned = {k: v for k, v in state.items() if k != 'error'}
            self.save({**cleaned, 'requested': state['requested'] if preserve_requested else 'off', 'phase': 'off'})
            return self.status()
        if state['phase'] != 'draining':
            state['transition_id'] = uuid.uuid4().hex
        state.update(phase='draining')
        state.pop('error', None)
        if not preserve_requested:
            state['requested'] = 'off'
        self.save(state)
        snapshot = self.component('pause')
        if 'paused' not in state:
            state['paused'] = snapshot['paused']
            self.save(state)
        current = snapshot
        workers = self.workers()
        reservations = list(self.control.glob('reservation-*.json'))
        while time.monotonic() < until:
            current = self.component('status')
            reservations = list(self.control.glob('reservation-*.json'))
            workers = self.workers()
            if not current['running'] and not reservations and not workers:
                self.compose('stop', '--timeout', '30', *RUNTIME_SERVICES)
                state['phase'] = 'off'
                state.pop('error', None)
                self.save(state)
                return self.status()
            time.sleep(2)
        message = 'Drain deadline exceeded: ' + json.dumps({'tasks': current['running'], 'workers': workers, 'reservations': [p.name for p in reservations]})
        self.save({**state, 'phase': 'draining', 'error': message})
        raise OperationError(message)

    def logs(self, service: str, lines: int) -> str:
        if service not in AIRFLOW_SERVICES or not 1 <= lines <= 1000:
            raise OperationError('Invalid service or log count')
        return self.compose('logs', '--no-color', '--tail', str(lines), service).decode()

    def backup_metadata(self, directory: Path) -> dict:
        import shutil

        if not directory.resolve().is_relative_to(self.root / 'backups'):
            raise OperationError('Backup must stay inside the deployment backup directory')
        if self.state()['phase'] != 'off' or self.workers() or list(self.control.glob('reservation-*.json')):
            raise OperationError('Airflow must be fully drained before its backup')
        running = self.compose('ps', '--status', 'running', '--services').decode().split()
        if 'airflow-init' in running:
            raise OperationError('Airflow initialization must finish before its backup')
        exists = self.compose('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'postgres',
                              '-tAc', "SELECT count(*) FROM pg_database WHERE datname='airflow'").strip()
        if exists != b'1':
            return {'metadata_present': False}
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        volume = self.environment().get('YUNESA_AIRFLOW_LOG_VOLUME')
        if not volume and (self.root / 'config/registry.json').is_file():
            try:
                volume = trusted_json(self.root / 'config/registry.json').get('airflow_log_volume')
            except OperationError:
                volume = None
        if not volume:
            volume = self.project + '_airflow-logs'
        labels = json.loads(run(['docker', 'volume', 'inspect', '--format', '{{json .Labels}}', volume])) or {}
        if labels.get('com.docker.compose.project') not in (self.project, 'yunesa-airflow'):
            raise OperationError('Airflow log volume ownership is not recognized')
        for name, arguments in (
            ('airflow.dump', ('pg_dump', '-U', 'postgres', '-d', 'airflow', '-Fc')),
            ('airflow-roles.sql', ('pg_dumpall', '-U', 'postgres', '--roles-only')),
        ):
            with (directory / name).open('wb') as stream:
                os.fchmod(stream.fileno(), 0o600)
                self.compose('exec', '-T', 'postgres', *arguments, output_file=stream)
        with (directory / 'airflow.dump').open('rb') as stream:
            self.compose('exec', '-T', 'postgres', 'pg_restore', '--list', input_file=stream)
        with (directory / 'airflow-logs.tar.gz').open('wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            run(['docker', 'run', '--rm', '--network', 'none', '--mount',
                 f'type=volume,src={volume},dst=/source,readonly', 'alpine:3.22', 'tar', '-cz', '-C', '/source', '.'],
                output_file=stream)
        with tarfile.open(directory / 'airflow-logs.tar.gz') as archive:
            for _ in archive:
                pass
        for source, name in ((self.state_path, 'airflow-state.json'), (self.release / '.env', 'airflow-recovery.env')):
            shutil.copyfile(source, directory / name)
            (directory / name).chmod(0o600)
        hashes = {}
        for path in directory.iterdir():
            if path.is_file() and path.name.startswith('airflow'):
                with path.open('rb') as stream:
                    hashes[path.name] = hashlib.file_digest(stream, 'sha256').hexdigest()
        atomic_json(directory / 'airflow-checksums.json', hashes, mode=0o600)
        return {'metadata_present': True, 'log_volume': volume, 'files': sorted(hashes)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('on', 'off', 'status', 'logs', 'reconcile'))
    parser.add_argument('--root', type=Path, default=Path('/opt/yunesa-app'))
    parser.add_argument('--project')
    parser.add_argument('--service', choices=AIRFLOW_SERVICES, default='airflow-scheduler')
    parser.add_argument('--lines', type=int, default=50)
    parser.add_argument('--deadline', type=int)
    args = parser.parse_args()
    if args.deadline is not None and not 1 <= args.deadline <= 3600:
        parser.error('--deadline must be between 1 and 3600 seconds')
    if os.geteuid() != 0:
        print('Use the authorized administrative SSH operation', file=sys.stderr)
        return 1
    operation = None
    try:
        if args.root.is_symlink() or args.root.stat().st_uid != 0 or args.root.stat().st_mode & 0o022:
            raise OperationError('Untrusted deployment root')
        operation = AirflowOperations(args.root, project=args.project)
        if args.action == 'status':
            print(json.dumps(operation.status(), sort_keys=True))
        elif args.action == 'logs':
            print(operation.logs(args.service, args.lines))
        else:
            with lifecycle_lock(args.root):
                try:
                    action = args.action
                    if action == 'reconcile':
                        action = operation.state()['requested']
                    result = operation.on(args.deadline or 180) if action == 'on' else operation.off(args.deadline or 600)
                    print(json.dumps(result, sort_keys=True))
                except (OperationError, OSError, ValueError, KeyError) as error:
                    message = str(error) if isinstance(error, OperationError) else f'Invalid lifecycle state ({type(error).__name__})'
                    try:
                        if operation.control.is_dir():
                            set_gate(operation.control, False, operation.release.name)
                        state = operation.state()
                        phase = 'draining' if message.startswith('Drain deadline exceeded:') else 'error'
                        operation.save({**state, 'phase': phase, 'error': message})
                    except (OperationError, OSError, ValueError) as recording_error:
                        print(f'Lifecycle error could not be recorded ({type(recording_error).__name__})', file=sys.stderr)
                    raise
        return 0
    except (OperationError, OSError, ValueError, KeyError) as error:
        message = str(error) if isinstance(error, OperationError) else f'Invalid lifecycle state ({type(error).__name__})'
        print(message, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
