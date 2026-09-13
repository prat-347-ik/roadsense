# RoadSense Backend Overview & Dashboard Integration Guide

This document is the technical source of truth for frontend teammates building the **Step 7 Reviewer Dashboard** against the RoadSense backend. It reflects the exact, verified state of the codebase.

---

## 1. What This System Does

RoadSense is an automated traffic violation corroboration and human-in-the-loop review platform. Edge devices (such as dashcams and smart intersection sensors) monitor traffic and transmit lightweight metadata bursts whenever they detect potential traffic infractions—specifically **red-light violations** and **wrong-side driving**.

To eliminate false positives from edge-sensor glitches, momentary overtakes, or parked vehicles, the backend ingests these raw bursts, enforces strict privacy boundaries, and clusters observations spatio-temporally. For wrong-side violations, the system analyzes vehicle trajectory consistency and velocity progression. Only when independent devices corroborate a genuine violation does the backend trigger video evidence retrieval from the reporting edge devices.

**Critical Policy**: The system **never auto-enforces violations**. The backend acts strictly as an evidentiary pipeline. Every corroborated incident requires explicit human verification via the Reviewer Dashboard, where an authorized reviewer inspects video evidence, trajectory points, and telemetry before choosing to approve or reject the incident.

---

## 2. Architecture at a Glance

- **FastAPI**: Asynchronous Python API server managing device observation ingestion, reviewer authentication, incident lifecycle state transitions, and presigned media URL delivery.
- **PostgreSQL + PostGIS**: Relational datastore storing devices, hashed observations, candidate incidents, and evidence records with spatial PostGIS geometry/geography indexing.
- **Redis**: High-speed in-memory store provisioned for pub/sub, burst deduplication, and rate limiting infrastructure.
- **MinIO**: High-performance S3-compatible object storage for securely storing uploaded video and image evidence clips and serving time-limited presigned viewing URLs.
- **APScheduler (AsyncIOScheduler)**: Embedded background scheduler running directly inside the FastAPI process lifespan. Chosen over Celery Beat at this stage because it eliminates the operational overhead of running extra worker/beat daemon processes and extra broker dependencies while sharing the async SQLAlchemy connection pool for lightweight periodic database sweeps.

---

## 3. Data Model

All primary entities use `BigInteger` auto-incrementing primary keys (mapped to `Integer` under SQLite testing) and UTC timestamps.

### Database Tables & Schema Rationale

```
+------------------+         +----------------------------+         +----------------------+
|     devices      |         |   incident_observations    |         | candidate_incidents  |
+------------------+         +----------------------------+         +----------------------+
| device_id (PK)   |<---+    | incident_id (PK, FK)       |<------->| id (PK)              |
| public_key       |    +---| observation_id (PK, FK)    |    +--->| violation_type       |
| trust_score      |    |    +----------------------------+    |    | plate_no (HASH)      |
| registered_at    |    |                                  |    | geo_cluster          |
| status           |    |    +----------------------------+    |    | window_start         |
+------------------+    |    |        observations        |    |    | window_end           |
          ^             |    +----------------------------+    |    | status               |
          |             +--->| id (PK)                    |----+    | reviewed_by (FK) ----+
          |                  | device_id (FK)             |         | reviewed_at          |
          |                  | violation_type             |         +----------------------+
          |                  | plate_no (HASH)            |                    |
          |                  | lat, lon, location (Geog)  |                    |
          |                  | ts, event_nonce, signature |                    |
          |                  | wrong_way_status           |                    |
          |                  +----------------------------+                    |
          |                                                                    |
+------------------+         +----------------------------+                    |
|    reviewers     |<--------|          evidence          |                    |
+------------------+         +----------------------------+                    |
| id (PK)          |         | incident_id (PK, FK)       |<-------------------+
| email            |         | device_id (PK, FK)         |
| password_hash    |         | event_nonce (PK)           |
| role             |         | requested_at               |
| created_at       |         | uploaded_at                |
+------------------+         | storage_ref                |
                             | retention_expires_at       |
                             +----------------------------+
```

