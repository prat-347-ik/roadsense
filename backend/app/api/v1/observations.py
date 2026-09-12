from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_async_db
from app.core.logging_config import logger
from app.core.security import hash_plate, verify_signature
from app.models.entities import (
    CandidateIncident,
    Device,
    Evidence,
    Observation,
    incident_observations,
)
from app.schemas.observation import ObservationBurstRequest, ObservationResponse
from app.services.clustering import (
    cluster_observations,
    evaluate_evidence_trigger,
)
from app.services.progression import (
    ObservationPoint,
    ProgressionStatus,
    evaluate_wrong_way_progression,
)

router = APIRouter(prefix="/observations", tags=["observations"])


@router.post("", response_model=ObservationResponse, status_code=status.HTTP_201_CREATED)
async def create_observation(
    payload: ObservationBurstRequest,
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> ObservationResponse:
    """Ingest observation burst from edge device.

    Privacy boundary guarantee: `hash_plate` is executed immediately.
    Raw `plate_no` is scrubbed and never persisted or logged.
    """
    # 1. Immediate hashing at the privacy boundary
    hashed_plate = hash_plate(payload.plate_no)

    # 2. Check event_nonce uniqueness for idempotency (clean 409 error)
    existing_stmt = select(Observation).where(Observation.event_nonce == payload.event_nonce)
    existing_res = await db.execute(existing_stmt)
    if existing_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Observation with event_nonce '{payload.event_nonce}' already exists",
        )

    # 3. Signature verification stub
    if not verify_signature(payload.model_dump(), payload.sig):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cryptographic signature",
        )

    # 4. Ensure reporting device exists (or auto-register default active)
    dev_stmt = select(Device).where(Device.device_id == payload.device_id)
    dev_res = await db.execute(dev_stmt)
    device = dev_res.scalar_one_or_none()
    if not device:
        device = Device(
            device_id=payload.device_id,
            public_key="stub_public_key",
            trust_score=0.5,
            status="active",
        )
        db.add(device)
        await db.flush()

    # 5. Wrong-way progression filter evaluation (Step 5)
    wrong_way_status: str | None = None
    if payload.violation_type == "wrong_side":
        # Fetch prior unconfirmed observations for this hashed plate
        prior_stmt = select(Observation).where(
            Observation.plate_no == hashed_plate,
            Observation.violation_type == "wrong_side",
        )
        prior_res = await db.execute(prior_stmt)
        priors = prior_res.scalars().all()

        prior_points = [
            ObservationPoint(
                lat=p.lat,
                lon=p.lon,
                ts=p.ts,
                device_id=p.device_id,
                event_nonce=p.event_nonce,
                hashed_plate=p.plate_no,
                wrong_way_status=p.wrong_way_status,
            )
            for p in priors
        ]

        new_point = ObservationPoint(
            lat=payload.lat,
            lon=payload.lon,
            ts=payload.timestamp,
            device_id=payload.device_id,
            event_nonce=payload.event_nonce,
            hashed_plate=hashed_plate,
        )

        eval_result = evaluate_wrong_way_progression(new_point, prior_points)
        wrong_way_status = eval_result.status.value

    # 6. Persist observation (location formatted as WKT Point)
    location_wkt = f"SRID=4326;POINT({payload.lon} {payload.lat})"
    observation = Observation(
        device_id=payload.device_id,
        violation_type=payload.violation_type,
        plate_no=hashed_plate,  # Only the hashed value is saved
        location=location_wkt,
        lat=payload.lat,
        lon=payload.lon,
        ts=payload.timestamp,
        event_nonce=payload.event_nonce,
        signature=payload.sig,
        wrong_way_status=wrong_way_status,
    )
    db.add(observation)
    await db.flush()

    # 7. Clustering & Candidate Incident evaluation
    obs_for_clustering_stmt = select(Observation).where(
        Observation.plate_no == hashed_plate,
        Observation.violation_type == payload.violation_type,
    )
    obs_for_clustering_res = await db.execute(obs_for_clustering_stmt)
    all_related_obs = obs_for_clustering_res.scalars().all()

    cluster_points = [
        ObservationPoint(
            lat=o.lat,
            lon=o.lon,
            ts=o.ts,
            device_id=o.device_id,
            event_nonce=o.event_nonce,
            hashed_plate=o.plate_no,
            wrong_way_status=o.wrong_way_status,
        )
        for o in all_related_obs
    ]

    clusters = cluster_observations(cluster_points, violation_type=payload.violation_type)

    for cluster in clusters:
        # Check if an incident already exists for this cluster
        inc_stmt = (
            select(CandidateIncident)
            .options(selectinload(CandidateIncident.observations))
            .where(
                CandidateIncident.plate_no == hashed_plate,
                CandidateIncident.violation_type == payload.violation_type,
                CandidateIncident.status.in_(["candidate", "corroborated", "corroborated_no_evidence"]),
            )
        )
        inc_res = await db.execute(inc_stmt)
        incident = inc_res.scalars().first()

        trigger_decision = evaluate_evidence_trigger(cluster)

        if not incident:
            incident = CandidateIncident(
                violation_type=payload.violation_type,
                plate_no=hashed_plate,
                geo_cluster=f"SRID=4326;POINT({cluster.centroid_lon} {cluster.centroid_lat})",
                window_start=cluster.window_start,
                window_end=cluster.window_end,
                status=trigger_decision.incident_status.value,
            )
            db.add(incident)
            await db.flush()
        else:
            incident.window_start = min(incident.window_start, cluster.window_start)
            incident.window_end = max(incident.window_end, cluster.window_end)
            if incident.status == "candidate" and trigger_decision.should_request_evidence:
                incident.status = trigger_decision.incident_status.value

        # Link observation to incident in association table
        link_check = await db.execute(
            select(incident_observations).where(
                incident_observations.c.incident_id == incident.id,
                incident_observations.c.observation_id == observation.id,
            )
        )
        if not link_check.first():
            await db.execute(
                insert(incident_observations).values(
                    incident_id=incident.id,
                    observation_id=observation.id,
                )
            )

        # Trigger evidence collection if corroborated
        if trigger_decision.should_request_evidence:
            for req_target in trigger_decision.evidence_requests:
                ev_stmt = select(Evidence).where(
                    Evidence.incident_id == incident.id,
                    Evidence.device_id == req_target.device_id,
                    Evidence.event_nonce == req_target.event_nonce,
                )
                ev_res = await db.execute(ev_stmt)
                if not ev_res.scalar_one_or_none():
                    ev_record = Evidence(
                        incident_id=incident.id,
                        device_id=req_target.device_id,
                        event_nonce=req_target.event_nonce,
                        retention_expires_at=req_target.retention_expires_at,
                    )
                    db.add(ev_record)

    await db.commit()

    logger.info(
        "Observation registered successfully",
        extra={
            "device_id": payload.device_id,
            "event_nonce": payload.event_nonce,
            "hashed_plate": hashed_plate,
        },
    )

    return ObservationResponse(
        status="accepted",
        event_nonce=payload.event_nonce,
        hashed_plate=hashed_plate,
        message="Observation recorded and queued for analysis",
    )
