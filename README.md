# RoadSense

RoadSense is a privacy-aware traffic incident corroboration and human-review platform. Edge devices submit lightweight observations for suspected red-light and wrong-side driving events. The backend validates and clusters those observations, requests supporting evidence when independent devices agree, and gives an authorized reviewer the final decision.

> RoadSense is an evidentiary decision pipeline. It does not automatically enforce traffic violations.

## Project Status

**Current milestone: reviewer dashboard, corroboration backend, and Track 1 edge CV prototype complete.**

The repository currently includes:

- FastAPI backend with asynchronous SQLAlchemy and Alembic migrations.
- PostgreSQL/PostGIS data model for devices, observations, incidents, reviewers, and evidence.
- Redis and MinIO services provisioned through Docker Compose.
- HMAC-SHA256 plate hashing at ingestion; raw plate values are not persisted.
- Idempotent observation ingestion using the device event nonce.
- Wrong-side progression checks for parked vehicles, unrealistic speed, stale observations, and inconsistent trajectories.
- Spatio-temporal clustering and independent-device corroboration thresholds.
- Evidence request, upload, retention, and presigned URL workflows.
- JWT reviewer authentication with bcrypt password hashing and audited approve/reject actions.
- Scheduled stale-observation and evidence-TTL sweeps with per-incident failure isolation.
- React/Vite reviewer dashboard with login, incident list/filtering, incident detail, map, evidence player, status badges, and review actions.
- Automated tests for privacy boundaries, security, API behavior, clustering, progression, evidence, and sweep scenarios.
- Track 1 edge prototype with pretrained YOLOv8 vehicle/traffic-light detection and HSV traffic-light color classification.
- Reproducible 25-frame `yolov8n`/`yolov8s` comparison tooling under `edge/detection/`.

## Delivery Plan

### Completed

1. Define the evidentiary workflow and incident lifecycle.
2. Establish the privacy boundary for license-plate data.
3. Build validated observation ingestion with duplicate protection.
4. Add wrong-side progression analysis and false-positive rejection rules.
5. Add spatial and temporal clustering across independent devices.
6. Trigger evidence collection only for corroborated incidents.
7. Build reviewer authentication, incident review, and audit fields.
8. Add evidence storage integration and retention handling.
9. Add background sweeps for stale candidates and expired evidence.
10. Deliver the initial reviewer dashboard.

### Next

- Replace the current device-signature verification stub with production public-key verification and device registration flows.
- Add production deployment configuration, secret management, and environment-specific CORS policies.
- Add device-facing SDK or reference client for observation and evidence exchange.
- Complete operational observability: metrics, dashboards, alerting, and documented incident response.
- Expand browser-level dashboard tests and add end-to-end tests against containerized dependencies.
- Harden reviewer administration, role permissions, pagination, and audit-log presentation.
- Evaluate moving scheduled sweeps to dedicated workers as throughput and deployment scale increase.

## Architecture

```text
Edge devices
    |
    | observation bursts and evidence uploads
    v
FastAPI API
    |-- privacy boundary: normalize + HMAC plate hash
    |-- progression and clustering
    |-- evidence requests and reviewer actions
    |-- APScheduler background sweeps
    |
    +--> PostgreSQL + PostGIS  (durable relational and spatial data)
    +--> Redis                 (provisioned for cache, rate limits, and pub/sub)
    +--> MinIO                 (S3-compatible evidence storage)
    |
    v
React reviewer dashboard
```

### Incident lifecycle

```text
observation
    -> candidate
    -> corroborated
    -> confirmed       (reviewer approval)
    -> rejected        (reviewer decision or safety rule)

corroborated -> corroborated_no_evidence
              (evidence retention window expires without upload)
```

Wrong-side observations must pass progression checks before they count toward corroboration. Red-light observations skip trajectory progression. A rejected trajectory propagates rejection to the incident so that invalid evidence cannot be rescued by later observations.

## Repository Layout

