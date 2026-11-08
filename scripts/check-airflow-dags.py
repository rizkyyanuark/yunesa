"""Render embedded managed DAG commands and inspect their worker boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
from types import SimpleNamespace

from airflow.models.dagbag import DagBag


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    forbidden = {'AWS_SECRET_ACCESS_KEY', 'TELEGRAM_BOT_TOKEN', 'AIRFLOW_ADMIN_PASSWORD', 'AIRFLOW_DB_PASSWORD',
                 'AIRFLOW_FERNET_KEY', 'AIRFLOW_API_SECRET', 'AIRFLOW_JWT_SECRET', 'JWT_SECRET_KEY', 'ADMIN_PASSWORD'}
    for key in forbidden:
        os.environ[key] = 'forbidden-' + key
    bag = DagBag('/opt/airflow/dags', include_examples=False)
    assert not bag.import_errors, bag.import_errors
    expected = {'unesa_lecturers_etl', 'unesa_papers_etl', 'unesa_kg_construction'}
    assert set(bag.dag_ids) == expected, bag.dag_ids
    rendered = []
    for dag in bag.dags.values():
        for task in dag.tasks:
            assert task.image == os.environ['ETL_WORKER_IMAGE']
            assert task.pool == 'yunesa-etl', (dag.dag_id, task.task_id, task.pool)
            assert task.mem_limit and task.cpus > 0
            assert not forbidden.intersection(task.environment)
            assert not any(value in task.environment.values() for value in ('forbidden-' + key for key in forbidden))
            for mode in ('sample', 'incremental', 'full'):
                context = {'dag': dag, 'task': task, 'run_id': 'manual__dag_contract',
                           'dag_run': SimpleNamespace(conf={'mode': mode, 'sample_size': 2}),
                           'params': dag.params.dump()}
                command = task.render_template(task.command, context)
                labels = task.render_template(task.labels, context)
                assert labels['io.yunesa.etl.dag'] == dag.dag_id
                assert labels['io.yunesa.etl.task'] == task.task_id
                assert labels['io.yunesa.etl.run'] == 'manual__dag_contract'
                assert labels['io.yunesa.etl.release'] == os.environ['YUNESA_RELEASE_ID']
                assert labels['io.yunesa.etl.project'] == os.environ['YUNESA_COMPOSE_PROJECT']
                rendered.append({'dag': dag.dag_id, 'task': task.task_id, 'mode': mode, 'command': command})
    report = {'architecture': platform.machine(), 'managed_dags': sorted(bag.dag_ids),
              'worker_image': os.environ['ETL_WORKER_IMAGE'],
              'shared_pool': 'yunesa-etl', 'commands': rendered, 'forbidden_credentials': 'absent',
              'embedded_sources': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                   for path in sorted(Path('/opt/airflow/dags').glob('*.py'))}}
    arguments.output.write_text(json.dumps(report, indent=2))
    print('DAG_CONTRACT_RESULT=' + json.dumps({'architecture': platform.machine(), 'dags': len(bag.dag_ids),
                                             'commands': len(rendered), 'forbidden_credentials': 'absent'}))


if __name__ == '__main__':
    main()
