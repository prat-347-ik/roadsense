from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from edge.detection.detector import Detection, YOLODetector, draw_detections
from edge.detection.traffic_light_color import classify_traffic_light_color

DATASET_DIR = Path(r"C:\Users\Pratik\Project_Repos\datasets\extracted_frames")
OUTPUT_DIR = Path(__file__).resolve().parent / "evaluation_output"
CROP_OUTPUT_DIR = OUTPUT_DIR / "traffic_light_crops"
SAMPLE_SIZE = 25


def choose_spread_sample(directory: Path, sample_size: int) -> list[Path]:
    clips: dict[str, list[Path]] = {}
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        clip_name = path.name.split("_f_", 1)[0]
        clips.setdefault(clip_name, []).append(path)
    if not clips:
        raise FileNotFoundError(f"No image frames found in {directory}.")

    selected: list[Path] = []
    clip_items = list(clips.items())
    for index in range(min(sample_size, len(clip_items))):
        frames = clip_items[index][1]
        selected.append(frames[len(frames) // 2])
    return selected


def annotate_frame(frame, detections: list[Detection]):
    annotated = draw_detections(frame, detections)
    colors: list[str] = []
    height, width = frame.shape[:2]
    for detection in detections:
        if detection.class_name != "traffic light":
            continue
        x1, y1, x2, y2 = [int(value) for value in detection.bbox]
        x1, x2 = max(0, min(width, x1)), max(0, min(width, x2))
        y1, y2 = max(0, min(height, y1)), max(0, min(height, y2))
        if x2 <= x1 or y2 <= y1:
            continue
        color = classify_traffic_light_color(frame[y1:y2, x1:x2])
        colors.append(color)
        cv2.putText(
            annotated,
            f"light: {color}",
            (x1, min(height - 5, y2 + 18)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    return annotated, colors


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a YOLO model on the spread dashcam sample.")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLO weights path or model name.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory for annotated frames and traffic-light crops.",
    )
    args = parser.parse_args()

    detector = YOLODetector(model_path=args.model)
    sample = choose_spread_sample(DATASET_DIR, SAMPLE_SIZE)
    output_dir = args.output_dir
    crop_output_dir = output_dir / "traffic_light_crops"
    output_dir.mkdir(parents=True, exist_ok=True)
    vehicle_frames = 0
    vehicle_class_counts: Counter[str] = Counter()
    traffic_light_colors: Counter[str] = Counter()
    unknown_crops: list[tuple[str, Path]] = []

    for frame_path in sample:
        frame = cv2.imread(str(frame_path))
        if frame is None:
            raise ValueError(f"Could not read {frame_path}")
        detections = detector.detect(frame)
        annotated, colors = annotate_frame(frame, detections)
        traffic_light_colors.update(colors)
        vehicle_class_counts.update(
            detection.class_name
            for detection in detections
            if detection.class_name != "traffic light"
        )
        light_index = 0
        height, width = frame.shape[:2]
        for detection in detections:
            if detection.class_name != "traffic light":
                continue
            x1, y1, x2, y2 = [int(value) for value in detection.bbox]
            x1, x2 = max(0, min(width, x1)), max(0, min(width, x2))
            y1, y2 = max(0, min(height, y1)), max(0, min(height, y2))
            if x2 <= x1 or y2 <= y1:
                continue
            color = colors[light_index]
            light_index += 1
            crop_path = crop_output_dir / f"{frame_path.stem}_light_{light_index}_{color}.jpg"
            crop_output_dir.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(crop_path), frame[y1:y2, x1:x2]):
                raise OSError(f"Could not write {crop_path}")
            if color == "unknown":
                unknown_crops.append((frame_path.name, crop_path))
        if any(detection.class_name != "traffic light" for detection in detections):
            vehicle_frames += 1
        output_path = output_dir / f"{frame_path.stem}_annotated.jpg"
        if not cv2.imwrite(str(output_path), annotated):
            raise OSError(f"Could not write {output_path}")
        print(f"{frame_path.name}: {len(detections)} detections -> {output_path.name}")

    print(f"Frames evaluated: {len(sample)}")
    print(f"Frames with at least one vehicle detection: {vehicle_frames}/{len(sample)}")
    print(f"Vehicle detections by class: {dict(vehicle_class_counts)}")
    print(f"Traffic-light detections: {sum(traffic_light_colors.values())}")
    print(f"Traffic-light color results: {dict(traffic_light_colors)}")
    print(f"Model: {args.model}")
    print(f"Annotated outputs: {output_dir}")
    print(f"Traffic-light crops: {crop_output_dir}")
    print(f"Unknown traffic-light crops: {unknown_crops}")


if __name__ == "__main__":
    main()