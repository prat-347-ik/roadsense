# RoadSense Backend Overview

## 1. What this system does

RoadSense receives bursts from dashcams that report two violation categories: `red_light` and `wrong_side`. Each burst includes a device ID, a license plate, a location, a capture timestamp, an event nonce, and a signature. The backend immediately normalizes and HMAC-hashes the plate, so raw plate text is not persisted or returned. It uses the event nonce to reject duplicate submissions.

For `wrong_side`, the backend checks whether observations over time describe a plausible moving trajectory. It groups related observations by hashed plate, violation type, time, and location, then requires independent corroboration before requesting video evidence. `red_light` observations skip the progression check but still need the corroboration thresholds. Evidence is stored in MinIO when a device uploads it.

A reviewer uses the incident API to inspect the observations and evidence, then approves or rejects the incident. Approval changes the incident to `confirmed`; rejection changes it to `rejected`. Nothing is auto-enforced: reviewer action is the authoritative decision.

## 2. Architecture at a glance

- **FastAPI app**: serves the `/health` endpoint, reviewer API, device observation/evidence API, and internal sweep triggers. APScheduler runs inside this process.
- **Postgres + PostGIS**: persists devices, observations, incidents, incident/observation links, evidence metadata, and reviewers; PostGIS stores observation and incident cluster points.
- **Redis**: exposed and configured through `REDIS_URL`, but the current application does not use it.
- **MinIO**: stores uploaded video/image evidence; the API returns a presigned `view_url` for stored evidence.
- **APScheduler**: runs the stale-observation sweep every 60 seconds and evidence-TTL sweep every 3600 seconds by default.

## 3. Data model

The migration creates the following tables. Plate values in both `observations` and `candidate_incidents` are HMAC-SHA256 hex strings, never raw plate text.

### `devices`

- `device_id`: string primary key; stable identifier of the reporting dashcam.
- `public_key`: text; intended public key for device signature verification. New devices are auto-registered with the placeholder `stub_public_key`.
- `trust_score`: float; device trust value, default `0.5`. It is stored but is not currently used in corroboration decisions.
- `registered_at`: timezone-aware timestamp; when the device record was created.
- `status`: string; device state. Database values are constrained to `active`, `suspended`, or `revoked`; new auto-registered devices are `active`.

### `observations`

- `id`: integer/bigint primary key; internal observation identifier.
- `device_id`: foreign key to `devices.device_id`; which dashcam reported the burst.
- `violation_type`: `wrong_side` or `red_light`.
- `plate_no`: text; HMAC-SHA256 hash of the normalized plate. It lets reports for the same plate be correlated without retaining the raw plate.
- `lat`: float; latitude in decimal degrees.
- `lon`: float; longitude in decimal degrees.
- `location`: PostGIS `geography(Point, 4326)` in Postgres, represented as a WKT point when using the SQLite test path; spatial point used for location clustering/indexing.
- `ts`: timezone-aware timestamp; capture time supplied by the device.
- `event_nonce`: unique string/UUID; idempotency key for the burst.
- `signature`: text; submitted device signature. Verification is currently a stub that accepts any non-empty signature.
- `wrong_way_status`: nullable string. For `wrong_side`, it is `unconfirmed`, `confirmed`, or `rejected`; `red_light` leaves it null. A rejected progression can have a reason in the service result, but the persisted field is currently just `rejected`.

### `candidate_incidents`

- `id`: integer/bigint primary key; incident identifier used by dashboard routes.
- `violation_type`: `wrong_side` or `red_light`.
- `plate_no`: text; HMAC-SHA256 plate hash shared by the linked observations.
- `geo_cluster`: PostGIS `geography(Point, 4326)`; centroid of the observation cluster. It is nullable in the ORM model but created as non-null in the initial Postgres migration.
- `window_start`: timezone-aware timestamp; earliest observation in the cluster.
- `window_end`: timezone-aware timestamp; latest observation in the cluster.
- `status`: one of `candidate`, `corroborated`, `corroborated_no_evidence`, `confirmed`, or `rejected`.
- `reviewed_by`: nullable foreign key to `reviewers.id`; reviewer who made the final approve/reject action.
- `reviewed_at`: nullable timestamp; when that reviewer action happened.

