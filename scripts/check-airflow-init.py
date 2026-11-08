"""Exercise interrupted initialization with real Airflow and a PostgreSQL lock."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import threading
from pathlib import Path

from airflow_operations import OperationError

SOURCE = Path(__file__).resolve().parents[1]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SOURCE / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


local = load('init_local', 'airflow-local-check.py')
kernel = load('init_kernel', 'check-airflow-kernel-guest.py')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    args = parser.parse_args()
    assert re.fullmatch(r'yunesa-airflow-it-[0-9a-f]{8}', args.project)
    operation = local.prepare(args.project)
    operation.provision_database()
    operation.compose('run', '--rm', '--no-deps', 'airflow-init', timeout=300)
    schema = kernel.query(operation, 'SELECT version_num FROM alembic_version')
    postgres = operation.compose('ps', '-q', 'postgres').decode().strip()
    lock_errors: list[str] = []

    def hold() -> None:
        try:
            operation.compose('exec', '-T', '-e', 'PGAPPNAME=yunesa-init-hold', 'postgres',
                'psql', '-X', '-U', 'postgres', '-d', 'airflow', '-v', 'ON_ERROR_STOP=1',
                data=b'BEGIN; LOCK TABLE alembic_version IN ACCESS EXCLUSIVE MODE; SELECT pg_sleep(600); ROLLBACK;',
                timeout=660)
        except OperationError as error:
            lock_errors.append(str(error))

    holder = threading.Thread(target=hold, daemon=True)
    holder.start()
    result = {'project': args.project, 'schema_before': schema, 'postgres_id': postgres}
    try:
        kernel.wait(lambda: kernel.query(operation, """
SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid
WHERE a.application_name='yunesa-init-hold' AND l.mode='AccessExclusiveLock' AND l.granted
""") == '1', 60)
        operation.compose('up', '-d', '--no-deps', 'airflow-init')
        identifier = operation.compose('ps', '-q', 'airflow-init').decode().strip()
        kernel.wait(lambda: kernel.query(operation, """
SELECT count(*) FROM pg_stat_activity WHERE usename='airflow' AND wait_event_type='Lock'
""") != '0', 180)
        status = operation.status()
        assert status['observed_health'] != 'off'
        assert status['readiness_error'] == 'Metadata initialization is still running'
        result['blocked_status'] = status['observed_health']
        for action in ('off', 'on'):
            attempt = subprocess.run([sys.executable, str(local.ROOT / 'bin/airflow_operations.py'),
                action, '--deadline', '1'], capture_output=True, text=True, timeout=60)
            assert attempt.returncode != 0, action
            assert 'metadata initialization is still running' in attempt.stderr, attempt.stderr
            assert operation.compose('ps', '-q', 'airflow-init').decode().strip() == identifier
            assert json.loads(local.docker('inspect', identifier))[0]['State']['Running']
            gate = json.loads((operation.control / 'gate.json').read_text())
            assert not gate['open']
            result[action + '_during_init'] = {'exit': attempt.returncode, 'init_id': identifier,
                                              'gate_open': gate['open'], 'state': operation.state()}
        operation.save({'requested': 'off', 'phase': 'off'})
        try:
            operation.backup_metadata(local.ROOT / 'backups/init-regression')
        except OperationError as error:
            assert 'initialization must finish' in str(error), str(error)
            result['backup_rejected'] = str(error)
        else:
            raise AssertionError('Backup accepted active initialization')
        result['init_log_lines'] = len(operation.logs('airflow-init', 2).splitlines())
    finally:
        kernel.query(operation, """
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='yunesa-init-hold'
""")
        holder.join(30)
        assert not holder.is_alive()

    def finished():
        item = json.loads(local.docker('inspect', identifier))[0]
        if item['State']['Running']:
            return False
        assert item['State']['ExitCode'] == 0, item['State']['ExitCode']
        return True

    kernel.wait(finished, 180)
    operation.off(deadline=30)
    assert operation.status()['observed_health'] == 'off'
    assert not operation.workers()
    assert operation.compose('ps', '-q', 'postgres').decode().strip() == postgres
    assert kernel.query(operation, 'SELECT version_num FROM alembic_version') == schema
    operation.off(deadline=30)
    result.update(init_id=identifier, init_exit=0, schema_after=schema, workers=[],
                  off_after_init='off', lock_released_by_backend_termination=True,
                  lock_command_exit_observed=bool(lock_errors))
    Path('/proof/init-regression.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
