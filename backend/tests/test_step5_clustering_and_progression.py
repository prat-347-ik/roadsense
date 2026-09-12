import uuid
from datetime import datetime, timedelta, timezone
import pytest

from app.core.security import hash_plate
from app.services.clustering import (
    IncidentClusteringStatus,
    ObservationCluster,
    cluster_observations,
    evaluate_evidence_timeout,
    evaluate_evidence_trigger,
)
from app.services.geo import calculate_bearing, encode_geohash, haversine_distance_meters
from app.services.progression import (
    ObservationPoint,
    ProgressionStatus,
    RejectionReason,
    calculate_bearing_difference,
    evaluate_stale_observation,
    evaluate_wrong_way_progression,
)


# ----------------------------------------------------------------------
# Scenario 1: Corroborated Real Incident (2 & 3+ points)
# ----------------------------------------------------------------------


def test_scenario_1_corroborated_real_incident():
    """Scenario 1: Vehicle moving along road, observed by multiple distinct devices.

    - Progression filter confirms active trajectory.
    - Spatial-temporal clustering groups points.
    - Evidence trigger requests clips from both devices and marks status CORROBORATED.
    """
    plate_hash = hash_plate("KA04MH1234")
    t0 = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=10)

    # Device 1: Point A
    obs1 = ObservationPoint(
        lat=18.52040,
        lon=73.85670,
        ts=t0,
        device_id="cam-junction-north",
        event_nonce=str(uuid.uuid4()),
        hashed_plate=plate_hash,
    )
    # Device 2: Point B (approx 60m away, moving at 6 m/s)
    obs2 = ObservationPoint(
        lat=18.52090,
        lon=73.85690,
        ts=t1,
        device_id="cam-junction-south",
        event_nonce=str(uuid.uuid4()),
        hashed_plate=plate_hash,
    )

    # 1. Evaluate Progression
    result = evaluate_wrong_way_progression(obs2, [obs1])
    assert result.status == ProgressionStatus.CONFIRMED
    assert result.displacement_meters > 50.0
    assert result.speed_mps > 1.0
    assert result.bearing_deg is not None
    obs1.wrong_way_status = "confirmed"
    obs2.wrong_way_status = "confirmed"

    # 2. Cluster observations
    clusters = cluster_observations([obs1, obs2], violation_type="wrong_side", cluster_radius_meters=150.0)
    assert len(clusters) == 1
    cluster = clusters[0]
    assert len(cluster.observations) == 2
    assert len(cluster.device_ids) == 2

    # 3. Evaluate Evidence Trigger
    decision = evaluate_evidence_trigger(cluster, corroboration_threshold_devices=2)
    assert decision.incident_status == IncidentClusteringStatus.CORROBORATED
    assert decision.should_request_evidence is True
    assert len(decision.evidence_requests) == 2
    requested_devs = {r.device_id for r in decision.evidence_requests}
    assert requested_devs == {"cam-junction-north", "cam-junction-south"}


def test_scenario_1b_consistent_multi_point_progression():
    """Scenario 1b: 3+ observations along a straight road segment showing sustained directional progression."""
    plate_hash = hash_plate("KA04MULTI3P")
    t0 = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)

    # Heading roughly North (0 deg)
    p1 = ObservationPoint(lat=18.5200, lon=73.8560, ts=t0, device_id="cam-1", event_nonce=str(uuid.uuid4()), hashed_plate=plate_hash)
    p2 = ObservationPoint(lat=18.5208, lon=73.8560, ts=t0 + timedelta(seconds=10), device_id="cam-2", event_nonce=str(uuid.uuid4()), hashed_plate=plate_hash)
    p3 = ObservationPoint(lat=18.5216, lon=73.8560, ts=t0 + timedelta(seconds=20), device_id="cam-3", event_nonce=str(uuid.uuid4()), hashed_plate=plate_hash)

    result = evaluate_wrong_way_progression(p3, [p1, p2])
    assert result.status == ProgressionStatus.CONFIRMED
    assert result.reason is None
    assert result.displacement_meters > 150.0


