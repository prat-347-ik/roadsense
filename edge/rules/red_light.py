from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from edge.tracking.tracker import Track


@dataclass
class RedLightCandidateDecision:
    """Decision outcome of red-light rule engine check."""

    is_candidate: bool
    reason: str
    track_id: int | None = None
    plate_text: str | None = None
    motion_vector: tuple[float, float] | None = None
    signal_color: str | None = None
    crossed_stop_line: bool = False
    sightline_clear: bool = True
    confidence: float | None = None


class TrafficLightStateSmoother:
    """Simple temporal state smoother for traffic-light classifications."""

    def __init__(
        self,
        history_length: int = 5,
        min_agreeing_observations: int = 3,
        min_agreement_ratio: float = 0.60,
    ) -> None:
        self.history_length = max(2, history_length)
        self.min_agreeing_observations = max(1, min_agreeing_observations)
        self.min_agreement_ratio = max(0.0, min(1.0, min_agreement_ratio))
        self.history: deque[str] = deque(maxlen=self.history_length)
        self.current_state = "UNKNOWN"

    @staticmethod
    def _normalize(value: str | Any | None) -> str:
        if value is None:
            return "UNKNOWN"
        if hasattr(value, "color"):
            value = value.color
        if hasattr(value, "value"):
            value = value.value
        normalized = str(value).strip().upper()
        return normalized if normalized in {"RED", "YELLOW", "GREEN", "UNKNOWN"} else "UNKNOWN"

    def update(self, observation: str | Any | None) -> str:
        normalized = self._normalize(observation)
        self.history.append(normalized)

        non_unknown = [v for v in self.history if v != "UNKNOWN"]
        if not non_unknown:
            self.current_state = "UNKNOWN"
            return self.current_state

        counts: dict[str, int] = {}
        for value in non_unknown:
            counts[value] = counts.get(value, 0) + 1

        candidate, candidate_count = max(counts.items(), key=lambda item: (item[1], item[0]))
        ratio = candidate_count / len(non_unknown)
        if candidate_count >= self.min_agreeing_observations and ratio >= self.min_agreement_ratio:
            self.current_state = candidate
            return self.current_state

        if self.current_state != "UNKNOWN" and self.current_state in counts:
            return self.current_state

        self.current_state = candidate
        return self.current_state

    @property
    def state(self) -> str:
        return self.current_state


def _resolve_stop_line_y(frame_height: int, stop_line_y: float | None = None, stop_line_y_ratio: float = 0.65) -> float:
    if stop_line_y is not None:
        return float(stop_line_y)
    return float(frame_height * max(0.0, min(stop_line_y_ratio, 1.0)))


def _vehicle_origin_in_approach_region(track: Track, frame_height: int, origin_bottom_ratio: float = 1.0 / 3.0) -> bool:
    if not track.bbox_history:
        return False
    _, first_bbox = track.bbox_history[0]
    first_bottom = float(first_bbox[3])
    boundary = float(frame_height * max(0.0, min(origin_bottom_ratio, 1.0)))
    return first_bottom >= boundary


def _bottom_center(bbox: list[float] | tuple[float, ...]) -> tuple[float, float]:
    x1, _, x2, y2 = bbox
    return float((x1 + x2) / 2.0), float(y2)


def crossed_stop_line(track: Track, stop_line_y: float, min_history: int = 2) -> bool:
    """Return True once the track reaches or passes the stop-line using bottom-center positions."""
    if len(track.bbox_history) < min_history:
        return False
    points = [_bottom_center(bbox) for _, bbox in track.bbox_history]
    previous = points[-2]
    latest = points[-1]
    return latest[1] <= stop_line_y or (previous[1] > stop_line_y and latest[1] <= stop_line_y)


def is_sightline_blocked(
    tracks: list[Track],
    frame_width: int = 1920,
    frame_height: int = 1080,
    min_bottom_ratio: float = 0.70,
    center_x_range: tuple[float, float] = (0.30, 0.70),
    min_width_ratio: float = 0.20,
) -> bool:
    """Check if host sightline into the intersection is blocked by a vehicle directly ahead.

    Per §3: If there's a vehicle directly in front of the host, the sightline is blocked,
    so nothing downstream of the host can be reliably observed.
    """
    for t in tracks:
        b = t.current_bbox
        w = b[2] - b[0]
        cx = (b[0] + b[2]) / 2.0
        y2 = b[3]

        if (
            y2 >= frame_height * min_bottom_ratio
            and (frame_width * center_x_range[0]) <= cx <= (frame_width * center_x_range[1])
            and w >= frame_width * min_width_ratio
        ):
            return True
    return False


def _normalize_signal_color(signal: str | Any | None) -> str:
    """Normalize traffic-light observations to a conservative, rule-engine-friendly enum."""
    if signal is None:
        return "UNKNOWN"
    if hasattr(signal, "color"):
        signal = signal.color
    elif hasattr(signal, "value"):
        signal = signal.value

    color = str(signal).strip().upper()
    if color not in {"RED", "YELLOW", "GREEN", "UNKNOWN"}:
        return "UNKNOWN"
    return color


