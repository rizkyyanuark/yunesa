#!/usr/bin/env bash
set -euo pipefail
exec python3 /opt/yunesa-app/bin/airflow_operations.py "$@"
