"""Hardware-specific frame sources for the edge pipeline."""

from edge.capture.sources import (
    FrameSource,
    ImageSequenceFrameSource,
    WebcamFrameSource,
)

__all__ = ["FrameSource", "WebcamFrameSource", "ImageSequenceFrameSource"]
