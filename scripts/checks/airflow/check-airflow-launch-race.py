"""Check admission ordering using real Docker containers and process termination."""

from __future__ import annotations

import json
import multiprocessing
import os
import tempfile
from pathlib import Path

from docker import APIClient
from docker.errors import ImageNotFound, NotFound

from etl_operator import AdmissionClient
from yunesa_airflow.admission import atomic_json, launch_lock, set_gate

IMAGE = 'yunesa-airflow-check:local'


def create(client, project, command=None):
    return client.create_container(
        image=IMAGE, command=command or ['python', '-c', 'import time; time.sleep(2)'],
        host_config=client.create_host_config(mem_limit='32m', cpu_shares=1024, network_mode='none'),
        labels={'io.yunesa.etl.project': project, 'io.yunesa.etl.release': 'race-check',
                'io.yunesa.etl.dag': 'admission-probe', 'io.yunesa.etl.run': 'race',
                'io.yunesa.etl.task': 'launch'})['Id']


def launch(project, ready, result):
    client = AdmissionClient(base_url='unix://var/run/docker.sock', version='auto')
    ready.set()
    try:
        identifier = create(client, project)
        client.start(identifier)
        result.put(('started', identifier))
    except RuntimeError:
        result.put(('closed', None))


def main():
    project = 'yunesa-airflow-race-' + os.urandom(4).hex()
    os.environ['YUNESA_RELEASE_ID'] = 'race-check'
    ordinary = APIClient(base_url='unix://var/run/docker.sock', version='auto')
    counts = {'started': 0, 'closed': 0}
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        os.environ['YUNESA_AIRFLOW_CONTROL'] = temporary
        client = AdmissionClient(base_url='unix://var/run/docker.sock', version='auto')
        try:
            set_gate(directory, False, 'race-check')
            try:
                create(client, project)
            except RuntimeError:
                pass
            else:
                raise AssertionError('Closed gate admitted create')
            set_gate(directory, True, 'race-check')
            identifier = create(client, project)
            inspected = ordinary.inspect_container(identifier)
            assert inspected['HostConfig']['Memory'] == 32 * 1024**2
            assert inspected['HostConfig']['MemorySwap'] == 64 * 1024**2
            assert len(inspected['Config']['Labels']) == 5
            set_gate(directory, False, 'race-check')
            try:
                client.start(identifier)
            except RuntimeError:
                pass
            else:
                raise AssertionError('Closed gate admitted start')
            try:
                ordinary.inspect_container(identifier)
            except NotFound:
                pass
            else:
                raise AssertionError('Rejected created container was left behind')
            set_gate(directory, True, 'race-check')
            identifier = create(client, project)
            client.start(identifier)
            set_gate(directory, False, 'race-check')
            try:
                client.start(identifier)
            except RuntimeError:
                pass
            assert ordinary.inspect_container(identifier)['State']['Running']
            assert ordinary.wait(identifier, timeout=30)['StatusCode'] == 0
            ordinary.remove_container(identifier)
            set_gate(directory, True, 'race-check')
            identifier = create(client, project, ['python', '-c', 'pass'])
            client.start(identifier)
            assert client.wait(identifier, timeout=30)['StatusCode'] == 0
            client.remove_container(identifier)
            assert not ordinary.containers(all=True, filters={'id': identifier})
            client.remove_container(identifier)
            identifier = create(client, project, ['python', '-c', 'raise SystemExit(7)'])
            client.start(identifier)
            assert client.wait(identifier, timeout=30)['StatusCode'] == 7
            client.remove_container(identifier)
            record = json.loads((directory / f'failed-worker-{identifier[:12]}.json').read_text())
            assert record['exit_code'] == 7 and record['oom'] is False
            assert ordinary.inspect_container(identifier)['State']['ExitCode'] == 7
            invalid_directory = directory / 'invalid-control-file'
            invalid_directory.write_text('not a directory')
            os.environ['YUNESA_AIRFLOW_CONTROL'] = str(invalid_directory)
            try:
                client.remove_container(identifier)
            except NotADirectoryError:
                pass
            else:
                raise AssertionError('Diagnostic write failure was hidden')
            finally:
                os.environ['YUNESA_AIRFLOW_CONTROL'] = temporary
            assert ordinary.inspect_container(identifier)['State']['ExitCode'] == 7
            client.remove_container(identifier, False, False, True)
            assert not ordinary.containers(all=True, filters={'id': identifier})
            for _ in range(20):
                set_gate(directory, True, 'race-check')
                ready, result = multiprocessing.Event(), multiprocessing.Queue()
                process = multiprocessing.Process(target=launch, args=(project, ready, result))
                process.start()
                assert ready.wait(30)
                set_gate(directory, False, 'race-check')
                outcome, identifier = result.get(timeout=30)
                process.join(30)
                assert process.exitcode == 0
                counts[outcome] += 1
                if identifier:
                    assert ordinary.wait(identifier, timeout=30)['StatusCode'] == 0
                    ordinary.remove_container(identifier)
                assert not list(directory.glob('reservation-*.json'))
            set_gate(directory, True, 'race-check')
            try:
                client.create_container(image='yunesa-intentionally-absent:race-check',
                                        host_config=client.create_host_config(mem_limit='32m'))
            except ImageNotFound:
                pass
            else:
                raise AssertionError('Missing image was accepted')
            assert len(list(directory.glob('reservation-*.json'))) == 1
            def interrupted():
                with launch_lock(directory):
                    atomic_json(directory / 'reservation-interrupted.json', {'release': 'race-check'})
                    os._exit(9)
            process = multiprocessing.Process(target=interrupted)
            process.start()
            process.join(30)
            assert process.exitcode == 9
            with launch_lock(directory):
                assert len(list(directory.glob('reservation-*.json'))) == 2
            print('RACE_RESULT=' + json.dumps({'iterations': 20, 'outcomes': counts,
                'create_then_close': 'removed', 'running_worker': 'finished_without_kill',
                'successful_cleanup': 'removed', 'failed_cleanup': 'retained_with_diagnostic',
                'diagnostic_write_failure': 'propagated_with_container_retained', 'positional_force': 'removed',
                'failed_create_reservation': 'retained', 'crash_reservation': 'retained'}))
        finally:
            for container in ordinary.containers(all=True, filters={'label': 'io.yunesa.etl.project=' + project}):
                ordinary.remove_container(container['Id'], force=True)


if __name__ == '__main__':
    main()
