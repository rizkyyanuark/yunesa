# Proposal

## Why

Airflow currently runs through an untracked, separate Compose project and a host script that can report success without readiness or stop without accounting for DockerOperator workers. Yunesa needs one versioned production deployment with SSH controls that let its owner run ETL on the existing server and stop Airflow without stopping the application or losing orchestration history.

## What Changes

- Add optional `etl` services to `docker-compose.prod.yml` under project `yunesa-app`: metadata initialization, API server, scheduler using LocalExecutor, and DAG processor.
- Build Airflow and ETL-worker ARM64 images in CI, embed matching DAG/code revisions, and deploy registry digests through the trusted release/bootstrap path.
- Provide SSH `on`, `off`, `status`, and `logs` operations plus the existing local PowerShell tunnel helper. Persist the requested on/off state independently of release directories.
- Make normal `off` drain existing work before stopping only Airflow services; report timeout/failure explicitly and never use project-wide `down` as the switch.
- Preserve the existing Airflow metadata database and logs during migration from the separate project. Separate metadata credentials from application credentials and keep UI access on localhost through SSH.
- Apply one shared ETL execution slot, explicit resource limits on DockerOperator containers, component-level health checks, and coordination with production backup/deploy/rollback.
- Document and verify on/off/on, interrupted startup/drain, state preservation across deployment, and one real bounded DAG execution while core application behavior remains available.
- Retire the separate Compose operational path only after migration acceptance. Existing local files are inputs to review, not assumed production-ready changes.
- Owner-approved scope extension on 7 November 2026: support explicit Memgraph selection in the existing KG graph writer, preserve Neo4j compatibility, and verify real destination persistence, retry idempotence and graph namespace isolation. This does not imply broader KG-001 acceptance.

## Capabilities

### New Capabilities

- `airflow-operations`: Integrated, resource-bounded Airflow deployment with persistent orchestration state, SSH lifecycle controls, and coordination with core releases.

### Modified Capabilities

None. `openspec list --specs --json` currently reports no promoted capability specs. DEP-001 explicitly excluded Airflow from its verified baseline; this change adds an acceptance boundary without rewriting its historical results or claiming ING-001/KG-001 complete.

## Impact

- Compose/images: `docker-compose.prod.yml`, `docker/airflow.Dockerfile`, `docker/etl-worker.Dockerfile`; eventual retirement of `docker-compose.airflow.yml` after cutover.
- Deployment/CI: `.gitlab-ci.yml`, `scripts/ci-build.sh`, `scripts/ci-integration.py`, `scripts/production-request.py`, `scripts/install-deployment-host.py`, `scripts/deploy-production.py`, and `scripts/deployment-readiness.py`.
- Operations/DAGs: `scripts/yunesa-airflow.sh`, `scripts/yunesa-airflow.ps1`, `orchestration/dags/etl_common.py`, lecturer/paper/KG DAGs, and worker command-contract coverage in `backend/package/yunesa/etl/tests/test_etl_dispatch.py`.
- Documentation and verification: `README.md`, `docs/deployment.md`, a future `docs/operations/airflow.md`, and focused deployment/operation integration checks.
- Real dependencies remain Docker Compose, PostgreSQL 16, Memgraph, Qdrant, and existing provider/scraping boundaries. No Kubernetes, Celery executor, new host, or RAM upgrade is proposed.
- No public Yunesa API change, academic schema redesign, destructive graph rebuild, production activation, commit, or push is authorized by this planning change. Existing deletion of `docs/database/supabase-schema.sql` remains outside scope.
