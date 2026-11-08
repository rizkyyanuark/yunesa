from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone


MANAGED_DAGS = ('unesa_lecturers_etl', 'unesa_papers_etl', 'unesa_kg_construction')


def metadata(action: str, paused: dict | None = None) -> dict:
    from airflow import settings
    from airflow.jobs.job import Job
    from airflow.models import DagModel, Pool, TaskInstance
    from sqlalchemy import text

    with settings.Session() as session:
        session.execute(text('SELECT 1'))
        dags = session.query(DagModel).filter(DagModel.dag_id.in_(MANAGED_DAGS)).all()
        running = session.query(TaskInstance).filter(TaskInstance.state == 'running').all()
        imports = session.execute(text('SELECT count(*) FROM import_error')).scalar_one()
        result = {
            'paused': {dag.dag_id: dag.is_paused for dag in dags},
            'running': [{'dag': task.dag_id, 'run': task.run_id, 'task': task.task_id} for task in running],
            'queued': session.query(TaskInstance).filter(TaskInstance.state == 'queued').count(),
            'import_errors': imports,
        }
        if action in ('pause', 'resume', 'setup'):
            pool = session.query(Pool).filter(Pool.pool == 'yunesa-etl').one_or_none()
            if pool is None:
                pool = Pool(pool='yunesa-etl', slots=0, description='Shared ETL capacity', include_deferred=False)
                session.add(pool)
            pool.slots = 1 if action == 'resume' else 0
            for dag in dags:
                if action == 'pause':
                    dag.is_paused = True
                elif paused is not None and dag.dag_id in paused:
                    dag.is_paused = paused[dag.dag_id]
            session.commit()
        if action == 'ready':
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
            for kind in ('SchedulerJob', 'DagProcessorJob'):
                job = session.query(Job).filter(Job.job_type == kind, Job.state == 'running').order_by(Job.latest_heartbeat.desc()).first()
                if job is None or job.latest_heartbeat is None or job.latest_heartbeat < cutoff:
                    raise RuntimeError(f'{kind} heartbeat unavailable')
            missing = set(MANAGED_DAGS) - {dag.dag_id for dag in dags}
            if imports or missing:
                raise RuntimeError('DAG import errors or missing managed DAGs')
            with urllib.request.urlopen('http://airflow-api-server:8080/api/v2/monitor/health', timeout=10) as response:
                health = json.load(response)
            for name in ('metadatabase', 'scheduler', 'dag_processor'):
                if health.get(name, {}).get('status') != 'healthy':
                    raise RuntimeError(f'{name} unhealthy')
        return result


def initialize() -> None:
    subprocess.run(['airflow', 'db', 'migrate'], check=True)
    users = subprocess.run(['airflow', 'users', 'list', '--output', 'json'], check=True, capture_output=True, text=True)
    # CLI logging can precede JSON; select the last JSON array rather than logging credentials.
    records = None
    for offset, character in enumerate(users.stdout):
        if character == '[':
            try:
                candidate, _ = json.JSONDecoder().raw_decode(users.stdout[offset:])
            except ValueError:
                continue
            if isinstance(candidate, list):
                records = candidate
                break
    if records is None:
        raise RuntimeError('Cannot read Airflow user inventory')
    if not any(user.get('username') == 'admin' for user in records):
        result = subprocess.run([
            'airflow', 'users', 'create', '--username', 'admin', '--password', os.environ['AIRFLOW_ADMIN_PASSWORD'],
            '--firstname', 'Airflow', '--lastname', 'Admin', '--role', 'Admin', '--email', 'admin@yunesa.local',
        ], capture_output=True)
        if result.returncode:
            raise RuntimeError('Airflow admin initialization failed')
    metadata('setup')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('init', 'ready', 'status', 'pause', 'resume'))
    args = parser.parse_args()
    if args.action == 'init':
        initialize()
    else:
        paused = json.load(sys.stdin) if args.action == 'resume' else None
        print('YUNESA_RESULT=' + json.dumps(metadata(args.action, paused)))


if __name__ == '__main__':
    main()
