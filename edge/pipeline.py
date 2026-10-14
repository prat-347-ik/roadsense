from __future__ import annotations
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import time
from typing import Any, Callable, Protocol

import numpy as np

from edge.capture import FrameSource
from edge.detection.detector import Detection as VehicleDetection
from edge.detection.traffic_light_color import classify_traffic_light_color
from edge.rules.red_light import (
    TrafficLightStateSmoother,
    check_red_light_candidate,
    is_sightline_blocked,
)
from edge.rules.wrong_way import check_wrong_way_candidate
from edge.storage.evidence_buffer import EvidenceBuffer
from edge.storage.observation_queue import ObservationQueue
from edge.tracking.tracker import Detection, IOUTracker, Track
from edge.uplink.burst import assemble_burst_from_decision
from edge.uplink.client import RoadSenseUplinkClient, UplinkConnectionError
from edge.uplink.signing import DeviceSigner

logger = logging.getLogger("edge.pipeline")


class Detector(Protocol):
    def detect(self, source: np.ndarray) -> list[Any]: ...


@dataclass
class StageTiming:
    samples: int = 0
    total_seconds: float = 0.0

    def add(self, elapsed: float) -> None:
        self.samples += 1
        self.total_seconds += elapsed

    @property
    def average_ms(self) -> float:
        return self.total_seconds / self.samples * 1000 if self.samples else 0.0


@dataclass
class PipelineMetrics:
    frames: int = 0
    candidates: int = 0
    skipped_without_plate: int = 0
    vehicle_detections: int = 0
    plate_detections: int = 0
    stage_timings: dict[str, StageTiming] = field(
        default_factory=lambda: {
            name: StageTiming()
            for name in (
                "capture",
                "vehicle_detection",
                "plate_detection",
                "tracking",
                "rules",
            )
        }
    )
    end_to_end_candidate_ms: list[float] = field(default_factory=list)
    memory_mb: list[float] = field(default_factory=list)
    cpu_percent: list[float] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "frames": self.frames,
            "candidates": self.candidates,
            "skipped_without_plate": self.skipped_without_plate,
            "vehicle_detections": self.vehicle_detections,
            "plate_detections": self.plate_detections,
            "plate_drop_rate": (
                max(0, self.vehicle_detections - self.plate_detections)
                / self.vehicle_detections
                if self.vehicle_detections
                else None
            ),
            "average_stage_ms": {
                name: timing.average_ms
                for name, timing in self.stage_timings.items()
            },
            "average_candidate_latency_ms": (
                sum(self.end_to_end_candidate_ms)
                / len(self.end_to_end_candidate_ms)
                if self.end_to_end_candidate_ms
                else None
            ),
            "peak_memory_mb": max(self.memory_mb, default=None),
            "average_cpu_percent": (
                sum(self.cpu_percent) / len(self.cpu_percent)
                if self.cpu_percent
                else None
            ),
        }


@dataclass(frozen=True)
class PipelineConfig:
    device_id: str = "edge-camera-node-01"
    location: tuple[float, float] = (18.5204, 73.8567)
    flush_interval_seconds: float = 5.0
    evidence_poll_interval_seconds: float = 10.0
    pending_candidate_timeout_seconds: float = 30.0
    realtime: bool = False
    target_fps: float | None = None
    max_frames: int | None = None
    duration_seconds: float | None = None


@dataclass
class _PendingCandidate:
    """Original violation evidence waiting for plate resolution."""

    track: Track
    decision: Any
    frame: np.ndarray
    location: tuple[float, float]
    captured_at: float
    violation_type: str
    resolver_attempted: bool = False


