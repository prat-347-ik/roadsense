"""OCR module for license plate recognition in RoadSense."""

from .plate_reader import PlateReader, read_plate

__all__ = [
    "PlateReader",
    "read_plate",
]
