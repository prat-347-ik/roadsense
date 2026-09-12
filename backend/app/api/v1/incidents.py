from datetime import datetime, timezone
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_reviewer, get_async_db
from app.core.logging_config import logger
from app.models.entities import CandidateIncident, Evidence, Observation, Reviewer
from app.schemas.observation import (
    IncidentDetail,
    IncidentReviewActionResponse,
    IncidentSummary,
    ObservationRead,
)
from app.services.storage import storage_service

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=List[IncidentSummary])
async def list_incidents(
    reviewer: Annotated[Reviewer, Depends(get_current_reviewer)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
    status_filter: Optional[str] = Query(None, alias="status"),
    violation_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> List[IncidentSummary]:
    """Reviewer-facing list of candidate and corroborated incidents."""
    stmt = select(CandidateIncident).options(selectinload(CandidateIncident.observations))

    if status_filter:
        stmt = stmt.where(CandidateIncident.status == status_filter)
    if violation_type:
        stmt = stmt.where(CandidateIncident.violation_type == violation_type)

    stmt = stmt.order_by(desc(CandidateIncident.window_end)).offset(offset).limit(limit)
    result = await db.execute(stmt)
    incidents = result.scalars().all()

    summaries = []
    for inc in incidents:
        summaries.append(
            IncidentSummary(
                id=inc.id,
                violation_type=inc.violation_type,
                hashed_plate=inc.plate_no,
                status=inc.status,
                window_start=inc.window_start,
                window_end=inc.window_end,
                observation_count=len(inc.observations),
                reviewed_by=inc.reviewed_by,
                reviewed_at=inc.reviewed_at,
            )
        )
    return summaries


@router.get("/{incident_id}", response_model=IncidentDetail)
async def get_incident(
    incident_id: int,
    reviewer: Annotated[Reviewer, Depends(get_current_reviewer)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> IncidentDetail:
    """Reviewer-facing incident detail with linked observations and evidence presigned URLs."""
    stmt = (
        select(CandidateIncident)
        .options(
            selectinload(CandidateIncident.observations),
            selectinload(CandidateIncident.evidence_items),
            selectinload(CandidateIncident.reviewer),
        )
        .where(CandidateIncident.id == incident_id)
    )
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID {incident_id} not found",
        )

    obs_list = [
        ObservationRead(
            id=o.id,
            device_id=o.device_id,
            violation_type=o.violation_type,
            hashed_plate=o.plate_no,
            lat=o.lat,
            lon=o.lon,
            ts=o.ts,
            event_nonce=o.event_nonce,
            wrong_way_status=o.wrong_way_status,
        )
        for o in incident.observations
    ]

    evidence_list = []
    for ev in incident.evidence_items:
        presigned_url = (
            storage_service.get_presigned_url(ev.storage_ref) if ev.storage_ref else None
        )
        evidence_list.append(
            {
                "device_id": ev.device_id,
                "event_nonce": ev.event_nonce,
                "uploaded_at": ev.uploaded_at,
                "storage_ref": ev.storage_ref,
                "view_url": presigned_url,
                "retention_expires_at": ev.retention_expires_at,
            }
        )

    return IncidentDetail(
        id=incident.id,
        violation_type=incident.violation_type,
        hashed_plate=incident.plate_no,
        status=incident.status,
        window_start=incident.window_start,
        window_end=incident.window_end,
        reviewed_by=incident.reviewed_by,
        reviewed_at=incident.reviewed_at,
        reviewer_email=incident.reviewer.email if incident.reviewer else None,
        observations=obs_list,
        evidence_items=evidence_list,
    )


@router.post("/{incident_id}/approve", response_model=IncidentReviewActionResponse)
async def approve_incident(
    incident_id: int,
    reviewer: Annotated[Reviewer, Depends(get_current_reviewer)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> IncidentReviewActionResponse:
    """Approve candidate/corroborated incident.

    Must write reviewed_by (from authenticated reviewer JWT) and reviewed_at.
    """
    if not reviewer or not reviewer.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid authenticated reviewer identity required for approval",
        )

    stmt = select(CandidateIncident).where(CandidateIncident.id == incident_id)
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID {incident_id} not found",
        )

    now = datetime.now(timezone.utc)
    incident.status = "confirmed"
    incident.reviewed_by = reviewer.id
    incident.reviewed_at = now

    await db.commit()

    logger.info(f"Incident {incident_id} approved by reviewer {reviewer.id} at {now.isoformat()}")

    return IncidentReviewActionResponse(
        status="success",
        incident_id=incident.id,
        new_status="confirmed",
        reviewed_by=reviewer.id,
        reviewed_at=now,
    )


@router.post("/{incident_id}/reject", response_model=IncidentReviewActionResponse)
async def reject_incident(
    incident_id: int,
    reviewer: Annotated[Reviewer, Depends(get_current_reviewer)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> IncidentReviewActionResponse:
    """Reject candidate/corroborated incident.

    Must write reviewed_by (from authenticated reviewer JWT) and reviewed_at.
    """
    if not reviewer or not reviewer.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid authenticated reviewer identity required for rejection",
        )

    stmt = select(CandidateIncident).where(CandidateIncident.id == incident_id)
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID {incident_id} not found",
        )

    now = datetime.now(timezone.utc)
    incident.status = "rejected"
    incident.reviewed_by = reviewer.id
    incident.reviewed_at = now

    await db.commit()

    logger.info(f"Incident {incident_id} rejected by reviewer {reviewer.id} at {now.isoformat()}")

    return IncidentReviewActionResponse(
        status="success",
        incident_id=incident.id,
        new_status="rejected",
        reviewed_by=reviewer.id,
        reviewed_at=now,
    )