# ----------------------------------------------------------------------
# Scenario 2: Parked-Car False Positive
# ----------------------------------------------------------------------


def test_scenario_2_parked_car_false_positive():
    """Scenario 2: Stationary vehicle detected multiple times at identical coordinates.

    - Progression filter rejects as 'parked' due to zero/minimal displacement over time.
    """
    plate_hash = hash_plate("DL01PARKED1")
    t0 = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=15)
    t2 = t0 + timedelta(seconds=45)

    obs1 = ObservationPoint(
        lat=28.6139,
        lon=77.2090,
        ts=t0,
        device_id="cam-parking-01",
        event_nonce=str(uuid.uuid4()),
        hashed_plate=plate_hash,
    )
    # Jitter under 1 meter
    obs2 = ObservationPoint(
        lat=28.613905,
        lon=77.209005,
        ts=t1,
        device_id="cam-parking-01",
        event_nonce=str(uuid.uuid4()),
        hashed_plate=plate_hash,
    )
    obs3 = ObservationPoint(
        lat=28.613902,
        lon=77.209001,
        ts=t2,
        device_id="cam-parking-01",
        event_nonce=str(uuid.uuid4()),
        hashed_plate=plate_hash,
    )

    result = evaluate_wrong_way_progression(obs3, [obs1, obs2], parked_threshold_meters=8.0)
    assert result.status == ProgressionStatus.REJECTED
    assert result.reason == RejectionReason.PARKED
    assert "Stationary target" in result.details


def test_scenario_2b_single_device_multi_burst_not_corroborated():
    """Scenario 2b: Single device sending multiple bursts (e.g. parked car or single camera).

    Assert evaluate_evidence_trigger on a cluster with a single device (even with 2+ observations)
    strictly returns CANDIDATE and does NOT trigger evidence collection.
    """
    plate_hash = hash_plate("DL01PARKED1")
    t0 = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=15)
    t2 = t0 + timedelta(seconds=45)

    obs1 = ObservationPoint(
        lat=28.6139,
        lon=77.2090,
        ts=t0,
        device_id="cam-parking-01",
        event_nonce=str(uuid.uuid4()),
        hashed_plate=plate_hash,
        wrong_way_status="confirmed",
    )
    obs2 = ObservationPoint(
        lat=28.613905,
        lon=77.209005,
        ts=t1,
        device_id="cam-parking-01",
        event_nonce=str(uuid.uuid4()),
        hashed_plate=plate_hash,
        wrong_way_status="confirmed",
    )
    obs3 = ObservationPoint(
        lat=28.613902,
        lon=77.209001,
        ts=t2,
        device_id="cam-parking-01",
        event_nonce=str(uuid.uuid4()),
        hashed_plate=plate_hash,
        wrong_way_status="confirmed",
    )

    # 1. Cluster all 3 observations from the single device
    clusters = cluster_observations([obs1, obs2, obs3], violation_type="wrong_side")
    assert len(clusters) == 1
    cluster = clusters[0]
    assert len(cluster.observations) == 3
    assert len(cluster.device_ids) == 1
    assert cluster.device_ids == {"cam-parking-01"}

    # 2. Evaluate evidence trigger - MUST NOT corroborate (requires multiple independent devices)
    decision = evaluate_evidence_trigger(
        cluster,
        corroboration_threshold_devices=2,
        corroboration_threshold_observations=2,
    )
    assert decision.incident_status == IncidentClusteringStatus.CANDIDATE
    assert decision.should_request_evidence is False
    assert len(decision.evidence_requests) == 0
    assert "Candidate only: 1 confirmed device(s)" in decision.reason


# ----------------------------------------------------------------------
# Scenario 3: Overtaking-Artifact False Positive (Reachable & Explicit)
# ----------------------------------------------------------------------