#### 1. `devices`
Tracks reporting edge hardware.
- `device_id` (`String(128)`, PK): Hardware identifier of the edge camera.
- `public_key` (`Text`): Public key used for cryptographic signature verification.
- `trust_score` (`Float`, default `0.5`): Reliability score weighting edge device reports.
- `registered_at` (`DateTime(timezone=True)`): Device provisioning timestamp.
- `status` (`String(32)`, default `'active'`): Operational state (`active`, `suspended`, `revoked`).

#### 2. `reviewers`
Authorized operators of the Step 7 dashboard.
- `id` (`BigInteger`, PK): Reviewer ID.
- `email` (`String(320)`, Unique): Reviewer login email.
- `password_hash` (`Text`): Bcrypt salted password hash.
- `role` (`String(32)`, default `'reviewer'`): Access tier (`reviewer`, `admin`).
- `created_at` (`DateTime(timezone=True)`): Account creation timestamp.

#### 3. `observations`
Raw burst detections ingested from edge devices.
- `id` (`BigInteger`, PK): Unique observation ID.
- `device_id` (`String(128)`, FK -> `devices.device_id`): Reporting device.
- `violation_type` (`String(32)`): `'wrong_side'` or `'red_light'`.
- `plate_no` (`Text`): **HMAC-SHA256 hash of the normalized license plate**. *Why:* Raw license plates represent PII and are irreversibly hashed at the ingestion boundary with `PLATE_HASH_KEY`. Plaintext plate numbers are never written to the database or logged.
- `lat`, `lon` (`Float`): Coordinates in decimal degrees.
- `location` (`Geography(Point, 4326)`): PostGIS geography point enabling spatial indexing and radius queries.
- `ts` (`DateTime(timezone=True)`): Edge capture timestamp.
- `event_nonce` (`String(128)`, Unique): UUID generated by the edge camera to ensure idempotent ingestion.
- `signature` (`Text`): Cryptographic payload signature from the device.
- `wrong_way_status` (`String(32)`, Nullable): Progression evaluation verdict (`'unconfirmed'`, `'confirmed'`, `'rejected'`). Always `NULL` for red-light violations.

#### 4. `candidate_incidents`
Clustered potential violations undergoing corroboration or review.
- `id` (`BigInteger`, PK): Incident ID referenced throughout dashboard.
- `violation_type` (`String(32)`): `'wrong_side'` or `'red_light'`.
- `plate_no` (`Text`): Hashed vehicle plate identifier matching clustered observations.
- `geo_cluster` (`Geography(Point, 4326)`): Centroid geography of clustered points.
- `window_start`, `window_end` (`DateTime(timezone=True)`): Time bounds spanning all linked observations.
- `status` (`String(32)`): Current lifecycle status (see status table below).
- `reviewed_by` (`BigInteger`, FK -> `reviewers.id`, Nullable): *Why:* Unambiguous audit trail recording exactly which authenticated reviewer made the final determination.
- `reviewed_at` (`DateTime(timezone=True)`, Nullable): *Why:* Timestamp when the reviewer approved or rejected the incident.

#### 5. `incident_observations`
Many-to-many join table linking `candidate_incidents.id` to `observations.id` with cascading deletion.

#### 6. `evidence`
Tracks media clip requests and uploads from edge devices.
- `incident_id` (`BigInteger`, FK -> `candidate_incidents.id`, Composite PK): Parent incident.
- `device_id` (`String(128)`, FK -> `devices.device_id`, Composite PK): Target device requested for clip.
- `event_nonce` (`String(128)`, Composite PK): Specific event nonce to retrieve.
- `requested_at` (`DateTime(timezone=True)`): *Why:* Records when the evidence request was queued, establishing the base time for TTL expiration calculation.
- `uploaded_at` (`DateTime(timezone=True)`, Nullable): Timestamp when the device completed media upload.
- `storage_ref` (`Text`, Nullable): Object path in MinIO (`minio://evidence/evidence/<nonce>.mp4`).
- `retention_expires_at` (`DateTime(timezone=True)`, Nullable): Evidence retention expiration date.

---

### Incident Status Values

