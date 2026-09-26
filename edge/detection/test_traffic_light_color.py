import cv2
import numpy as np
import pytest

from edge.detection.traffic_light_color import classify_traffic_light_color


@pytest.mark.parametrize(
    ("color", "expected"),
    [((0, 0, 255), "red"), ((0, 255, 0), "green"), ((128, 128, 128), "unknown")],
)
def test_classify_solid_color_patch(color: tuple[int, int, int], expected: str) -> None:
    patch = np.full((40, 40, 3), color, dtype=np.uint8)
    assert classify_traffic_light_color(patch, min_pixel_count=10) == expected


def test_red_hue_wraparound_is_supported() -> None:
    hsv_patch = np.full((20, 20, 3), (175, 255, 255), dtype=np.uint8)
    patch = cv2.cvtColor(hsv_patch, cv2.COLOR_HSV2BGR)
    assert classify_traffic_light_color(patch) == "red"


def test_empty_crop_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        classify_traffic_light_color(np.empty((0, 0, 3), dtype=np.uint8))