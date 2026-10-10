#!/usr/bin/env bash
set -euo pipefail
exec /usr/bin/python3 /opt/yunesa-app/bin/deploy-production.py "${1:?operation required}"
