"""Command-line entrypoint for the continuous RoadSense edge pipeline."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from edge.capture import ImageSequenceFrameSource, WebcamFrameSource
from edge.detection.detector import YOLODetector
from edge.detection.plate_detector import YOLOPlateDetector
from edge.pipeline import EdgePipeline, PipelineConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the RoadSense edge pipeline.")
    parser.add_argument("--source", default="0", help="Camera index, video/.ts path, or image directory.")
    parser.add_argument("--location", nargs=2, type=float, metavar=("LAT", "LON"), default=(18.5204, 73.8567))
    parser.add_argument("--vehicle-model", default="yolov8n.pt")
    parser.add_argument("--plate-model", default=None)
    parser.add_argument("--plate-geometry", choices=["letterbox", "stretch640"], default="letterbox", help="Plate detection input geometry.")
    parser.add_argument("--plate-assign", choices=["first", "one_to_one"], default="first", help="Plate-to-track association strategy.")
    parser.add_argument("--ocr-engine", choices=["easyocr", "fpo"], default="easyocr", help="OCR engine to use.")
    parser.add_argument("--fpo-model", default="cct-xs-v2-global-model", help="Fast Plate OCR model.")
    parser.add_argument("--fpo-padding", type=float, default=0.0, help="Crop padding ratio for the FPO engine only.")
    parser.add_argument("--plate-min-conf", type=float, default=0.0, help="Minimum OCR confidence threshold.")
    parser.add_argument("--plate-min-width", type=float, default=75.0, help="Minimum raw plate width for OCR gating.")
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--duration-seconds", type=float, default=None)
    parser.add_argument("--realtime", action="store_true")
    parser.add_argument("--image-fps", type=float, default=1.0)
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    source_value = args.source
    source: object
    if Path(source_value).is_dir():
        source = ImageSequenceFrameSource(source_value, location=tuple(args.location), fps=args.image_fps)
    else:
        try:
            source_value = int(source_value)
        except ValueError:
            pass
        source = WebcamFrameSource(source_value, location=tuple(args.location))
    from edge.tracking.tracker import IOUTracker
    pipeline = EdgePipeline(
        source,  # type: ignore[arg-type]
        YOLODetector(args.vehicle_model),
        YOLOPlateDetector(args.plate_model, plate_geometry=args.plate_geometry),
        tracker=IOUTracker(
            plate_assign=args.plate_assign,
            gating_threshold=args.plate_min_width,
            ocr_engine=args.ocr_engine,
            fpo_model=args.fpo_model,
            fpo_padding=args.fpo_padding,
            plate_min_conf=args.plate_min_conf,
        ),
        config=PipelineConfig(
            location=tuple(args.location),
            max_frames=args.max_frames,
            duration_seconds=args.duration_seconds,
            realtime=args.realtime,
            plate_min_conf=args.plate_min_conf,
        ),
    )
    print(pipeline.run().summary())


if __name__ == "__main__":
    main()
