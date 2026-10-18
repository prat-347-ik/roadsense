from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, TypeAlias

import cv2
import numpy as np
from ultralytics import YOLO

BoundingBox: TypeAlias = tuple[float, float, float, float]
DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[1] / "runs" / "plate_v1" / "weights" / "best.pt"


@dataclass(frozen=True)
class Detection:
    class_name: str
    confidence: float
    bbox: BoundingBox
    class_id: int


class YOLOPlateDetector:
    """Ultralytics YOLO wrapper for license plate detection."""

    def __init__(
        self,
        model_path: str | os.PathLike[str] | None = None,
        confidence_threshold: float = 0.25,
        plate_geometry: str = "letterbox",
    ):
        if model_path is None:
            model_path = DEFAULT_MODEL_PATH

        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"Plate model weights not found at: {self.model_path}")

        self.confidence_threshold = float(confidence_threshold)
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0.0 and 1.0.")

        if plate_geometry not in ("letterbox", "stretch640"):
            raise ValueError(
                f"Invalid plate_geometry '{plate_geometry}'; must be 'letterbox' or 'stretch640'."
            )
        self.plate_geometry = plate_geometry

        self.model = YOLO(str(self.model_path))

    def _coerce_frame(self, source: Any) -> np.ndarray:
        if isinstance(source, np.ndarray):
            if source.size == 0:
                raise ValueError("Empty frame provided.")
            if source.ndim not in (2, 3):
                raise ValueError(
                    "Invalid frame shape. Expected a 2D or 3D NumPy array with image data."
                )
            return source

        if isinstance(source, (str, os.PathLike)):
            image_path = Path(source).expanduser()
            if not image_path.exists():
                raise FileNotFoundError(f"Image path does not exist: {image_path}")
            if not image_path.is_file():
                raise ValueError(f"Image path is not a file: {image_path}")

            frame = cv2.imread(str(image_path))
            if frame is None:
                raise ValueError(f"Could not read image file: {image_path}")
            return frame

        raise TypeError(
            "Input must be a NumPy/OpenCV image array or a valid image file path."
        )

    def detect(self, source: Any) -> list[Detection]:
        """Run plate detection and return filtered bounding boxes."""
        frame = self._coerce_frame(source)
        h, w = frame.shape[:2]

        if self.plate_geometry == "stretch640":
            resized = cv2.resize(frame, (640, 640), interpolation=cv2.INTER_LINEAR)
            results = self.model(
                resized,
                imgsz=640,
                conf=self.confidence_threshold,
                iou=0.7,
                verbose=False,
            )
            if not results or len(results) == 0:
                return []

            result = results[0]
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                return []

            detections: list[Detection] = []
            for box in boxes:
                confidence = float(box.conf[0])
                if confidence < self.confidence_threshold:
                    continue

                bx = box.xyxy[0].cpu().numpy() if hasattr(box.xyxy[0], "cpu") else box.xyxy[0]
                x1 = float(bx[0]) * w / 640.0
                y1 = float(bx[1]) * h / 640.0
                x2 = float(bx[2]) * w / 640.0
                y2 = float(bx[3]) * h / 640.0
                bbox: BoundingBox = (x1, y1, x2, y2)
                detections.append(
                    Detection(
                        class_id=int(box.cls[0]),
                        class_name="plate",
                        confidence=confidence,
                        bbox=bbox,
                    )
                )

            return detections

        # Default: letterbox (Ultralytics default)
        results = self.model(frame, verbose=False)
        if not results or len(results) == 0:
            return []

        detections: list[Detection] = []
        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []

        for box in boxes:
            class_id = int(box.cls[0])
            confidence = float(box.conf[0])
            if confidence < self.confidence_threshold:
                continue

            bbox: BoundingBox = tuple(float(value) for value in box.xyxy[0])  # type: ignore[assignment]
            detections.append(
                Detection(
                    class_id=class_id,
                    class_name="plate",
                    confidence=confidence,
                    bbox=bbox,
                )
            )

        return detections


def draw_plate_detections(
    frame: np.ndarray,
    detections: Iterable[Detection],
    output_path: str | os.PathLike[str] | None = None,
) -> np.ndarray:
    """Draw plate detection bounding boxes onto a frame."""
    image = frame.copy()
    for detection in detections:
        x1, y1, x2, y2 = [int(value) for value in detection.bbox]
        label = f"{detection.class_name} {detection.confidence:.2f}"

        # Distinct bright yellow/green box for license plate detection
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 255), 2)
        cv2.putText(
            image,
            label,
            (x1, max(15, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )

    if output_path is not None:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        success = cv2.imwrite(str(output_file), image)
        if not success:
            raise OSError(f"Failed to save visualization to {output_file}")

    return image
