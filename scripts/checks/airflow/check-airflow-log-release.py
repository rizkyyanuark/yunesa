"""Verify an explicitly adopted log volume through local releases and rollback."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[3]
ROOT = Path('/opt/yunesa-app')
PROOF = Path('/proof/log-release.json')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--registry', required=True)
    parser.add_argument('--images', type=Path, required=True)
    args = parser.parse_args()
    if (not re.fullmatch(r'yunesa-airflow-it-[a-f0-9]{8}', args.project)
            or not re.fullmatch(r'127\.0\.0\.1:[0-9]{1,5}', args.registry)):
        parser.error('Disposable project and localhost registry required')
    def expired(signum, frame):
        raise TimeoutError('Local log-volume rehearsal exceeded one hour')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(3600)
    spec = importlib.util.spec_from_file_location('core', SOURCE / 'scripts/checks/airflow/check-airflow-core-release.py')
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    # Sibling Docker containers resolve bind sources on the daemon, outside this controller.
    mounts = json.loads(core.command('docker', 'inspect', args.project + '-controller'))[0]['Mounts']
    root_mount = next(mount for mount in mounts if mount['Destination'] == str(ROOT))
    assert root_mount['Type'] == 'volume' and root_mount['Name'] == args.project + '-root'
    docker_binary = shutil.which('docker')
    bridge = Path('/tmp/log-release-docker')
    bridge.mkdir(mode=0o700)
    adapter = bridge / 'docker'
    adapter.write_text(f'''#!{sys.executable}
import os
import sys
arguments = [value.replace('type=bind,src=/opt/yunesa-app/backups/',
    {'type=bind,src=' + root_mount['Source'] + '/backups/'!r}, 1)
    if value.startswith('type=bind,src=/opt/yunesa-app/backups/') else value for value in sys.argv[1:]]
os.execv({docker_binary!r}, [{docker_binary!r}, *arguments])
''')
    adapter.chmod(0o700)
    os.environ['PATH'] = str(bridge) + os.pathsep + os.environ['PATH']
    os.environ['DOCKER_DEFAULT_PLATFORM'] = 'linux/amd64'
    os.environ['YUNESA_AIRFLOW_READINESS_DEADLINE'] = '600'
    legacy = args.project + '-adopted-logs'
    marker = Path('/legacy-logs/historical-task.log')
    Path('/legacy-logs').chmod(0o775)
    marker.write_text('Retained historical fixture task log\n')
    marker.chmod(0o644)
    original_hash = hashlib.sha256(marker.read_bytes()).hexdigest()
    report = {'project': args.project, 'log_volume': legacy, 'phases': {}, 'status': 'failed',
              'fixture_adapter': 'Backup bind sources translated to the controller root-volume daemon path'}
    def save():
        PROOF.write_text(json.dumps(report, indent=2))
    def verify(operation):
        assert operation.environment()['YUNESA_AIRFLOW_LOG_VOLUME'] == legacy
        assert operation.manifest['airflow_log_volume'] == legacy
        assert hashlib.sha256(marker.read_bytes()).hexdigest() == original_hash
        records = core.inspect(args.project)
        mounts = [mount['Name'] for record in records for mount in record['Mounts']
                  if mount['Destination'] == '/opt/airflow/logs']
        assert mounts and set(mounts) == {legacy}, mounts
        return {'release': operation.release.name, 'manifest_log_volume': legacy,
                'historical_log_sha256': original_hash, 'actual_log_mounts': mounts}
    try:
        common = [sys.executable, str(SOURCE / 'scripts/install-deployment-host.py'), '--source', str(SOURCE),
            '--registry', args.registry, '--image-prefix', args.registry + '/yunesa-integration',
            '--project', args.project, '--architecture', 'amd64',
            '--local-base-url', 'http://web', '--public-base-url', 'http://web']
        core.command(*common, '--airflow-log-volume', legacy)
        core.command(*common)
        installed = (ROOT / 'config/registry.json').read_bytes()
        assert json.loads(installed)['airflow_log_volume'] == legacy
        rejected = subprocess.run([*common, '--airflow-log-volume', args.project + '-wrong-logs'],
                                  capture_output=True, timeout=60)
        assert rejected.returncode != 0 and (ROOT / 'config/registry.json').read_bytes() == installed
        report['phases']['installer'] = {'refresh_preserved': True, 'remap_rejected': True}
        save()
        operation, payload, baseline = core.prepare(args.project, args.registry,
            json.loads(args.images.read_text()), 'b6924e196f6728c73dd70864c20b1c655db9f50f', 'amd64', log_volume=legacy)
        report['phases']['core_baseline'] = baseline
        print('LOG_RELEASE_PHASE=initial_on', flush=True)
        core.local.success('on', 600)
        before = verify(operation)
        dag = '/api/v2/dags/unesa_kg_construction'
        core.local.api(operation, dag, 'PATCH', {'is_paused': False})
        run_id = 'manual__persistent_logs_' + os.urandom(4).hex()
        core.local.api(operation, dag + '/dagRuns', 'POST', {'dag_run_id': run_id,
            'logical_date': core.datetime.now(core.UTC).isoformat(), 'conf': {'mode': 'sample', 'sample_size': 1,
                'use_gliner': False, 'write_neo4j': True, 'write_milvus': False, 'graph_name': args.project}})
        def completed():
            state = core.local.api(operation, dag + '/dagRuns/' + run_id)['state']
            if state == 'failed':
                raise RuntimeError('Historical KG fixture failed')
            return state == 'success'
        core.local.wait_until(completed, 600)
        report['run_id'] = run_id
        report['phases']['initial_on'] = before
        save()
        deployment = core.module('log_deployment', ROOT / 'bin/deploy-production.py')
        deployment.PROJECT = args.project
        deployment.ARCHITECTURE = 'amd64'
        print('LOG_RELEASE_PHASE=next_release', flush=True)
        backup = deployment.backup(operation.release)
        time.sleep(1)
        next_release = deployment.create_release(payload)
        deployment.compose(next_release, 'up', '-d', '--no-build', '--wait', '--wait-timeout', '300',
                           *core.SERVICES, label='Activate next isolated core release')
        next_readiness = deployment.readiness(next_release, providers=False)
        deployment.restore_airflow(next_release)
        deployment.set_release_link('previous', operation.release)
        deployment.set_release_link('current', next_release)
        current = core.AirflowOperations(ROOT)
        report['phases']['next_release'] = {**verify(current), 'core_readiness': next_readiness,
            'backup': str(backup), 'provider_gate': 'deferred; real release/lifecycle functions used'}
        assert current.state()['requested'] == 'on'
        assert core.local.api(current, dag + '/dagRuns/' + run_id)['state'] == 'success'
        save()
        print('LOG_RELEASE_PHASE=on_rollback', flush=True)
        rollback = core.finished(core.wrapper('rollback', payload))
        current = core.AirflowOperations(ROOT)
        report['phases']['on_rollback'] = {**verify(current), 'wrapper_exit': rollback['exit_code']}
        assert current.state()['requested'] == 'on'
        assert core.local.api(current, dag + '/dagRuns/' + run_id)['state'] == 'success'
        save()
        print('LOG_RELEASE_PHASE=off_rollback', flush=True)
        core.local.success('off', 600)
        rollback = core.finished(core.wrapper('rollback', payload))
        current = core.AirflowOperations(ROOT)
        report['phases']['off_rollback'] = {**verify(current), 'wrapper_exit': rollback['exit_code']}
        assert current.state()['requested'] == 'off' and not current.workers()
        report['post_off_application'] = core.probe.http_probe('http://web', ROOT / 'shared/admin-credentials.json', False, False)
        report['provider_chat'] = 'deferred by owner'
        report['status'] = 'passed'
        save()
    except (RuntimeError, ValueError, OSError, AssertionError, subprocess.SubprocessError) as error:
        report['error_type'] = type(error).__name__
        report['error'] = str(error)
        save()
        raise


if __name__ == '__main__':
    main()
