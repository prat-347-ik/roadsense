import cv2
import numpy as np
import pytest

from edge.detection.traffic_light_color import (
    TrafficLightResult,
    classify_traffic_light_color,
)


@pytest.mark.parametrize(
    ("color", "expected"),
    [
        ((0, 0, 255), "red"),
        ((0, 255, 0), "green"),
        ((30, 255, 255), "yellow"),
        ((128, 128, 128), "unknown"),
    ],
)
def test_classify_solid_color_patch(color: tuple[int, int, int], expected: str) -> None:
    patch = np.full((40, 40, 3), color, dtype=np.uint8)
    result = classify_traffic_light_color(patch, min_pixel_count=10)
    assert str(result) == expected


def test_red_hue_wraparound_is_supported() -> None:
    hsv_patch = np.full((20, 20, 3), (175, 255, 255), dtype=np.uint8)
    patch = cv2.cvtColor(hsv_patch, cv2.COLOR_HSV2BGR)
    assert str(classify_traffic_light_color(patch)) == "red"


def test_classify_returns_result_metadata() -> None:
    patch = np.full((30, 30, 3), (0, 0, 255), dtype=np.uint8)
    result = classify_traffic_light_color(patch, min_pixel_count=5)
    assert isinstance(result, TrafficLightResult)
    assert result.color == "red"
    assert result.confidence > 0.0
    assert result.red_pixel_count > 0


def test_yellow_and_green_are_separated() -> None:
    yellow_patch = np.full((30, 30, 3), (30, 255, 255), dtype=np.uint8)
    green_patch = np.full((30, 30, 3), (0, 255, 0), dtype=np.uint8)
    assert classify_traffic_light_color(yellow_patch, min_pixel_count=5).color == "yellow"
    assert classify_traffic_light_color(green_patch, min_pixel_count=5).color == "green"


def test_ambiguous_red_green_is_unknown() -> None:
    patch = np.zeros((40, 40, 3), dtype=np.uint8)
    patch[:, :20] = (0, 0, 255)
    patch[:, 20:] = (0, 255, 0)
    result = classify_traffic_light_color(patch, min_pixel_count=1)
    assert result.color == "unknown"


def test_pixel_ratio_threshold_rejects_tiny_noise() -> None:
    patch = np.zeros((20, 20, 3), dtype=np.uint8)
    patch[0, 0] = (0, 0, 255)
    result = classify_traffic_light_color(patch, min_pixel_count=1)
    assert result.color == "unknown"


def test_empty_crop_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        classify_traffic_light_color(np.empty((0, 0, 3), dtype=np.uint8))


def test_invalid_shape_is_rejected() -> None:
    with pytest.raises(ValueError, match="BGR image"):
        classify_traffic_light_color(np.zeros((10, 10), dtype=np.uint8))
