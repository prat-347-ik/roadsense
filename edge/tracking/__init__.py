"""Tracking package for vehicle and license plate association across video frames."""

from edge.tracking.tracker import (
    Detection,
    EdgeTracker,
    IOUTracker,
    Track,
    Tracklet,
    compute_iou,
)

__all__ = [
    "Detection",
    "EdgeTracker",
    "IOUTracker",
    "Track",
    "Tracklet",
    "compute_iou",
]
