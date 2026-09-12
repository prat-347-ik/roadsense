from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from app.services.geo import calculate_bearing, haversine_distance_meters


class ProgressionStatus(str, Enum):
    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class RejectionReason(str, Enum):
    PARKED = "parked"
    OVERTAKING_ARTIFACT = "overtaking_artifact"
    UNREALISTIC_SPEED = "unrealistic_speed"
    INCONSISTENT_TRAJECTORY = "inconsistent_trajectory"


@dataclass
class ObservationPoint:
    lat: float
    lon: float
    ts: datetime
    device_id: str
    event_nonce: str
    hashed_plate: str
    wrong_way_status: Optional[str] = None


@dataclass
class ProgressionEvaluationResult:
    status: ProgressionStatus
    reason: Optional[RejectionReason] = None
    displacement_meters: float = 0.0
    elapsed_seconds: float = 0.0
    speed_mps: float = 0.0
    bearing_deg: Optional[float] = None
    details: str = ""


def calculate_bearing_difference(b1: float, b2: float) -> float:
    """Calculate the smallest angular difference between two bearings in degrees [0..180]."""
    diff = abs(b1 - b2) % 360.0
    return diff if diff <= 180.0 else 360.0 - diff


def evaluate_stale_observation(
    obs: ObservationPoint,
    time_window_seconds: float = 300.0,
    now: Optional[datetime] = None,
) -> ProgressionEvaluationResult:
    """Evaluate a solitary unconfirmed observation that has aged past the corroboration time window.

    If no second moving observation arrived within `time_window_seconds`, the isolated flag is
    rejected as an overtaking artifact (e.g. momentary overtake on the oncoming lane rather than
    sustained wrong-way travel).
    """
    current_time = now or datetime.now(timezone.utc)
    elapsed = (current_time - obs.ts).total_seconds()

    if elapsed > time_window_seconds:
        return ProgressionEvaluationResult(
            status=ProgressionStatus.REJECTED,
            reason=RejectionReason.OVERTAKING_ARTIFACT,
            elapsed_seconds=elapsed,
            details=(
                f"Solitary observation aged {elapsed:.1f}s past the {time_window_seconds:.1f}s window "
                "with no corroborating trajectory (overtaking artifact)."
            ),
        )

    return ProgressionEvaluationResult(
        status=ProgressionStatus.UNCONFIRMED,
        elapsed_seconds=elapsed,
        details=f"Observation aged {elapsed:.1f}s; still within corroboration window.",
    )


