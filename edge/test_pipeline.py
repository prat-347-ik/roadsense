from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from edge.pipeline import EdgePipeline, PipelineConfig
from edge.rules.wrong_way import WrongWayCandidateDecision
from edge.storage.observation_queue import ObservationQueue
from edge.tracking.tracker import IOUTracker, Track


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
    def __init__(
        self,
        bbox: tuple[float, float, float, float],
        class_name: str,
        confidence: float = 0.9,
    ) -> None:
        self.bbox = bbox
        self.class_name = class_name
        self.confidence = confidence


class FakeDetector:
    def __init__(self, predictions: list[list[Prediction]]) -> None:
        self.predictions = iter(predictions)

    def detect(self, _frame: np.ndarray) -> list[Prediction]:
        return next(self.predictions)


def test_pipeline_processes_continuous_frames_and_keeps_metrics(
    tmp_path: Path,
) -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frames = [frame.copy() for _ in range(3)]
    vehicle = FakeDetector(
        [[Prediction((5, 20, 35, 45), "car")] for _ in frames]
    )
    plate = FakeDetector([[] for _ in frames])
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    tracker = IOUTracker(
        min_hits_to_confirm=2,
        max_lost_frames=1,
        gating_threshold=0,
    )
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


def _make_candidate_decision(
    plate_text: str | None = None,
) -> WrongWayCandidateDecision:
    return WrongWayCandidateDecision(
        is_candidate=True,
        reason="test candidate",
        track_id=1,
        plate_text=plate_text,
        motion_vector=(0.0, 20.0),
    )


def _make_test_track(track_id: int = 1) -> Track:
    return Track(
        track_id=track_id,
        current_bbox=[10, 20, 120, 70],
        vehicle_class="car",
        first_frame_idx=1,
        last_frame_idx=1,
    )


def test_pending_candidate_waits_for_delayed_ocr(
    tmp_path: Path,
) -> None:
    """A candidate should remain pending until OCR supplies a plate."""
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    queue = ObservationQueue(tmp_path / "delayed-ocr.db")
    tracker = IOUTracker(gating_threshold=0)
    pipeline = EdgePipeline(
        FakeSource([]),
        FakeDetector([]),
        FakeDetector([]),
        tracker=tracker,
        queue=queue,
    )
    track = _make_test_track()
    tracker.active_tracks[track.track_id] = track
    decision = _make_candidate_decision()

    pipeline._emit_candidate(
        track, decision, frame, (18.5204, 73.8567), 1.0
    )

    key = (track.track_id, "wrong_side")
    assert key in pipeline._pending_candidates
    assert queue.get_queue_depth() == 0

    track.plate_text = "MH12AB1234"
    track.ocr_attempted = True
    pipeline._resolve_pending_candidates()

    assert key not in pipeline._pending_candidates
    assert key in pipeline._emitted_tracks
    assert queue.get_queue_depth() == 1
    assert pipeline.metrics.candidates == 1


def test_pending_candidate_without_plate_is_skipped_at_finalization(
    tmp_path: Path,
) -> None:
    """An unreadable plate must not leave a candidate pending indefinitely."""
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    queue = ObservationQueue(tmp_path / "unreadable-plate.db")
    tracker = IOUTracker(gating_threshold=0)
    pipeline = EdgePipeline(
        FakeSource([]),
        FakeDetector([]),
        FakeDetector([]),
        tracker=tracker,
        queue=queue,
    )
    track = _make_test_track()
    tracker.active_tracks[track.track_id] = track

    pipeline._emit_candidate(
        track,
        _make_candidate_decision(),
        frame,
        (18.5204, 73.8567),
        1.0,
    )

    assert (track.track_id, "wrong_side") in pipeline._pending_candidates

    pipeline._finalize_pending_candidates()

    assert pipeline._pending_candidates == {}
    assert queue.get_queue_depth() == 0
    assert pipeline.metrics.skipped_without_plate == 1
    assert track.ocr_attempted is True


def test_repeated_candidate_is_enqueued_only_once(
    tmp_path: Path,
) -> None:
    """Repeated decisions for one track and violation must not duplicate bursts."""
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    queue = ObservationQueue(tmp_path / "duplicate-candidate.db")
    pipeline = EdgePipeline(
        FakeSource([]),
        FakeDetector([]),
        FakeDetector([]),
        tracker=IOUTracker(gating_threshold=0),
        queue=queue,
    )
    track = _make_test_track()
    track.plate_text = "MH12AB1234"
    track.ocr_attempted = True
    decision = _make_candidate_decision("MH12AB1234")

    for _ in range(3):
        pipeline._emit_candidate(
            track, decision, frame, (18.5204, 73.8567), 1.0
        )

    assert queue.get_queue_depth() == 1
    assert pipeline.metrics.candidates == 1
    assert (track.track_id, "wrong_side") in pipeline._emitted_tracks
    assert pipeline._pending_candidates == {}
