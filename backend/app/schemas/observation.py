from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ViolationType(str, Enum):
    WRONG_SIDE = "wrong_side"
    RED_LIGHT = "red_light"


class IncidentStatus(str, Enum):
    CANDIDATE = "candidate"
    CORROBORATED = "corroborated"
    CORROBORATED_NO_EVIDENCE = "corroborated_no_evidence"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ObservationBurstRequest(BaseModel):
    """Payload sent by edge device representing a burst observation.

    Note: `plate_no` is bounded to 1-16 characters and immediately hashed
    upon receipt.
    """

    device_id: str = Field(..., min_length=1, max_length=128, description="Unique ID of reporting edge device")
    violation_type: Literal["wrong_side", "red_light"] = Field(
        ..., description="Detected violation category: wrong_side or red_light"
    )
    plate_no: str = Field(..., min_length=1, max_length=16, description="Raw license plate text observed at the scene")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    timestamp: datetime = Field(..., description="Observation capture time in ISO8601 format")
    event_nonce: str = Field(..., description="Unique UUID nonce for the burst event to guarantee idempotency")
    sig: str = Field(..., min_length=1, description="Cryptographic signature of the burst payload")

    @field_validator("event_nonce")
    @classmethod
    def validate_event_nonce_is_uuid(cls, v: str) -> str:
        try:
            UUID(str(v))
        except (ValueError, AttributeError, TypeError) as e:
            raise ValueError(f"event_nonce must be a valid UUID string: {e}")
        return str(v)

    model_config = {
        "json_schema_extra": {
            "example": {
                "device_id": "cam-sensor-north-01",
                "violation_type": "wrong_side",
                "plate_no": "MH12AB1234",
                "lat": 18.5204,
                "lon": 73.8567,
                "timestamp": "2026-09-12T10:30:00Z",
                "event_nonce": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
                "sig": "MEQCIFq9Q..."
            }
        }
    }


class ObservationResponse(BaseModel):
    """API response after registering an observation.

    Guarantees raw plate_no is NEVER returned.
    """

    status: str
    event_nonce: str
    hashed_plate: str
    message: str | None = None


class ObservationRead(BaseModel):
    id: int
    device_id: str
    violation_type: str
    hashed_plate: str
    lat: float
    lon: float
    ts: datetime
    event_nonce: str
    wrong_way_status: str | None = None

    model_config = {"from_attributes": True}


class EvidenceRequestItem(BaseModel):
    incident_id: int
    device_id: str
    event_nonce: str
    violation_type: str
    requested_at: datetime
    retention_expires_at: datetime | None = None


class EvidenceUploadResponse(BaseModel):
    status: str
    event_nonce: str
    storage_ref: str
    uploaded_at: datetime


class IncidentSummary(BaseModel):
    id: int
    violation_type: str
    hashed_plate: str
    status: str
    window_start: datetime
    window_end: datetime
    observation_count: int = 0
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None

    model_config = {"from_attributes": True}


class IncidentDetail(BaseModel):
    id: int
    violation_type: str
    hashed_plate: str
    status: str
    window_start: datetime
    window_end: datetime
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    reviewer_email: str | None = None
    observations: list[ObservationRead] = []
    evidence_items: list[dict[str, Any]] = []

    model_config = {"from_attributes": True}


class IncidentReviewActionResponse(BaseModel):
    status: str
    incident_id: int
    new_status: str
    reviewed_by: int
    reviewed_at: datetime


class ReviewerLoginRequest(BaseModel):
    email: str = Field(..., max_length=320)
    password: str = Field(..., min_length=6)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    reviewer: dict[str, Any]