| Status | Meaning & Lifecycle Stage | Dashboard Rendering Behavior |
| :--- | :--- | :--- |
| `candidate` | Initial state. Observations are grouped but have not met multi-device corroboration thresholds or progression criteria. | Display as "Pending Corroboration" / "Candidate". Review action buttons disabled (waiting for corroboration or sweep). |
| `corroborated` | Corroboration criteria satisfied (>= 2 devices, >= 2 valid observations). Evidence requests dispatched. Media uploaded or in-flight. | **Primary review queue item**. Display "Ready for Review", render video player / presigned media links, enable **Approve** and **Reject** buttons. |
| `corroborated_no_evidence` | Incident was corroborated, but device evidence upload TTL expired without receiving clips. | Display as "Corroborated (Missing Evidence)". Flag telemetry and lack of video. Still allows reviewer decision or dismissal. |
| `confirmed` | Human reviewer approved the violation (`POST /v1/incidents/{id}/approve`). Terminal state. | Display badge "Confirmed / Approved". Show reviewer email and reviewed timestamp. Disable review action buttons. |
| `rejected` | Violation dismissed by reviewer OR auto-rejected by progression/sweep algorithms. Terminal state. | Display badge "Rejected". Show rejection metadata / audit timestamp. Disable review action buttons. |

---

## 4. The Incident Lifecycle

```
[ Edge Device Burst ]
        |
        v
1. Ingestion & Privacy Boundary
   - Immediate HMAC-SHA256 plate hashing (raw plate discarded)
   - Idempotency check on event_nonce (409 on duplicate)
        |
        +----------------------------+
        | (wrong_side)               | (red_light)
        v                            v
2a. Trajectory Filter          2b. Skip Filter
   - Parked check (<8m / >3s)       (Straight to clustering)
   - Speed upper bound (>60m/s)
   - Bearing deviation (<60 deg)
   - Stale span check
        |
        v
3. Spatio-Temporal Clustering (100m radius, 300s window)
        |
        +---> Any observation rejected? --------> [ Status: REJECTED ] (Overrides corroboration)
        |
        +---> >=2 devices & >=2 confirmed obs?
                 |
                 +--- NO  ----------------------> [ Status: CANDIDATE ]
                 |                                      | (Ages past 300s solitary)
                 |                                      v
                 |                                [ Sweep: REJECTED (overtaking_artifact) ]
                 |
                 +--- YES ----------------------> [ Status: CORROBORATED ]
                                                        |
                                            +-----------+-----------+
                                            |                       |
                                    Evidence Uploaded       Evidence TTL Expired (30d)
                                            |                       |
                                            v                       v
                                   [ Ready for Review ]  [ Status: CORROBORATED_NO_EVIDENCE ]
                                            |                       |
                                            +-----------+-----------+
                                                        |
                                                        v
                                         4. Human Reviewer Action
                                            - POST /approve -> [ Status: CONFIRMED ]
                                            - POST /reject  -> [ Status: REJECTED ]
```

### Step-by-Step Flow:
1. **Ingestion & Normalization**: An edge camera posts a burst payload. The plate string is uppercase-normalized, whitespace-stripped, and HMAC-SHA256 hashed immediately.
2. **Progression Analysis (`wrong_side` only)**:
   - Evaluated against prior unconfirmed points for that hashed plate.
   - **Parked Check**: > 3 seconds elapsed with total movement <= 8.0 meters -> `REJECTED (parked)`.
   - **Speed Check**: Speed > 60.0 m/s (216 km/h) -> `REJECTED (unrealistic_speed)`.
   - **Bearing Consistency**: Intermediate trajectory bearing reversing or deviating > 60° from overall vector -> `REJECTED (inconsistent_trajectory)`.
   - **Valid Progression**: Distance >= 12.0m, speed >= 1.0 m/s, within 300s window -> `CONFIRMED`.
