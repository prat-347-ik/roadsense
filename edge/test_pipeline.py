from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from edge.pipeline import EdgePipeline, PipelineConfig
from edge.storage.observation_queue import ObservationQueue
from edge.tracking.tracker import IOUTracker


class FakeSource:
    def __init__(self, frames: list[np.ndarray]) -> None:
        self.frames = iter(frames)

    def get_frame(self) -> np.ndarray:
        return next(self.frames)

    def get_location(self) -> tuple[float, float] | None:
        return (18.5204, 73.8567)

    def close(self) -> None:
        return None


class Prediction:
    def __init__(self, bbox: tuple[float, float, float, float], class_name: str, confidence: float = 0.9) -> None:
        self.bbox = bbox
        self.class_name = class_name
        self.confidence = confidence


class FakeDetector:
    def __init__(self, predictions: list[list[Prediction]]) -> None:
        self.predictions = iter(predictions)

    def detect(self, _frame: np.ndarray) -> list[Prediction]:
        return next(self.predictions)


def test_pipeline_processes_continuous_frames_and_keeps_metrics(tmp_path: Path) -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frames = [frame.copy() for _ in range(3)]
    vehicle = FakeDetector(
        [[Prediction((5, 20, 35, 45), "car")] for _ in frames]
    )
    plate = FakeDetector([[ ] for _ in frames])
    queue = ObservationQueue(tmp_path / "queue.db")
    pipeline = EdgePipeline(
        FakeSource(frames),
        vehicle,
        plate,
        tracker=IOUTracker(min_hits_to_confirm=2),
        queue=queue,
        config=PipelineConfig(max_frames=3),
    )

    metrics = pipeline.run()

    assert metrics.frames == 3
    assert metrics.stage_timings["vehicle_detection"].samples == 3
    assert metrics.stage_timings["tracking"].samples == 3
    assert queue.get_queue_depth() == 0


def test_pipeline_track_completion_runs_ocr_once_after_silent_drop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OCR is triggered by tracker completion, not repeated active-frame inspection."""
    ocr_calls: list[np.ndarray] = []

    def fake_read_plate(crop: np.ndarray) -> str:
        ocr_calls.append(crop)
        return "MH12AB1234"

    monkeypatch.setattr("edge.tracking.tracker.read_plate", fake_read_plate)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frames = [frame.copy() for _ in range(4)]
    vehicle = FakeDetector(
        [
            [Prediction((10, 20, 120, 70), "car")],
            [Prediction((10, 21, 120, 71), "car")],
            [],
            [],
        ]
    )
    plate = FakeDetector(
        [
            [Prediction((30, 50, 110, 65), "plate")],
            [Prediction((30, 51, 110, 66), "plate")],
            [],
            [],
        ]
    )
    tracker = IOUTracker(min_hits_to_confirm=2, max_lost_frames=1, gating_threshold=0)
    pipeline = EdgePipeline(
        FakeSource(frames),
        vehicle,
        plate,
        tracker=tracker,
        queue=ObservationQueue(tmp_path / "queue.db"),
        config=PipelineConfig(max_frames=4),
    )

    pipeline.run()

    assert len(ocr_calls) == 1
    assert tracker.active_tracks == {}
    assert len(tracker.lost_tracks) == 1
    assert tracker.lost_tracks[0].plate_text == "MH12AB1234"
    assert tracker.lost_tracks[0].ocr_attempted is True
