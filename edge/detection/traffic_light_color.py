from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class TrafficLightResult:
    """Heuristic red/yellow/green evidence for a traffic-light crop.

    The confidence field is intentionally a deterministic heuristic evidence score in the
    range [0, 1], not a machine-learning probability. It is a transparent score derived from
    the relative strength of the winning HSV signal in the crop.
    """

    color: str
    confidence: float
    red_pixel_count: int = 0
    yellow_pixel_count: int = 0
    green_pixel_count: int = 0

    def __str__(self) -> str:
        return self.color

    @property
    def value(self) -> str:
        return self.color


def _normalize_color_name(color: str | None) -> str:
    if color is None:
        return "unknown"
    return str(color).strip().lower()


def _resolve_hsv_ranges(
    min_saturation: int,
    min_value: int,
    red_hsv_ranges: tuple[tuple[int, int, int], tuple[int, int, int]] | None = None,
    yellow_hsv_range: tuple[tuple[int, int, int], tuple[int, int, int]] | None = None,
    green_hsv_range: tuple[tuple[int, int, int], tuple[int, int, int]] | None = None,
) -> tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...]:
    if red_hsv_ranges is None:
        red_hsv_ranges = (
            ((0, min_saturation, min_value), (10, 255, 255)),
            ((170, min_saturation, min_value), (179, 255, 255)),
        )
    if yellow_hsv_range is None:
        yellow_hsv_range = ((15, min_saturation, min_value), (35, 255, 255))
    if green_hsv_range is None:
        green_hsv_range = ((40, min_saturation, min_value), (90, 255, 255))

    return red_hsv_ranges, yellow_hsv_range, green_hsv_range


def classify_traffic_light_color(
    crop: np.ndarray,
    min_pixel_count: int = 3,
    min_saturation: int = 80,
    min_value: int = 80,
    *,
    min_signal_ratio: float = 0.55,
    min_relative_signal_ratio: float = 0.12,
    red_hsv_ranges: tuple[tuple[int, int, int], tuple[int, int, int]] | None = None,
    yellow_hsv_range: tuple[tuple[int, int, int], tuple[int, int, int]] | None = None,
    green_hsv_range: tuple[tuple[int, int, int], tuple[int, int, int]] | None = None,
) -> TrafficLightResult:
    """Classify a traffic-light crop using HSV masks with yellow support.

    The returned confidence is a deterministic heuristic evidence score in [0, 1], not a
    machine-learning probability.
    """
    if not isinstance(crop, np.ndarray) or crop.size == 0:
        raise ValueError("Traffic-light crop must be a non-empty NumPy image array.")
    if crop.ndim != 3 or crop.shape[2] != 3:
        raise ValueError("Traffic-light crop must be a BGR image with shape H x W x 3.")
    if min_pixel_count < 1:
        raise ValueError("min_pixel_count must be at least 1.")
    if not 0.0 <= min_signal_ratio <= 1.0:
        raise ValueError("min_signal_ratio must be between 0.0 and 1.0.")
    if not 0.0 <= min_relative_signal_ratio <= 1.0:
        raise ValueError("min_relative_signal_ratio must be between 0.0 and 1.0.")

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    area = int(crop.shape[0] * crop.shape[1])
    min_absolute_pixels = max(min_pixel_count, int(area * min_relative_signal_ratio))

    red_ranges, yellow_range, green_range = _resolve_hsv_ranges(
        min_saturation=min_saturation,
        min_value=min_value,
        red_hsv_ranges=red_hsv_ranges,
        yellow_hsv_range=yellow_hsv_range,
        green_hsv_range=green_hsv_range,
    )

    red_count = 0
    for lower, upper in red_ranges:
        red_count += int(
            cv2.countNonZero(
                cv2.inRange(
                    hsv,
                    np.array(lower, dtype=np.uint8),
                    np.array(upper, dtype=np.uint8),
                )
            )
        )

    yellow_count = int(
        cv2.countNonZero(
            cv2.inRange(hsv, np.array(yellow_range[0], dtype=np.uint8), np.array(yellow_range[1], dtype=np.uint8))
        )
    )
    green_count = int(
        cv2.countNonZero(
            cv2.inRange(hsv, np.array(green_range[0], dtype=np.uint8), np.array(green_range[1], dtype=np.uint8))
        )
    )

    total_signal = red_count + yellow_count + green_count
    if total_signal < min_absolute_pixels:
        return TrafficLightResult(
            color="unknown",
            confidence=0.0,
            red_pixel_count=red_count,
            yellow_pixel_count=yellow_count,
            green_pixel_count=green_count,
        )

    counts = {"red": red_count, "yellow": yellow_count, "green": green_count}
    winner = max(counts, key=counts.get)
    winner_count = counts[winner]
    if total_signal == 0:
        return TrafficLightResult(
            color="unknown",
            confidence=0.0,
            red_pixel_count=red_count,
            yellow_pixel_count=yellow_count,
            green_pixel_count=green_count,
        )

    relative_signal = winner_count / total_signal
    if relative_signal < min_signal_ratio:
        return TrafficLightResult(
            color="unknown",
            confidence=float(min(1.0, relative_signal)),
            red_pixel_count=red_count,
            yellow_pixel_count=yellow_count,
            green_pixel_count=green_count,
        )

    second_best = sorted(counts.values(), reverse=True)[1]
    margin = (winner_count - second_best) / max(total_signal, 1)
    heuristic_confidence = float(min(1.0, max(0.0, 0.55 * relative_signal + 0.45 * margin + 0.05)))

    if winner == "red" and red_count >= max(green_count, yellow_count):
        color = "red"
    elif winner == "yellow" and yellow_count >= max(red_count, green_count):
        color = "yellow"
    elif winner == "green" and green_count >= max(red_count, yellow_count):
        color = "green"
    else:
        color = "unknown"
        heuristic_confidence *= 0.35

    return TrafficLightResult(
        color=color,
        confidence=float(max(0.0, min(1.0, heuristic_confidence))),
        red_pixel_count=red_count,
        yellow_pixel_count=yellow_count,
        green_pixel_count=green_count,
    )
