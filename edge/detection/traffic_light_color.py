from __future__ import annotations

import cv2
import numpy as np


def classify_traffic_light_color(
    crop: np.ndarray,
    min_pixel_count: int = 3,
    min_saturation: int = 80,
    min_value: int = 80,
) -> str:
    """Classify a traffic-light crop as red, green, or unknown using HSV masks."""
    if not isinstance(crop, np.ndarray) or crop.size == 0:
        raise ValueError("Traffic-light crop must be a non-empty NumPy image array.")
    if crop.ndim != 3 or crop.shape[2] != 3:
        raise ValueError("Traffic-light crop must be a BGR image with shape H x W x 3.")
    if min_pixel_count < 1:
        raise ValueError("min_pixel_count must be at least 1.")

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    lower_red_1 = np.array([0, min_saturation, min_value], dtype=np.uint8)
    upper_red_1 = np.array([10, 255, 255], dtype=np.uint8)
    lower_red_2 = np.array([170, min_saturation, min_value], dtype=np.uint8)
    upper_red_2 = np.array([179, 255, 255], dtype=np.uint8)
    lower_green = np.array([35, min_saturation, min_value], dtype=np.uint8)
    upper_green = np.array([85, 255, 255], dtype=np.uint8)

    red_count = int(
        cv2.countNonZero(cv2.inRange(hsv, lower_red_1, upper_red_1))
        + cv2.countNonZero(cv2.inRange(hsv, lower_red_2, upper_red_2))
    )
    green_count = int(cv2.countNonZero(cv2.inRange(hsv, lower_green, upper_green)))

    if max(red_count, green_count) < min_pixel_count:
        return "unknown"
    if red_count > green_count:
        return "red"
    if green_count > red_count:
        return "green"
    return "unknown"