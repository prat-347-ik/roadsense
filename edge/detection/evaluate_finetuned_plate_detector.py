from __future__ import annotations

import json
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(r"c:\Users\Pratik\Project_Repos\roadsense")
EXTRACTED_FRAMES_DIR = Path(r"C:\Users\Pratik\Project_Repos\datasets\extracted_frames")
LABELED_DATASET_DIR = ROOT / "edge" / "data" / "plate-labeled-v1"
OUTPUT_DIR = ROOT / "edge" / "detection" / "evaluation_finetuned_plate_model"
CONTACT_SHEET_FILE = OUTPUT_DIR / "finetuned_evaluation_contact_sheet.jpg"
CROPS_DIR = OUTPUT_DIR / "plate_crops"

import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from edge.detection.plate_detector import YOLOPlateDetector, draw_plate_detections
from edge.detection.detector import YOLODetector

def get_labeled_frame_stems() -> set[str]:
    stems = set()
    for split in ["train", "valid", "test"]:
        img_dir = LABELED_DATASET_DIR / split / "images"
        if img_dir.exists():
            for p in img_dir.glob("*.jpg"):
                # Clean stem in case roboflow added suffix
                clean_name = p.stem.split("_f_")[0] + "_f_" + p.stem.split("_f_")[1][:4] if "_f_" in p.stem else p.stem
                stems.add(clean_name)
                stems.add(p.stem)
    return stems

def select_out_of_sample_frames(sample_size: int = 25) -> list[Path]:
    labeled_stems = get_labeled_frame_stems()
    
    # We want frames that were NOT in the training/validation sets, but contain vehicles
    all_frames = sorted(EXTRACTED_FRAMES_DIR.glob("*.jpg"))
    candidate_unseen = [p for p in all_frames if p.stem not in labeled_stems]
    
    # Let's pick a spread across various video clips
    clips: dict[str, list[Path]] = {}
    for p in candidate_unseen:
        clip = p.name.split("_f_")[0]
        clips.setdefault(clip, []).append(p)
        
    selected: list[Path] = []
    # Pick mid-frame from diverse clips
    for clip, frames in sorted(clips.items()):
        if len(selected) >= sample_size:
            break
        mid = frames[len(frames) // 2]
        selected.append(mid)
        
    # If still need more, pick from remaining
    if len(selected) < sample_size:
        for clip, frames in sorted(clips.items()):
            if len(selected) >= sample_size:
                break
            if len(frames) > 2:
                selected.append(frames[len(frames) // 4])
                
    return selected[:sample_size]

def create_contact_sheet(image_paths: list[Path], output_path: Path, cols: int = 5, thumb_w: int = 384, thumb_h: int = 216) -> None:
    if not image_paths:
        return
    rows = (len(image_paths) + cols - 1) // cols
    sheet = np.zeros((rows * thumb_h, cols * thumb_w, 3), dtype=np.uint8)
    for index, path in enumerate(image_paths):
        img = cv2.imread(str(path))
        if img is None:
            continue
        resized = cv2.resize(img, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
        r = index // cols
        c = index % cols
        sheet[r * thumb_h : (r + 1) * thumb_h, c * thumb_w : (c + 1) * thumb_w] = resized
    cv2.imwrite(str(output_path), sheet)
    print(f"Saved contact sheet to {output_path}")

def evaluate():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CROPS_DIR.mkdir(parents=True, exist_ok=True)

    weights_path = ROOT / "edge" / "runs" / "plate_v1" / "weights" / "best.pt"
    if not weights_path.exists():
        print(f"Weights file not found at {weights_path}")
        return

    plate_detector = YOLOPlateDetector(model_path=weights_path, confidence_threshold=0.25)
    vehicle_detector = YOLODetector(model_path="yolov8n.pt", confidence_threshold=0.25)

    sample_frames = select_out_of_sample_frames(sample_size=25)
    print(f"Selected {len(sample_frames)} fresh out-of-sample frames.")

    results = []
    annotated_paths = []

    for idx, frame_path in enumerate(sample_frames, 1):
        frame = cv2.imread(str(frame_path))
        h, w = frame.shape[:2]

        # Vehicle detections for reference
        veh_dets = vehicle_detector.detect(frame)
        relevant_vehicles = [d for d in veh_dets if d.class_name in {"car", "truck", "bus", "motorcycle"}]

        # Plate detections
        plate_dets = plate_detector.detect(frame)

        annotated = frame.copy()
        crops_saved = []

        for p_idx, p in enumerate(plate_dets):
            x1, y1, x2, y2 = [int(v) for v in p.bbox]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(
                annotated,
                f"plate: {p.confidence:.2f}",
                (x1, max(18, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

            if x2 > x1 and y2 > y1:
                crop = frame[y1:y2, x1:x2]
                crop_name = f"sample_{idx:02d}_{frame_path.stem}_plate_{p_idx+1}.jpg"
                cv2.imwrite(str(CROPS_DIR / crop_name), crop)
                crops_saved.append(crop_name)

        out_path = OUTPUT_DIR / f"sample_{idx:02d}_{frame_path.stem}_annotated.jpg"
        cv2.imwrite(str(out_path), annotated)
        annotated_paths.append(out_path)

        res_entry = {
            "index": idx,
            "frame_name": frame_path.name,
            "frame_path": str(frame_path),
            "vehicles_count": len(relevant_vehicles),
            "plates_detected_count": len(plate_dets),
            "detections": [
                {
                    "confidence": p.confidence,
                    "bbox": [round(float(v), 1) for v in p.bbox],
                    "width": round(p.bbox[2] - p.bbox[0], 1),
                    "height": round(p.bbox[3] - p.bbox[1], 1),
                }
                for p in plate_dets
            ],
            "annotated_file": str(out_path),
        }
        results.append(res_entry)
        print(f"[{idx:02d}/25] {frame_path.name}: {len(relevant_vehicles)} vehicles, {len(plate_dets)} plates detected")

    with open(OUTPUT_DIR / "results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    create_contact_sheet(annotated_paths, CONTACT_SHEET_FILE, cols=5)
    print("Evaluation finished.")

if __name__ == "__main__":
    evaluate()
