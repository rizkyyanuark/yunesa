# Spec Delta

## Purpose

Let the Yunesa owner operate integrated Airflow through SSH while preserving application availability, orchestration history, bounded ETL execution, and trusted release behavior.

## ADDED Requirements

### Requirement: Optional integrated orchestration
The production deployment SHALL include Airflow in the same managed application project as an optional ETL profile. Starting the core application alone MUST NOT activate Airflow, and stopping Airflow MUST NOT stop or recreate core services.

#### Scenario: Core-only startup
- **WHEN** the application starts with ETL disabled
- **THEN** core services start without requiring running Airflow components
- **AND** no ETL task container is created

#### Scenario: Airflow is disabled while the application is serving users
- **WHEN** the owner successfully turns Airflow off
- **THEN** core container identities remain unchanged
- **AND** application health, authenticated API access, and the existing queued chat path remain available

### Requirement: Authorized SSH lifecycle operations
The system SHALL expose on, off, status, and logs operations to an authorized SSH administrator. The local helper SHALL propagate remote failures and provide an SSH tunnel to the loopback-only authenticated Airflow UI without printing credentials.

#### Scenario: Owner operates from Windows
- **WHEN** the owner invokes a supported operation through the PowerShell helper
- **THEN** the helper invokes the managed host operation and returns its success or failure exit status

#### Scenario: Unsupported operation or unauthorized access
- **WHEN** an unsupported operation is requested or the caller lacks administrative authorization
- **THEN** the operation fails without changing lifecycle state or services

#### Scenario: UI access
- **WHEN** the owner opens the configured SSH tunnel
- **THEN** the UI is reachable locally and requires Airflow authentication
- **AND** the Airflow UI port is not published on a public server interface

### Requirement: Successful start requires component readiness
The on operation SHALL return success only when metadata access, API access, scheduler heartbeat, and DAG processor heartbeat are healthy and required DAGs import successfully. Initialization or readiness failure MUST produce a nonzero result with a redacted actionable reason.

#### Scenario: Start from off
- **WHEN** on is requested with valid dependencies and credentials
- **THEN** Airflow initializes as needed, reaches component readiness, and permits managed work

#### Scenario: HTTP succeeds but scheduler is unhealthy
- **WHEN** the health endpoint returns HTTP 200 but a required component is unhealthy
- **THEN** on does not report readiness success

#### Scenario: Startup deadline or migration failure
- **WHEN** readiness exceeds its configured deadline or metadata initialization fails
- **THEN** on returns nonzero, keeps new ETL work blocked, and reports the failing phase
- **AND** core services remain available

### Requirement: Drain before normal shutdown
The off operation SHALL block new managed task execution, wait for executing tasks and their worker containers to finish, and stop only Airflow services. Queued work MUST remain recoverable. A drain deadline MUST fail visibly without killing active workers or claiming off is complete.

#### Scenario: Off during a running task
- **WHEN** off is requested while an ETL task executes and another task is queued
- **THEN** the running task can finish but the queued task cannot start
- **AND** off succeeds only after execution and worker-container counts reach zero and Airflow services stop
- **AND** queued work retains a resumable state

#### Scenario: Drain timeout
- **WHEN** active execution does not finish before the configured deadline
- **THEN** off returns nonzero with active run/task identifiers
- **AND** admission remains closed, active workers are not killed, and status reports draining or failed shutdown

#### Scenario: Repeated off
- **WHEN** off is requested after a completed shutdown
- **THEN** it succeeds without removing volumes or modifying core services

#### Scenario: Initialization remains active after interrupted startup
- **WHEN** the owner requests off while a metadata initialization container remains running
- **THEN** admission stays closed and off waits for initialization to finish
- **AND** a deadline returns nonzero with draining state and leaves the initialization process intact
- **AND** status cannot report observed off while initialization remains active
- **AND** a subsequent on cannot replace active initialization and metadata backup is rejected until it finishes

### Requirement: Persist requested state and preserve scheduling intent
The system SHALL preserve requested on/off state across release changes and host restart, distinguish it from observed health, and restore pre-shutdown DAG pause choices on successful restart. It MUST preserve existing schedules and catchup settings without automatically replaying every missed interval.

#### Scenario: Deploy after explicit off
- **WHEN** a release is deployed or rolled back after the owner turned Airflow off
- **THEN** Airflow remains off and historical metadata and queued work remain stored

#### Scenario: Resume after a scheduled interval was missed
- **WHEN** on completes after an off interval
- **THEN** DAGs previously paused by the owner remain paused
- **AND** only lifecycle-induced pauses are restored
- **AND** configured catchup behavior determines scheduled work while explicit manual runs remain possible

#### Scenario: Lifecycle interrupted or state invalid
- **WHEN** lifecycle state is corrupt, absent on a fresh installation, or records an incomplete transition
- **THEN** new ETL execution remains closed until a validated recovery or explicit on completes
- **AND** status identifies the actual state rather than inferring success from intent