class EdgePipeline:
    """Continuous capture-to-uplink pipeline with bounded operational telemetry."""

    def __init__(
        self,
        source: FrameSource,
        vehicle_detector: Detector,
        plate_detector: Detector,
        *,
        tracker: IOUTracker | None = None,
        queue: ObservationQueue | None = None,
        client: RoadSenseUplinkClient | None = None,
        evidence_buffer: EvidenceBuffer | None = None,
        signer: DeviceSigner | None = None,
        config: PipelineConfig | None = None,
        traffic_light_smoother: TrafficLightStateSmoother | None = None,
        plate_text_resolver: Callable[[Track], str | None] | None = None,
    ) -> None:
        self.source = source
        self.vehicle_detector = vehicle_detector
        self.plate_detector = plate_detector
        self.tracker = tracker or IOUTracker()
        self.queue = queue or ObservationQueue()
        self.client = client or RoadSenseUplinkClient()
        self.evidence_buffer = evidence_buffer
        self.signer = signer
        self.config = config or PipelineConfig()
        self.traffic_light_smoother = (
            traffic_light_smoother or TrafficLightStateSmoother()
        )
        self.plate_text_resolver = plate_text_resolver
        self.metrics = PipelineMetrics()

        # A candidate is emitted only after its observation is successfully queued.
        self._emitted_tracks: set[tuple[int, str]] = set()
        self._pending_candidates: dict[
            tuple[int, str], _PendingCandidate
        ] = {}

        now = time.perf_counter()
        self._last_flush = now
        self._last_evidence_poll = now
        self._last_cpu_time = time.process_time()
        self._last_wall_time = time.perf_counter()

    def _sample_process_metrics(self) -> None:
        try:
            import psutil

            process = psutil.Process(os.getpid())
            now_wall = time.perf_counter()
            now_cpu = time.process_time()
            wall_delta = now_wall - self._last_wall_time
            cpu_delta = now_cpu - self._last_cpu_time

            self.metrics.memory_mb.append(
                process.memory_info().rss / (1024 * 1024)
            )
            if wall_delta > 0:
                self.metrics.cpu_percent.append(
                    100.0 * cpu_delta / wall_delta
                )

            self._last_wall_time = now_wall
            self._last_cpu_time = now_cpu
        except ImportError:
            logger.warning(
                "psutil is unavailable; memory telemetry will be omitted."
            )

    def _traffic_light_color(
        self, frame: np.ndarray, detections: list[Any]
    ) -> str:
        colors = []
        for detection in detections:
            if getattr(detection, "class_name", None) != "traffic light":
                continue

            x1, y1, x2, y2 = (
                max(0, int(value)) for value in detection.bbox
            )
            crop = frame[y1:y2, x1:x2]
            if crop.size:
                colors.append(classify_traffic_light_color(crop))

        if not colors:
            return self.traffic_light_smoother.state

        return self.traffic_light_smoother.update(
            max(colors, key=lambda item: item.confidence)
        )

    def _emit_candidate(
        self,
        track: Track,
        decision: Any,
        frame: np.ndarray,
        location: tuple[float, float],
        captured_at: float,
    ) -> None:
        violation_type = (
            "red_light"
            if decision.__class__.__name__.startswith("RedLight")
            else "wrong_side"
        )
        key = (track.track_id, violation_type)

        if (
            key in self._emitted_tracks
            or key in self._pending_candidates
        ):
            return

        # Preserve the original decision and frame. Do not rerun the rules
        # later, when the track or traffic-light state may have changed.
        self._pending_candidates[key] = _PendingCandidate(
            track=track,
            decision=decision,
            frame=frame.copy(),
            location=location,
            captured_at=captured_at,
            violation_type=violation_type,
        )

        self._resolve_pending_candidates()

    def _resolve_pending_candidates(
        self,
        finalized_track_ids: set[int] | None = None,
    ) -> None:
        finalized_ids = set(finalized_track_ids or ())
        now = time.perf_counter()

        # The tracker finalizes OCR as tracks expire. Lost tracks are not
        # necessarily returned in the active-track list for this frame.
        finalized_ids.update(
            track.track_id
            for track in self.tracker.lost_tracks
            if track.ocr_attempted
        )

        for key, pending in list(self._pending_candidates.items()):
            if key in self._emitted_tracks:
                self._pending_candidates.pop(key, None)
                continue

            track = pending.track
            is_finalized = (
                track.track_id in finalized_ids
                or track.ocr_attempted
            )
            if (
                not is_finalized
                and now - pending.captured_at
                >= self.config.pending_candidate_timeout_seconds
            ):
                track.finalize_ocr(
                    gating_threshold=self.tracker.gating_threshold
                )
                is_finalized = True
                logger.warning(
                    "Candidate track=%s type=%s reached OCR timeout; "
                    "finalizing with the current best plate crop.",
                    track.track_id,
                    pending.violation_type,
                )

            # Preserve the optional custom resolver, but call it at most
            # once per pending candidate.
            if (
                self.plate_text_resolver is not None
                and not pending.resolver_attempted
                and not track.plate_text
            ):
                pending.resolver_attempted = True
                resolved = self.plate_text_resolver(track)
                if resolved:
                    track.plate_text = resolved

            # Prefer the finalized track OCR result. The decision's plate
            # text is retained as a fallback for existing rule behavior.
            plate_text = track.plate_text or getattr(
                pending.decision, "plate_text", None
            )

            if not plate_text:
                if not is_finalized:
                    continue

                self.metrics.skipped_without_plate += 1
                self._pending_candidates.pop(key, None)
                logger.info(
                    "Candidate track=%s type=%s skipped: "
                    "OCR produced no readable plate after track completion.",
                    track.track_id,
                    pending.violation_type,
                )
                continue

            burst = assemble_burst_from_decision(
                pending.decision,
                track=track,
                device_id=self.config.device_id,
                lat=pending.location[0],
                lon=pending.location[1],
                signer=self.signer,
                override_plate=track.plate_text or plate_text,
            )

            if burst is None:
                if not is_finalized:
                    continue

                self.metrics.skipped_without_plate += 1
                self._pending_candidates.pop(key, None)
                logger.info(
                    "Candidate track=%s type=%s skipped: "
                    "observation could not be assembled.",
                    track.track_id,
                    pending.violation_type,
                )
                continue

            # Do not mark the candidate emitted until enqueue succeeds.
            # If enqueue raises, it remains pending for error handling/retry.
            self.queue.enqueue(burst)

            # Once queued, avoid a duplicate enqueue if evidence storage fails.
            self._emitted_tracks.add(key)
            self._pending_candidates.pop(key, None)

            self.metrics.candidates += 1
            self.metrics.end_to_end_candidate_ms.append(
                (time.perf_counter() - pending.captured_at) * 1000
            )

            logger.info(
                "Candidate emitted track=%s type=%s nonce=%s",
                track.track_id,
                pending.violation_type,
                burst["event_nonce"],
            )

            if self.evidence_buffer is not None:
                self.evidence_buffer.store_clip(
                    burst["event_nonce"],
                    pending.frame,
                    metadata={
                        "violation_type": pending.violation_type,
                        "track_id": track.track_id,
                    },
                )

    def process_frame(
        self,
        frame: np.ndarray,
        frame_idx: int,
        location: tuple[float, float],
    ) -> None:
        frame_start = time.perf_counter()

        stage_start = time.perf_counter()
        vehicle_predictions = self.vehicle_detector.detect(frame)
        self.metrics.stage_timings["vehicle_detection"].add(
            time.perf_counter() - stage_start
        )

        stage_start = time.perf_counter()
        plate_predictions = self.plate_detector.detect(frame)
        self.metrics.stage_timings["plate_detection"].add(
            time.perf_counter() - stage_start
        )

        vehicle_detections = [
            Detection(
                bbox=list(prediction.bbox),
                score=float(prediction.confidence),
                class_name=str(prediction.class_name),
            )
            for prediction in vehicle_predictions
            if getattr(prediction, "class_name", None)
            in {"car", "truck", "bus", "motorcycle"}
        ]
        plate_detections = [
            {
                "bbox": list(prediction.bbox),
                "score": float(prediction.confidence),
            }
            for prediction in plate_predictions
        ]

        self.metrics.vehicle_detections += len(vehicle_detections)
        self.metrics.plate_detections += len(plate_detections)

        stage_start = time.perf_counter()
        tracks = self.tracker.update(
            vehicle_detections,
            frame_idx=frame_idx,
            frame_image=frame,
            plate_detections=plate_detections,
        )
        self.metrics.stage_timings["tracking"].add(
            time.perf_counter() - stage_start
        )

        stage_start = time.perf_counter()
        signal_color = self._traffic_light_color(
            frame, vehicle_predictions
        )
        blocked = is_sightline_blocked(
            tracks,
            frame_width=frame.shape[1],
            frame_height=frame.shape[0],
        )

        for track in tracks:
            wrong_way = check_wrong_way_candidate(
                track,
                frame_width=frame.shape[1],
                frame_height=frame.shape[0],
            )
            if wrong_way.is_candidate:
                self._emit_candidate(
                    track, wrong_way, frame, location, frame_start
                )

            red_light = check_red_light_candidate(
                track,
                signal_color,
                frame_width=frame.shape[1],
                frame_height=frame.shape[0],
                sightline_blocked=blocked,
            )
            if red_light.is_candidate:
                self._emit_candidate(
                    track, red_light, frame, location, frame_start
                )

        # Resolve candidates whose tracks may have been finalized by update(),
        # even when those tracks are no longer in the active tracks list.
        self._resolve_pending_candidates()

        self.metrics.stage_timings["rules"].add(
            time.perf_counter() - stage_start
        )
        self.metrics.frames += 1
        self._sample_process_metrics()

    def _service_uplink(self, now: float) -> None:
        if now - self._last_flush >= self.config.flush_interval_seconds:
            try:
                result = self.queue.flush(self.client)
                logger.info("Observation queue flush: %s", result)
            except UplinkConnectionError as exc:
                logger.warning(
                    "Backend unavailable; queued observations remain durable: %s",
                    exc,
                )
            self._last_flush = now

        if (
            now - self._last_evidence_poll
            >= self.config.evidence_poll_interval_seconds
        ):
            try:
                for request in self.client.poll_evidence_requests(
                    self.config.device_id
                ):
                    nonce = request.get("event_nonce")
                    if nonce:
                        result = self.client.upload_evidence(nonce)
                        logger.info(
                            "Evidence upload nonce=%s result=%s",
                            nonce,
                            result,
                        )
            except UplinkConnectionError as exc:
                logger.warning(
                    "Backend unavailable; evidence polling will retry: %s",
                    exc,
                )
            self._last_evidence_poll = now

    def _finalize_pending_candidates(self) -> None:
        """Finalize pending tracks when capture stops, including at EOF."""
        pending_track_ids = {
            pending.track.track_id
            for pending in self._pending_candidates.values()
        }
        finalized_ids: set[int] = set()

        for track_id in pending_track_ids:
            track = self.tracker.active_tracks.get(track_id)

            if track is None:
                # A removed track should already have been finalized by
                # the tracker. Confirm its status from the lost-track list.
                lost_track = next(
                    (
                        item
                        for item in reversed(self.tracker.lost_tracks)
                        if item.track_id == track_id
                    ),
                    None,
                )
                if lost_track is not None and lost_track.ocr_attempted:
                    finalized_ids.add(track_id)
                continue

            track.finalize_ocr(
                gating_threshold=self.tracker.gating_threshold
            )
            if track.ocr_attempted:
                finalized_ids.add(track_id)

        self._resolve_pending_candidates(
            finalized_track_ids=finalized_ids
        )

    def run(self) -> PipelineMetrics:
        started = time.perf_counter()
        frame_idx = 0
        next_frame_at = started

        try:
            while True:
                now = time.perf_counter()

                if (
                    self.config.max_frames is not None
                    and frame_idx >= self.config.max_frames
                ):
                    break

                if (
                    self.config.duration_seconds is not None
                    and now - started >= self.config.duration_seconds
                ):
                    break

                if self.config.realtime and now < next_frame_at:
                    time.sleep(next_frame_at - now)

                capture_start = time.perf_counter()
                frame = self.source.get_frame()
                location = (
                    self.source.get_location() or self.config.location
                )
                self.metrics.stage_timings["capture"].add(
                    time.perf_counter() - capture_start
                )

                frame_idx += 1
                self.process_frame(frame, frame_idx, location)
                self._service_uplink(time.perf_counter())

                if self.config.realtime:
                    fps = (
                        self.config.target_fps
                        or getattr(self.source, "fps", 0.0)
                        or 1.0
                    )
                    next_frame_at = (
                        max(next_frame_at, time.perf_counter()) + 1.0 / fps
                    )

        finally:
            try:
                self._finalize_pending_candidates()
            finally:
                close = getattr(self.source, "close", None)
                if close is not None:
                    close()

                logger.info(
                    "Edge pipeline metrics: %s",
                    self.metrics.summary(),
                )

        return self.metrics
