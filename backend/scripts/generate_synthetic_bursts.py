#!/usr/bin/env python3
"""Synthetic burst generator for RoadSense API — 9 scenarios.

Sends realistic fake observation bursts to the live API and asserts against
both the immediate observation response AND the clustered incident status
(GET /v1/incidents) for every scenario that should produce an incident.

Usage (stack running via docker-compose up):
    python backend/scripts/generate_synthetic_bursts.py [--base-url URL] [--scenario N]

Requires a reviewer JWT for incident-level assertions.  The generator will
attempt to fetch/create a default reviewer account via the /v1/auth endpoints
and obtain a token automatically.

Scenarios
---------
 1  Corroborated real incident (wrong_side)
    Two distinct cameras, 10 s / ~60 m apart.
    Incident status → corroborated.

 2  Parked-car false positive (wrong_side)
    Three bursts, sub-meter jitter.
    Incident status → rejected (parked progression verdict rejects the incident).

 3  Overtaking-artifact false positive (wrong_side)
    Single burst, then POST /v1/internal/sweep/stale-observations with a
    zero-second window forces an immediate sweep.
    Incident status → rejected.

 4  Inconsistent trajectory (wrong_side)
    North / south-reversal / north again.
    Incident status → rejected (REJECTED progression verdict rejects the
    incident even when multiple devices report the same path).

 5  Red-light violation (red_light)
    Two cameras at same intersection.
    Incident status → corroborated.

 6  Stale-span UNCONFIRMED (wrong_side, slow corroboration)
    Two bursts 360 s apart — physically plausible.
    Incident status → candidate (UNCONFIRMED returns to standard
    clustering lifecycle, which needs > corroboration_threshold to upgrade).

 7  Degraded-GPS burst (wrong_side)
    Two cameras with realistic GPS jitter (~30–40 m) within cluster radius.
    Assert single incident created (not fragmented into two candidates).

 8  Never-corroborated flag (wrong_side)
    Single observation, no sweep, no second report.
    Incident status → candidate (the "nothing has happened yet" baseline;
    distinct from scenario 3 which ages out via the sweep).

 9  Evidence-TTL exhaustion (wrong_side)
    Corroborated incident, evidence requested, nothing uploaded, then
    POST /v1/internal/sweep/evidence-ttl with tiny TTL forces expiry.
    Incident status → corroborated_no_evidence.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL_DEFAULT = "http://localhost:8000"
OBS_ENDPOINT = "/v1/observations"
INCIDENTS_ENDPOINT = "/v1/incidents"
SWEEP_STALE_ENDPOINT = "/v1/internal/sweep/stale-observations"
SWEEP_TTL_ENDPOINT = "/v1/internal/sweep/evidence-ttl"

STUB_SIG = "STUB_SIG_FOR_DEV_ONLY"

# Default reviewer credentials (created by entrypoint.sh or seed script).
# Override via env or CLI flags if needed.
DEFAULT_REVIEWER_EMAIL = "admin@roadsense.local"
DEFAULT_REVIEWER_PASSWORD = "roadsense-admin-password"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _nonce() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(dt: datetime) -> str:
    return dt.isoformat()


def _unique_plate(prefix: str) -> str:
    return f"{prefix}{_nonce()[:6].upper()}"


def _burst(
    device_id: str,
    violation_type: str,
    plate_no: str,
    lat: float,
    lon: float,
    timestamp: datetime,
    nonce: str | None = None,
) -> dict[str, Any]:
    return {
        "device_id": device_id,
        "violation_type": violation_type,
        "plate_no": plate_no,
        "lat": lat,
        "lon": lon,
        "timestamp": _ts(timestamp),
        "event_nonce": nonce or _nonce(),
        "sig": STUB_SIG,
    }


def _jitter(base: float, max_meters: float = 35.0) -> float:
    """Apply random jitter of up to max_meters in decimal-degree equivalent."""
    # 1 degree lat ~ 111 000 m; 35 m jitter ~ 0.000315 deg
    deg_per_meter = 1.0 / 111_000
    return base + random.uniform(-max_meters, max_meters) * deg_per_meter


@dataclass
class ScenarioResult:
    name: str
    expected_outcome: str
    requests_sent: list[dict[str, Any]] = field(default_factory=list)
    responses: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    passed: bool = False


def _post_burst(
    client: httpx.Client, base_url: str, payload: dict[str, Any]
) -> dict[str, Any]:
    resp = client.post(f"{base_url}{OBS_ENDPOINT}", json=payload, timeout=30)
    try:
        body = resp.json()
    except Exception:
        body = {"_raw": resp.text}
    body.setdefault("_http_status", resp.status_code)
    return body


def _get_incidents(
    client: httpx.Client,
    base_url: str,
    token: str,
    *,
    status_filter: str | None = None,
    violation_type: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Fetch incident list from the reviewer-authenticated endpoint."""
    params: dict[str, Any] = {"limit": limit}
    if status_filter:
        params["status"] = status_filter
    if violation_type:
        params["violation_type"] = violation_type
    resp = client.get(
        f"{base_url}{INCIDENTS_ENDPOINT}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30,
    )
    if resp.status_code != 200:
        return []
    return resp.json()


