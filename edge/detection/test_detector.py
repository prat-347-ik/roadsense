from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from edge.detection.detector import Detection, YOLODetector, draw_detections

DATASET_DIR = Path(r"C:\Users\Pratik\Project_Repos\datasets\extracted_frames")
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def list_test_images(directory: Path, limit: int = 5) -> list[Path]:
    image_files = [
        path
        for path in sorted(directory.iterdir())
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]
    if not image_files:
        raise FileNotFoundError(
            f"No JPG/JPEG/PNG frames were found in {directory}."
        )
    return image_files[:limit]


def print_detections(frame_path: Path, detections: list[Detection]) -> None:
    print("=" * 40)
    print(f"Frame: {frame_path.name}")
    print("=" * 40)

    if not detections:
        print("No target objects detected.")
        print()
        return

    for detection in detections:
        label = detection.class_name
        confidence = detection.confidence
        x1, y1, x2, y2 = [int(value) for value in detection.bbox]

        print(label)
        print(f"confidence: {confidence:.2f}")
        print(f"bbox: ({x1}, {y1}, {x2}, {y2})")
        print()


def main() -> None:
    detector = YOLODetector(model_path="yolov8n.pt", confidence_threshold=0.25)
    sample_images = list_test_images(DATASET_DIR, limit=5)

    output_image_path: Path | None = None
    for image_path in sample_images:
        detections = detector.detect(str(image_path))
        print_detections(image_path, detections)

        if detections and output_image_path is None:
            output_image_path = OUTPUT_DIR / f"{image_path.stem}_detections.jpg"
            draw_detections(detector._coerce_frame(str(image_path)), detections, output_path=output_image_path)
            print(f"Visualization saved to: {output_image_path}")
            print()

    if output_image_path is None:
        print(f"No visualization generated because no target objects were found in the sample frames.")


if __name__ == "__main__":
    main()
