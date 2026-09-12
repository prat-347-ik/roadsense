from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from app.core.config import settings
from app.services.geo import encode_geohash, haversine_distance_meters
from app.services.progression import ObservationPoint


class IncidentClusteringStatus(str, Enum):
    CANDIDATE = "candidate"
    CORROBORATED = "corroborated"
    CORROBORATED_NO_EVIDENCE = "corroborated_no_evidence"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


@dataclass
class ObservationCluster:
    violation_type: str
    hashed_plate: str
    geohash: str
    centroid_lat: float
    centroid_lon: float
    window_start: datetime
    window_end: datetime
    observations: List[ObservationPoint] = field(default_factory=list)
    device_ids: Set[str] = field(default_factory=set)


@dataclass
class EvidenceRequestTarget:
    device_id: str
    event_nonce: str
    violation_type: str
    requested_at: datetime
    retention_expires_at: datetime


@dataclass
class EvidenceTriggerDecision:
    incident_status: IncidentClusteringStatus
    should_request_evidence: bool
    evidence_requests: List[EvidenceRequestTarget] = field(default_factory=list)
    reason: str = ""


def cluster_observations(
    observations: List[ObservationPoint],
    violation_type: str,
    cluster_radius_meters: float | None = None,
    time_window_seconds: float | None = None,
    geohash_precision: int | None = None,
) -> List[ObservationCluster]:
    """Group observations agreeing on violation_type, hashed plate_no, spatial proximity, and time window.

    Pure function with configurable clustering thresholds.
    """
    radius = cluster_radius_meters or settings.CLUSTER_RADIUS_METERS
    window_sec = time_window_seconds or float(settings.CORROBORATION_TIME_WINDOW_SECONDS)
    precision = geohash_precision or settings.GEOHASH_PRECISION

    if not observations:
        return []

    # Sort observations chronologically
    sorted_obs = sorted(observations, key=lambda o: o.ts)
    clusters: List[ObservationCluster] = []

    for obs in sorted_obs:
        assigned = False
        obs_geohash = encode_geohash(obs.lat, obs.lon, precision=precision)

        for cluster in clusters:
            # Check violation type and plate match
            if cluster.violation_type != violation_type or cluster.hashed_plate != obs.hashed_plate:
                continue

            # Check time window
            time_diff = (obs.ts - cluster.window_start).total_seconds()
            if abs(time_diff) > window_sec:
                continue

            # Check distance to cluster centroid
            dist = haversine_distance_meters(
                obs.lat, obs.lon, cluster.centroid_lat, cluster.centroid_lon
            )
            if dist <= radius:
                # Add to existing cluster and update centroid & window
                cluster.observations.append(obs)
                cluster.device_ids.add(obs.device_id)
                cluster.window_end = max(cluster.window_end, obs.ts)
                cluster.window_start = min(cluster.window_start, obs.ts)

                # Recompute centroid
                n = len(cluster.observations)
                cluster.centroid_lat = sum(o.lat for o in cluster.observations) / n
                cluster.centroid_lon = sum(o.lon for o in cluster.observations) / n
                cluster.geohash = encode_geohash(cluster.centroid_lat, cluster.centroid_lon, precision=precision)

                assigned = True
                break

        if not assigned:
            # Create a new cluster
            new_cluster = ObservationCluster(
                violation_type=violation_type,
                hashed_plate=obs.hashed_plate,
                geohash=obs_geohash,
                centroid_lat=obs.lat,
                centroid_lon=obs.lon,
                window_start=obs.ts,
                window_end=obs.ts,
                observations=[obs],
                device_ids={obs.device_id},
            )
            clusters.append(new_cluster)

    return clusters


def evaluate_evidence_trigger(
    cluster: ObservationCluster,
    corroboration_threshold_devices: int = 2,
    corroboration_threshold_observations: int = 2,
    evidence_ttl_days: int | None = None,
    now: datetime | None = None,
) -> EvidenceTriggerDecision:
    """Evaluate whether an observation cluster has crossed the corroboration threshold

    to trigger evidence collection from source devices.
    """
    current_time = now or datetime.now(timezone.utc)
    ttl_days = evidence_ttl_days or settings.EVIDENCE_TTL_DAYS
    retention_expiration = current_time + timedelta(days=ttl_days)

    unique_devices = len(cluster.device_ids)
    obs_count = len(cluster.observations)

    # Condition for corroboration: either multiple distinct reporting devices
    # or confirmed multiple observations crossing threshold
    is_corroborated = (
        unique_devices >= corroboration_threshold_devices
        or obs_count >= corroboration_threshold_observations
    )

    if not is_corroborated:
        return EvidenceTriggerDecision(
            incident_status=IncidentClusteringStatus.CANDIDATE,
            should_request_evidence=False,
            reason=f"Candidate only: {unique_devices} device(s), {obs_count} observation(s).",
        )

    # Generate evidence requests for each unique device observation
    evidence_requests = [
        EvidenceRequestTarget(
            device_id=obs.device_id,
            event_nonce=obs.event_nonce,
            violation_type=cluster.violation_type,
            requested_at=current_time,
            retention_expires_at=retention_expiration,
        )
        for obs in cluster.observations
    ]

    return EvidenceTriggerDecision(
        incident_status=IncidentClusteringStatus.CORROBORATED,
        should_request_evidence=True,
        evidence_requests=evidence_requests,
        reason=f"Corroborated by {unique_devices} device(s) and {obs_count} observation(s). Evidence requested.",
    )


def evaluate_evidence_timeout(
    incident_status: str,
    evidence_requested_at: datetime,
    uploaded_evidence_count: int,
    expected_evidence_count: int,
    timeout_duration: timedelta = timedelta(days=1),
    now: datetime | None = None,
) -> IncidentClusteringStatus:
    """Evaluate if an incident with pending evidence has timed out without evidence uploads,

    transitioning it to terminal state `corroborated_no_evidence`.
    """
    current_time = now or datetime.now(timezone.utc)

    if incident_status != IncidentClusteringStatus.CORROBORATED.value:
        return IncidentClusteringStatus(incident_status)

    if uploaded_evidence_count >= expected_evidence_count and expected_evidence_count > 0:
        return IncidentClusteringStatus.CORROBORATED

    if (current_time - evidence_requested_at) > timeout_duration:
        # TTL expired without sufficient uploaded evidence
        return IncidentClusteringStatus.CORROBORATED_NO_EVIDENCE

    return IncidentClusteringStatus.CORROBORATED
