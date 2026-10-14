from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any
import httpx

logger = logging.getLogger("edge.uplink.client")

DEFAULT_API_BASE_URL = os.environ.get("ROADSENSE_API_URL") or os.environ.get("API_URL") or "http://localhost:8000"


class UplinkError(Exception):
    """Base exception for edge uplink communications."""
    pass


class UplinkConnectionError(UplinkError):
    """Raised when connection to backend server fails."""
    pass


class DuplicateNonceError(UplinkError):
    """Raised on HTTP 409 Conflict (event_nonce duplicate)."""
    pass


class UplinkValidationError(UplinkError):
    """Raised on HTTP 422 Unprocessable Entity (payload schema mismatch)."""
    pass


class RoadSenseUplinkClient:
    """HTTP client communicating with RoadSense FastAPI backend.

    Handles:
    - POST /v1/observations: Register candidate observation bursts.
    - GET /v1/evidence-requests: Poll for queued evidence clip collection jobs.
    - POST /v1/evidence/{event_nonce}: Upload evidence media files.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 10.0,
        evidence_buffer: Any | None = None,
    ):
        self.base_url = (base_url or DEFAULT_API_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.evidence_buffer = evidence_buffer

    def send_observation(self, burst: dict[str, Any]) -> dict[str, Any]:
        """Transmits an observation burst to the backend.

        Args:
            burst: Dict conforming to ObservationBurstRequest.

        Returns:
            ObservationResponse dictionary on success (HTTP 201) or handled duplicate (HTTP 409).

        Raises:
            DuplicateNonceError: On duplicate nonce (if re-raise behavior desired).
            UplinkValidationError: On schema rejection (HTTP 422).
            UplinkConnectionError: On network or server unreachable error.
        """
        url = f"{self.base_url}/v1/observations"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=burst)

            if response.status_code == 201:
                data = response.json()
                logger.info(
                    "Observation registered successfully (nonce: %s, hashed_plate: %s)",
                    data.get("event_nonce"),
                    data.get("hashed_plate"),
                )
                return data

            if response.status_code == 409:
                err_detail = response.json().get("detail", "Duplicate nonce")
                logger.warning("Duplicate observation nonce '%s': %s", burst.get("event_nonce"), err_detail)
                return {
                    "status": "duplicate",
                    "event_nonce": burst.get("event_nonce"),
                    "detail": err_detail,
                }

            if response.status_code == 422:
                err_detail = response.json().get("detail", response.text)
                logger.error("Backend schema validation failed (HTTP 422): %s", err_detail)
                raise UplinkValidationError(f"Backend schema validation failed: {err_detail}")

            if response.status_code == 400:
                err_detail = response.json().get("detail", "Bad Request")
                logger.error("Backend rejected request (HTTP 400): %s", err_detail)
                raise UplinkError(f"Bad Request: {err_detail}")

            response.raise_for_status()
            return response.json()

        except httpx.RequestError as exc:
            logger.error("Failed to connect to RoadSense backend at %s: %s", url, exc)
            raise UplinkConnectionError(f"Connection to backend failed at {url}: {exc}") from exc

    def poll_evidence_requests(self, device_id: str) -> list[dict[str, Any]]:
        """Polls backend for pending evidence requests addressed to device_id."""
        url = f"{self.base_url}/v1/evidence-requests"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params={"device_id": device_id})
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as exc:
            logger.error("Failed to poll evidence requests from %s: %s", url, exc)
            raise UplinkConnectionError(f"Polling evidence requests failed: {exc}") from exc

    def upload_evidence(
        self,
        event_nonce: str,
        clip_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Uploads evidence media file for an incident event nonce.

        If clip_path is omitted, automatically resolves the file via the configured
        local evidence_buffer. If no clip is found or unexpired, returns a pending status.
        """
        # Resolve clip from evidence_buffer if not explicitly provided
        if clip_path is None and self.evidence_buffer is not None:
            clip_path = self.evidence_buffer.get_clip(event_nonce)

        if clip_path is None or not Path(clip_path).exists():
            logger.info(
                "Upload evidence called for nonce %s without valid local media file.",
                event_nonce,
            )
            return {
                "status": "pending_local_storage",
                "event_nonce": event_nonce,
                "message": "Local evidence buffer did not contain an unexpired clip for this event nonce.",
            }

        url = f"{self.base_url}/v1/evidence/{event_nonce}"
        path_obj = Path(clip_path)
        ext = path_obj.suffix.lower()
        if ext == ".mp4":
            content_type = "video/mp4"
        elif ext in (".jpg", ".jpeg"):
            content_type = "image/jpeg"
        elif ext == ".png":
            content_type = "image/png"
        else:
            content_type = "application/octet-stream"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with open(path_obj, "rb") as f:
                    files = {"file": (path_obj.name, f, content_type)}
                    response = client.post(url, files=files)
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as exc:
            logger.error("Failed to upload evidence for nonce %s to %s: %s", event_nonce, url, exc)
            raise UplinkConnectionError(f"Evidence upload failed: {exc}") from exc
