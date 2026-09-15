import io
import uuid
from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_async_db
from app.core.logging_config import PlateRedactionFilter
from app.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    hash_plate,
    verify_password,
)
from app.core.sentry import sentry_before_send
from app.main import app
from app.models.entities import Base, CandidateIncident, Device, Evidence, Observation, Reviewer


# In-memory SQLite with StaticPool so all async sessions share the exact same database
test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
    future=True,
)
TestAsyncSession = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def override_get_async_db():
    async with TestAsyncSession() as session:
        yield session


app.dependency_overrides[get_async_db] = override_get_async_db


@pytest_asyncio.fixture(autouse=True)
async def setup_test_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def reviewer_user():
    async with TestAsyncSession() as db:
        reviewer = Reviewer(
            email="auditor@roadsense.gov",
            password_hash=get_password_hash("securePassword123!"),
            role="reviewer",
        )
        db.add(reviewer)
        await db.commit()
        await db.refresh(reviewer)
        return reviewer


@pytest.fixture
def auth_header(reviewer_user):
    token = create_access_token(
        subject=reviewer_user.id,
        claims={"email": reviewer_user.email, "role": reviewer_user.role},
    )
    return {"Authorization": f"Bearer {token}"}


# -------------------------------------------------------------
# 1. Privacy & Redaction Boundary Tests
# -------------------------------------------------------------


