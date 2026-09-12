"""Internal admin endpoints — not for external device or reviewer use.

These endpoints allow on-demand triggering of background sweep jobs that are
normally run on a schedule by APScheduler.  Useful for:
  - Integration tests / the synthetic burst generator (which cannot wait for
    the scheduler to fire on its own timetable).
  - Operational runbooks (force a sweep without restarting the service).

No reviewer JWT is required — these should be placed behind a network-level
firewall or internal service mesh policy in production; they are intentionally
NOT authenticated here so the synthetic generator can call them without
setting up reviewer credentials.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Query

from app.services.sweeps import sweep_evidence_ttl, sweep_stale_observations

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/sweep/stale-observations")
async def trigger_stale_observation_sweep(
    time_window_seconds: Optional[float] = Query(
        None,
        description=(
            "Override corroboration time window in seconds. "
            "Defaults to CORROBORATION_TIME_WINDOW_SECONDS from settings."
        ),
    ),
) -> dict:
    """Trigger the stale-observation sweep job on demand.

    Finds candidate incidents older than time_window_seconds with a single
    observation and rejects them as overtaking_artifact via
    evaluate_stale_observation().
    """
    return await sweep_stale_observations(time_window_seconds=time_window_seconds)


@router.post("/sweep/evidence-ttl")
async def trigger_evidence_ttl_sweep(
    ttl_days: Optional[float] = Query(
        None,
        description=(
            "Override evidence TTL in days. "
            "Defaults to EVIDENCE_TTL_DAYS from settings."
        ),
    ),
) -> dict:
    """Trigger the evidence-TTL sweep job on demand.

    Finds corroborated incidents with no uploaded evidence past their TTL and
    transitions them to corroborated_no_evidence via evaluate_evidence_timeout().
    """
    timeout = timedelta(days=ttl_days) if ttl_days is not None else None
    return await sweep_evidence_ttl(timeout_duration=timeout)