### Requirement: Persistent metadata and logs
Airflow metadata, run history, credentials needed to interpret stored configuration, task logs, and queued work SHALL survive off/on and migration from the separate installation. Migration MUST fail rather than replace existing metadata with an empty database or discard inaccessible logs.

#### Scenario: Move existing installation
- **WHEN** the separate installation is migrated into the application project
- **THEN** recorded DAG/run identifiers, metadata row counts, and retained log samples remain verifiable
- **AND** only one scheduler installation is allowed to execute managed work

#### Scenario: Stop and restart
- **WHEN** Airflow is turned off and on again
- **THEN** prior run status and retained task logs remain accessible

### Requirement: Bounded execution resources
All managed lecturer, paper, and KG tasks SHALL share a single heavy-task execution slot initially. Every launched ETL worker MUST have explicit memory and CPU allocation controls; health/status MUST expose worker resource usage and exhaustion without labeling failed work successful.

#### Scenario: Two DAGs become runnable
- **WHEN** tasks in two managed DAGs are eligible simultaneously
- **THEN** no more than one heavy ETL task executes at a time across those DAGs

#### Scenario: Worker exceeds its memory limit
- **WHEN** a worker is terminated for memory exhaustion
- **THEN** the task is reported failed or eligible for its bounded retry policy
- **AND** the failure identifies the resource cause where observable
- **AND** the system does not return a fabricated successful output

#### Scenario: Core queue worker health observation
- **WHEN** the core queue worker healthcheck runs alongside orchestration
- **THEN** it checks the existing ARQ heartbeat without importing application job handlers
- **AND** a live worker passes while an absent heartbeat or invalid Redis configuration fails

### Requirement: Coordinate lifecycle with release and backup
Airflow operations, deploy, rollback, and backup SHALL serialize conflicting transitions and close ETL admission before storage snapshots or replacement. A busy or failed quiescence check MUST prevent cutover; successful operations MUST restore the owner's requested state with matching release assets.

#### Scenario: Deploy while ETL writes storage
- **WHEN** deployment encounters a running ETL worker
- **THEN** it drains work before backing up or replacing shared services
- **AND** a failed drain aborts cutover without interrupting that worker

#### Scenario: Concurrent on and deploy
- **WHEN** on races with a deployment holding the lifecycle lock
- **THEN** one operation is serialized or fails as busy before it changes services
- **AND** no worker starts against storage undergoing backup or cutover

#### Scenario: Rollback while Airflow was on
- **WHEN** rollback restores a compatible prior release after quiescence
- **THEN** Airflow uses that release's corresponding assets and resumes only after readiness
- **AND** incompatible metadata restoration requires a verified recovery procedure rather than an assumed image-only rollback

### Requirement: Release provenance and secret boundaries
Airflow, DAGs, and worker code SHALL have verifiable release identities and production images MUST be addressed by immutable registry digests. Metadata and UI authentication secrets MUST remain out of source, logs, and unprivileged status output; unsupported release inputs MUST be rejected.

#### Scenario: Mutable or untrusted image reference
- **WHEN** a deployment request provides an ETL image tag without a digest or from an unauthorized registry prefix
- **THEN** the request is rejected before service changes

#### Scenario: Release code consistency
- **WHEN** a DAG launches its worker
- **THEN** the DAG and worker image identities correspond to the recorded release
- **AND** production does not depend on a mutable laptop or host source-code mount

### Requirement: KG writer supports the deployed graph backend
The existing graph-store worker command SHALL support explicitly selected Memgraph and retain Neo4j compatibility. Memgraph writes MUST use its actual Bolt/authentication/schema interfaces, preserve graph namespace isolation, remain idempotent on retry, and propagate connection, schema and write failures rather than report fabricated success.

#### Scenario: Managed KG run writes Memgraph
- **WHEN** a bounded managed KG DAG enables graph persistence with the Memgraph backend
- **THEN** actual destination queries return the expected nodes, relationships and publication properties
- **AND** repeating the write does not duplicate nodes or relationships

#### Scenario: Clear one graph namespace
- **WHEN** an explicitly requested clear-and-write targets one graph name
- **THEN** other graph namespaces remain unchanged

#### Scenario: Unsupported backend or rejected write
- **WHEN** backend configuration is invalid or Memgraph rejects schema/data writes
- **THEN** the worker returns failure and does not silently switch backend or report success

### Requirement: Operational acceptance uses the real path
Acceptance SHALL include on/off/on through SSH, a bounded real DAG using the production worker entrypoint and actual isolated storage, and core application checks during execution. Peak resources, restart/OOM events, persisted output, and unverified external boundaries MUST be recorded explicitly.

#### Scenario: Bounded DAG smoke
- **WHEN** the acceptance DAG completes against an isolated namespace of the real dependencies
- **THEN** its output is queried from the actual destination and tied to the run and release identities
- **AND** resource samples and application health/authenticated API/queued chat results are recorded
- **AND** a successful import test alone does not count as this execution proof