@pytest.mark.asyncio
async def test_validation_error_redacts_raw_plate():
    """Verify that validation errors on plate_no never echo raw text to the client."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        secret_raw_plate = "SECRET_SUPER_LONG_PLATE_12345"
        payload = {
            "device_id": "cam-101",
            "violation_type": "wrong_side",
            "plate_no": secret_raw_plate,  # > 16 chars (invalid)
            "lat": 18.5204,
            "lon": 73.8567,
            "timestamp": "2026-09-12T10:00:00Z",
            "event_nonce": str(uuid.uuid4()),
            "sig": "sig123",
        }
        response = await ac.post("/v1/observations", json=payload)
        assert response.status_code == 422
        resp_text = response.text
        # The secret raw plate must NEVER appear in the response payload
        assert secret_raw_plate not in resp_text
        assert "invalid plate_no format" in resp_text


def test_sentry_before_send_strips_plate_no():
    """Verify Sentry before_send callback strips raw plate_no from all payloads."""
    raw_event = {
        "request": {
            "data": {
                "plate_no": "DL01AB9999",
                "device_id": "cam-99",
            },
            "query_string": "plate_no=DL01AB9999&limit=10",
        },
        "breadcrumbs": {
            "values": [
                {"data": {"plate_no": "DL01AB9999", "action": "scan"}}
            ]
        },
        "extra": {
            "plate_no": "DL01AB9999",
            "hashed_plate": "a1b2c3d4",
        },
    }

    sanitized = sentry_before_send(raw_event, {})
    assert sanitized["request"]["data"]["plate_no"] == "[REDACTED]"
    assert sanitized["request"]["data"]["device_id"] == "cam-99"
    assert sanitized["breadcrumbs"]["values"][0]["data"]["plate_no"] == "[REDACTED]"
    assert sanitized["extra"]["plate_no"] == "[REDACTED]"
    assert sanitized["extra"]["hashed_plate"] == "a1b2c3d4"


def test_plate_redaction_filter():
    """Verify logging filter scrubs plate patterns."""
    import logging

    record = logging.LogRecord(
        name="roadsense",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Obs received with plate_no=MH12AB1234 from device 1",
        args=(),
        exc_info=None,
    )
    filter_obj = PlateRedactionFilter()
    filter_obj.filter(record)
    assert "MH12AB1234" not in record.msg
    assert "[REDACTED]" in record.msg


# -------------------------------------------------------------
# 2. Reviewer Auth & BCrypt Tests
# -------------------------------------------------------------


def test_password_hashing_bcrypt():
    password = "SuperSecretPassword123!"
    hashed = get_password_hash(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_token_generation_and_decoding():
    token = create_access_token(subject=42, claims={"email": "reviewer@roadsense.gov", "role": "admin"})
    decoded = decode_access_token(token)
    assert decoded["sub"] == "42"
    assert decoded["email"] == "reviewer@roadsense.gov"
    assert decoded["role"] == "admin"


@pytest.mark.asyncio
async def test_reviewer_login_flow(reviewer_user):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Valid login
        resp = await ac.post(
            "/v1/auth/login",
            json={"email": "auditor@roadsense.gov", "password": "securePassword123!"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["reviewer"]["email"] == "auditor@roadsense.gov"

        # Invalid login
        resp_invalid = await ac.post(
            "/v1/auth/login",
            json={"email": "auditor@roadsense.gov", "password": "wrong-password"},
        )
        assert resp_invalid.status_code == 401


# -------------------------------------------------------------
# 3. Observation API & Idempotency / 409 Conflict Tests
# -------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_observation_success_and_duplicate_409():
    nonce = str(uuid.uuid4())
    payload = {
        "device_id": "cam-001",
        "violation_type": "wrong_side",
        "plate_no": "MH12AB1234",
        "lat": 18.5204,
        "lon": 73.8567,
        "timestamp": "2026-09-12T10:00:00Z",
        "event_nonce": nonce,
        "sig": "sig123",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. First submission -> 201 Created
        resp1 = await ac.post("/v1/observations", json=payload)
        assert resp1.status_code == 201
        data1 = resp1.json()
        assert data1["status"] == "accepted"
        assert data1["event_nonce"] == nonce
        assert data1["hashed_plate"] == hash_plate("MH12AB1234")

        # 2. Duplicate submission with exact same event_nonce -> 409 Conflict
        resp2 = await ac.post("/v1/observations", json=payload)
        assert resp2.status_code == 409
        assert "already exists" in resp2.json()["detail"]


# -------------------------------------------------------------
# 4. Reviewer Incidents Review & Audit Field Tests
# -------------------------------------------------------------


@pytest.mark.asyncio
async def test_incidents_approval_and_rejection_audit_fields(auth_header, reviewer_user):
    # Setup candidate incident in DB
    async with TestAsyncSession() as db:
        incident = CandidateIncident(
            violation_type="wrong_side",
            plate_no=hash_plate("KA01AB9999"),
            geo_cluster="SRID=4326;POINT(73.85 18.52)",
            window_start=datetime.now(timezone.utc),
            window_end=datetime.now(timezone.utc),
            status="candidate",
        )
        db.add(incident)
        await db.commit()
        await db.refresh(incident)
        inc_id = incident.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Accessing without JWT -> 401
        resp_unauth = await ac.get(f"/v1/incidents/{inc_id}")
        assert resp_unauth.status_code == 401

        # 2. Accessing with JWT -> 200
        resp_auth = await ac.get(f"/v1/incidents/{inc_id}", headers=auth_header)
        assert resp_auth.status_code == 200
        assert resp_auth.json()["id"] == inc_id

        # 3. Approve incident -> Must populate reviewed_by and reviewed_at
        resp_approve = await ac.post(f"/v1/incidents/{inc_id}/approve", headers=auth_header)
        assert resp_approve.status_code == 200
        approve_data = resp_approve.json()
        assert approve_data["new_status"] == "confirmed"
        assert approve_data["reviewed_by"] == reviewer_user.id
        assert approve_data["reviewed_at"] is not None

        # Verify DB state
        async with TestAsyncSession() as db:
            updated = await db.get(CandidateIncident, inc_id)
            assert updated.status == "confirmed"
            assert updated.reviewed_by == reviewer_user.id
            assert updated.reviewed_at is not None

        # 4. Reject incident -> Must update status to rejected and update reviewed_by/at
        resp_reject = await ac.post(f"/v1/incidents/{inc_id}/reject", headers=auth_header)
        assert resp_reject.status_code == 200
        reject_data = resp_reject.json()
        assert reject_data["new_status"] == "rejected"
        assert reject_data["reviewed_by"] == reviewer_user.id


# -------------------------------------------------------------
# 5. Evidence Requests & Clip Upload Tests
# -------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_polling_and_upload_flow():
    device_id = "cam-edge-55"
    nonce = str(uuid.uuid4())

    async with TestAsyncSession() as db:
        device = Device(device_id=device_id, public_key="pubkey", trust_score=0.8, status="active")
        incident = CandidateIncident(
            violation_type="wrong_side",
            plate_no=hash_plate("DL01CD2222"),
            window_start=datetime.now(timezone.utc),
            window_end=datetime.now(timezone.utc),
            status="candidate",
        )
        db.add_all([device, incident])
        await db.flush()

        evidence = Evidence(
            incident_id=incident.id,
            device_id=device_id,
            event_nonce=nonce,
        )
        db.add(evidence)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Device polls for pending evidence requests
        poll_resp = await ac.get(f"/v1/evidence-requests?device_id={device_id}")
        assert poll_resp.status_code == 200
        items = poll_resp.json()
        assert len(items) == 1
        assert items[0]["event_nonce"] == nonce

        # 2. Device uploads clip
        clip_content = b"\x00\x00\x00\x20ftypisom"  # Mock MP4 header
        files = {"file": ("clip.mp4", io.BytesIO(clip_content), "video/mp4")}
        upload_resp = await ac.post(f"/v1/evidence/{nonce}", files=files)
        assert upload_resp.status_code == 200
        upload_data = upload_resp.json()
        assert upload_data["status"] == "uploaded"
        assert upload_data["storage_ref"].startswith("minio://")

        # 3. Subsequent poll returns 0 pending items
        poll_resp2 = await ac.get(f"/v1/evidence-requests?device_id={device_id}")
        assert len(poll_resp2.json()) == 0


@pytest.mark.asyncio
async def test_stale_sweep_ignores_solitary_red_light_observations(monkeypatch):
    from app.services import sweeps

    stale_ts = datetime.now(timezone.utc) - timedelta(minutes=10)
    wrong_side_incident = CandidateIncident(
        violation_type="wrong_side",
        plate_no=hash_plate("KA01AB1111"),
        window_start=stale_ts,
        window_end=stale_ts,
        status="candidate",
    )
    red_light_incident = CandidateIncident(
        violation_type="red_light",
        plate_no=hash_plate("KA01AB2222"),
        window_start=stale_ts,
        window_end=stale_ts,
        status="candidate",
    )
    wrong_side_observation = Observation(
        device_id="cam-sweep-wrong-side",
        violation_type="wrong_side",
        plate_no=wrong_side_incident.plate_no,
        lat=18.5204,
        lon=73.8567,
        location="POINT(73.8567 18.5204)",
        ts=stale_ts,
        event_nonce=str(uuid.uuid4()),
        signature="sig",
    )
    red_light_observation = Observation(
        device_id="cam-sweep-red-light",
        violation_type="red_light",
        plate_no=red_light_incident.plate_no,
        lat=18.5205,
        lon=73.8568,
        location="POINT(73.8568 18.5205)",
        ts=stale_ts,
        event_nonce=str(uuid.uuid4()),
        signature="sig",
    )

    async with TestAsyncSession() as db:
        db.add_all(
            [
                Device(device_id="cam-sweep-wrong-side", public_key="pubkey"),
                Device(device_id="cam-sweep-red-light", public_key="pubkey"),
                wrong_side_incident,
                red_light_incident,
                wrong_side_observation,
                red_light_observation,
            ]
        )
        wrong_side_incident.observations.append(wrong_side_observation)
        red_light_incident.observations.append(red_light_observation)
        await db.commit()
        wrong_side_incident_id = wrong_side_incident.id
        red_light_incident_id = red_light_incident.id
        red_light_observation_id = red_light_observation.id

    monkeypatch.setattr(sweeps, "get_session_factory", lambda: TestAsyncSession)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/v1/internal/sweep/stale-observations?time_window_seconds=300"
        )

    assert response.status_code == 200
    summary = response.json()
    assert summary["rejected"] == 1
    assert summary["errors"] == 0
    assert summary["failed"] == []

    async with TestAsyncSession() as db:
        wrong_side = await db.get(CandidateIncident, wrong_side_incident_id)
        red_light = await db.get(CandidateIncident, red_light_incident_id)
        red_light_observation = await db.get(Observation, red_light_observation_id)

    assert wrong_side.status == "rejected"
    assert red_light.status == "candidate"
    assert red_light_observation.wrong_way_status is None


# -------------------------------------------------------------
# 6. Evidence Proxy Integrity & Check Constraint Tests
# -------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_media_retrieval_failure_returns_502(monkeypatch):
    """When storage_ref exists but MinIO retrieval fails, return 502 Bad Gateway instead of fake bytes."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "USE_SIMULATED_EVIDENCE", False)

    # Insert incident & evidence record with storage_ref
    async with TestAsyncSession() as db:
        dev = Device(device_id="cam-ev-1", public_key="key")
        inc = CandidateIncident(
            violation_type="wrong_side",
            plate_no="hash123",
            window_start=datetime.now(timezone.utc),
            window_end=datetime.now(timezone.utc),
            status="corroborated",
        )
        db.add_all([dev, inc])
        await db.flush()

        ev = Evidence(
            incident_id=inc.id,
            device_id=dev.device_id,
            event_nonce="nonce-fail-test",
            storage_ref="minio://evidence/evidence/nonce-fail-test.mp4",
            uploaded_at=datetime.now(timezone.utc),
        )
        db.add(ev)
        await db.commit()

    # Request media proxy — storage is unreachable / mock returns None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/v1/evidence/nonce-fail-test/media")

    assert response.status_code == 502
    assert response.json()["detail"] == "Evidence retrieval temporarily unavailable"