def evaluate_wrong_way_progression(
    new_obs: ObservationPoint,
    prior_observations: List[ObservationPoint],
    parked_threshold_meters: float = 8.0,
    min_movement_meters: float = 12.0,
    min_speed_mps: float = 1.0,
    max_speed_mps: float = 60.0,
    time_window_seconds: float = 300.0,
    max_bearing_deviation_deg: float = 60.0,
    now: Optional[datetime] = None,
) -> ProgressionEvaluationResult:
    """Evaluate wrong-way progression across a sequence of observations sharing the same hashed plate.

    Pure function with no direct database dependency.

    Rules:
    1. Single isolated observation:
       - If aged > time_window_seconds via evaluate_stale_observation -> REJECTED (overtaking_artifact).
       - If within time window -> UNCONFIRMED (waiting for additional spatial-temporal points).
    2. Repeated observations with delta_time > 0 but total displacement <= parked_threshold_meters -> REJECTED (parked).
    3. Trajectory with 3+ points:
       - Every intermediate consecutive segment is checked for directional consistency.
       - If segment bearing reverses or deviates by > max_bearing_deviation_deg -> REJECTED (inconsistent_trajectory).
    4. Consecutive observations with sustained displacement, valid directional consistency, and realistic speed:
       - If total time <= time_window_seconds -> CONFIRMED.
       - If total time > time_window_seconds -> UNCONFIRMED (span exceeded window; remains unconfirmed awaiting evidence/clustering).
    """
    if not prior_observations:
        if now is not None:
            return evaluate_stale_observation(new_obs, time_window_seconds=time_window_seconds, now=now)
        return ProgressionEvaluationResult(
            status=ProgressionStatus.UNCONFIRMED,
            details="First observation for plate; awaiting corroboration.",
        )

    # Combine and sort all points chronologically
    all_points = sorted(prior_observations + [new_obs], key=lambda p: p.ts)

    first_point = all_points[0]
    last_point = all_points[-1]

    total_time = (last_point.ts - first_point.ts).total_seconds()
    total_displacement = haversine_distance_meters(
        first_point.lat, first_point.lon, last_point.lat, last_point.lon
    )

    # 1. Parked car detection: multiple observations over time at stationary position
    if total_time >= 3.0 and total_displacement <= parked_threshold_meters:
        return ProgressionEvaluationResult(
            status=ProgressionStatus.REJECTED,
            reason=RejectionReason.PARKED,
            displacement_meters=total_displacement,
            elapsed_seconds=total_time,
            details=f"Stationary target: moved only {total_displacement:.1f}m over {total_time:.1f}s.",
        )

    # 2. Zero or negative time delta
    if total_time <= 0.0:
        return ProgressionEvaluationResult(
            status=ProgressionStatus.UNCONFIRMED,
            displacement_meters=total_displacement,
            elapsed_seconds=0.0,
            details="Zero time delta between observations.",
        )

    calculated_speed = total_displacement / total_time

    # 3. Check for unrealistic speed / sensor glitches
    if calculated_speed > max_speed_mps:
        return ProgressionEvaluationResult(
            status=ProgressionStatus.REJECTED,
            reason=RejectionReason.UNREALISTIC_SPEED,
            displacement_meters=total_displacement,
            elapsed_seconds=total_time,
            speed_mps=calculated_speed,
            details=f"Calculated speed {calculated_speed:.1f}m/s exceeds upper bound {max_speed_mps:.1f}m/s.",
        )

    # 4. Check for intermediate path consistency on 3+ observations
    overall_bearing = calculate_bearing(
        first_point.lat, first_point.lon, last_point.lat, last_point.lon
    )

    if len(all_points) >= 3:
        for i in range(len(all_points) - 1):
            p_curr = all_points[i]
            p_next = all_points[i + 1]
            seg_dist = haversine_distance_meters(p_curr.lat, p_curr.lon, p_next.lat, p_next.lon)

            # Check segments with meaningful displacement (> 3 meters to filter sub-meter GPS noise)
            if seg_dist >= 3.0:
                seg_bearing = calculate_bearing(p_curr.lat, p_curr.lon, p_next.lat, p_next.lon)
                bearing_dev = calculate_bearing_difference(seg_bearing, overall_bearing)

                if bearing_dev > max_bearing_deviation_deg:
                    return ProgressionEvaluationResult(
                        status=ProgressionStatus.REJECTED,
                        reason=RejectionReason.INCONSISTENT_TRAJECTORY,
                        displacement_meters=total_displacement,
                        elapsed_seconds=total_time,
                        speed_mps=calculated_speed,
                        bearing_deg=overall_bearing,
                        details=(
                            f"Inconsistent trajectory: segment {i}->{i+1} bearing {seg_bearing:.1f}° "
                            f"deviates by {bearing_dev:.1f}° from overall bearing {overall_bearing:.1f}° "
                            f"(tolerance: {max_bearing_deviation_deg:.1f}°)."
                        ),
                    )

    # 5. Check if movement and speed qualify for progression
    if total_displacement >= min_movement_meters and calculated_speed >= min_speed_mps:
        # If total corroboration span exceeded time_window_seconds, do NOT auto-reject:
        # return UNCONFIRMED so it flows into the standard clustering & evidence lifecycle.
        if total_time > time_window_seconds:
            return ProgressionEvaluationResult(
                status=ProgressionStatus.UNCONFIRMED,
                displacement_meters=total_displacement,
                elapsed_seconds=total_time,
                speed_mps=calculated_speed,
                bearing_deg=overall_bearing,
                details=f"Corroboration span ({total_time:.1f}s) exceeded window ({time_window_seconds:.1f}s); remaining unconfirmed, awaiting further evidence.",
            )

        return ProgressionEvaluationResult(
            status=ProgressionStatus.CONFIRMED,
            displacement_meters=total_displacement,
            elapsed_seconds=total_time,
            speed_mps=calculated_speed,
            bearing_deg=overall_bearing,
            details=f"Confirmed active progression: {total_displacement:.1f}m in {total_time:.1f}s at {calculated_speed:.1f}m/s.",
        )

    # Intermediate state: moved some distance but hasn't reached min_movement_meters yet
    return ProgressionEvaluationResult(
        status=ProgressionStatus.UNCONFIRMED,
        displacement_meters=total_displacement,
        elapsed_seconds=total_time,
        speed_mps=calculated_speed,
        details="Observation received; progressing towards corroboration threshold.",
    )
