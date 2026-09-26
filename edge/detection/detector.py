from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, TypeAlias

import cv2
import numpy as np
from ultralytics import YOLO

WANTED_CLASSES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
    9: "traffic light",
}
BoundingBox: TypeAlias = tuple[float, float, float, float]


@dataclass(frozen=True)
class Detection:
    class_name: str
    confidence: float
    bbox: BoundingBox
    class_id: int


class YOLODetector:
    """Thin wrapper around a pretrained Ultralytics YOLO model."""

    def __init__(self, model_path: str = "yolov8n.pt", confidence_threshold: float = 0.25):
        self.model_path = model_path
        self.confidence_threshold = float(confidence_threshold)
        if self.confidence_threshold < 0.0 or self.confidence_threshold > 1.0:
            raise ValueError("confidence_threshold must be between 0.0 and 1.0.")

        self.model = YOLO(self.model_path)

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
        """Run YOLO inference and return filtered detections."""
        frame = self._coerce_frame(source)

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
            if class_id not in WANTED_CLASSES:
                continue

            confidence = float(box.conf[0])
            if confidence < self.confidence_threshold:
                continue

            bbox: BoundingBox = tuple(float(value) for value in box.xyxy[0])  # type: ignore[assignment]
            detections.append(
                Detection(
                    class_id=class_id,
                    class_name=WANTED_CLASSES[class_id],
                    confidence=confidence,
                    bbox=bbox,
                )
            )

        return detections


def draw_detections(
    frame: np.ndarray,
    detections: Iterable[Detection],
    output_path: str | os.PathLike[str] | None = None,
) -> np.ndarray:
    """Draw detection boxes onto an image and optionally save it."""
    image = frame.copy()
    for detection in detections:
        x1, y1, x2, y2 = [int(value) for value in detection.bbox]
        label = f"{detection.class_name} {detection.confidence:.2f}"

        color = {
            2: (0, 255, 0),
            3: (0, 165, 255),
            5: (255, 0, 0),
            7: (255, 255, 0),
            9: (255, 0, 255),
        }.get(detection.class_id, (255, 255, 255))

        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            image,
            label,
            (x1, max(15, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
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
