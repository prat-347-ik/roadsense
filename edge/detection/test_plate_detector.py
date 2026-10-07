from __future__ import annotations

import sys
from pathlib import Path
import pytest
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from edge.detection.plate_detector import YOLOPlateDetector, draw_plate_detections, Detection

MODEL_PATH = ROOT / "edge" / "runs" / "plate_v1" / "weights" / "best.pt"

def test_plate_detector_init():
    detector = YOLOPlateDetector(model_path=MODEL_PATH, confidence_threshold=0.25)
    assert detector.confidence_threshold == 0.25
    assert detector.model is not None

def test_plate_detector_invalid_threshold():
    with pytest.raises(ValueError):
        YOLOPlateDetector(model_path=MODEL_PATH, confidence_threshold=1.5)

def test_plate_detector_detect_blank_frame():
    detector = YOLOPlateDetector(model_path=MODEL_PATH, confidence_threshold=0.25)
    blank_frame = np.zeros((640, 640, 3), dtype=np.uint8)
    detections = detector.detect(blank_frame)
    assert isinstance(detections, list)
    assert len(detections) == 0

def test_plate_detector_draw_detections():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    detections = [
        Detection(class_id=0, class_name="plate", confidence=0.85, bbox=(100.0, 100.0, 200.0, 150.0))
    ]
    drawn = draw_plate_detections(frame, detections)
    assert drawn.shape == frame.shape
    assert not np.array_equal(drawn, frame)
