from __future__ import annotations

import fcntl
import hashlib
import json
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit

IMAGE_KINDS = ('API', 'WEB', 'MINIO')
TRUSTED_FILES = {
    'docker-compose.prod.yml': 'config/docker-compose.prod.yml',
    'scripts/deployment-readiness.py': 'config/deployment-readiness.py',
    'scripts/airflow_operations.py': 'bin/airflow_operations.py',
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


@contextmanager
def lifecycle_lock(root: Path) -> Iterator[None]:
    with (root / '.deploy.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise OperationError('Lifecycle busy; retry after the active operation') from error
        yield
