"""Exercise restart and reconciliation against the retained isolated core fixture."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import secrets
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from airflow_operations import AirflowOperations, OperationError, RUNTIME_SERVICES
from yunesa_airflow.admission import atomic_json, require_open

SOURCE = Path(__file__).resolve().parents[1]
ROOT = Path('/opt/yunesa-app')
PROOF = Path('/proof')
spec = importlib.util.spec_from_file_location('core_checks', SOURCE / 'scripts/check-airflow-core-release.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
local = core.local


def query(operation: AirflowOperations, sql: str) -> str:
    return operation.compose('exec', '-T', 'postgres', 'psql', '-X', '-U', 'postgres', '-d', 'airflow',
                             '-At', '-v', 'ON_ERROR_STOP=1', data=sql.encode()).decode().strip()


def application(operation: AirflowOperations, identities: dict) -> dict:
    assert core.identities(operation.project) == identities
    return core.probe.http_probe('http://web', ROOT / 'shared/admin-credentials.json', False, False)


def healthy(operation: AirflowOperations) -> None:
    def ready():
        try:
            operation.component('ready')
            return True
        except RuntimeError:
            return False
    local.wait_until(ready, seconds=240)


def read_only(operation: AirflowOperations, expected: str) -> dict:
    before = (operation.state_path.read_bytes(), (operation.control / 'gate.json').read_bytes())
    result = local.cli('status')
    assert result.returncode == 0
    status = json.loads(result.stdout)
    assert status['observed_health'] == expected, status['observed_health']
    selections = {}
    for service in RUNTIME_SERVICES:
        logs = subprocess.run(['python', str(ROOT / 'bin/airflow_operations.py'), 'logs',
                               '--service', service, '--lines', '3'], capture_output=True, text=True, timeout=60)
        assert logs.returncode == 0
        lines = [line for line in logs.stdout.splitlines() if line.strip()]
        assert 0 < len(lines) <= 3
        assert all(line.lstrip().startswith(service) for line in lines)
        selections[service] = {'lines': len(lines), 'sha256': hashlib.sha256(logs.stdout.encode()).hexdigest()}
    invalid = subprocess.run(['python', str(ROOT / 'bin/airflow_operations.py'), 'logs', '--lines', '1001'],
                             capture_output=True, text=True, timeout=60)
    assert invalid.returncode != 0 and 'Invalid service or log count' in invalid.stderr
    assert before == (operation.state_path.read_bytes(), (operation.control / 'gate.json').read_bytes())
    return {'desired': status['lifecycle']['requested'], 'observed': expected,
            'state_gate_bytes_preserved': True, 'service_logs': selections, 'invalid_tail_rejected': True}


def prepare(project: str) -> dict:
    operation = AirflowOperations(ROOT)
    assert operation.project == project
    configuration = json.loads((ROOT / 'config/registry.json').read_text())
    assert configuration['architecture'] == 'amd64'
    assert (ROOT / 'bin/airflow_operations.py').read_bytes() == (SOURCE / 'scripts/airflow_operations.py').read_bytes()
    operation.compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '240', *core.SERVICES, timeout=360)
    networks = json.loads(local.docker('inspect', project + '-controller'))[0]['NetworkSettings']['Networks']
    if project + '_app-network' not in networks:
        local.docker('network', 'connect', project + '_app-network', project + '-controller')
    local.success('off')
    ids = core.identities(project)
    history = query(operation, "SELECT run_id FROM dag_run WHERE state='success' ORDER BY run_id").splitlines()
    assert history
    logs = {str(path.relative_to('/airflow-logs')): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in Path('/airflow-logs').rglob('*.log')
            if any('/run_id=' + run + '/' in str(path) for run in history)}
    assert logs
    result = {'project': project, 'core_ids': ids, 'successful_runs': history, 'historical_logs': logs,
              'baseline_application': application(operation, ids), 'requested': 'off'}
    (PROOF / 'prepared.json').write_text(json.dumps(result, indent=2))
    return result


def verify(project: str) -> dict:
    operation = AirflowOperations(ROOT)
    assert operation.project == project
    baseline = json.loads((PROOF / 'prepared.json').read_text())
    ids = baseline['core_ids']
    assert baseline['project'] == project
    assert core.identities(project) == ids
    result = {'project': project, 'platform': 'linux/amd64', 'core_ids': ids,
              'boot_boundary': 'stale boot record plus real component/container restarts; kernel/systemd reboot not executed',
              'provider_chat': 'deferred by owner instruction'}
    def checkpoint(name: str, value: dict) -> None:
        result[name] = value
        (PROOF / 'restart-progress.json').write_text(json.dumps(result, indent=2))
        print('RESTART_PHASE=' + name, flush=True)

    local.success('off')
    local.docker('restart', '-t', '30', *ids.values(), timeout=240)
    core_start_attempts = 1
    try:
        operation.compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '240', *core.SERVICES, timeout=360)
    except OperationError:
        containers = core.inspect(project)
        worker = next(item for item in containers
                      if item['Config']['Labels'].get('com.docker.compose.service') == 'worker')
        dependencies = [item for item in containers
                        if item['Config']['Labels'].get('com.docker.compose.service') in core.SERVICES
                        and item['Config']['Labels']['com.docker.compose.service'] != 'worker']
        worker_logs = subprocess.run(['docker', 'logs', '--tail', '70', worker['Id']],
                                     capture_output=True, text=True, check=True, timeout=30)
        if (worker['State']['ExitCode'] != 1 or worker['State']['OOMKilled']
                or 'Temporary failure in name resolution' not in worker_logs.stdout + worker_logs.stderr
                or not all(item['State'].get('Health', {}).get('Status') == 'healthy' for item in dependencies)):
            raise
        print('CORE_RECOVERY=worker_dns_retry', flush=True)
        core_start_attempts = 2
        operation.compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '240', *core.SERVICES, timeout=360)
    local.success('reconcile')
    assert operation.state()['requested'] == 'off'
    assert not set(RUNTIME_SERVICES).intersection(operation.compose('ps', '--status', 'running', '--services').decode().split())
    checkpoint('off_after_core_restart', {'requested': 'off', 'runtime_count': 0,
               'core_start_attempts': core_start_attempts,
               'application': application(operation, ids)})

    local.success('on')
    choices = {'unesa_lecturers_etl': True, 'unesa_papers_etl': True, 'unesa_kg_construction': False}
    for dag, paused in choices.items():
        local.api(operation, '/api/v2/dags/' + dag, 'PATCH', {'is_paused': paused})
    checkpoint('read_only_healthy', read_only(operation, 'healthy'))
    gate = json.loads((operation.control / 'gate.json').read_text())
    atomic_json(operation.control / 'gate.json', {**gate, 'boot_id': 'prior-boot-' + secrets.token_hex(8)})
    operation.compose('restart', '--timeout', '30', *RUNTIME_SERVICES, timeout=180)
    healthy(operation)
    stale = read_only(operation, 'degraded')
    assert stale['desired'] == 'on'
    scheduler = operation.compose('ps', '-q', 'airflow-scheduler').decode().strip()
    rejected = subprocess.run(['docker', 'exec', scheduler, 'python', '-c',
        "import os; from pathlib import Path; from yunesa_airflow.admission import require_open; "
        "require_open(Path(os.environ['YUNESA_AIRFLOW_CONTROL']),os.environ['YUNESA_RELEASE_ID'])"],
        capture_output=True, text=True, timeout=60)
    assert rejected.returncode != 0 and 'release/boot reconciliation required' in rejected.stderr
    run_id = 'manual__restart_' + secrets.token_hex(4)
    logical = datetime.now(timezone.utc).isoformat()
    dag = '/api/v2/dags/unesa_kg_construction'
    local.api(operation, dag + '/dagRuns', 'POST', {'dag_run_id': run_id, 'logical_date': logical,
        'conf': {'mode': 'sample', 'sample_size': 1, 'use_gliner': False,
                 'write_neo4j': False, 'write_milvus': False, 'graph_name': project}})
    def refused():
        assert not operation.workers()
        state = query(operation, f"SELECT state FROM task_instance WHERE run_id='{run_id}' AND task_id='load_data'")
        return state if state in ('up_for_retry', 'failed') else None
    attempt = local.wait_until(refused, seconds=240)
    failed_logs = [path for path in Path('/airflow-logs').rglob('*.log') if '/run_id=' + run_id + '/' in str(path)]
    assert any('release/boot reconciliation required' in path.read_text() for path in failed_logs)
    workers = local.docker('ps', '-aq', '--filter', 'label=io.yunesa.etl.run=' + run_id).split()
    assert workers == []
    checkpoint('stale_boot_blocks_real_task', {'status': stale, 'run': run_id, 'attempt_state': attempt,
               'worker_containers': workers, 'scheduler_gate_rejected': True,
               'application': application(operation, ids)})
    local.success('reconcile')
    require_open(operation.control, operation.release.name)
    paused = operation.component('status')['paused']
    assert paused == choices, paused
    cleared = local.api(operation, dag + '/clearTaskInstances', 'POST', {
        'dag_run_id': run_id, 'task_ids': ['load_data'], 'only_failed': False, 'dry_run': False})
    assert cleared['total_entries'] == 1
    assert [(task['dag_run_id'], task['task_id']) for task in cleared['task_instances']] == [(run_id, 'load_data')]
    def resumed():
        state = local.api(operation, dag + '/dagRuns/' + run_id)['state']
        if state == 'failed':
            raise RuntimeError('Reconciled managed run failed')
        return state == 'success'
    local.wait_until(resumed, seconds=900)
    assert not operation.workers()
    checkpoint('reconciled_run_resumed', {'run': run_id, 'state': 'success', 'pause_choices': paused,
               'application': application(operation, ids)})

    operation.compose('stop', '--timeout', '30', 'airflow-dag-processor')
    degraded = json.loads(local.cli('status').stdout)
    assert degraded['observed_health'] == 'degraded' and degraded['lifecycle']['requested'] == 'on'
    local.success('reconcile')
    require_open(operation.control, operation.release.name)
    checkpoint('missing_processor_recovery', {'before': 'desired_on_observed_degraded', 'after': 'healthy',
               'application': application(operation, ids)})

    scheduler = operation.compose('ps', '-q', 'airflow-scheduler').decode().strip()
    prior_restarts = json.loads(local.docker('inspect', scheduler))[0]['RestartCount']
    crash = """from pathlib import Path