@pytest.mark.asyncio
async def test_evidence_media_simulated_when_flag_enabled(monkeypatch):
    """When USE_SIMULATED_EVIDENCE=True, simulated bytes can be returned for offline local dev."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "USE_SIMULATED_EVIDENCE", True)

    async with TestAsyncSession() as db:
        dev = Device(device_id="cam-ev-2", public_key="key")
        inc = CandidateIncident(
            violation_type="wrong_side",
            plate_no="hash123",
            window_start=datetime.now(timezone.utc),
            window_end=datetime.now(timezone.utc),
            status="corroborated",
        )
        db.add_all([dev, inc])
        await db.flush()

        ev = Evidence(
            incident_id=inc.id,
            device_id=dev.device_id,
            event_nonce="nonce-sim-test",
            storage_ref="minio://evidence/evidence/nonce-sim-test.mp4",
            uploaded_at=datetime.now(timezone.utc),
        )
        db.add(ev)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/v1/evidence/nonce-sim-test/media")

    assert response.status_code == 200
    assert response.headers.get("x-evidence-simulated") == "true"
    assert response.headers.get("content-type") == "video/mp4"


@pytest.mark.asyncio
async def test_evidence_media_nonexistent_returns_404():
    """Nonexistent nonce or missing storage_ref returns 404."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/v1/evidence/nonexistent-nonce/media")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_schema_check_constraints_enforced():
    """Verify ORM models enforce CheckConstraints on table creation."""
    from sqlalchemy.exc import IntegrityError

    async with TestAsyncSession() as db:
        dev = Device(device_id="cam-cc-test", public_key="key")
        db.add(dev)
        await db.commit()

        # Invalid wrong_way_status for red_light violation (must be NULL)
        bad_obs = Observation(
            device_id=dev.device_id,
            violation_type="red_light",
            plate_no="hash",
            lat=18.5,
            lon=73.8,
            location="POINT(73.8 18.5)",
            ts=datetime.now(timezone.utc),
            event_nonce="bad-nonce-1",
            signature="sig",
            wrong_way_status="confirmed",  # Violates ck_observations_wrong_way_status!
        )
        db.add(bad_obs)
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

