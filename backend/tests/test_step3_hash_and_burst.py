import os
import uuid
import pytest
from pydantic import ValidationError

from app.core.security import hash_plate, normalize_plate, verify_signature
from app.schemas.observation import ObservationBurstRequest


def test_normalize_plate():
    assert normalize_plate("abc 1234") == "ABC1234"
    assert normalize_plate("  AbC  1234   ") == "ABC1234"
    assert normalize_plate("mh-12-ab-1234") == "MH-12-AB-1234"
    assert normalize_plate("ka 01  ab 9999") == "KA01AB9999"


def test_hash_plate_collision_consistency():
    key = "test-secret-key-123"
    hash1 = hash_plate("abc 1234", hash_key=key)
    hash2 = hash_plate("ABC1234", hash_key=key)
    hash3 = hash_plate("  aBc  1234  ", hash_key=key)
    hash_diff = hash_plate("XYZ9999", hash_key=key)

    # Normalized versions must produce identical hashes
    assert hash1 == hash2
    assert hash2 == hash3
    # Different plate must produce a different hash
    assert hash1 != hash_diff
    # Result should be a 64-character SHA-256 hex string
    assert len(hash1) == 64


def test_hash_plate_reads_env(monkeypatch):
    monkeypatch.setenv("PLATE_HASH_KEY", "env-secret-456")
    h = hash_plate("DL01A1111")
    assert isinstance(h, str)
    assert len(h) == 64


def test_verify_signature_stub():
    payload = {"device_id": "cam-1", "plate_no": "MH12AB1234"}
    assert verify_signature(payload, "sig-sample-123") is True
    assert verify_signature(payload, "") is False


def test_observation_burst_request_valid():
    valid_payload = {
        "device_id": "cam-001",
        "violation_type": "wrong_side",
        "plate_no": "ABC 1234",
        "lat": 37.7749,
        "lon": -122.4194,
        "timestamp": "2026-09-12T10:30:00Z",
        "event_nonce": str(uuid.uuid4()),
        "sig": "MEQCIFq9QsampleSignature",
    }
    model = ObservationBurstRequest(**valid_payload)
    assert model.device_id == "cam-001"
    assert model.violation_type == "wrong_side"
    assert model.plate_no == "ABC 1234"
    assert model.lat == 37.7749
    assert model.lon == -122.4194


def test_observation_burst_request_max_length_plate():
    # Length <= 16 is valid
    valid_payload = {
        "device_id": "cam-001",
        "violation_type": "wrong_side",
        "plate_no": "1234567890123456",  # 16 chars
        "lat": 37.7749,
        "lon": -122.4194,
        "timestamp": "2026-09-12T10:30:00Z",
        "event_nonce": str(uuid.uuid4()),
        "sig": "sig123",
    }
    model = ObservationBurstRequest(**valid_payload)
    assert len(model.plate_no) == 16

    # Length > 16 must fail validation
    invalid_payload = {**valid_payload, "plate_no": "12345678901234567"}  # 17 chars
    with pytest.raises(ValidationError) as exc_info:
        ObservationBurstRequest(**invalid_payload)
    assert "plate_no" in str(exc_info.value)


def test_observation_burst_request_invalid_violation_type():
    invalid_payload = {
        "device_id": "cam-001",
        "violation_type": "speeding",  # Invalid type
        "plate_no": "ABC 1234",
        "lat": 37.7749,
        "lon": -122.4194,
        "timestamp": "2026-09-12T10:30:00Z",
        "event_nonce": str(uuid.uuid4()),
        "sig": "sig123",
    }
    with pytest.raises(ValidationError) as exc_info:
        ObservationBurstRequest(**invalid_payload)
    assert "violation_type" in str(exc_info.value)


def test_observation_burst_request_invalid_nonce():
    invalid_payload = {
        "device_id": "cam-001",
        "violation_type": "red_light",
        "plate_no": "ABC 1234",
        "lat": 37.7749,
        "lon": -122.4194,
        "timestamp": "2026-09-12T10:30:00Z",
        "event_nonce": "not-a-valid-uuid",  # Invalid UUID
        "sig": "sig123",
    }
    with pytest.raises(ValidationError) as exc_info:
        ObservationBurstRequest(**invalid_payload)
    assert "event_nonce" in str(exc_info.value)


def test_observation_burst_request_invalid_coordinates():
    # Lat out of range (> 90)
    with pytest.raises(ValidationError):
        ObservationBurstRequest(
            device_id="cam-001",
            violation_type="red_light",
            plate_no="ABC1234",
            lat=95.0,
            lon=50.0,
            timestamp="2026-09-12T10:30:00Z",
            event_nonce=str(uuid.uuid4()),
            sig="sig123",
        )

    # Lon out of range (< -180)
    with pytest.raises(ValidationError):
        ObservationBurstRequest(
            device_id="cam-001",
            violation_type="red_light",
            plate_no="ABC1234",
            lat=45.0,
            lon=-190.0,
            timestamp="2026-09-12T10:30:00Z",
            event_nonce=str(uuid.uuid4()),
            sig="sig123",
        )
