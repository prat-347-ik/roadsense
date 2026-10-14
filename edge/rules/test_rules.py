import pytest
from edge.rules.red_light import (
    TrafficLightStateSmoother,
    check_red_light_candidate,
    crossed_stop_line,
    is_sightline_blocked,
)
from edge.rules.wrong_way import check_wrong_way_candidate
from edge.tracking.tracker import Track


def create_synthetic_track(
    track_id: int,
    positions: list[list[float]],
    vehicle_class: str = "car",
    plate_text: str | None = None,
) -> Track:
    """Helper to generate a Track with a predetermined trajectory."""
    t = Track(
        track_id=track_id,
        current_bbox=positions[0],
        vehicle_class=vehicle_class,
        first_frame_idx=1,
        last_frame_idx=1,
        plate_text=plate_text,
    )
    for idx, box in enumerate(positions[1:], start=2):
        t.update(bbox=box, score=0.9, frame_idx=idx)
    return t


# ============================================================================
# RED LIGHT UNIT TESTS (§3)
# ============================================================================

def test_red_light_crossing_on_red_flags():
    """A vehicle originating in bottom 2/3 moving upward past the stop line during RED."""
    # Screen: 1920x1080. Bottom 2/3 boundary = 360px.
    # Start at y=800 (near bottom), move upward to y=400 (past stop line 700px).
    boxes = [
        [800, 800, 1000, 950],
        [800, 700, 1000, 850],
        [800, 600, 1000, 750],
        [800, 500, 1000, 650],
        [800, 400, 1000, 550],
    ]
    track = create_synthetic_track(1, boxes, plate_text="MH12AB1234")
    decision = check_red_light_candidate(track, traffic_light_color="RED")

    assert decision.is_candidate is True
    assert "Vehicle crossed through intersection" in decision.reason
    assert decision.track_id == 1
    assert decision.plate_text == "MH12AB1234"
    assert decision.motion_vector[1] < -10.0


def test_red_light_stopped_before_stop_line_does_not_flag():
    """A vehicle stationary before the stop line during RED."""
    # Stopped at y=850 (below stop line 702px) with minimal/no motion
    boxes = [
        [800, 850, 1000, 1000],
        [800, 851, 1000, 1001],
        [800, 850, 1000, 1000],
        [800, 849, 1000, 999],
    ]
    track = create_synthetic_track(2, boxes)
    decision = check_red_light_candidate(track, traffic_light_color="RED")

    assert decision.is_candidate is False
    assert "stationary" in decision.reason or "has not crossed stop line" in decision.reason


def test_red_light_crossing_on_green_does_not_flag():
    """A vehicle crossing cleanly while signal is GREEN."""
    boxes = [
        [800, 800, 1000, 950],
        [800, 600, 1000, 750],
        [800, 400, 1000, 550],
    ]
    track = create_synthetic_track(3, boxes)
    decision = check_red_light_candidate(track, traffic_light_color="GREEN")

    assert decision.is_candidate is False
    assert "Traffic light is not RED" in decision.reason


def test_red_light_left_edge_exit_exclusion():
    """A vehicle turning left exiting via the left edge of frame per §3 exclusion."""
    # Moving upward and leftward, exiting near left edge (x1 <= 150px)
    boxes = [
        [500, 800, 700, 950],
        [350, 650, 550, 800],
        [200, 500, 400, 650],
        [40, 400, 240, 550],   # x1 = 40px (< 153px left margin)
    ]
    track = create_synthetic_track(4, boxes, plate_text="MH14CD5678")
    decision = check_red_light_candidate(track, traffic_light_color="RED")

    assert decision.is_candidate is False
    assert "left-turn exclusion" in decision.reason


def test_red_light_reversing_or_wrong_direction_does_not_flag():
    """A vehicle moving downward (reversing / oncoming) should not flag."""
    boxes = [
        [800, 500, 1000, 650],
        [800, 600, 1000, 750],
        [800, 700, 1000, 850],
    ]
    track = create_synthetic_track(5, boxes)
    decision = check_red_light_candidate(track, traffic_light_color="RED")

    assert decision.is_candidate is False
    assert "moving downward/reversing" in decision.reason


def test_red_light_sightline_blocked_aborts():
    """Sightline blocked by vehicle directly ahead aborts the check."""
    boxes = [
        [800, 700, 1000, 850],
        [800, 500, 1000, 650],
    ]
    track = create_synthetic_track(6, boxes)

    # Large vehicle right in front of camera
    front_vehicle = create_synthetic_track(7, [[700, 850, 1220, 1050]])
    blocked = is_sightline_blocked([front_vehicle])
    assert blocked is True

    decision = check_red_light_candidate(track, traffic_light_color="RED", sightline_blocked=blocked)
    assert decision.is_candidate is False
    assert "Sightline into intersection is blocked" in decision.reason


