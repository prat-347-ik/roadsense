from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from edge.rules.red_light import RedLightCandidateDecision
from edge.rules.wrong_way import WrongWayCandidateDecision
from edge.tracking.tracker import Track
from edge.uplink.signing import DeviceSigner

logger = logging.getLogger("edge.uplink.burst")

DEFAULT_DEVICE_ID = "edge-camera-node-01"
# Default Pune location coordinates matching project baseline
DEFAULT_LAT = 18.5204
DEFAULT_LON = 73.8567


class NoPlateAvailableError(ValueError):
    """Raised when attempting to assemble a burst without a valid license plate."""
    pass


def assemble_burst(
    violation_type: str,
    plate_no: str | None,
    device_id: str = DEFAULT_DEVICE_ID,
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    timestamp: datetime | str | None = None,
    event_nonce: str | None = None,
    signer: DeviceSigner | None = None,
    allow_skip_without_plate: bool = True,
) -> dict[str, Any] | None:
    """Assembles and cryptographically signs an ObservationBurstRequest payload.

    Backend Schema Compatibility:
    The backend's ObservationBurstRequest schema strictly enforces:
    `plate_no: str = Field(..., min_length=1, max_length=16)`
    An observation without a readable license plate cannot be clustered or tracked.
    Therefore, if plate_no is None or empty:
    - If allow_skip_without_plate=True, returns None (skips burst transmission).
    - If allow_skip_without_plate=False, raises NoPlateAvailableError.

    Args:
        violation_type: 'red_light' or 'wrong_side'.
        plate_no: Raw plaintext plate string (unhashed — backend handles privacy hashing).
        device_id: Configurable identifier for this edge device.
        lat: Latitude in decimal degrees (-90.0 to 90.0).
        lon: Longitude in decimal degrees (-180.0 to 180.0).
        timestamp: ISO8601 timestamp or datetime object.
        event_nonce: Unique UUID string (freshly generated if None).
        signer: Optional DeviceSigner instance (creates default if None).
        allow_skip_without_plate: Whether to return None instead of raising if no plate.

    Returns:
        Dictionary conforming to ObservationBurstRequest with 'sig', or None if skipped.
    """
    # 1. Normalize violation_type
    vtype = str(violation_type).lower().strip()
    if vtype not in ("wrong_side", "red_light"):
        raise ValueError(f"Invalid violation_type '{violation_type}'; must be 'wrong_side' or 'red_light'")

    # 2. Check plate number availability
    cleaned_plate = plate_no.strip().upper() if plate_no else ""
    if not cleaned_plate:
        if allow_skip_without_plate:
            logger.info("Plate unreadable or below gating threshold. Skipping burst transmission per privacy design.")
            return None
        raise NoPlateAvailableError("Cannot assemble burst without valid license plate (schema requires 1-16 chars).")

    # Bound plate string length to backend schema max_length (16)
    if len(cleaned_plate) > 16:
        cleaned_plate = cleaned_plate[:16]

    # 3. Format timestamp to ISO 8601 UTC
    if timestamp is None:
        ts_str = datetime.now(timezone.utc).isoformat()
    elif isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        ts_str = timestamp.isoformat()
    else:
        ts_str = str(timestamp)

    # 4. Generate fresh UUID event_nonce for backend idempotency
    nonce_str = str(event_nonce) if event_nonce is not None else str(uuid.uuid4())

    # 5. Assemble unsigned payload
    burst: dict[str, Any] = {
        "device_id": str(device_id),
        "violation_type": vtype,
        "plate_no": cleaned_plate,
        "lat": float(lat),
        "lon": float(lon),
        "timestamp": ts_str,
        "event_nonce": nonce_str,
    }

    # 6. Cryptographically sign the payload
    active_signer = signer or DeviceSigner()
    signature = active_signer.sign_payload(burst)
    burst["sig"] = signature

    return burst


def assemble_burst_from_decision(
    decision: RedLightCandidateDecision | WrongWayCandidateDecision,
    track: Track | None = None,
    device_id: str = DEFAULT_DEVICE_ID,
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    timestamp: datetime | str | None = None,
    signer: DeviceSigner | None = None,
    override_plate: str | None = None,
) -> dict[str, Any] | None:
    """Convenience helper to assemble a burst directly from a rule candidate decision."""
    if not decision.is_candidate:
        return None

    if isinstance(decision, RedLightCandidateDecision):
        vtype = "red_light"
    elif isinstance(decision, WrongWayCandidateDecision):
        vtype = "wrong_side"
    else:
        raise TypeError(f"Unsupported decision type: {type(decision)}")

    plate = override_plate or decision.plate_text or (track.plate_text if track else None)

    return assemble_burst(
        violation_type=vtype,
        plate_no=plate,
        device_id=device_id,
        lat=lat,
        lon=lon,
        timestamp=timestamp,
        signer=signer,
    )