def test_scenario_3_overtaking_artifact_false_positive():
    """Scenario 3: Single brief overtaking flash where no second moving position ever arrives

    and the solitary observation ages past the corroboration time window.
    - Specifically exercises the reachable overtaking artifact path.
    """
    plate_hash = hash_plate("MH02OVERTAKE")
    t0 = datetime(2026, 9, 12, 14, 0, 0, tzinfo=timezone.utc)
    now_past_window = t0 + timedelta(seconds=350)

    obs_single = ObservationPoint(
        lat=19.0760,
        lon=72.8777,
        ts=t0,
        device_id="cam-highway-99",
        event_nonce=str(uuid.uuid4()),
        hashed_plate=plate_hash,
    )

    # 1. At ingestion time (within window): status is UNCONFIRMED
    ingest_res = evaluate_wrong_way_progression(obs_single, [], now=t0 + timedelta(seconds=1))
    assert ingest_res.status == ProgressionStatus.UNCONFIRMED

    # 2. When stale observation check runs after time window expires: REJECTED with OVERTAKING_ARTIFACT
    stale_res = evaluate_stale_observation(obs_single, time_window_seconds=300.0, now=now_past_window)
    assert stale_res.status == ProgressionStatus.REJECTED
    assert stale_res.reason == RejectionReason.OVERTAKING_ARTIFACT
    assert "overtaking artifact" in stale_res.details


def test_scenario_3b_inconsistent_out_and_back_path_rejected():
    """Scenario 3b: 3+ points where net start-to-end displacement is large,

    but intermediate path reverses/deviates (out-and-back-and-out).
    - Must NOT confirm; rejected with INCONSISTENT_TRAJECTORY.
    """
    plate_hash = hash_plate("MH12ERRATIC")
    t0 = datetime(2026, 9, 12, 11, 0, 0, tzinfo=timezone.utc)

    # Point 1: Start (0, 0)
    p1 = ObservationPoint(lat=18.5200, lon=73.8560, ts=t0, device_id="cam-1", event_nonce=str(uuid.uuid4()), hashed_plate=plate_hash)
    # Point 2: Moved North ~110m (bearing 0 deg)
    p2 = ObservationPoint(lat=18.5210, lon=73.8560, ts=t0 + timedelta(seconds=10), device_id="cam-2", event_nonce=str(uuid.uuid4()), hashed_plate=plate_hash)
    # Point 3: Reversed South ~90m back towards start! (bearing 180 deg - 180 deg reversal!)
    p3 = ObservationPoint(lat=18.5202, lon=73.8560, ts=t0 + timedelta(seconds=20), device_id="cam-3", event_nonce=str(uuid.uuid4()), hashed_plate=plate_hash)
    # Point 4: Moved North again ~140m
    p4 = ObservationPoint(lat=18.5215, lon=73.8560, ts=t0 + timedelta(seconds=30), device_id="cam-4", event_nonce=str(uuid.uuid4()), hashed_plate=plate_hash)

    # Endpoints p1 -> p4 net displacement is ~166m, but segment p2 -> p3 reverses direction
    result = evaluate_wrong_way_progression(p4, [p1, p2, p3], max_bearing_deviation_deg=60.0)

    assert result.status == ProgressionStatus.REJECTED
    assert result.reason == RejectionReason.INCONSISTENT_TRAJECTORY
    assert "Inconsistent trajectory" in result.details


