FROM apache/airflow:3.1.7-python3.12

ARG CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-3.1.7/constraints-3.12.txt"

RUN pip install --no-cache-dir \
    "apache-airflow==3.1.7" \
    "apache-airflow-providers-docker" \
    "apache-airflow-providers-fab" \
    "apache-airflow-providers-ssh" \
    "apache-airflow-providers-standard" \
    "requests" \
    "psycopg2-binary" \
    --constraint "${CONSTRAINT_URL}"

COPY --chown=airflow:root orchestration/dags /opt/airflow/dags
COPY --chown=airflow:root orchestration/yunesa_airflow /opt/airflow/yunesa_airflow
ENV PYTHONPATH=/opt/airflow


