from __future__ import annotations

import os
import uuid
from functools import cached_property
from pathlib import Path

from airflow.providers.docker.operators.docker import DockerOperator
from docker import APIClient
from docker.errors import NotFound

from yunesa_airflow.admission import atomic_json, launch_lock, require_open


class AdmissionClient(APIClient):
    def create_container(self, *args, **kwargs):
        directory = Path(os.environ['YUNESA_AIRFLOW_CONTROL'])
        release = os.environ['YUNESA_RELEASE_ID']
        with launch_lock(directory):
            require_open(directory, release)
            host_config = kwargs['host_config']
            memory = host_config.get('Memory', 0)
            if memory <= 0:
                raise RuntimeError('ETL worker requires a positive memory limit')
            host_config['MemorySwap'] = int(os.getenv('ETL_WORKER_SWAP_BYTES', str(memory * 2)))
            if host_config['MemorySwap'] < memory:
                raise RuntimeError('ETL swap allowance cannot be lower than memory limit')
            marker = directory / ('reservation-' + uuid.uuid4().hex + '.json')
            atomic_json(marker, {'release': release, 'labels': kwargs.get('labels', {})})
            result = super().create_container(*args, **kwargs)
            # A failed create may have reached Docker; retain its reservation for reconciliation.
            marker.unlink()
            return result

    def start(self, container, *args, **kwargs):
        directory = Path(os.environ['YUNESA_AIRFLOW_CONTROL'])
        release = os.environ['YUNESA_RELEASE_ID']
        with launch_lock(directory):
            try:
                require_open(directory, release)
            except RuntimeError:
                identifier = container.get('Id') if isinstance(container, dict) else container
                state = super().inspect_container(identifier)['State']['Status']
                if state == 'created':
                    super().remove_container(identifier)
                raise
            return super().start(container, *args, **kwargs)

    def remove_container(self, container, v=False, link=False, force=False):
        if force:
            return super().remove_container(container, v=v, link=link, force=True)
        identifier = container.get('Id') if isinstance(container, dict) else container
        try:
            inspected = super().inspect_container(identifier)
            state = inspected.get('State', {})
            if state.get('Status') == 'exited' and (state.get('ExitCode') != 0 or state.get('OOMKilled')):
                failure_record = Path(os.environ['YUNESA_AIRFLOW_CONTROL']) / f'failed-worker-{identifier[:12]}.json'
                atomic_json(failure_record, {
                    'id': identifier,
                    'exit_code': state.get('ExitCode'),
                    'oom': state.get('OOMKilled', False),
                    'finished_at': state.get('FinishedAt'),
                    'labels': inspected.get('Config', {}).get('Labels', {}),
                })
                return
            return super().remove_container(container, v=v, link=link)
        except NotFound:
            return


class ManagedDockerOperator(DockerOperator):
    template_fields = tuple(dict.fromkeys((*DockerOperator.template_fields, 'labels')))

    def __init__(self, **kwargs):
        production = os.getenv('AIRFLOW_ENV', 'dev').lower() in ('prod', 'production')
        kwargs.setdefault('pool', 'yunesa-etl' if production else 'default_pool')
        kwargs.setdefault('mem_limit', os.getenv('ETL_WORKER_MEMORY', '512m'))
        kwargs.setdefault('cpus', float(os.getenv('ETL_WORKER_CPUS', '1')))
        kwargs.setdefault('labels', {
            'io.yunesa.etl.project': os.getenv('YUNESA_COMPOSE_PROJECT', 'yunesa-app'),
            'io.yunesa.etl.release': os.getenv('YUNESA_RELEASE_ID', 'development'),
            'io.yunesa.etl.dag': '{{ dag.dag_id }}',
            'io.yunesa.etl.run': '{{ run_id }}',
            'io.yunesa.etl.task': '{{ task.task_id }}',
        })
        super().__init__(**kwargs)

    @cached_property
    def cli(self):
        if not os.getenv('YUNESA_AIRFLOW_CONTROL'):
            return super().cli
        return AdmissionClient(base_url=self.docker_url, version='auto', timeout=60)