def _get_incident(
    client: httpx.Client, base_url: str, token: str, incident_id: int
) -> dict[str, Any] | None:
    resp = client.get(
        f"{base_url}{INCIDENTS_ENDPOINT}/{incident_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code != 200:
        return None
    return resp.json()


def _find_incident_for_plate(
    client: httpx.Client,
    base_url: str,
    token: str,
    hashed_plate: str,
    violation_type: str,
) -> dict[str, Any] | None:
    """Find the most recent incident matching a hashed plate and violation type."""
    incidents = _get_incidents(
        client, base_url, token, violation_type=violation_type, limit=200
    )
    matches = [i for i in incidents if i.get("hashed_plate") == hashed_plate]
    if not matches:
        return None
    # Return the most recent
    return sorted(matches, key=lambda x: x.get("window_end", ""), reverse=True)[0]


def _login(
    client: httpx.Client, base_url: str, email: str, password: str
) -> str | None:
    """Return a reviewer JWT token, or None if login failed."""
    resp = client.post(
        f"{base_url}/v1/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json().get("access_token")
    return None


def _trigger_stale_sweep(
    client: httpx.Client, base_url: str, time_window_seconds: float = 0.0
) -> dict[str, Any]:
    """POST /v1/internal/sweep/stale-observations with an overridden time window."""
    params = {"time_window_seconds": time_window_seconds}
    resp = client.post(
        f"{base_url}{SWEEP_STALE_ENDPOINT}",
        params=params,
        timeout=30,
    )
    try:
        return resp.json()
    except Exception:
        return {"_raw": resp.text, "_status": resp.status_code}


def _trigger_ttl_sweep(
    client: httpx.Client, base_url: str, ttl_days: float = 0.0
) -> dict[str, Any]:
    """POST /v1/internal/sweep/evidence-ttl with a zero/near-zero TTL to force expiry."""
    params = {"ttl_days": ttl_days}
    resp = client.post(
        f"{base_url}{SWEEP_TTL_ENDPOINT}",
        params=params,
        timeout=30,
    )
    try:
        return resp.json()
    except Exception:
        return {"_raw": resp.text, "_status": resp.status_code}


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def scenario_1_corroborated_real_incident(
    client: httpx.Client, base_url: str, token: str
) -> ScenarioResult:
    result = ScenarioResult(
        name="Scenario 1: Corroborated Real Incident (wrong_side)",
        expected_outcome="Both HTTP 201. Incident status → corroborated.",
    )
    plate = _unique_plate("MH12SYN")
    t0 = _now()
    b1 = _burst("cam-syn-north-01", "wrong_side", plate, 18.52040, 73.85670, t0)
    b2 = _burst(
        "cam-syn-south-02",
        "wrong_side",
        plate,
        18.52090,
        73.85690,
        t0 + timedelta(seconds=10),
    )

    r1 = _post_burst(client, base_url, b1)
    r2 = _post_burst(client, base_url, b2)

    result.requests_sent = [b1, b2]
    result.responses = [r1, r2]

    ok1 = r1.get("_http_status") == 201
    ok2 = r2.get("_http_status") == 201
    hashed = r1.get("hashed_plate")
    same_hash = hashed == r2.get("hashed_plate") and hashed is not None

    result.notes.append(f"Burst 1 HTTP {r1.get('_http_status')}: {r1.get('status', r1.get('detail', ''))}")
    result.notes.append(f"Burst 2 HTTP {r2.get('_http_status')}: {r2.get('status', r2.get('detail', ''))}")
    result.notes.append(f"Same hashed_plate: {same_hash}")

    # Incident-level assertion
    incident = _find_incident_for_plate(client, base_url, token, hashed, "wrong_side") if hashed else None
    inc_status = incident.get("status") if incident else None
    result.notes.append(f"Incident status (GET /v1/incidents): {inc_status}")

    result.passed = ok1 and ok2 and same_hash and inc_status == "corroborated"
    result.notes.append(
        "PASS" if result.passed else "FAIL -- expected incident status 'corroborated'"
    )
    return result


def scenario_2_parked_car_false_positive(
    client: httpx.Client, base_url: str, token: str
) -> ScenarioResult:
    result = ScenarioResult(
        name="Scenario 2: Parked-Car False Positive (wrong_side)",
        expected_outcome=(
            "All 3 HTTP 201. Progression filter marks observations as parked. "
            "Incident status → rejected (stationary vehicle rejected by progression)."
        ),
    )
    plate = _unique_plate("DL01PARK")
    t0 = _now()
    cam = "cam-parking-syn-01"
    bursts = [
        _burst(cam, "wrong_side", plate, 28.6139, 77.2090, t0),
        _burst(cam, "wrong_side", plate, 28.613905, 77.209005, t0 + timedelta(seconds=15)),
        _burst(cam, "wrong_side", plate, 28.613902, 77.209001, t0 + timedelta(seconds=45)),
    ]
    responses = [_post_burst(client, base_url, b) for b in bursts]
    result.requests_sent = bursts
    result.responses = responses

    all_201 = all(r.get("_http_status") == 201 for r in responses)
    hashed = responses[0].get("hashed_plate")
    for i, r in enumerate(responses):
        result.notes.append(
            f"Burst {i+1} HTTP {r.get('_http_status')}: {r.get('status', r.get('detail', ''))}"
        )

    incident = _find_incident_for_plate(client, base_url, token, hashed, "wrong_side") if hashed else None
    inc_status = incident.get("status") if incident else None
    result.notes.append(f"Incident status (GET /v1/incidents): {inc_status}")

    # Parked car: rejected by progression filter → incident status is rejected
    result.passed = all_201 and inc_status == "rejected"
    result.notes.append("PASS" if result.passed else f"FAIL -- expected rejected, got {inc_status}")
    return result


def scenario_3_overtaking_artifact(
    client: httpx.Client, base_url: str, token: str
) -> ScenarioResult:
    result = ScenarioResult(
        name="Scenario 3: Overtaking-Artifact False Positive (wrong_side)",
        expected_outcome=(
            "Single burst HTTP 201. "
            "POST /v1/internal/sweep/stale-observations (time_window_seconds=0) "
            "forces immediate sweep → incident status rejected."
        ),
    )
    plate = _unique_plate("MH02OVTK")
    t0 = _now()
    b1 = _burst("cam-highway-syn-99", "wrong_side", plate, 19.0760, 72.8777, t0)
    r1 = _post_burst(client, base_url, b1)
    result.requests_sent = [b1]
    result.responses = [r1]

    ok1 = r1.get("_http_status") == 201
    hashed = r1.get("hashed_plate")
    result.notes.append(f"Burst HTTP {r1.get('_http_status')}: {r1.get('status', r1.get('detail', ''))}")

    # Check incident status before sweep (should be candidate)
    incident_before = (
        _find_incident_for_plate(client, base_url, token, hashed, "wrong_side") if hashed else None
    )
    result.notes.append(f"Before sweep: incident status = {incident_before.get('status') if incident_before else None}")

    # Trigger sweep with time_window_seconds=0 to force immediate rejection
    sweep_result = _trigger_stale_sweep(client, base_url, time_window_seconds=0.0)
    result.notes.append(f"Sweep result: {sweep_result}")

    # Re-fetch incident — should now be rejected
    incident_after = (
        _find_incident_for_plate(client, base_url, token, hashed, "wrong_side") if hashed else None
    )
    inc_status = incident_after.get("status") if incident_after else None
    result.notes.append(f"After sweep: incident status = {inc_status}")

    result.passed = ok1 and inc_status == "rejected"
    result.notes.append(
        "PASS" if result.passed else "FAIL -- expected incident status 'rejected' after sweep"
    )
    return result


def scenario_4_inconsistent_trajectory(
    client: httpx.Client, base_url: str, token: str
) -> ScenarioResult:
    result = ScenarioResult(
        name="Scenario 4: Inconsistent Trajectory (wrong_side)",
        expected_outcome=(
            "All 3 HTTP 201. Trajectory reversal rejected by progression filter. "
            "Incident status → rejected."
        ),
    )
    plate = _unique_plate("MH12ERR")
    t0 = _now()
    bursts = [
        _burst("cam-1-syn", "wrong_side", plate, 18.5200, 73.8560, t0),
        _burst("cam-2-syn", "wrong_side", plate, 18.5210, 73.8560, t0 + timedelta(seconds=10)),
        _burst("cam-3-syn", "wrong_side", plate, 18.5202, 73.8560, t0 + timedelta(seconds=20)),
    ]
    responses = [_post_burst(client, base_url, b) for b in bursts]
    result.requests_sent = bursts
    result.responses = responses

    all_201 = all(r.get("_http_status") == 201 for r in responses)
    hashed = responses[0].get("hashed_plate")
    for i, r in enumerate(responses):
        result.notes.append(
            f"Burst {i+1} HTTP {r.get('_http_status')}: {r.get('status', r.get('detail', ''))}"
        )

    incident = _find_incident_for_plate(client, base_url, token, hashed, "wrong_side") if hashed else None
    inc_status = incident.get("status") if incident else None
    result.notes.append(f"Incident status (GET /v1/incidents): {inc_status}")

    # Inconsistent trajectory: progression rejects the trajectory, forcing incident to rejected
    result.passed = all_201 and inc_status == "rejected"
    result.notes.append(
        "PASS" if result.passed else f"FAIL -- expected rejected, got {inc_status}"
    )
    return result


def scenario_5_red_light_violation(
    client: httpx.Client, base_url: str, token: str
) -> ScenarioResult:
    result = ScenarioResult(
        name="Scenario 5: Red-Light Violation (red_light)",
        expected_outcome="Both HTTP 201. Incident status → corroborated.",
    )
    plate = _unique_plate("GJ05RED")
    t0 = _now()
    b1 = _burst("cam-intersection-east", "red_light", plate, 23.0225, 72.5714, t0)
    b2 = _burst(
        "cam-intersection-west",
        "red_light",
        plate,
        23.02255,
        72.57143,
        t0 + timedelta(seconds=2),
    )
    r1 = _post_burst(client, base_url, b1)
    r2 = _post_burst(client, base_url, b2)
    result.requests_sent = [b1, b2]
    result.responses = [r1, r2]

    ok1 = r1.get("_http_status") == 201
    ok2 = r2.get("_http_status") == 201
    hashed = r1.get("hashed_plate")
    same_hash = hashed == r2.get("hashed_plate") and hashed is not None

    result.notes.append(f"Burst 1 HTTP {r1.get('_http_status')}: {r1.get('status', r1.get('detail', ''))}")
    result.notes.append(f"Burst 2 HTTP {r2.get('_http_status')}: {r2.get('status', r2.get('detail', ''))}")
    result.notes.append(f"Same hashed_plate: {same_hash}")
    result.notes.append("red_light — no wrong_way progression filter.")

    incident = _find_incident_for_plate(client, base_url, token, hashed, "red_light") if hashed else None
    inc_status = incident.get("status") if incident else None
    result.notes.append(f"Incident status (GET /v1/incidents): {inc_status}")

    result.passed = ok1 and ok2 and same_hash and inc_status == "corroborated"
    result.notes.append(
        "PASS" if result.passed else "FAIL -- expected incident status 'corroborated'"
    )
    return result


def scenario_6_stale_span_unconfirmed(
    client: httpx.Client, base_url: str, token: str
) -> ScenarioResult:
    result = ScenarioResult(
        name="Scenario 6: Stale-Span UNCONFIRMED (wrong_side, slow corroboration)",
        expected_outcome=(
            "Both HTTP 201. Progression → UNCONFIRMED (not rejected). "
            "Incident status → candidate (unconfirmed observations do not corroborate)."
        ),
    )
    plate = _unique_plate("DL05SLOW")
    t0 = _now()
    t1 = t0 + timedelta(seconds=360)  # > 300s window
    b1 = _burst("cam-south-gate-syn", "wrong_side", plate, 28.6139, 77.2090, t0)
    b2 = _burst("cam-north-gate-syn", "wrong_side", plate, 28.6300, 77.2090, t1)
    r1 = _post_burst(client, base_url, b1)
    time.sleep(0.1)
    r2 = _post_burst(client, base_url, b2)
    result.requests_sent = [b1, b2]
    result.responses = [r1, r2]

    ok1 = r1.get("_http_status") == 201
    ok2 = r2.get("_http_status") == 201
    hashed = r1.get("hashed_plate")
    same_hash = hashed == r2.get("hashed_plate") and hashed is not None

    result.notes.append(f"Burst 1 HTTP {r1.get('_http_status')}: {r1.get('status', r1.get('detail', ''))}")
    result.notes.append(f"Burst 2 HTTP {r2.get('_http_status')}: {r2.get('status', r2.get('detail', ''))}")
    result.notes.append(f"Same hashed_plate: {same_hash}")

    incident = _find_incident_for_plate(client, base_url, token, hashed, "wrong_side") if hashed else None
    inc_status = incident.get("status") if incident else None
    result.notes.append(f"Incident status (GET /v1/incidents): {inc_status}")
    result.notes.append(
        "Note: 360s span > 300s window → wrong_way_status=UNCONFIRMED (not rejected). "
        "Two distinct bursts exceed the 300s time window, so they remain candidate. "
        "Expected: candidate."
    )

    result.passed = ok1 and ok2 and same_hash and inc_status == "candidate"
    result.notes.append(
        "PASS" if result.passed else f"FAIL -- expected candidate, got {inc_status}"
    )
    return result


def scenario_7_degraded_gps_burst(
    client: httpx.Client, base_url: str, token: str
) -> ScenarioResult:
    """Two cameras with realistic GPS jitter, both within CLUSTER_RADIUS_METERS (100m).

    Assert: single incident created — NOT fragmented into two candidates.
    """
    result = ScenarioResult(
        name="Scenario 7: Degraded-GPS Burst (wrong_side)",
        expected_outcome=(
            "Both HTTP 201. GPS jitter ≤ 40 m. "
            "Single incident created (not fragmented). "
            "Incident status → corroborated."
        ),
    )
    plate = _unique_plate("GJ01GPS")
    t0 = _now()

    # Base location; add realistic GPS jitter (up to ~35 m)
    base_lat, base_lon = 23.02250, 72.57140
    random.seed(42)  # reproducible jitter
    lat1, lon1 = _jitter(base_lat), _jitter(base_lon)
    lat2, lon2 = _jitter(base_lat), _jitter(base_lon)

    b1 = _burst("cam-gps-noisy-syn-1", "wrong_side", plate, lat1, lon1, t0)
    b2 = _burst(
        "cam-gps-noisy-syn-2",
        "wrong_side",
        plate,
        lat2,
        lon2,
        t0 + timedelta(seconds=5),
    )
    r1 = _post_burst(client, base_url, b1)
    r2 = _post_burst(client, base_url, b2)
    result.requests_sent = [b1, b2]
    result.responses = [r1, r2]

    ok1 = r1.get("_http_status") == 201
    ok2 = r2.get("_http_status") == 201
    hashed = r1.get("hashed_plate")
    same_hash = hashed == r2.get("hashed_plate") and hashed is not None

    result.notes.append(
        f"Jittered coords: cam1=({lat1:.6f},{lon1:.6f}) cam2=({lat2:.6f},{lon2:.6f})"
    )
    result.notes.append(f"Burst 1 HTTP {r1.get('_http_status')}: {r1.get('status', r1.get('detail', ''))}")
    result.notes.append(f"Burst 2 HTTP {r2.get('_http_status')}: {r2.get('status', r2.get('detail', ''))}")

    # Count distinct incidents for this plate
    if hashed:
        all_incidents = _get_incidents(
            client, base_url, token, violation_type="wrong_side", limit=200
        )
        matching = [i for i in all_incidents if i.get("hashed_plate") == hashed]
        incident_count = len(matching)
        inc_status = matching[0].get("status") if matching else None
    else:
        incident_count = 0
        inc_status = None

    result.notes.append(
        f"Distinct incidents for this plate: {incident_count} (expected 1)"
    )
    result.notes.append(f"Incident status: {inc_status}")

    result.passed = ok1 and ok2 and same_hash and incident_count == 1 and inc_status == "corroborated"
    result.notes.append(
        "PASS" if result.passed
        else f"FAIL -- expected 1 corroborated incident, got {incident_count} with status {inc_status}"
    )
    return result


def scenario_8_never_corroborated_flag(
    client: httpx.Client, base_url: str, token: str
) -> ScenarioResult:
    """Single observation, no second report, NO sweep run.

    Asserts incident stays candidate — the 'nothing has happened yet' baseline.
    Distinct from scenario 3 which actively ages out via the sweep.
    """
    result = ScenarioResult(
        name="Scenario 8: Never-Corroborated Flag (wrong_side, no sweep)",
        expected_outcome=(
            "Single burst HTTP 201. No sweep triggered. "
            "Incident status → candidate (awaiting corroboration)."
        ),
    )
    plate = _unique_plate("MH14SOLO")
    t0 = _now()
    b1 = _burst("cam-solo-syn-1", "wrong_side", plate, 18.5204, 73.8567, t0)
    r1 = _post_burst(client, base_url, b1)
    result.requests_sent = [b1]
    result.responses = [r1]

    ok1 = r1.get("_http_status") == 201
    hashed = r1.get("hashed_plate")
    result.notes.append(
        f"Burst HTTP {r1.get('_http_status')}: {r1.get('status', r1.get('detail', ''))}"
    )
    result.notes.append("No sweep triggered — incident should remain candidate.")

    incident = _find_incident_for_plate(client, base_url, token, hashed, "wrong_side") if hashed else None
    inc_status = incident.get("status") if incident else None
    result.notes.append(f"Incident status (GET /v1/incidents): {inc_status}")

    result.passed = ok1 and inc_status == "candidate"
    result.notes.append(
        "PASS" if result.passed else "FAIL -- expected incident status 'candidate'"
    )
    return result


def scenario_9_evidence_ttl_exhaustion(
    client: httpx.Client, base_url: str, token: str
) -> ScenarioResult:
    """Corroborated incident, evidence requested, no uploads, then TTL sweep forces expiry.

    Uses POST /v1/internal/sweep/evidence-ttl with ttl_days=0.0001 (~8 seconds)
    to immediately expire the TTL without waiting.
    """
    result = ScenarioResult(
        name="Scenario 9: Evidence-TTL Exhaustion (wrong_side)",
        expected_outcome=(
            "Two bursts HTTP 201. Incident → corroborated, evidence requested. "
            "No evidence uploaded. Sweep with near-zero TTL → corroborated_no_evidence."
        ),
    )
    plate = _unique_plate("HR26TTL")
    t0 = _now()
    b1 = _burst("cam-ttl-north", "wrong_side", plate, 28.4595, 77.0266, t0)
    b2 = _burst(
        "cam-ttl-south",
        "wrong_side",
        plate,
        28.4601,
        77.0268,
        t0 + timedelta(seconds=10),
    )
    r1 = _post_burst(client, base_url, b1)
    r2 = _post_burst(client, base_url, b2)
    result.requests_sent = [b1, b2]
    result.responses = [r1, r2]

    ok1 = r1.get("_http_status") == 201
    ok2 = r2.get("_http_status") == 201
    hashed = r1.get("hashed_plate")

    result.notes.append(f"Burst 1 HTTP {r1.get('_http_status')}: {r1.get('status', r1.get('detail', ''))}")
    result.notes.append(f"Burst 2 HTTP {r2.get('_http_status')}: {r2.get('status', r2.get('detail', ''))}")

    incident_before = (
        _find_incident_for_plate(client, base_url, token, hashed, "wrong_side") if hashed else None
    )
    inc_status_before = incident_before.get("status") if incident_before else None
    result.notes.append(f"Before TTL sweep: incident status = {inc_status_before}")

    if inc_status_before != "corroborated":
        result.notes.append("FAIL -- incident not corroborated before TTL sweep; cannot test TTL exhaustion.")
        result.passed = False
        return result

    # Trigger TTL sweep with 0.0 TTL to force immediate corroborated_no_evidence
    time.sleep(0.05)
    sweep_result = _trigger_ttl_sweep(client, base_url, ttl_days=0.0)
    result.notes.append(f"TTL sweep result: {sweep_result}")

    # Re-fetch incident
    incident_after = (
        _find_incident_for_plate(client, base_url, token, hashed, "wrong_side") if hashed else None
    )
    inc_status_after = incident_after.get("status") if incident_after else None
    result.notes.append(f"After TTL sweep: incident status = {inc_status_after}")

    result.passed = ok1 and ok2 and inc_status_after == "corroborated_no_evidence"
    result.notes.append(
        "PASS" if result.passed
        else "FAIL -- expected corroborated_no_evidence after TTL sweep"
    )
    return result


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------


def _print_separator(char: str = "-", width: int = 76) -> None:
    print(char * width)


def _print_result(r: ScenarioResult, idx: int) -> None:
    _print_separator()
    status_icon = "PASS" if r.passed else "FAIL"
    print(f"\n[{idx}] [{status_icon}]  {r.name}")
    print(f"     Expected: {r.expected_outcome}\n")
    for note in r.notes:
        print(f"     {note}")
    print()


def _print_summary(results: list[ScenarioResult]) -> None:
    _print_separator("=")
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n  SUMMARY: {passed}/{total} scenarios passed\n")
    for i, r in enumerate(results, 1):
        icon = "PASS" if r.passed else "FAIL"
        print(f"  [{icon}]  [{i}] {r.name}")
    print()
    _print_separator("=")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send synthetic observation bursts to RoadSense API and report results."
    )
    parser.add_argument(
        "--base-url", default=BASE_URL_DEFAULT,
        help=f"API base URL (default: {BASE_URL_DEFAULT})",
    )
    parser.add_argument(
        "--scenario", type=int, default=0,
        help="Run a single scenario by number (1-9). Default 0 = all.",
    )
    parser.add_argument(
        "--reviewer-email", default=DEFAULT_REVIEWER_EMAIL,
        help="Reviewer email for JWT login (for incident-level assertions).",
    )
    parser.add_argument(
        "--reviewer-password", default=DEFAULT_REVIEWER_PASSWORD,
        help="Reviewer password for JWT login.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    print(f"\nRoadSense Synthetic Burst Generator — 9 scenarios")
    print(f"Target: {base_url}{OBS_ENDPOINT}")
    print(f"Time:   {_now().isoformat()}")
    _print_separator()

    # Health check
    try:
        health_resp = httpx.get(f"{base_url}/health", timeout=10)
        health_resp.raise_for_status()
        print(f"Health check: {health_resp.json()}")
    except Exception as exc:
        print(
            f"\nFAIL: Cannot reach {base_url}/health -- is the stack running?\n  Error: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Reviewer JWT (required for incident-level assertions)
    with httpx.Client() as client:
        token = _login(client, base_url, args.reviewer_email, args.reviewer_password)
        if not token:
            print(
                f"\nWARNING: Could not obtain reviewer JWT from {base_url}/v1/auth/login. "
                f"Incident-level assertions will show None status. "
                f"Make sure a reviewer account exists with email={args.reviewer_email!r}.",
                file=sys.stderr,
            )
            token = ""

        scenario_fns = [
            scenario_1_corroborated_real_incident,
            scenario_2_parked_car_false_positive,
            scenario_3_overtaking_artifact,
            scenario_4_inconsistent_trajectory,
            scenario_5_red_light_violation,
            scenario_6_stale_span_unconfirmed,
            scenario_7_degraded_gps_burst,
            scenario_8_never_corroborated_flag,
            scenario_9_evidence_ttl_exhaustion,
        ]

        if args.scenario:
            if not 1 <= args.scenario <= len(scenario_fns):
                print(f"--scenario must be 1-{len(scenario_fns)}", file=sys.stderr)
                sys.exit(1)
            selected = [(args.scenario, scenario_fns[args.scenario - 1])]
        else:
            selected = list(enumerate(scenario_fns, start=1))

        results: list[ScenarioResult] = []
        for idx, fn in selected:
            print(f"\nRunning scenario {idx}: {fn.__name__}...")
            try:
                r = fn(client, base_url, token)
            except Exception as exc:
                r = ScenarioResult(
                    name=fn.__name__,
                    expected_outcome="",
                    passed=False,
                    notes=[f"FAIL: Exception: {exc}"],
                )
            results.append(r)
            _print_result(r, idx)

    _print_summary(results)
    if not all(r.passed for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
