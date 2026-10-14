from __future__ import annotations

from dataclasses import dataclass

from edge.tracking.tracker import Track


@dataclass
class WrongWayCandidateDecision:
    """Decision outcome of wrong-way candidate rule engine check (§4.1)."""

    is_candidate: bool
    reason: str
    track_id: int | None = None
    plate_text: str | None = None
    motion_vector: tuple[float, float] | None = None


def check_wrong_way_candidate(
    track: Track,
    frame_width: int = 1920,
    frame_height: int = 1080,
    roi_max_x_ratio: float = 0.50,
    min_downward_displacement: float = 10.0,
    min_consecutive_downward_steps: int = 2,
    window_frames: int = 6,
) -> WrongWayCandidateDecision:
    """Evaluates whether a tracked vehicle is a candidate wrong-way driver (§4.1).

    Logic:
    1. Vehicle is situated in the left-half ROI of the frame ([0, 0.5 * W]).
    2. Vehicle shows downward motion (closing toward the camera / opposite flow, dy > 0).
    3. Motion is verified across consecutive tracked frames (rejecting stationary/jittery tracks).

    Note: Per §4.1, this is an intentionally minimal edge candidate flag.
    Complex disambiguation (e.g. progression filtering, overtake elimination)
    is intentionally executed server-side.
    """
    tid = track.track_id
    plate = track.plate_text

    # 1. Check ROI: Left half of the frame
    latest_bbox = track.current_bbox
    center_x = (latest_bbox[0] + latest_bbox[2]) / 2.0
    roi_limit_x = frame_width * roi_max_x_ratio

    if center_x > roi_limit_x:
        return WrongWayCandidateDecision(
            is_candidate=False,
            reason=f"Vehicle center ({center_x:.1f}px) is outside left-half ROI (<= {roi_limit_x:.1f}px)",
            track_id=tid,
            plate_text=plate,
        )

    # 2. Check track history sufficiency
    if len(track.bbox_history) < 2:
        return WrongWayCandidateDecision(
            is_candidate=False,
            reason="Insufficient track history to evaluate motion (<2 frames)",
            track_id=tid,
            plate_text=plate,
        )

    # 3. Overall motion vector over window
    mvec = track.get_motion_vector(last_n_frames=window_frames)
    if mvec is None:
        return WrongWayCandidateDecision(
            is_candidate=False,
            reason="Unable to compute motion vector over window",
            track_id=tid,
            plate_text=plate,
        )

    dx, dy = mvec

    # 1. Stationary / sub-threshold check
    if abs(dy) < min_downward_displacement:
        return WrongWayCandidateDecision(
            is_candidate=False,
            reason=f"Vehicle displacement is sub-threshold / stationary (dy={dy:.1f}px < {min_downward_displacement:.1f}px)",
            track_id=tid,
            plate_text=plate,
            motion_vector=mvec,
        )

    # 2. In camera coordinates, moving towards camera is downward (dy > 0)
    if dy < 0:
        return WrongWayCandidateDecision(
            is_candidate=False,
            reason=f"Vehicle is moving upward / away from camera (dy={dy:.1f}px <= 0)",
            track_id=tid,
            plate_text=plate,
            motion_vector=mvec,
        )

    # 4. Check step-by-step consistency across consecutive tracked frames
    steps = track.get_step_displacements(last_n_frames=window_frames)
    downward_steps = sum(1 for _, s_dy in steps if s_dy > 1.0)
    upward_steps = sum(1 for _, s_dy in steps if s_dy < -1.0)

    if downward_steps < min_consecutive_downward_steps:
        return WrongWayCandidateDecision(
            is_candidate=False,
            reason=f"Insufficient downward steps ({downward_steps} < {min_consecutive_downward_steps})",
            track_id=tid,
            plate_text=plate,
            motion_vector=mvec,
        )

    # Ambiguity check: if upward steps exceed downward steps or erratic oscillation
    if upward_steps >= downward_steps:
        return WrongWayCandidateDecision(
            is_candidate=False,
            reason=f"Motion is erratic or oscillating (downward={downward_steps}, upward={upward_steps})",
            track_id=tid,
            plate_text=plate,
            motion_vector=mvec,
        )

    # All conditions met: flag candidate
    return WrongWayCandidateDecision(
        is_candidate=True,
        reason=f"Vehicle in left-half ROI moving downward toward camera (dy={dy:.1f}px across {downward_steps} steps)",
        track_id=tid,
        plate_text=plate,
        motion_vector=mvec,
    )