def test_red_light_origin_outside_bottom_two_thirds_rejected():
    """A vehicle originating in the top third (distant cross-traffic) does not flag."""
    # Top 1/3 is y < 360px
    boxes = [
        [800, 150, 950, 250],
        [800, 120, 950, 220],
        [800, 90, 950, 190],
    ]
    track = create_synthetic_track(8, boxes)
    decision = check_red_light_candidate(track, traffic_light_color="RED")

    assert decision.is_candidate is False
    assert "Vehicle did not originate in bottom two-thirds" in decision.reason


def test_traffic_light_state_smoother_keeps_red_through_unknown():
    smoother = TrafficLightStateSmoother(history_length=5, min_agreeing_observations=3)
    for obs in ["RED", "RED", "UNKNOWN", "RED", "RED"]:
        state = smoother.update(obs)
    assert state == "RED"


def test_traffic_light_state_smoother_eventually_accepts_sustained_green_transition():
    smoother = TrafficLightStateSmoother(history_length=5, min_agreeing_observations=3)
    for obs in ["RED", "RED", "GREEN", "GREEN", "GREEN"]:
        state = smoother.update(obs)
    assert state == "GREEN"


def test_crossed_stop_line_uses_bottom_center():
    boxes = [
        [100, 800, 200, 900],
        [100, 750, 200, 850],
        [100, 700, 200, 800],
        [100, 550, 200, 650],
    ]
    track = create_synthetic_track(9, boxes)
    assert crossed_stop_line(track, stop_line_y=650) is True


def test_track_bottom_center_is_derived_from_lowest_edge():
    track = create_synthetic_track(15, [[100, 250, 200, 350], [110, 220, 210, 330]])
    center = track.get_bottom_center()
    assert center == (160.0, 330.0)


# ============================================================================
# WRONG WAY UNIT TESTS (§4.1)
# ============================================================================

def test_wrong_way_downward_in_left_roi_flags():
    """A vehicle in the left-half ROI moving downward (toward camera) across frames."""
    # Left ROI: x in [0, 960] for 1920w. Downward: dy > 0.
    boxes = [
        [200, 200, 400, 350],
        [200, 250, 400, 400],
        [200, 310, 400, 460],
        [200, 380, 400, 530],
    ]
    track = create_synthetic_track(10, boxes, plate_text="MH46EF9999")
    decision = check_wrong_way_candidate(track)

    assert decision.is_candidate is True
    assert "Vehicle in left-half ROI moving downward toward camera" in decision.reason
    assert decision.track_id == 10
    assert decision.plate_text == "MH46EF9999"
    assert decision.motion_vector[1] > 10.0


def test_wrong_way_moving_normally_away_does_not_flag():
    """A vehicle in left ROI moving away from camera (normal flow, dy < 0) does not flag."""
    boxes = [
        [200, 600, 400, 750],
        [200, 520, 400, 670],
        [200, 440, 400, 590],
    ]
    track = create_synthetic_track(11, boxes)
    decision = check_wrong_way_candidate(track)

    assert decision.is_candidate is False
    assert "Vehicle is moving upward / away from camera" in decision.reason


def test_wrong_way_outside_left_roi_does_not_flag():
    """A vehicle in the right half of the frame (regardless of direction) does not flag."""
    # Right half: center x > 960px
    boxes = [
        [1200, 200, 1400, 350],
        [1200, 270, 1400, 420],
        [1200, 350, 1400, 500],
    ]
    track = create_synthetic_track(12, boxes)
    decision = check_wrong_way_candidate(track)

    assert decision.is_candidate is False
    assert "outside left-half ROI" in decision.reason


def test_wrong_way_stationary_does_not_flag():
    """A stationary vehicle in the left ROI does not flag."""
    boxes = [
        [200, 300, 400, 450],
        [201, 302, 401, 452],
        [200, 301, 400, 451],
        [200, 300, 400, 450],
    ]
    track = create_synthetic_track(13, boxes)
    decision = check_wrong_way_candidate(track)

    assert decision.is_candidate is False
    assert "stationary" in decision.reason or "Insufficient downward steps" in decision.reason


def test_wrong_way_erratic_noisy_motion_rejected():
    """Oscillating / jittery track does not satisfy consecutive direction checks."""
    boxes = [
        [200, 300, 400, 450],
        [200, 340, 400, 490],  # +40 down
        [200, 300, 400, 450],  # -40 up
        [200, 345, 400, 495],  # +45 down
        [200, 325, 400, 475],  # -20 up (net dy = +25, but oscillating: 2 down, 2 up)
    ]
    track = create_synthetic_track(14, boxes)
    decision = check_wrong_way_candidate(track)

    assert decision.is_candidate is False
    assert "erratic" in decision.reason or "oscillating" in decision.reason or "Insufficient downward steps" in decision.reason