3. **Clustering & Evidence Triggering**:
   - Observations with identical violation type and hashed plate within 100 meters and 300 seconds are clustered.
   - **Rejection Propagation Rule**: *Crucial fix.* Only `confirmed` wrong-side observations (or any red-light observation) count toward corroboration thresholds. If **any** observation in an incident is `rejected`, the entire incident transitions to `rejected` immediately. A rejected trajectory cannot be salvaged or overridden by additional devices.
   - If >= 2 distinct devices and >= 2 valid observations match, status becomes `corroborated` and `evidence` request rows are inserted.
4. **Media Fetch & Reviewer Decision**:
   - Devices poll `/v1/evidence-requests` and upload clips to `/v1/evidence/{event_nonce}` stored in MinIO.
   - The Reviewer views the incident, plays the presigned video clip, and submits an Approval (`confirmed`) or Rejection (`rejected`).

---

### Critical Backend Guarantees (The Hardest-Won Fixes)

#### 1. Rejection Propagation is Absolute
- If a vehicle trajectory is flagged as `parked`, `unrealistic_speed`, `inconsistent_trajectory`, or `overtaking_artifact`, the entire incident becomes `rejected`.
- Even if an incident previously reached `corroborated`, a subsequent rejected observation for that cluster forces the incident to `rejected`.
- The dashboard can trust that `corroborated` incidents contain zero rejected trajectory segments.

#### 2. Isolated, Per-Incident Background Sweeps
Two scheduled background jobs run periodically in the FastAPI process:
- **`sweep_stale_observations`**: Runs every 60s. Finds single-observation `wrong_side` candidate incidents older than 300s and marks them `rejected` with reason `overtaking_artifact` (momentary lane cross rather than sustained wrong-way travel). **Strictly scoped to `wrong_side`** so `red_light` violations are never purged by progression aging.
- **`sweep_evidence_ttl`**: Runs hourly. Finds `corroborated` incidents where evidence request TTL (30 days default) has expired without receiving clips, transitioning them to `corroborated_no_evidence`.
- **Per-Incident Transaction Isolation**: Each candidate row is processed in its own independent database session and commit block. If one record has corrupt data or fails, it logs an error and skips cleanly—it **never rolls back or locks updates** for unrelated incidents.

---

## 5. API Reference for Dashboard Use

Base URL in development: `http://localhost:8000`

### Authentication Endpoints

#### `POST /v1/auth/login`
- **Auth**: None
- **Purpose**: Authenticate reviewer credentials and retrieve a JWT bearer token.
- **Request Body**:
  ```json
  {
    "email": "admin@roadsense.local",
    "password": "roadsense-admin-password"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "reviewer": {
      "id": 1,
      "email": "admin@roadsense.local",
      "role": "admin"
    }
  }
  ```
- **Error `401 UNAUTHORIZED`**: `{"detail": "Invalid email or password"}`

---

#### `GET /v1/auth/me`
- **Auth**: `Bearer <token>`
- **Purpose**: Retrieve identity and permissions of the currently authenticated reviewer.
- **Response `200 OK`**:
  ```json
  {
    "id": 1,
    "email": "admin@roadsense.local",
    "role": "admin",
    "created_at": "2026-09-13T10:00:00Z"
  }
  ```

---

### Incident Review Endpoints

#### `GET /v1/incidents`
- **Auth**: `Bearer <token>`
- **Purpose**: Fetch paginated list of candidate, corroborated, and reviewed incidents for table/queue views.
- **Query Parameters**:
  - `status` (optional, string): Filter by status (`candidate`, `corroborated`, `corroborated_no_evidence`, `confirmed`, `rejected`).
  - `violation_type` (optional, string): Filter by type (`wrong_side`, `red_light`).
  - `limit` (optional, int, default `50`, min `1`, max `200`): Results per page.
  - `offset` (optional, int, default `0`, min `0`): Pagination offset.
- **Response `200 OK`**:
  ```json
  [
    {
      "id": 12,
      "violation_type": "wrong_side",
      "hashed_plate": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "status": "corroborated",
      "window_start": "2026-09-13T18:00:00Z",
      "window_end": "2026-09-13T18:00:10Z",
      "observation_count": 2,
      "reviewed_by": null,
      "reviewed_at": null
    }
  ]
  ```

---