def test_scenario_3d_multi_device_rejected_trajectory_forces_rejected_incident_status():
    """Regression: 2+ devices on an inconsistent trajectory must not corroborate.

    Reuses the out-and-back points from test_scenario_3b. Device count must not
    override a REJECTED progression verdict — the incident stays rejected.
    """
    plate_hash = hash_plate("MH12ERRATIC")
    t0 = datetime(2026, 9, 12, 11, 0, 0, tzinfo=timezone.utc)

    # 4 distinct devices reporting the erratic trajectory
    p1 = ObservationPoint(lat=18.5200, lon=73.8560, ts=t0, device_id="cam-1", event_nonce=str(uuid.uuid4()), hashed_plate=plate_hash)
    p2 = ObservationPoint(lat=18.5210, lon=73.8560, ts=t0 + timedelta(seconds=10), device_id="cam-2", event_nonce=str(uuid.uuid4()), hashed_plate=plate_hash)
    p3 = ObservationPoint(lat=18.5202, lon=73.8560, ts=t0 + timedelta(seconds=20), device_id="cam-3", event_nonce=str(uuid.uuid4()), hashed_plate=plate_hash)
    p4 = ObservationPoint(lat=18.5215, lon=73.8560, ts=t0 + timedelta(seconds=30), device_id="cam-4", event_nonce=str(uuid.uuid4()), hashed_plate=plate_hash)

    # 1. Progression evaluates trajectory and rejects it as inconsistent
    prog_result = evaluate_wrong_way_progression(p4, [p1, p2, p3], max_bearing_deviation_deg=60.0)
    assert prog_result.status == ProgressionStatus.REJECTED

    # Update points with rejection status
    p1.wrong_way_status = "rejected"
    p2.wrong_way_status = "rejected"
    p3.wrong_way_status = "rejected"
    p4.wrong_way_status = "rejected"

    # 2. Cluster observations
    clusters = cluster_observations([p1, p2, p3, p4], violation_type="wrong_side", cluster_radius_meters=300.0)
    assert len(clusters) == 1
    cluster = clusters[0]
    assert len(cluster.observations) == 4
    assert len(cluster.device_ids) == 4  # 4 distinct devices!

    # 3. Evidence trigger must reject the incident despite 4 devices
    decision = evaluate_evidence_trigger(cluster, corroboration_threshold_devices=2, corroboration_threshold_observations=2)
    assert decision.incident_status == IncidentClusteringStatus.REJECTED
    assert decision.should_request_evidence is False
    assert len(decision.evidence_requests) == 0
    assert "Incident rejected" in decision.reason


def test_unconfirmed_multi_device_cluster_stays_candidate():
    """UNCONFIRMED wrong-side observations must not corroborate even with 2+ devices."""
    plate_hash = hash_plate("DL05SLOWCORROB")
    t0 = datetime(2026, 9, 12, 15, 0, 0, tzinfo=timezone.utc)
    p1 = ObservationPoint(
        lat=28.6139, lon=77.2090, ts=t0, device_id="cam-south-gate",
        event_nonce=str(uuid.uuid4()), hashed_plate=plate_hash, wrong_way_status="unconfirmed",
    )
    p2 = ObservationPoint(
        lat=28.6145, lon=77.2090, ts=t0 + timedelta(seconds=10), device_id="cam-north-gate",
        event_nonce=str(uuid.uuid4()), hashed_plate=plate_hash, wrong_way_status="unconfirmed",
    )
    clusters = cluster_observations([p1, p2], violation_type="wrong_side")
    assert len(clusters) == 1
    assert len(clusters[0].device_ids) == 2
    decision = evaluate_evidence_trigger(clusters[0], corroboration_threshold_devices=2)
    assert decision.incident_status == IncidentClusteringStatus.CANDIDATE
    assert decision.should_request_evidence is False


def test_scenario_3c_widely_spaced_real_observations_unconfirmed():
    """Scenario 3c: Two real, physically-plausible observations spaced further apart than time_window_seconds.

    - Must return UNCONFIRMED (not REJECTED), leaving it to flow into clustering/evidence lifecycle.
    """
    plate_hash = hash_plate("DL05SLOWCORROB")
    t0 = datetime(2026, 9, 12, 15, 0, 0, tzinfo=timezone.utc)
    # Spaced 360s apart (exceeds 300s window) with 1800m displacement at 5m/s (18 km/h)
    t1 = t0 + timedelta(seconds=360)

    p1 = ObservationPoint(lat=28.6139, lon=77.2090, ts=t0, device_id="cam-south-gate", event_nonce=str(uuid.uuid4()), hashed_plate=plate_hash)
    p2 = ObservationPoint(lat=28.6300, lon=77.2090, ts=t1, device_id="cam-north-gate", event_nonce=str(uuid.uuid4()), hashed_plate=plate_hash)

    result = evaluate_wrong_way_progression(p2, [p1], time_window_seconds=300.0)

    # Must return UNCONFIRMED, not REJECTED
    assert result.status == ProgressionStatus.UNCONFIRMED
    assert result.reason is None
    assert "exceeded window" in result.details.lower()
    assert result.displacement_meters > 1000.0


