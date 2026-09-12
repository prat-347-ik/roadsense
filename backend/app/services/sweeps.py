"""Scheduled sweep jobs for RoadSense.

Approach: APScheduler (AsyncIOScheduler) embedded in FastAPI's lifespan.

Why NOT Celery beat at this prototype stage
-------------------------------------------
Celery beat requires three extra processes (redis broker is already present,
but you also need a celery worker process and a celery beat process) plus
celery/kombu dependencies.  For two lightweight DB-sweep jobs that run
every few minutes and have no fan-out parallelism requirements, the added
operational complexity outweighs the benefit.

APScheduler runs inside the existing FastAPI process on the same asyncio
event loop, reuses the existing SQLAlchemy async session factory, and adds a
single pip dependency (apscheduler>=3.10).  It can be replaced with Celery
beat with ~30 lines of refactoring if/when the system needs distributed task
execution (e.g. the sweep itself fans out to parallel DB shards).

Jobs registered here
--------------------
1. sweep_stale_observations  — runs every `SWEEP_INTERVAL_SECONDS` seconds.
   Finds single-observation candidate incidents that have not received a
   second corroborating observation within `CORROBORATION_TIME_WINDOW_SECONDS`
   and marks their linked observations as rejected (overtaking_artifact).
   Uses evaluate_stale_observation() for the actual decision.

2. sweep_evidence_ttl  — runs every `EVIDENCE_TTL_CHECK_INTERVAL_SECONDS` seconds.
   Finds corroborated incidents whose evidence-request TTL has expired with no
   uploaded evidence and transitions them to corroborated_no_evidence.
   Uses evaluate_evidence_timeout() for the actual decision.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import get_session_factory
from app.models.entities import CandidateIncident, Evidence, Observation
from app.services.clustering import evaluate_evidence_timeout, IncidentClusteringStatus
from app.services.progression import (
    ObservationPoint,
    ProgressionStatus,
    RejectionReason,
    evaluate_stale_observation,
)

logger = logging.getLogger(__name__)


async def _get_db_session() -> AsyncSession:
    """Open a standalone (non-request-scoped) async DB session for use by sweep jobs."""
    session_factory = get_session_factory()
    return session_factory()


# ---------------------------------------------------------------------------
# Job 1: sweep_stale_observations
# ---------------------------------------------------------------------------


async def sweep_stale_observations(
    time_window_seconds: float | None = None,
) -> dict:
    """Sweep unconfirmed single-observation incidents past the corroboration window.

    For each candidate incident that has exactly one observation and whose
    window_end is older than time_window_seconds, evaluate_stale_observation()
    is called.  If it returns REJECTED (overtaking_artifact), the observation's
    wrong_way_status is updated and the incident is set to 'rejected'.

    Returns a summary dict with counts for monitoring/logging.
    """
    window_sec = (
        float(settings.CORROBORATION_TIME_WINDOW_SECONDS)
        if time_window_seconds is None
        else time_window_seconds
    )
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_sec)

    rejected_count = 0
    skipped_count = 0
    error_count = 0

    async with await _get_db_session() as db:
        try:
            # Find candidate incidents older than the corroboration window that
            # have only a single linked observation (no second corroboration arrived).
            stmt = (
                select(CandidateIncident)
                .options(selectinload(CandidateIncident.observations))
                .where(
                    CandidateIncident.status == "candidate",
                    CandidateIncident.window_end <= cutoff,
                )
            )
            result = await db.execute(stmt)
            incidents: List[CandidateIncident] = result.scalars().all()

            for incident in incidents:
                obs_list = incident.observations
                if len(obs_list) != 1:
                    # Multiple observations — not a solitary unconfirmed flag.
                    # This incident stays candidate; clustering will handle it.
                    skipped_count += 1
                    continue

                obs_orm = obs_list[0]
                obs_point = ObservationPoint(
                    lat=obs_orm.lat,
                    lon=obs_orm.lon,
                    ts=obs_orm.ts,
                    device_id=obs_orm.device_id,
                    event_nonce=obs_orm.event_nonce,
                    hashed_plate=obs_orm.plate_no,
                    wrong_way_status=obs_orm.wrong_way_status,
                )

                stale_result = evaluate_stale_observation(
                    obs_point,
                    time_window_seconds=window_sec,
                )

                if stale_result.status == ProgressionStatus.REJECTED:
                    obs_orm.wrong_way_status = "rejected"
                    incident.status = "rejected"
                    rejected_count += 1
                    logger.info(
                        "Stale sweep: rejected incident %d (observation %d) as %s — %s",
                        incident.id,
                        obs_orm.id,
                        stale_result.reason,
                        stale_result.details,
                    )
                else:
                    skipped_count += 1

            await db.commit()

        except Exception as exc:
            logger.exception("sweep_stale_observations failed: %s", exc)
            error_count += 1
            await db.rollback()

    summary = {
        "job": "sweep_stale_observations",
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "rejected": rejected_count,
        "skipped": skipped_count,
        "errors": error_count,
    }
    logger.info("sweep_stale_observations completed: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# Job 2: sweep_evidence_ttl
# ---------------------------------------------------------------------------


async def sweep_evidence_ttl(
    timeout_duration: timedelta | None = None,
) -> dict:
    """Sweep corroborated incidents whose evidence-request TTL has expired without uploads.

    For each corroborated incident, evaluate_evidence_timeout() is called with
    the count of uploaded vs expected evidence items.  If it returns
    CORROBORATED_NO_EVIDENCE, the incident status is updated accordingly.

    Returns a summary dict with counts.
    """
    ttl = (
        timedelta(days=settings.EVIDENCE_TTL_DAYS)
        if timeout_duration is None
        else timeout_duration
    )

    transitioned_count = 0
    skipped_count = 0
    error_count = 0

    async with await _get_db_session() as db:
        try:
            stmt = (
                select(CandidateIncident)
                .options(selectinload(CandidateIncident.evidence_items))
                .where(CandidateIncident.status == "corroborated")
            )
            result = await db.execute(stmt)
            incidents: List[CandidateIncident] = result.scalars().all()

            now = datetime.now(timezone.utc)

            for incident in incidents:
                ev_items = incident.evidence_items
                expected = len(ev_items)

                if expected == 0:
                    # No evidence was requested — nothing to time out.
                    skipped_count += 1
                    continue

                uploaded = sum(1 for ev in ev_items if ev.uploaded_at is not None)

                # Determine earliest evidence requested_at timestamp directly from the evidence items.
                # Fall back to retention_expires_at - ttl or window_end only if requested_at is not populated.
                earliest_request_time: datetime | None = None
                for ev in ev_items:
                    req_time = ev.requested_at
                    if req_time is None and ev.retention_expires_at is not None:
                        req_time = ev.retention_expires_at - ttl
                    if req_time is not None:
                        if earliest_request_time is None or req_time < earliest_request_time:
                            earliest_request_time = req_time

                if earliest_request_time is None:
                    earliest_request_time = incident.window_end

                new_status = evaluate_evidence_timeout(
                    incident_status=incident.status,
                    evidence_requested_at=earliest_request_time,
                    uploaded_evidence_count=uploaded,
                    expected_evidence_count=expected,
                    timeout_duration=ttl,
                    now=now,
                )

                if new_status == IncidentClusteringStatus.CORROBORATED_NO_EVIDENCE:
                    incident.status = new_status.value
                    transitioned_count += 1
                    logger.info(
                        "Evidence TTL sweep: incident %d transitioned to corroborated_no_evidence "
                        "(uploaded=%d/%d, ttl=%s)",
                        incident.id,
                        uploaded,
                        expected,
                        ttl,
                    )
                else:
                    skipped_count += 1

            await db.commit()

        except Exception as exc:
            logger.exception("sweep_evidence_ttl failed: %s", exc)
            error_count += 1
            await db.rollback()

    summary = {
        "job": "sweep_evidence_ttl",
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "transitioned_to_no_evidence": transitioned_count,
        "skipped": skipped_count,
        "errors": error_count,
    }
    logger.info("sweep_evidence_ttl completed: %s", summary)
    return summary