def check_red_light_candidate(
    track: Track,
    traffic_light_color: str | Any | None,
    frame_width: int = 1920,
    frame_height: int = 1080,
    stop_line_y: float | None = None,
    stop_line_y_ratio: float = 0.65,
    sightline_blocked: bool = False,
    min_upward_displacement: float = 10.0,
    left_exit_margin_ratio: float = 0.08,
    origin_bottom_ratio: float = 1.0 / 3.0,
) -> RedLightCandidateDecision:
    """Evaluates whether a tracked vehicle is a candidate red-light runner (§3).

    Flowchart:
    1. Signal in frame is RED.
    2. Sightline is clear (not blocked by a vehicle directly in front).
    3. Vehicle originates in bottom two-thirds of the frame (host lane group).
    4. Vehicle is moving upward (receding forward into intersection, dy < 0).
    5. Vehicle is at or past the stop-line.
    6. Exclude vehicles that exit via the left edge (left turns).
    """
    tid = track.track_id
    plate = track.plate_text

    signal_color = _normalize_signal_color(traffic_light_color)
    if signal_color == "UNKNOWN":
        return RedLightCandidateDecision(
            is_candidate=False,
            reason="Traffic light evidence is insufficient or unknown",
            track_id=tid,
            plate_text=plate,
            signal_color=signal_color,
        )

    if signal_color != "RED":
        return RedLightCandidateDecision(
            is_candidate=False,
            reason=f"Traffic light is not RED (current={signal_color})",
            track_id=tid,
            plate_text=plate,
            signal_color=signal_color,
        )

    if sightline_blocked:
        return RedLightCandidateDecision(
            is_candidate=False,
            reason="Sightline into intersection is blocked by vehicle directly in front",
            track_id=tid,
            plate_text=plate,
            signal_color=signal_color,
            sightline_clear=False,
        )

    if not track.bbox_history:
        return RedLightCandidateDecision(
            is_candidate=False,
            reason="No bounding box history available for track",
            track_id=tid,
            plate_text=plate,
            signal_color=signal_color,
        )

    if not _vehicle_origin_in_approach_region(track, frame_height, origin_bottom_ratio=origin_bottom_ratio):
        _, first_bbox = track.bbox_history[0]
        first_bottom = float(first_bbox[3])
        boundary = float(frame_height * max(0.0, min(origin_bottom_ratio, 1.0)))
        return RedLightCandidateDecision(
            is_candidate=False,
            reason=f"Vehicle did not originate in bottom two-thirds of frame (initial y2={first_bottom:.1f} < {boundary:.1f})",
            track_id=tid,
            plate_text=plate,
            signal_color=signal_color,
        )

    mvec = track.get_motion_vector(last_n_frames=10)
    if mvec is None:
        return RedLightCandidateDecision(
            is_candidate=False,
            reason="Insufficient track motion history (<2 frames)",
            track_id=tid,
            plate_text=plate,
            signal_color=signal_color,
        )

    dx, dy = mvec

    if abs(dy) < min_upward_displacement:
        reason = f"Vehicle is stationary (dy={dy:.1f}px, threshold={min_upward_displacement:.1f}px)"
        return RedLightCandidateDecision(
            is_candidate=False,
            reason=reason,
            track_id=tid,
            plate_text=plate,
            motion_vector=mvec,
            signal_color=signal_color,
        )

    if dy >= 0:
        reason = f"Vehicle is moving downward/reversing (dy={dy:.1f}px, threshold=-{min_upward_displacement:.1f}px)"
        return RedLightCandidateDecision(
            is_candidate=False,
            reason=reason,
            track_id=tid,
            plate_text=plate,
            motion_vector=mvec,
            signal_color=signal_color,
        )

    effective_stop_line = _resolve_stop_line_y(frame_height, stop_line_y=stop_line_y, stop_line_y_ratio=stop_line_y_ratio)
    _, latest_bbox = track.bbox_history[-1]
    latest_bottom_center = _bottom_center(latest_bbox)
    if not crossed_stop_line(track, effective_stop_line):
        return RedLightCandidateDecision(
            is_candidate=False,
            reason=f"Vehicle has not crossed stop line (bottom_center_y={latest_bottom_center[1]:.1f} > stop_line={effective_stop_line:.1f})",
            track_id=tid,
            plate_text=plate,
            motion_vector=mvec,
            signal_color=signal_color,
            crossed_stop_line=False,
        )

    left_margin = frame_width * left_exit_margin_ratio
    is_at_left_edge = latest_bbox[0] <= left_margin
    is_heading_left = dx < -5.0

    if is_at_left_edge and is_heading_left:
        return RedLightCandidateDecision(
            is_candidate=False,
            reason=f"Vehicle exited via left edge (left-turn exclusion: x1={latest_bbox[0]:.1f} <= {left_margin:.1f}, dx={dx:.1f})",
            track_id=tid,
            plate_text=plate,
            motion_vector=mvec,
            signal_color=signal_color,
            crossed_stop_line=True,
        )

    return RedLightCandidateDecision(
        is_candidate=True,
        reason="Vehicle crossed through intersection past stop line during RED signal",
        track_id=tid,
        plate_text=plate,
        motion_vector=mvec,
        signal_color=signal_color,
        crossed_stop_line=True,
        sightline_clear=True,
        confidence=0.8,
    )
