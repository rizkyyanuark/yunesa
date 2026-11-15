"""Compare ARQ health probes and verify a real worker heartbeat lifecycle."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import time
from pathlib import Path

PROFILE = '''
import json
import os
import resource
import subprocess
import sys
import time

started = time.monotonic()
environment = dict(os.environ, PYTHONPROFILEIMPORTTIME='1')
completed = subprocess.run(sys.argv[1:], capture_output=True, text=True, env=environment, timeout=120)
imports = [line.rsplit('|', 1)[-1].strip() for line in completed.stderr.splitlines()
           if line.startswith('import time:')]
tail = completed.stderr[-800:]
for key in ('GLOBAL_PASSWORD', 'JWT_SECRET_KEY', 'GEMINI_API_KEY', 'SILICONFLOW_API_KEY'):
    if os.environ.get(key):
        tail = tail.replace(os.environ[key], '<redacted>')
print(json.dumps({'exit': completed.returncode, 'seconds': time.monotonic() - started,
                 'child_peak_rss_kib': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                 'imports_chat_service': 'yunesa.services.chat_service' in imports,
                 'imports_torch': 'torch' in imports,
                 'missing_heartbeat': 'no health check sentinel value found' in completed.stderr,
                 'stderr_tail': tail}))
'''


def docker(*arguments: str, timeout=180) -> str:
    result = subprocess.run(['docker', *arguments], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'Docker {arguments[0]} failed with exit {result.returncode}: {result.stderr[-300:]}')
    return result.stdout


def wait(check, timeout=120):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if check():
            return
        time.sleep(1)
    raise TimeoutError('Worker health diagnostic deadline exceeded')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--image', default='yunesa-api:health-diagnosis-native')
    args = parser.parse_args()
    project = args.project
    assert re.fullmatch(r'yunesa-worker-health-it-[0-9a-f]{8}', project)
    password = secrets.token_hex(16)
    environment = {
        'REDIS_URL': 'redis://redis:6379/0',
        'POSTGRES_URL': f'postgresql+asyncpg://postgres:{password}@postgres:5432/postgres',
        'GLOBAL_PASSWORD': password, 'JWT_SECRET_KEY': secrets.token_hex(32),
        'GEMINI_API_KEY': 'provider-unavailable', 'SILICONFLOW_API_KEY': 'provider-unavailable',
        'YUNESA_ENV': 'production', 'RUNNING_IN_DOCKER': 'true', 'SANDBOX_ENABLED': 'false',
        'OPIK_ENABLED': 'false', 'YUNESA_VECTOR_BACKEND': 'qdrant',
    }
    env_args = [part for key, value in environment.items() for part in ('-e', key + '=' + value)]
    result = {'project': project, 'image': args.image, 'provider_chat': 'deferred', 'probes': {}}
    proof = Path('/proof/worker-health.json')
    containers = []
    docker('network', 'create', '--internal', '--label', 'io.yunesa.worker-health=' + project, project)
    try:
        postgres = docker('run', '-d', '--pull=never', '--name', project + '-postgres',
            '--label', 'io.yunesa.worker-health=' + project, '--network', project, '--network-alias', 'postgres',
            '--memory', '160m', '--memory-swap', '512m', '-e', 'POSTGRES_PASSWORD=' + password,
            '--platform', 'linux/amd64', 'postgres:16-alpine', 'postgres', '-c', 'shared_buffers=64MB').strip()
        containers.append(postgres)
        redis = docker('run', '-d', '--pull=never', '--name', project + '-redis',
            '--label', 'io.yunesa.worker-health=' + project, '--network', project, '--network-alias', 'redis',
            '--memory', '64m', '--platform', 'linux/amd64',
            'redis:7-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499').strip()
        containers.append(redis)
        wait(lambda: subprocess.run(['docker', 'exec', postgres, 'pg_isready', '-U', 'postgres'],
             capture_output=True, timeout=15).returncode == 0)
        for name, command in (('old', ['arq', '--check', 'server.worker_main.WorkerSettings']),
                              ('new', ['python', '-m', 'server.worker_health'])):
            output = docker('run', '--rm', '--pull=never', '--network', project,
                '--label', 'io.yunesa.worker-health=' + project, '--memory', '256m', '--memory-swap', '1g',
                *env_args, '--entrypoint', 'python', args.image, '-c', PROFILE, *command)
            measured = json.loads(output.splitlines()[-1])
            assert measured['exit'] == 1 and measured['missing_heartbeat'], measured
            result['probes'][name] = measured
            proof.write_text(json.dumps(result, indent=2))
        assert result['probes']['old']['imports_chat_service']
        assert not result['probes']['new']['imports_chat_service']
        worker = docker('run', '-d', '--pull=never', '--name', project + '-worker',
            '--label', 'io.yunesa.worker-health=' + project, '--network', project,
            '--memory', '256m', '--memory-swap', '1g', '--health-cmd', 'python -m server.worker_health',
            '--health-interval', '30s', '--health-timeout', '45s', '--health-start-period', '30s',
            '--health-retries', '5', *env_args, args.image, 'arq', 'server.worker_main.WorkerSettings').strip()
        containers.append(worker)
        wait(lambda: json.loads(docker('inspect', '--format', '{{json .State.Health}}', worker))['Status'] == 'healthy')
        assert subprocess.run(['docker', 'exec', worker, 'python', '-m', 'server.worker_health'],
                              capture_output=True, timeout=45).returncode == 0
        docker('stop', '--time', '30', worker)
        failed = docker('run', '--rm', '--pull=never', '--network', project, *env_args,
                        '--entrypoint', 'python', args.image, '-c', PROFILE,
                        'python', '-m', 'server.worker_health')
        stopped = json.loads(failed.splitlines()[-1])
        assert stopped['exit'] == 1 and stopped['missing_heartbeat'], stopped
        invalid = subprocess.run(['docker', 'run', '--rm', '--pull=never', '--network', project,
            '-e', 'REDIS_URL=redis://user:do-not-print@redis:invalid/0', '--entrypoint', 'python',
            args.image, '-m', 'server.worker_health'], capture_output=True, text=True, timeout=45)
        assert invalid.returncode == 1, invalid.returncode
        assert 'ValueError' in invalid.stderr and 'do-not-print' not in invalid.stderr
        result.update(real_worker_healthy=True, stopped_worker_probe=stopped,
                      invalid_config_exit=invalid.returncode, worker_id=worker, postgres_id=postgres, redis_id=redis)
        proof.write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    except (RuntimeError, OSError, ValueError, AssertionError, subprocess.SubprocessError) as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
        proof.write_text(json.dumps(result, indent=2))
        raise
    finally:
        for identifier in reversed(containers):
            docker('rm', '-fv', identifier)
        docker('network', 'rm', project)


if __name__ == '__main__':
    main()