Status meanings and normal movement:

- `candidate`: observations are grouped, but corroboration thresholds have not been met. The dashboard should show this as awaiting more corroboration.
- `corroborated`: at least two distinct devices and at least two eligible observations agree; evidence records have been requested or are pending. This is reviewable while evidence is pending.
- `corroborated_no_evidence`: evidence did not arrive before the evidence TTL. It remains a corroborated incident with no uploaded evidence and should be visibly marked as evidence-expired/missing.
- `confirmed`: a reviewer approved the incident. This is the authoritative positive decision.
- `rejected`: progression, stale-observation handling, clustering policy, or a reviewer rejected the incident. A rejected observation can override an already-`corroborated` incident when that incident is re-evaluated.

### `incident_observations`

- `incident_id`: foreign key to `candidate_incidents.id`; linked incident.
- `observation_id`: foreign key to `observations.id`; linked observation.
- The pair is the composite primary key. This is the many-to-many link used to render an incident's observations.

### `evidence`

- `incident_id`: foreign key to `candidate_incidents.id`; parent incident.
- `device_id`: foreign key to `devices.device_id`; device asked to provide the clip.
- `event_nonce`: event whose clip was requested; together with `incident_id` and `device_id`, forms the composite primary key.
- `requested_at`: nullable timestamp; when evidence collection was requested.
- `uploaded_at`: nullable timestamp; when the device upload completed. Null means not uploaded.
- `storage_ref`: nullable text; MinIO object reference. Null means no stored file.
- `retention_expires_at`: nullable timestamp; requested retention deadline used by the evidence workflow.

### `reviewers`

- `id`: integer/bigint primary key; reviewer identity.
- `email`: unique string; login identifier.
- `password_hash`: bcrypt password hash; raw passwords are not stored.
- `role`: `reviewer` or `admin`; returned by login but not used for route authorization beyond requiring a reviewer account.
- `created_at`: timezone-aware timestamp; account creation time.

## 4. The incident lifecycle

1. **Device sends a burst.** `POST /v1/observations` validates the payload with Pydantic, immediately normalizes and HMAC-hashes `plate_no`, then checks `event_nonce`. A duplicate nonce returns HTTP `409`. The device is auto-registered as active if it does not exist. A non-empty signature is currently accepted by the signature-verification stub.

2. **Progression filtering.** For `wrong_side`, the service compares the new point with prior observations for the same hashed plate. It produces `confirmed`, `rejected`, or `unconfirmed`. Rejection reasons are `parked`, `unrealistic_speed`, `inconsistent_trajectory`, or `overtaking_artifact`. The first point is normally `unconfirmed`; a solitary point becomes `rejected` as `overtaking_artifact` when the stale sweep ages it past the corroboration window. For `red_light`, this progression step is skipped and `wrong_way_status` is null.

3. **Clustering.** Related observations are grouped by violation type and hashed plate, within the configured spatial and time limits. Defaults are a 100-meter cluster radius, geohash precision 7, and a 300-second corroboration window. The cluster stores its time window and centroid and is linked to a `candidate_incidents` row.

4. **Corroboration.** For `wrong_side`, only observations with `wrong_way_status == confirmed` count. For `red_light`, all observations count. Both types require at least 2 eligible observations from at least 2 distinct devices. An unconfirmed wrong-side report therefore leaves the incident `candidate`. If any wrong-side observation in the cluster is rejected, the whole incident becomes `rejected`; this can override an already-`corroborated` incident when a later burst causes re-evaluation. The evidence trigger does not request evidence after rejection.

5. **Evidence request.** Once corroborated, an evidence row is created for each contributing observation/device, with `requested_at` and a retention deadline. Devices poll for their pending requests and upload clips separately. The dashboard reads evidence through incident detail; it does not request evidence itself.

6. **Background sweeps.** The stale-observation sweep runs every 60 seconds by default. It rejects candidate incidents with exactly one old observation as `overtaking_artifact`. The evidence-TTL sweep runs every 3600 seconds by default. It changes `corroborated` to `corroborated_no_evidence` when requested evidence has not arrived before the configured 30-day TTL. Both sweeps can also be triggered through internal endpoints for local testing.