import os, signal, time
children = Path('/proc/1/task/1/children').read_text().split()
targets = [int(pid) for pid in children
           if b'airflow scheduler' in (Path('/proc') / pid / 'cmdline').read_bytes().replace(b'\\0', b' ')]
assert len(targets) == 1
time.sleep(1)
os.kill(targets[0], signal.SIGKILL)
"""
    local.docker('exec', '--detach', scheduler, 'python', '-c', crash)
    def restarted():
        current = json.loads(local.docker('inspect', scheduler))[0]
        return current['RestartCount'] > prior_restarts and current['State']['Status'] == 'running'
    local.wait_until(restarted, seconds=120)
    healthy(operation)
    local.success('reconcile')
    after_restarts = json.loads(local.docker('inspect', scheduler))[0]['RestartCount']
    assert operation.compose('ps', '-q', 'airflow-scheduler').decode().strip() == scheduler
    checkpoint('scheduler_crash_recovery', {'container': scheduler, 'restart_before': prior_restarts,
               'restart_after': after_restarts, 'application': application(operation, ids)})

    saved_state = operation.state()
    operation.state_path.write_text('{broken-fixture-state')
    bad = local.cli('reconcile')
    assert bad.returncode != 0
    broken = json.loads(local.cli('status').stdout)
    assert broken['observed_health'] == 'error' and broken['lifecycle']['requested'] == 'unknown'
    local.closed(operation, operation.release.name)
    operation.save(saved_state)
    local.success('reconcile')
    checkpoint('corrupt_state_recovery', {'exit': bad.returncode, 'observed': 'error',
               'recovery': 'administrator restored known checkpoint then reconciled',
               'application': application(operation, ids)})

    local.success('off')
    process = subprocess.Popen(['python', str(ROOT / 'bin/airflow_operations.py'), 'on', '--deadline', '600'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        local.wait_until(lambda: operation.state()['phase'] == 'starting', seconds=60)
        process.kill()
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
    local.closed(operation, operation.release.name)
    partial = json.loads(local.cli('status').stdout)
    assert partial['lifecycle']['requested'] == 'on' and partial['observed_health'] == 'starting'
    local.success('reconcile')
    assert operation.component('status')['paused'] == choices
    checkpoint('interrupted_start_recovery', {'interrupted_exit': process.returncode,
               'before': 'desired_on_observed_starting', 'after': 'healthy',
               'application': application(operation, ids)})

    local.success('off')
    local.success('reconcile')
    retained = query(operation, "SELECT run_id FROM dag_run WHERE state='success' ORDER BY run_id").splitlines()
    assert set(baseline['successful_runs'] + [run_id]).issubset(retained)
    for name, checksum in baseline['historical_logs'].items():
        assert hashlib.sha256((Path('/airflow-logs') / name).read_bytes()).hexdigest() == checksum
    assert not operation.workers()
    checkpoint('final_off', {'requested': operation.state()['requested'], 'retained_runs': retained,
               'retained_log_files': len(baseline['historical_logs']), 'workers': [],
               'application': application(operation, ids)})
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--phase', choices=('prepare', 'verify'), required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'yunesa-airflow-it-[a-f0-9]{8}', args.project):
        raise ValueError('A disposable project namespace is required')
    def expired(signum, frame):
        raise TimeoutError('Restart check exceeded 45 minutes')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(2700)
    result = prepare(args.project) if args.phase == 'prepare' else verify(args.project)
    (PROOF / (args.phase + '-result.json')).write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