```text
backend/
  app/
    api/v1/       API routes for auth, observations, evidence, and incidents
    core/         settings, security, errors, logging, and Sentry integration
    models/       SQLAlchemy entities
    services/     geo, progression, clustering, storage, and sweeps
  migrations/     Alembic migration history
  tests/          backend unit and API tests
edge/
  detection/      YOLO vehicle/traffic-light detection and OpenCV light-color classification
frontend/
  src/
    components/   map, evidence, navigation, and status UI
    pages/        login, incident list, and incident detail views
    services/     typed API client
```

## Quick Start with Docker

### Prerequisites

- Docker Desktop with Compose.
- Node.js 18+ and npm for local frontend development.
- Python 3.12+ and a virtual environment for local backend development.

### 1. Configure local secrets

Create a `.env` file in the repository root. The Compose defaults are suitable only for local development; replace these values before any shared or production deployment.

```dotenv
JWT_SECRET=replace-with-a-long-random-secret
PLATE_HASH_KEY=replace-with-a-different-long-random-secret
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=replace-with-a-local-minio-password
AUTO_INIT_DB=false
```

### 2. Start backend dependencies and API

```powershell
docker compose up --build
```

The API is available at `http://localhost:8000` and its health endpoint is `http://localhost:8000/health`. The Compose setup exposes PostgreSQL on port `5433`, Redis on `6379`, MinIO API on `9000`, and the MinIO console on `9001`.

The API container runs Alembic migrations, seeds the configured default reviewer, and starts Uvicorn automatically.

### 3. Start the frontend

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal. The frontend expects the API routes to be available through the configured Vite development proxy or a same-origin deployment.

## Local Backend Development

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
cd backend
uvicorn app.main:app --reload
```

For a standalone local database, set `DATABASE_URL`, `AUTO_INIT_DB`, and the storage settings in `.env`. The default application configuration is designed around the Docker Compose service names.

## Testing and Builds

Run the backend tests from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
pytest backend\tests
```

Build the frontend:

```powershell
cd frontend
npm run build
```

The backend API tests use an in-memory SQLite database where possible. Production behavior depends on PostgreSQL/PostGIS, Redis, and MinIO, so containerized integration testing remains part of the planned hardening work.

### Edge CV Evaluation

The evaluator uses 25 frames spread across clips from `C:\Users\Pratik\Project_Repos\datasets\extracted_frames` and requires the project virtual environment plus Ultralytics weights. Run a model comparison with:

```powershell
.\.venv\Scripts\python edge\detection\evaluate_sample.py --model yolov8n.pt
.\.venv\Scripts\python edge\detection\evaluate_sample.py --model yolov8s.pt --output-dir edge\detection\evaluation_output\yolov8s
```

Weights and generated visualizations are ignored by Git. The current comparison is documented in the project vault's `10 Research/Experiments.md`.

## API Surface

The versioned API is rooted at `/v1`:

| Area | Routes | Purpose |
| --- | --- | --- |
| Health | `GET /health` | Service liveness and version |
| Auth | `/v1/auth/*` | Reviewer login and current-user access |
| Observations | `POST /v1/observations` | Ingest validated edge bursts |
| Incidents | `/v1/incidents/*` | List, inspect, approve, and reject incidents |
| Evidence | `/v1/evidence*` | Request polling, upload, and media access |

See [BACKEND_OVERVIEW.md](BACKEND_OVERVIEW.md) for the detailed data model, lifecycle rules, endpoint payloads, and operational guarantees.

## Privacy and Safety Principles

- Raw license plates are normalized and HMAC-hashed at the ingestion boundary.
- Validation errors, logs, and Sentry payloads redact raw plate values.
- Evidence is stored through object storage references and time-limited access URLs.
- Corroboration requires independent devices and valid observations.
- A human reviewer must approve an incident before it becomes confirmed.
- Rejected trajectory evidence cannot be overridden by later corroboration.

## Contributing

Keep changes focused on the relevant backend service, API route, frontend view, or test slice. Add or update tests for behavior changes, keep secrets out of source control, and document changes to lifecycle rules or privacy guarantees in [BACKEND_OVERVIEW.md](BACKEND_OVERVIEW.md).

## License

No license file has been added to this repository yet.