7. **Human review.** A reviewer loads the incident, linked observations, and evidence, then calls approve or reject. Approval writes `reviewed_by` and `reviewed_at` and sets status to `confirmed`. Rejection writes the same audit fields and sets status to `rejected`. This is the only authoritative decision step.

## 5. API reference for dashboard use

All paths below are relative to the API origin, normally `http://localhost:8000`. Reviewer endpoints require `Authorization: Bearer <JWT>` from `/v1/auth/login`.

### `POST /v1/auth/login`

- **Auth**: none.
- **Request**: JSON `{ "email": string, "password": string }`.
- **Response**: `{ "access_token": string, "token_type": "bearer", "reviewer": { "id": number, "email": string, "role": string } }`.
- **Purpose**: authenticate a reviewer and obtain the JWT for dashboard calls. Invalid credentials return HTTP `401`.

### `GET /v1/incidents`

- **Auth**: reviewer JWT required.
- **Query**: optional `status` (exact incident status), optional `violation_type` (`wrong_side` or `red_light`), `limit` (default 50, maximum 200), and `offset` (default 0).
- **Response**: JSON array of `{ "id": number, "violation_type": string, "hashed_plate": string, "status": string, "window_start": timestamp, "window_end": timestamp, "observation_count": number, "reviewed_by": number|null, "reviewed_at": timestamp|null }`, ordered newest `window_end` first.
- **Purpose**: populate the dashboard incident queue and filter it by status/type.

### `GET /v1/incidents/{id}`

- **Auth**: reviewer JWT required.
- **Request**: no body; `{id}` is the numeric incident ID.
- **Response**: `{ "id": number, "violation_type": string, "hashed_plate": string, "status": string, "window_start": timestamp, "window_end": timestamp, "reviewed_by": number|null, "reviewed_at": timestamp|null, "reviewer_email": string|null, "observations": [ { "id": number, "device_id": string, "violation_type": string, "hashed_plate": string, "lat": number, "lon": number, "ts": timestamp, "event_nonce": string, "wrong_way_status": string|null } ], "evidence_items": [ { "device_id": string, "event_nonce": string, "uploaded_at": timestamp|null, "storage_ref": string|null, "view_url": string|null, "retention_expires_at": timestamp|null } ] }`.
- **Purpose**: render the incident detail, progression outcomes, and evidence links. Missing incidents return HTTP `404`.

### `POST /v1/incidents/{id}/approve`

- **Auth**: reviewer JWT required.
- **Request**: no body.
- **Response**: `{ "status": "success", "incident_id": number, "new_status": "confirmed", "reviewed_by": number, "reviewed_at": timestamp }`.
- **Purpose**: record the authenticated reviewer's authoritative approval.

### `POST /v1/incidents/{id}/reject`

- **Auth**: reviewer JWT required.
- **Request**: no body.
- **Response**: `{ "status": "success", "incident_id": number, "new_status": "rejected", "reviewed_by": number, "reviewed_at": timestamp }`.
- **Purpose**: record the authenticated reviewer's authoritative rejection.

### Device-facing endpoints (dashboard does not call these directly)

- `POST /v1/observations`: no auth currently. Request fields are `device_id`, `violation_type`, `plate_no`, `lat`, `lon`, `timestamp`, `event_nonce`, and `sig`; response is `{status, event_nonce, hashed_plate, message}`. It returns HTTP `201` when accepted.
- `GET /v1/evidence-requests?device_id=...`: no auth currently. Returns an array of `{incident_id, device_id, event_nonce, violation_type, requested_at, retention_expires_at}` for that device's unuploaded requests.
- `POST /v1/evidence/{event_nonce}`: no auth currently; multipart field `file`. Returns `{status, event_nonce, storage_ref, uploaded_at}` after storing the file.

`GET /health` is also available without auth and returns `{ "status": "ok", "version": "0.1.0" }`.

## 6. What's already there to build against

### Local development stack

From the repository root:

```text
docker compose up
```

The API container runs migrations, seeds the default reviewer, and listens on `http://localhost:8000`. The default local services are:

