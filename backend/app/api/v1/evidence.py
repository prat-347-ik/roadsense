from datetime import datetime, timezone
from typing import Annotated, List
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_db
from app.core.logging_config import logger
from app.models.entities import CandidateIncident, Evidence
from app.schemas.observation import EvidenceRequestItem, EvidenceUploadResponse
from app.services.storage import storage_service

router = APIRouter(prefix="", tags=["evidence"])


@router.get("/evidence-requests", response_model=List[EvidenceRequestItem])
async def get_evidence_requests(
    device_id: Annotated[str, Query(..., description="Device ID requesting pending evidence collection jobs")],
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> List[EvidenceRequestItem]:
    """Device polls for pending evidence clip collection requests addressed to its device_id."""
    stmt = (
        select(Evidence, CandidateIncident.violation_type, CandidateIncident.window_start)
        .join(CandidateIncident, Evidence.incident_id == CandidateIncident.id)
        .where(
            Evidence.device_id == device_id,
            Evidence.uploaded_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    items: List[EvidenceRequestItem] = []

    for ev, violation_type, window_start in result.all():
        items.append(
            EvidenceRequestItem(
                incident_id=ev.incident_id,
                device_id=ev.device_id,
                event_nonce=ev.event_nonce,
                violation_type=violation_type,
                requested_at=window_start,
                retention_expires_at=ev.retention_expires_at,
            )
        )
    return items


@router.post("/evidence/{event_nonce}", response_model=EvidenceUploadResponse)
async def upload_evidence(
    event_nonce: str,
    file: Annotated[UploadFile, File(description="Video or image evidence clip file")],
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> EvidenceUploadResponse:
    """Device uploads video/image evidence clip for an event nonce."""
    # Find evidence record
    stmt = select(Evidence).where(Evidence.event_nonce == event_nonce)
    result = await db.execute(stmt)
    evidence = result.scalar_one_or_none()

    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No pending evidence request found for event_nonce '{event_nonce}'",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    # Upload clip to MinIO storage
    content_type = file.content_type or "video/mp4"
    storage_ref = storage_service.upload_evidence(
        event_nonce=event_nonce,
        file_bytes=file_bytes,
        content_type=content_type,
    )

    now = datetime.now(timezone.utc)
    evidence.storage_ref = storage_ref
    evidence.uploaded_at = now

    # Update parent incident status if appropriate
    incident_stmt = select(CandidateIncident).where(CandidateIncident.id == evidence.incident_id)
    incident_res = await db.execute(incident_stmt)
    incident = incident_res.scalar_one_or_none()
    if incident and incident.status == "candidate":
        incident.status = "corroborated"

    await db.commit()

    logger.info(f"Evidence clip uploaded successfully for event_nonce {event_nonce}")

    return EvidenceUploadResponse(
        status="uploaded",
        event_nonce=event_nonce,
        storage_ref=storage_ref,
        uploaded_at=now,
    )


@router.get("/evidence/{event_nonce}/media")
async def get_evidence_media(
    event_nonce: str,
    db: Annotated[AsyncSession, Depends(get_async_db)],
):
    """Proxy/stream evidence video or placeholder for in-browser playback."""
    from fastapi.responses import Response

    stmt = select(Evidence).where(Evidence.event_nonce == event_nonce)
    result = await db.execute(stmt)
    evidence = result.scalar_one_or_none()

    if not evidence or not evidence.storage_ref:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence for nonce '{event_nonce}' not found",
        )

    data, content_type = storage_service.get_evidence_bytes(evidence.storage_ref)
    if data:
        return Response(
            content=data,
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename={event_nonce}.mp4",
                "Accept-Ranges": "bytes",
            },
        )

    # Simulated/offline fallback: only if explicitly enabled via settings.USE_SIMULATED_EVIDENCE
    from app.core.config import settings

    if settings.USE_SIMULATED_EVIDENCE:
        sample_mp4 = (
            b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41"
            b"\x00\x00\x00\x08free\x00\x00\x00\x08mdat"
        )
        return Response(
            content=sample_mp4,
            media_type="video/mp4",
            headers={
                "Content-Disposition": f"inline; filename={event_nonce}.mp4",
                "Accept-Ranges": "bytes",
                "X-Evidence-Simulated": "true",
            },
        )

    # When storage_ref exists but retrieval fails, return explicit gateway error
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Evidence retrieval temporarily unavailable",
    )

