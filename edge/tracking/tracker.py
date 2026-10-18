from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Any
import numpy as np

from edge.ocr.plate_reader import MIN_PLATE_WIDTH_GATING, read_plate


def compute_iou(box1: list[float] | np.ndarray, box2: list[float] | np.ndarray) -> float:
    """Compute Intersection over Union (IoU) between two bounding boxes [x1, y1, x2, y2]."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter_area = inter_w * inter_h

    area1 = max(0.0, (box1[2] - box1[0]) * (box1[3] - box1[1]))
    area2 = max(0.0, (box2[2] - box2[0]) * (box2[3] - box2[1]))
    union_area = area1 + area2 - inter_area

    if union_area <= 0.0:
        return 0.0

    return float(inter_area / union_area)


@dataclass
class Detection:
    """Represents a single frame object detection."""

    bbox: list[float]
    score: float = 1.0
    class_name: str = "vehicle"
    plate_bbox: list[float] | None = None
    plate_score: float = 0.0
    plate_crop: np.ndarray | None = None


@dataclass
class Track:
    """Represents an active or finalized vehicle tracklet."""

    track_id: int
    current_bbox: list[float]
    vehicle_class: str
    first_frame_idx: int
    last_frame_idx: int
    age: int = 1  # Total hit count / frames tracked
    frames_since_matched: int = 0  # Missing frame counter

    # History of bounding boxes: list of (frame_idx, bbox)
    bbox_history: list[tuple[int, list[float]]] = field(default_factory=list)

    # Best plate opportunity recorded over trajectory
    best_plate_crop: np.ndarray | None = None
    best_plate_bbox: list[float] | None = None
    best_plate_width: float = 0.0
    best_plate_score: float = 0.0
    best_plate_frame_idx: int = -1

    # OCR outcome (executed on track completion / loss)
    plate_text: str | None = None
    plate_confidence: float = 0.0
    ocr_attempted: bool = False
    ocr_engine: str = "easyocr"
    fpo_model: str = "cct-xs-v2-global-model"
    plate_min_conf: float = 0.0
    funnel_outcome: str | None = None

    def __post_init__(self) -> None:
        if not self.bbox_history and self.current_bbox:
            self.bbox_history.append((self.first_frame_idx, list(self.current_bbox)))

    @property
    def is_confirmed(self) -> bool:
        return self.age >= 2

    def record_plate_observation(
        self,
        plate_bbox: list[float] | None,
        plate_crop: np.ndarray | None,
        plate_score: float,
        frame_idx: int,
    ) -> bool:
        """Update best plate pointer if new raw plate box width is larger.

        Does NOT trigger OCR immediately — stores reference for track finalization.
        """
        if plate_bbox is None:
            return False

        pw = float(plate_bbox[2] - plate_bbox[0])
        if pw > self.best_plate_width:
            self.best_plate_width = pw
            self.best_plate_bbox = plate_bbox
            self.best_plate_score = plate_score
            self.best_plate_crop = plate_crop
            self.best_plate_frame_idx = frame_idx
            return True
        return False

    def update(
        self,
        bbox: list[float],
        score: float,
        frame_idx: int,
        plate_bbox: list[float] | None = None,
        plate_crop: np.ndarray | None = None,
        plate_score: float = 0.0,
    ) -> None:
        """Update track with matching detection."""
        self.current_bbox = bbox
        self.last_frame_idx = frame_idx
        self.age += 1
        self.frames_since_matched = 0
        self.bbox_history.append((frame_idx, list(bbox)))

        self.record_plate_observation(
            plate_bbox=plate_bbox,
            plate_crop=plate_crop,
            plate_score=plate_score,
            frame_idx=frame_idx,
        )

    @staticmethod
    def bottom_center_from_bbox(bbox: list[float] | np.ndarray) -> tuple[float, float]:
        """Return the bottom-center point for a vehicle box [x1, y1, x2, y2]."""
        x1, _, x2, y2 = bbox
        return float((x1 + x2) / 2.0), float(y2)

    def get_bottom_center(self, frame_idx: int | None = None) -> tuple[float, float] | None:
        """Return the most recent or selected-frame bottom-center endpoint."""
        if not self.bbox_history:
            return None
        target = self.bbox_history[-1] if frame_idx is None else next(
            (frame, bbox) for frame, bbox in self.bbox_history if frame == frame_idx
        )
        return self.bottom_center_from_bbox(target[1])

    def get_recent_bottom_centers(self, last_n_frames: int = 5) -> list[tuple[float, float]]:
        """Return bottom-center positions over the recent trajectory window."""
        if len(self.bbox_history) < 2:
            return []
        window = self.bbox_history[-last_n_frames:] if last_n_frames > 1 else self.bbox_history
        return [self.bottom_center_from_bbox(bbox) for _, bbox in window]

    def get_motion_vector(self, last_n_frames: int = 5) -> tuple[float, float] | None:
        """Calculate the total motion vector (dx, dy) of the vehicle bottom-center over the last N frames.

        dx = x_latest - x_earliest
        dy = y_latest - y_earliest

        Coordinate conventions:
        - dy < 0: Upward motion in image (moving away / receding into scene).
        - dy > 0: Downward motion in image (closing toward camera).
        - dx < 0: Leftward motion in image.
        - dx > 0: Rightward motion in image.

        Returns None if fewer than 2 positions are available.
        """
        if len(self.bbox_history) < 2:
            return None

        window = self.bbox_history[-last_n_frames:] if last_n_frames > 1 else self.bbox_history
        if len(window) < 2:
            return None

        start = self.bottom_center_from_bbox(window[0][1])
        end = self.bottom_center_from_bbox(window[-1][1])
        return float(end[0] - start[0]), float(end[1] - start[1])

    def get_step_displacements(self, last_n_frames: int = 5) -> list[tuple[float, float]]:
        """Get consecutive frame-to-frame displacement vectors [(dx, dy), ...] over the window."""
        if len(self.bbox_history) < 2:
            return []
        window = self.bbox_history[-last_n_frames:] if last_n_frames > 1 else self.bbox_history
        displacements = []
        for i in range(1, len(window)):
            _, b_prev = window[i - 1]
            _, b_curr = window[i]
            prev_x, prev_y = self.bottom_center_from_bbox(b_prev)
            curr_x, curr_y = self.bottom_center_from_bbox(b_curr)
            displacements.append((float(curr_x - prev_x), float(curr_y - prev_y)))
        return displacements

    def finalize_ocr(
        self,
        gating_threshold: float = MIN_PLATE_WIDTH_GATING,
        ocr_engine: str | None = None,
        fpo_model: str | None = None,
        plate_min_conf: float | None = None,
    ) -> str | None:
        """Execute OCR once on the best recorded plate frame if above gating threshold."""
        if self.ocr_attempted:
            return self.plate_text

        self.ocr_attempted = True
        engine = ocr_engine or self.ocr_engine
        model = fpo_model or self.fpo_model
        min_conf = self.plate_min_conf if plate_min_conf is None else plate_min_conf

        if self.best_plate_crop is not None and self.best_plate_width >= gating_threshold:
            if engine == "fpo":
                from edge.ocr.fpo_reader import read_plate as fpo_read_plate

                res = fpo_read_plate(self.best_plate_crop, model_name=model, return_confidence=True)
                if isinstance(res, tuple):
                    self.plate_text, self.plate_confidence = res
                else:
                    self.plate_text = res
            else:
                self.plate_text = read_plate(self.best_plate_crop)

            if self.plate_text is not None:
                if min_conf > 0.0 and self.plate_confidence < min_conf:
                    self.funnel_outcome = "OCR_LOW_CONFIDENCE"
                else:
                    self.funnel_outcome = "OK"

        return self.plate_text


# Backward compatibility alias
Tracklet = Track


class IOUTracker:
    """Simple, ultra-fast IOU tracker for edge video processing.

    Greedily associates detection bounding boxes across frames using IOU,
    maintains track lifecycles, and manages the best-frame plate OCR trigger.
    """

    def __init__(
        self,
        iou_threshold: float = 0.3,
        max_lost_frames: int = 10,
        min_hits_to_confirm: int = 2,
        gating_threshold: float = MIN_PLATE_WIDTH_GATING,
        plate_assign: str = "first",
        ocr_engine: str = "easyocr",
        fpo_model: str = "cct-xs-v2-global-model",
        plate_padding_ratio: float | None = None,
        fpo_padding: float | None = None,
        plate_min_conf: float = 0.0,
    ):
        if plate_assign not in ("first", "one_to_one"):
            raise ValueError(
                f"Invalid plate_assign '{plate_assign}'; must be 'first' or 'one_to_one'."
            )
        self.plate_assign = plate_assign
        self.iou_threshold = iou_threshold
        self.max_lost_frames = max_lost_frames
        self.min_hits_to_confirm = min_hits_to_confirm
        self.gating_threshold = gating_threshold
        self.ocr_engine = ocr_engine
        self.fpo_model = fpo_model
        self.plate_min_conf = plate_min_conf

        if fpo_padding is not None and ocr_engine == "fpo":
            self.plate_padding_ratio = fpo_padding
        elif plate_padding_ratio is not None:
            self.plate_padding_ratio = plate_padding_ratio
        else:
            self.plate_padding_ratio = 0.0 if ocr_engine == "fpo" else 0.15

        self.next_track_id: int = 1
        self.active_tracks: dict[int, Track] = {}
        self.lost_tracks: list[Track] = []
        self.current_frame_idx: int = 0

    def _extract_crop(
        self,
        plate_bbox: list[float],
        frame_image: np.ndarray | None,
        padding_ratio: float | None = None,
    ) -> np.ndarray | None:
        if padding_ratio is None:
            padding_ratio = self.plate_padding_ratio
        """Extract padded crop from full-resolution frame image."""
        if frame_image is None or plate_bbox is None:
            return None

        h_img, w_img = frame_image.shape[:2]
        bw = plate_bbox[2] - plate_bbox[0]
        bh = plate_bbox[3] - plate_bbox[1]
        pad_x = int(bw * padding_ratio)
        pad_y = int(bh * padding_ratio)

        x1 = max(0, int(plate_bbox[0] - pad_x))
        y1 = max(0, int(plate_bbox[1] - pad_y))
        x2 = min(w_img, int(plate_bbox[2] + pad_x))
        y2 = min(h_img, int(plate_bbox[3] + pad_y))

        if x2 > x1 and y2 > y1:
            return frame_image[y1:y2, x1:x2]
        return None

    def _associate_plate(
        self,
        vehicle_bbox: list[float],
        plate_detections: list[dict[str, Any]] | None,
        frame_image: np.ndarray | None,
        consumed_indices: set[int] | None = None,
    ) -> tuple[list[float] | None, np.ndarray | None, float]:
        """Associate matching plate box inside vehicle detection."""
        if not plate_detections:
            return None, None, 0.0

        if self.plate_assign == "one_to_one":
            best_idx = -1
            best_score = -1.0
            best_pb = None
            best_area = float("inf")

            for idx, p_det in enumerate(plate_detections):
                if consumed_indices is not None and idx in consumed_indices:
                    continue
                pb = p_det.get("bbox", p_det.get("box"))
                if pb is None:
                    continue
                pcx = (pb[0] + pb[2]) / 2.0
                pcy = (pb[1] + pb[3]) / 2.0
                if vehicle_bbox[0] <= pcx <= vehicle_bbox[2] and vehicle_bbox[1] <= pcy <= vehicle_bbox[3]:
                    score = float(p_det.get("score", p_det.get("conf", 1.0)))
                    area = (pb[2] - pb[0]) * (pb[3] - pb[1])
                    if score > best_score or (score == best_score and area < best_area):
                        best_score = score
                        best_area = area
                        best_pb = pb
                        best_idx = idx

            if best_idx != -1 and best_pb is not None:
                if consumed_indices is not None:
                    consumed_indices.add(best_idx)
                crop = self._extract_crop(best_pb, frame_image)
                return best_pb, crop, best_score

            return None, None, 0.0

        for p_det in plate_detections:
            pb = p_det.get("bbox", p_det.get("box"))
            if pb is None:
                continue
            pcx = (pb[0] + pb[2]) / 2.0
            pcy = (pb[1] + pb[3]) / 2.0
            if vehicle_bbox[0] <= pcx <= vehicle_bbox[2] and vehicle_bbox[1] <= pcy <= vehicle_bbox[3]:
                crop = self._extract_crop(pb, frame_image)
                score = float(p_det.get("score", p_det.get("conf", 1.0)))
                return pb, crop, score

        return None, None, 0.0

    def update(
        self,
        detections: list[Detection] | list[dict[str, Any]],
        frame_idx: int | None = None,
        frame_image: np.ndarray | None = None,
        plate_detections: list[dict[str, Any]] | None = None,
    ) -> list[Track]:
        """Update tracker with detections from the current frame.

        Args:
            detections: List of Detection objects or dictionaries with 'bbox'/'box'.
            frame_idx: Optional frame counter.
            frame_image: Optional image array for extracting plate crops.
            plate_detections: Optional separate plate detections to associate.

        Returns:
            List of confirmed active Tracks.
        """
        if frame_idx is not None:
            self.current_frame_idx = frame_idx
        else:
            self.current_frame_idx += 1

        # Normalize detections to Detection instances
        norm_dets: list[Detection] = []

        if self.plate_assign == "one_to_one" and plate_detections:
            # Greedy one-to-one association across all vehicle detections in the frame
            candidates = []
            for v_idx, d in enumerate(detections):
                v_box = d.bbox if isinstance(d, Detection) else d.get("bbox", d.get("box"))
                if v_box is None:
                    continue
                v_area = (v_box[2] - v_box[0]) * (v_box[3] - v_box[1])
                for p_idx, p_det in enumerate(plate_detections):
                    pb = p_det.get("bbox", p_det.get("box"))
                    if pb is None:
                        continue
                    pcx = (pb[0] + pb[2]) / 2.0
                    pcy = (pb[1] + pb[3]) / 2.0
                    if v_box[0] <= pcx <= v_box[2] and v_box[1] <= pcy <= v_box[3]:
                        p_score = float(p_det.get("score", p_det.get("conf", 1.0)))
                        p_area = (pb[2] - pb[0]) * (pb[3] - pb[1])
                        candidates.append((p_score, v_area, p_area, v_idx, p_idx))

            # Sort by plate confidence descending, then smaller vehicle box area
            candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
            assigned_v_to_p: dict[int, int] = {}
            consumed_p: set[int] = set()
            for p_score, v_area, p_area, v_idx, p_idx in candidates:
                if v_idx not in assigned_v_to_p and p_idx not in consumed_p:
                    assigned_v_to_p[v_idx] = p_idx
                    consumed_p.add(p_idx)

            for v_idx, d in enumerate(detections):
                if v_idx in assigned_v_to_p:
                    p_det = plate_detections[assigned_v_to_p[v_idx]]
                    pb = p_det.get("bbox", p_det.get("box"))
                    p_crop = self._extract_crop(pb, frame_image)
                    p_score = float(p_det.get("score", p_det.get("conf", 1.0)))
                else:
                    pb = None
                    p_crop = None
                    p_score = 0.0

                if isinstance(d, Detection):
                    norm_dets.append(
                        Detection(
                            bbox=d.bbox,
                            score=d.score,
                            class_name=d.class_name,
                            plate_bbox=pb,
                            plate_score=p_score,
                            plate_crop=p_crop,
                        )
                    )
                else:
                    bbox = d.get("bbox", d.get("box"))
                    score = float(d.get("score", d.get("conf", 1.0)))
                    c_name = d.get("class_name", d.get("label", "vehicle"))
                    norm_dets.append(
                        Detection(
                            bbox=bbox,
                            score=score,
                            class_name=c_name,
                            plate_bbox=pb,
                            plate_score=p_score,
                            plate_crop=p_crop,
                        )
                    )
        else:
            # Default "first" association
            for d in detections:
                if isinstance(d, Detection):
                    if d.plate_bbox is None and plate_detections:
                        p_bbox, p_crop, p_score = self._associate_plate(
                            d.bbox, plate_detections, frame_image
                        )
                        d = Detection(
                            bbox=d.bbox,
                            score=d.score,
                            class_name=d.class_name,
                            plate_bbox=p_bbox,
                            plate_score=p_score,
                            plate_crop=p_crop,
                        )
                    elif d.plate_bbox is not None and d.plate_crop is None and frame_image is not None:
                        d.plate_crop = self._extract_crop(d.plate_bbox, frame_image)
                    norm_dets.append(d)
                else:
                    bbox = d.get("bbox", d.get("box"))
                    score = float(d.get("score", d.get("conf", 1.0)))
                    c_name = d.get("class_name", d.get("label", "vehicle"))
                    p_bbox, p_crop, p_score = self._associate_plate(bbox, plate_detections, frame_image)
                    norm_dets.append(
                        Detection(
                            bbox=bbox,
                            score=score,
                            class_name=c_name,
                            plate_bbox=p_bbox,
                            plate_score=p_score,
                            plate_crop=p_crop,
                        )
                    )

        active_track_ids = list(self.active_tracks.keys())
        active_boxes = [self.active_tracks[tid].current_bbox for tid in active_track_ids]
        det_boxes = [d.bbox for d in norm_dets]

        # Match detections to existing tracks greedily by highest IOU
        matched_tracks: set[int] = set()
        matched_dets: set[int] = set()

        if active_boxes and det_boxes:
            iou_matrix = np.zeros((len(active_boxes), len(det_boxes)), dtype=np.float32)
            for r, ab in enumerate(active_boxes):
                for c, db in enumerate(det_boxes):
                    iou_matrix[r, c] = compute_iou(ab, db)

            # Sort pair indices by IOU descending
            flat_order = np.argsort(-iou_matrix, axis=None)
            for idx in flat_order:
                r = int(idx // len(det_boxes))
                c = int(idx % len(det_boxes))
                if iou_matrix[r, c] < self.iou_threshold:
                    break
                if r not in matched_tracks and c not in matched_dets:
                    matched_tracks.add(r)
                    matched_dets.add(c)
                    tid = active_track_ids[r]
                    det = norm_dets[c]
                    self.active_tracks[tid].update(
                        bbox=det.bbox,
                        score=det.score,
                        frame_idx=self.current_frame_idx,
                        plate_bbox=det.plate_bbox,
                        plate_crop=det.plate_crop,
                        plate_score=det.plate_score,
                    )

        # Unmatched detections -> create new tracks
        for c, det in enumerate(norm_dets):
            if c not in matched_dets:
                new_track = Track(
                    track_id=self.next_track_id,
                    current_bbox=det.bbox,
                    vehicle_class=det.class_name,
                    first_frame_idx=self.current_frame_idx,
                    last_frame_idx=self.current_frame_idx,
                    ocr_engine=self.ocr_engine,
                    fpo_model=self.fpo_model,
                    plate_min_conf=self.plate_min_conf,
                )
                new_track.record_plate_observation(
                    plate_bbox=det.plate_bbox,
                    plate_crop=det.plate_crop,
                    plate_score=det.plate_score,
                    frame_idx=self.current_frame_idx,
                )
                self.active_tracks[self.next_track_id] = new_track
                self.next_track_id += 1

        # Unmatched active tracks -> increment lost counter & prune if exceeded max_lost_frames
        to_delete = []
        for r, tid in enumerate(active_track_ids):
            if r not in matched_tracks:
                track = self.active_tracks[tid]
                track.frames_since_matched += 1
                if track.frames_since_matched > self.max_lost_frames:
                    # Finalize OCR on the best recorded frame before discarding
                    track.finalize_ocr(
                        gating_threshold=self.gating_threshold,
                        ocr_engine=self.ocr_engine,
                        fpo_model=self.fpo_model,
                        plate_min_conf=self.plate_min_conf,
                    )
                    self.lost_tracks.append(track)
                    to_delete.append(tid)

        for tid in to_delete:
            del self.active_tracks[tid]

        # Return confirmed active tracks
        return [t for t in self.active_tracks.values() if t.age >= self.min_hits_to_confirm]


# Backward compatibility aliases
EdgeTracker = IOUTracker