- API: host port `8000` -> container port `8000`
- Postgres/PostGIS: host port `5433` -> container port `5432`; database `roadsense`, user `roadsense`, password `roadsense`
- Redis: host port `6379`
- MinIO API: host port `9000`
- MinIO console: host port `9001`

The default MinIO console credentials are `minioadmin` / `minioadmin` from `docker-compose.yml`. The API's default local reviewer is:

- Email: `admin@roadsense.local`
- Password: `roadsense-admin-password`
- Role: `admin`

### Synthetic burst generator

Run it with the stack up:

```text
python backend/scripts/generate_synthetic_bursts.py
```

It sends nine independent scenarios and uses the reviewer login to assert incident results. Each scenario produces the following test data:

1. **Corroborated real incident (`wrong_side`)**: two cameras, two moving observations; status `corroborated` and evidence requests created.
2. **Parked-car false positive (`wrong_side`)**: three near-stationary bursts; progression rejects them as `parked`; status `rejected`.
3. **Overtaking-artifact false positive (`wrong_side`)**: one burst, then stale-observation sweep with a zero-second override; status changes from `candidate` to `rejected` with `overtaking_artifact` behavior.
4. **Inconsistent trajectory (`wrong_side`)**: three reports with a reversal; status `rejected` with `inconsistent_trajectory` behavior.
5. **Red-light violation (`red_light`)**: two cameras at one intersection; progression is skipped; status `corroborated` and evidence requests created.
6. **Stale-span unconfirmed (`wrong_side`)**: two plausible bursts 360 seconds apart, beyond the 300-second progression window; observations remain `unconfirmed`; status `candidate`.
7. **Degraded-GPS burst (`wrong_side`)**: two cameras with reproducible GPS jitter within the 100-meter radius; one incident, status `corroborated`.
8. **Never-corroborated flag (`wrong_side`)**: one burst with no sweep; status `candidate`.
9. **Evidence-TTL exhaustion (`wrong_side`)**: two corroborating bursts, no evidence upload, then TTL sweep with a zero-day override; status `corroborated_no_evidence`.

The generator uses unique random plates per scenario, so its output accumulates unless the database volumes are removed. It can run one case with `--scenario N` and can target another API origin with `--base-url URL`.

## 7. Known gaps / things the dashboard needs to account for

- Device signature verification is explicitly stubbed: any non-empty `sig` is accepted, and auto-registered devices receive `stub_public_key`.
- Device observation/evidence endpoints and the internal sweep endpoints have no application-level authentication. Internal sweep routes are intended to be network/firewall protected in production.
- Redis is present in Compose and configuration but is not currently used for caching, queues, or coordination.
- The dashboard receives only the deterministic `hashed_plate`, not the raw plate. It cannot display or search by the original plate number.
- Progression rejection reasons are not exposed as a separate observation API field. Incident detail exposes `wrong_way_status: "rejected"`, but the reason (`parked`, `unrealistic_speed`, `inconsistent_trajectory`, or `overtaking_artifact`) is not persisted in its own column or returned in the reviewer response.
- Review action endpoints accept no reason or note. The audit trail contains reviewer identity and timestamp only.
- Approve/reject routes do not enforce a status transition policy in the endpoint; they set the requested final status for any existing incident.
- Evidence detail exposes `storage_ref` as well as a presigned `view_url`. A missing `storage_ref` produces `view_url: null`; the frontend should handle pending evidence without a playable URL.
- `corroborated_no_evidence` is a terminal timeout state in the sweep logic, but the review endpoints can still set an existing incident to `confirmed` or `rejected`.
- The configured default secrets (`JWT_SECRET`, `PLATE_HASH_KEY`, and MinIO credentials) are development placeholders and must be replaced outside local development.
- CORS currently allows all origins with credentials enabled, which is suitable only as a development convenience.
- APScheduler is embedded in the API process. If the package is absent, the jobs are disabled and only manually triggered sweeps work.
- The Postgres migration models `location` and `geo_cluster` as PostGIS geography, while the ORM annotations are text-oriented and the SQLite test path stores WKT strings. Frontend responses provide `lat`/`lon` for observations; there is no location geometry in the incident API response.