# ----------------------------------------------------------------------
# Scenario 4: Single Never-Corroborated Flag
# ----------------------------------------------------------------------


def test_scenario_4_single_never_corroborated_flag():
    """Scenario 4: Single uncorroborated observation.

    - Progression is UNCONFIRMED.
    - Cluster status is CANDIDATE (no evidence requested).
    - If TTL expires without second device evidence, evaluate_evidence_timeout marks it CORROBORATED_NO_EVIDENCE.
    """
    plate_hash = hash_plate("MH14SOLO999")
    t0 = datetime(2026, 9, 12, 8, 0, 0, tzinfo=timezone.utc)

    obs1 = ObservationPoint(
        lat=18.5204,
        lon=73.8567,
        ts=t0,
        device_id="cam-solo-1",
        event_nonce=str(uuid.uuid4()),
        hashed_plate=plate_hash,
    )

    # 1. Progression of single observation is UNCONFIRMED
    prog_result = evaluate_wrong_way_progression(obs1, [])
    assert prog_result.status == ProgressionStatus.UNCONFIRMED

    # 2. Clustering produces single-device candidate
    clusters = cluster_observations([obs1], violation_type="wrong_side")
    assert len(clusters) == 1
    cluster = clusters[0]

    # 3. Evidence decision remains CANDIDATE with no requests
    decision = evaluate_evidence_trigger(cluster, corroboration_threshold_devices=2, corroboration_threshold_observations=2)
    assert decision.incident_status == IncidentClusteringStatus.CANDIDATE
    assert decision.should_request_evidence is False

    # 4. Timeout evaluation after TTL expires transitions to terminal state
    now_past_ttl = t0 + timedelta(days=2)
    timed_out_status = evaluate_evidence_timeout(
        incident_status="corroborated",
        evidence_requested_at=t0,
        uploaded_evidence_count=0,
        expected_evidence_count=1,
        timeout_duration=timedelta(days=1),
        now=now_past_ttl,
    )
    assert timed_out_status == IncidentClusteringStatus.CORROBORATED_NO_EVIDENCE


# ----------------------------------------------------------------------
# Scenario 5: Degraded-GPS Burst Queued Cleanly
# ----------------------------------------------------------------------


def test_scenario_5_degraded_gps_burst():
    """Scenario 5: Degraded GPS burst with positional uncertainty / jitter (e.g. 25-40m noise).

    - Geohash and radius clustering still successfully cluster points into a candidate queue rather than discarding.
    """
    plate_hash = hash_plate("GJ01DEGRADED")
    t0 = datetime(2026, 9, 12, 16, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=5)

    # GPS noisy coordinates (30m jitter, within 100m cluster radius)
    obs1 = ObservationPoint(
        lat=23.02250,
        lon=72.57140,
        ts=t0,
        device_id="cam-gps-noisy-1",
        event_nonce=str(uuid.uuid4()),
        hashed_plate=plate_hash,
    )
    obs2 = ObservationPoint(
        lat=23.02275,
        lon=72.57165,
        ts=t1,
        device_id="cam-gps-noisy-2",
        event_nonce=str(uuid.uuid4()),
        hashed_plate=plate_hash,
    )

    clusters = cluster_observations(
        [obs1, obs2],
        violation_type="red_light",
        cluster_radius_meters=100.0,
    )
    assert len(clusters) == 1
    cluster = clusters[0]
    assert len(cluster.observations) == 2
    assert len(cluster.device_ids) == 2

    # Centroid is averaged properly
    assert 23.02250 <= cluster.centroid_lat <= 23.02275
    assert 72.57140 <= cluster.centroid_lon <= 72.57165