#### `GET /v1/incidents/{incident_id}`
- **Auth**: `Bearer <token>`
- **Purpose**: Fetch complete details for a single incident, including all underlying observation coordinates, telemetry, and presigned MinIO video URLs.
- **Response `200 OK`**:
  ```json
  {
    "id": 12,
    "violation_type": "wrong_side",
    "hashed_plate": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "status": "corroborated",
    "window_start": "2026-09-13T18:00:00Z",
    "window_end": "2026-09-13T18:00:10Z",
    "reviewed_by": null,
    "reviewed_at": null,
    "reviewer_email": null,
    "observations": [
      {
        "id": 101,
        "device_id": "CAM-MUM-001",
        "violation_type": "wrong_side",
        "hashed_plate": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "lat": 19.1197,
        "lon": 72.8468,
        "ts": "2026-09-13T18:00:00Z",
        "event_nonce": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
        "wrong_way_status": "confirmed"
      },
      {
        "id": 102,
        "device_id": "CAM-MUM-002",
        "violation_type": "wrong_side",
        "hashed_plate": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "lat": 19.1202,
        "lon": 72.8475,
        "ts": "2026-09-13T18:00:10Z",
        "event_nonce": "6a2f4c81-8e1a-4d43-85dc-9d41b6c7a401",
        "wrong_way_status": "confirmed"
      }
    ],
    "evidence_items": [
      {
        "device_id": "CAM-MUM-001",
        "event_nonce": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
        "uploaded_at": "2026-09-13T18:01:00Z",
        "storage_ref": "minio://evidence/evidence/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d.mp4",
        "view_url": "http://minio:9000/evidence/evidence/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d.mp4?X-Amz-Signature=...",
        "retention_expires_at": "2026-10-13T18:00:00Z"
      }
    ]
  }
  ```

---

#### `POST /v1/incidents/{incident_id}/approve`
- **Auth**: `Bearer <token>`
- **Purpose**: Reviewer approves violation. Sets `status = "confirmed"`, populates `reviewed_by` with reviewer ID from JWT, and records `reviewed_at`.
- **Response `200 OK`**:
  ```json
  {
    "status": "success",
    "incident_id": 12,
    "new_status": "confirmed",
    "reviewed_by": 1,
    "reviewed_at": "2026-09-13T18:15:30.123456Z"
  }
  ```

---

#### `POST /v1/incidents/{incident_id}/reject`
- **Auth**: `Bearer <token>`
- **Purpose**: Reviewer rejects violation. Sets `status = "rejected"`, populates `reviewed_by` and `reviewed_at`.
- **Response `200 OK`**:
  ```json
  {
    "status": "success",
    "incident_id": 12,
    "new_status": "rejected",
    "reviewed_by": 1,
    "reviewed_at": "2026-09-13T18:16:05.654321Z"
  }
  ```

---

### Other Endpoints (Device & Internal Ops)

These are not called directly by the dashboard frontend, but are useful context:
- `POST /v1/observations`: Edge camera ingest for observation bursts.
- `GET /v1/evidence-requests?device_id=...`: Edge camera poll for pending clip upload requests.
- `POST /v1/evidence/{event_nonce}`: Edge camera multipart file upload for MP4/image clips.
- `POST /v1/internal/sweep/stale-observations`: On-demand trigger for stale burst sweep.
- `POST /v1/internal/sweep/evidence-ttl`: On-demand trigger for evidence-TTL expiration sweep.
- `GET /health`: Basic health check (`{"status": "ok", "version": "0.1.0"}`).

---

## 6. What's Already There to Build Against

### Local Development Stack

Start the entire backend environment via Docker Compose:
```bash
docker compose up -d
```

| Service | Internal Port | Exposed Port | Purpose / Credentials |
| :--- | :--- | :--- | :--- |
| **FastAPI Backend** | `8000` | `http://localhost:8000` | Core API & Swagger Docs (`/docs`) |
| **PostgreSQL + PostGIS** | `5432` | `localhost:5433` | DB: `roadsense`, User/Pass: `roadsense`/`roadsense` |
| **Redis** | `6379` | `localhost:6379` | Cache / pub-sub |
| **MinIO API** | `9000` | `http://localhost:9000` | S3 API, User/Pass: `minioadmin`/`minioadmin` |
| **MinIO Console** | `9001` | `http://localhost:9001` | Storage Web UI |

