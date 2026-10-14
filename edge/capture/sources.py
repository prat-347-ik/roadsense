from __future__ import annotations

from pathlib import Path
from typing import Protocol

import cv2
import numpy as np


class FrameSource(Protocol):
    """Minimal boundary between capture hardware and the edge pipeline."""

    def get_frame(self) -> np.ndarray:
        """Return the next BGR frame, or raise StopIteration at end of input."""

    def get_location(self) -> tuple[float, float] | None:
        """Return the current camera location when available."""


class WebcamFrameSource:
    """OpenCV source for a webcam, video file, or transport stream."""

    def __init__(
        self,
        source: int | str | Path = 0,
        location: tuple[float, float] | None = None,
        *,
        loop: bool = False,
    ) -> None:
        self.source = source
        self.location = location
        self.loop = loop
        self._capture = cv2.VideoCapture(str(source) if isinstance(source, Path) else source)
        if not self._capture.isOpened():
            raise OSError(f"Unable to open capture source: {source}")

    def get_frame(self) -> np.ndarray:
        success, frame = self._capture.read()
        if success and frame is not None:
            return frame

        if self.loop and isinstance(self.source, (str, Path)):
            self._capture.release()
            self._capture = cv2.VideoCapture(str(self.source))
            success, frame = self._capture.read()
            if success and frame is not None:
                return frame

        raise StopIteration("Capture source has no more frames.")

    def get_location(self) -> tuple[float, float] | None:
        return self.location

    @property
    def fps(self) -> float:
        value = float(self._capture.get(cv2.CAP_PROP_FPS))
        return value if value > 0 else 0.0

    def close(self) -> None:
        self._capture.release()

    def __enter__(self) -> WebcamFrameSource:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class ImageSequenceFrameSource:
    """Timed replay source for extracted JPEGs when no playable clip is available."""

    def __init__(
        self,
        directory: str | Path,
        location: tuple[float, float] | None = None,
        fps: float = 1.0,
        *,
        loop: bool = False,
    ) -> None:
        if fps <= 0:
            raise ValueError("fps must be greater than zero.")
        self.files = sorted(
            path
            for path in Path(directory).expanduser().glob("*")
            if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )
        if not self.files:
            raise FileNotFoundError(f"No image frames found in {directory}")
        self.location = location
        self.fps = float(fps)
        self.loop = loop
        self._index = 0

    def get_frame(self) -> np.ndarray:
        if self._index >= len(self.files):
            if not self.loop:
                raise StopIteration("Image sequence has no more frames.")
            self._index = 0

        path = self.files[self._index]
        self._index += 1
        frame = cv2.imread(str(path))
        if frame is None:
            raise ValueError(f"Unable to read image frame: {path}")
        return frame

    def get_location(self) -> tuple[float, float] | None:
        return self.location

    def close(self) -> None:
        return None
