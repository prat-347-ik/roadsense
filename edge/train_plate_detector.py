from __future__ import annotations

import sys
from pathlib import Path
from ultralytics import YOLO

import torch

ROOT = Path(__file__).resolve().parent.parent
DATA_YAML = ROOT / "edge" / "data" / "plate-labeled-v1" / "data.yaml"
PROJECT_DIR = ROOT / "edge" / "runs"

def train():
    torch.set_num_threads(8)
    print(f"Starting YOLOv8n fine-tuning on {DATA_YAML}...")
    model = YOLO("yolov8n.pt")
    results = model.train(
        data=str(DATA_YAML),
        epochs=50,
        imgsz=640,
        batch=16,
        patience=10,
        project=str(PROJECT_DIR),
        name="plate_v1",
        exist_ok=True,
        workers=0,
        verbose=True,
    )
    print("Training finished.")
    return results

if __name__ == "__main__":
    train()