### Pre-Seeded Reviewer Credentials
The database automatically seeds an initial administrator/reviewer account on container startup:
- **Email**: `admin@roadsense.local`
- **Password**: `roadsense-admin-password`

---

### Test Data Generator: `scripts/generate_synthetic_bursts.py`

Run the generator from within the `backend` environment or local Python venv:
```bash
python backend/scripts/generate_synthetic_bursts.py
```

This script seeds **9 realistic end-to-end scenarios**, populating all possible lifecycle statuses and edge cases to test your dashboard UI:

1. **Scenario 1: Corroborated Real Incident (`wrong_side`)**
   - 2 independent cameras, 10s / 60m apart.
   - **Result Status**: `corroborated` (with valid trajectory).
2. **Scenario 2: Parked Car False Positive (`wrong_side`)**
   - 3 bursts with sub-meter jitter (<8m over time).
   - **Result Status**: `rejected` (auto-rejected with `reason: parked`).
3. **Scenario 3: Overtaking Artifact False Positive (`wrong_side`)**
   - Single isolated burst aged out via internal sweep.
   - **Result Status**: `rejected` (auto-rejected with `reason: overtaking_artifact`).
4. **Scenario 4: Inconsistent Trajectory (`wrong_side`)**
   - Observations showing direction reversal (>60° bearing deviation).
   - **Result Status**: `rejected` (auto-rejected with `reason: inconsistent_trajectory`).
5. **Scenario 5: Red-Light Violation (`red_light`)**
   - 2 cameras at the same intersection reporting red light.
   - **Result Status**: `corroborated` (skips trajectory filter, requires device agreement).
6. **Scenario 6: Slow Corroboration / Stale Span (`wrong_side`)**
   - 2 bursts separated by 360 seconds (physically plausible but beyond standard 300s window).
   - **Result Status**: `candidate` (stays unconfirmed in queue).
7. **Scenario 7: Degraded GPS Jitter (`wrong_side`)**
   - Multiple bursts with 30–40m GPS noise within cluster radius.
   - **Result Status**: single `corroborated` cluster (proves spatial resilience).
8. **Scenario 8: Solitary Observation Baseline (`wrong_side`)**
   - Single report, no second device, sweep not yet run.
   - **Result Status**: `candidate` ("waiting for corroboration" baseline).
9. **Scenario 9: Evidence TTL Expiration (`wrong_side`)**
   - Corroborated incident where evidence requests timed out without upload.
   - **Result Status**: `corroborated_no_evidence`.

---

## 7. Known Gaps & Rough Edges

1. **Device Signature Verification is Stubbed**: `verify_signature()` in `backend/app/core/security.py` currently returns `True` as long as a non-empty signature string is provided. Asymmetric ECDSA/Ed25519 public key verification against `devices.public_key` is not yet enforced at ingest.
2. **Environment Secrets**: Default fallback values for `JWT_SECRET` (`"change-me-in-development"`) and `PLATE_HASH_KEY` (`"change-me-to-a-random-secret"`) are active in dev. In production, these must be set to 32+ byte cryptographically secure random values.
3. **No Self-Service Reviewer Registration Endpoint**: Reviewers cannot sign up via the API; accounts must be provisioned through seed scripts (`python -m app.db.seed`) or directly in the PostgreSQL database.
4. **MinIO Presigned URL Hostnames in Local Docker**: MinIO generates presigned URLs containing the internal Docker container endpoint (`http://minio:9000/...`). If testing the frontend directly on host browser outside Docker network, ensure `localhost:9000` is mapped or access MinIO through host port mappings. If MinIO is offline, the backend gracefully falls back to returning the raw storage reference string.
5. **Internal Sweep Endpoints are Unauthenticated**: `/v1/internal/sweep/...` endpoints do not check reviewer JWT headers so synthetic test scripts can trigger sweeps. In production deployment, these must be protected at the network firewall/mesh level.
