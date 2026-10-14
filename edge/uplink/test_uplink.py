import uuid
import pytest
import httpx

from edge.rules.red_light import RedLightCandidateDecision
from edge.rules.wrong_way import WrongWayCandidateDecision
from edge.uplink.burst import (
    NoPlateAvailableError,
    assemble_burst,
    assemble_burst_from_decision,
)
from edge.uplink.client import (
    DuplicateNonceError,
    RoadSenseUplinkClient,
    UplinkConnectionError,
    UplinkValidationError,
)
from edge.uplink.signing import DeviceSigner


def test_device_signer_keypair_and_verification(tmp_path):
    """Test Ed25519 key generation, signing, and signature verification."""
    key_file = tmp_path / "test_private_key.pem"
    signer = DeviceSigner(key_path=key_file)
    assert key_file.exists()
    assert len(signer.public_key_hex) == 64

    payload = {
        "device_id": "test-cam-01",
        "violation_type": "wrong_side",
        "plate_no": "MH12AB1234",
        "lat": 18.5204,
        "lon": 73.8567,
    }

    sig = signer.sign_payload(payload)
    assert isinstance(sig, str)
    assert len(sig) == 128  # Ed25519 signature is 64 bytes -> 128 hex chars

    # Verify signature
    assert DeviceSigner.verify_signature(payload, sig, signer.public_key_hex) is True

    # Tampered payload fails verification
    tampered_payload = dict(payload, plate_no="MH14CD9999")
    assert DeviceSigner.verify_signature(tampered_payload, sig, signer.public_key_hex) is False


def test_assemble_burst_valid(tmp_path):
    """Test that assemble_burst produces all fields matching backend schema."""
    signer = DeviceSigner(key_path=tmp_path / "key.pem")
    burst = assemble_burst(
        violation_type="red_light",
        plate_no="MH46P7913",
        device_id="cam-junction-4",
        lat=18.5204,
        lon=73.8567,
        signer=signer,
    )

    assert burst is not None
    assert burst["device_id"] == "cam-junction-4"
    assert burst["violation_type"] == "red_light"
    assert burst["plate_no"] == "MH46P7913"
    assert burst["lat"] == 18.5204
    assert burst["lon"] == 73.8567
    assert "timestamp" in burst
    assert "event_nonce" in burst
    assert "sig" in burst

    # event_nonce must be a valid UUID
    parsed_uuid = uuid.UUID(burst["event_nonce"])
    assert str(parsed_uuid) == burst["event_nonce"]

    # Signature must verify against payload
    assert DeviceSigner.verify_signature(burst, burst["sig"], signer.public_key_hex) is True


def test_assemble_burst_skips_when_no_plate(tmp_path):
    """Test that missing plate skips burst or raises appropriately."""
    signer = DeviceSigner(key_path=tmp_path / "key.pem")

    # Default: allow_skip_without_plate=True returns None
    result = assemble_burst(
        violation_type="wrong_side",
        plate_no=None,
        signer=signer,
        allow_skip_without_plate=True,
    )
    assert result is None

    # Strict: allow_skip_without_plate=False raises NoPlateAvailableError
    with pytest.raises(NoPlateAvailableError):
        assemble_burst(
            violation_type="wrong_side",
            plate_no="",
            signer=signer,
            allow_skip_without_plate=False,
        )


def test_assemble_burst_from_decisions(tmp_path):
    """Test assembling burst directly from rule candidate decisions."""
    signer = DeviceSigner(key_path=tmp_path / "key.pem")

    # Red-light decision
    rl_dec = RedLightCandidateDecision(
        is_candidate=True,
        reason="Crossed stop line on red",
        plate_text="MH12NE4410",
    )
    rl_burst = assemble_burst_from_decision(rl_dec, signer=signer)
    assert rl_burst is not None
    assert rl_burst["violation_type"] == "red_light"
    assert rl_burst["plate_no"] == "MH12NE4410"

    # Non-candidate decision returns None
    non_cand = WrongWayCandidateDecision(
        is_candidate=False,
        reason="Vehicle is moving away",
        plate_text="MH12NE4410",
    )
    assert assemble_burst_from_decision(non_cand, signer=signer) is None


def test_client_mock_responses():
    """Test HTTP client behavior on 201, 409, and 422 status codes using MockTransport."""
    # 1. Test 201 Created
    def mock_handler_201(request: httpx.Request):
        return httpx.Response(
            201,
            json={
                "status": "candidate",
                "event_nonce": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
                "hashed_plate": "abc123hash",
            },
        )

    client_201 = RoadSenseUplinkClient(base_url="http://testserver")
    client_201_transport = httpx.Client(transport=httpx.MockTransport(mock_handler_201))
    # Test send_observation directly by mocking httpx.Client
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(httpx, "Client", lambda **kwargs: client_201_transport)
        res = client_201.send_observation({
            "device_id": "d1",
            "violation_type": "wrong_side",
            "plate_no": "MH12AB1234",
            "lat": 18.5,
            "lon": 73.8,
            "timestamp": "2026-09-12T10:00:00Z",
            "event_nonce": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "sig": "fakesig",
        })
        assert res["status"] == "candidate"
        assert res["event_nonce"] == "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"

    # 2. Test 409 Conflict handled gracefully
    def mock_handler_409(request: httpx.Request):
        return httpx.Response(
            409,
            json={"detail": "Observation with event_nonce already exists"},
        )

    client_409 = RoadSenseUplinkClient(base_url="http://testserver")
    client_409_transport = httpx.Client(transport=httpx.MockTransport(mock_handler_409))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(httpx, "Client", lambda **kwargs: client_409_transport)
        res = client_409.send_observation({
            "device_id": "d1",
            "violation_type": "wrong_side",
            "plate_no": "MH12AB1234",
            "lat": 18.5,
            "lon": 73.8,
            "timestamp": "2026-09-12T10:00:00Z",
            "event_nonce": "duplicate-nonce",
            "sig": "fakesig",
        })
        assert res["status"] == "duplicate"
        assert res["event_nonce"] == "duplicate-nonce"

    # 3. Test 422 Unprocessable Entity raises UplinkValidationError
    def mock_handler_422(request: httpx.Request):
        return httpx.Response(422, json={"detail": "Field required"})

    client_422 = RoadSenseUplinkClient(base_url="http://testserver")
    client_422_transport = httpx.Client(transport=httpx.MockTransport(mock_handler_422))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(httpx, "Client", lambda **kwargs: client_422_transport)
        with pytest.raises(UplinkValidationError):
            client_422.send_observation({})
