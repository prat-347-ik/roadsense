"""Pretrained YOLO-based detection utilities for RoadSense."""

from .detector import WANTED_CLASSES, Detection, YOLODetector
from .plate_detector import YOLOPlateDetector, draw_plate_detections
from .traffic_light_color import TrafficLightResult, classify_traffic_light_color

__all__ = [
    "WANTED_CLASSES",
    "Detection",
    "TrafficLightResult",
    "YOLODetector",
    "YOLOPlateDetector",
    "classify_traffic_light_color",
    "draw_plate_detections",
]
