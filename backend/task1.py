from ultralytics import YOLO
from pathlib import Path

# -----------------------------
# 1. Load YOLO model
# -----------------------------
model = YOLO("yolov8n.pt")

# -----------------------------
# 2. Frames folder
# -----------------------------
FRAMES_DIR = Path(
    r"C:\Users\Pratik\Project_Repos\datasets\extracted_frames"
)

# -----------------------------
# 3. Classes we care about
# -----------------------------
WANTED_CLASSES = {2, 3, 5, 7, 9}

# -----------------------------
# 4. Find all image frames
# -----------------------------
image_extensions = {".jpg", ".jpeg", ".png", ".webp"}

frames = [
    path for path in FRAMES_DIR.iterdir()
    if path.suffix.lower() in image_extensions
]

print(f"Found {len(frames)} frames.")

# -----------------------------
# 5. Process every frame
# -----------------------------
for frame_path in frames:

    print(f"\nProcessing: {frame_path.name}")

    # Run YOLO
    results = model(
    str(frame_path),
    conf=0.5
    )
    detections = []

    # -----------------------------
    # 6. Process detections
    # -----------------------------
    for box in results[0].boxes:

        class_id = int(box.cls)

        # Ignore objects we don't care about
        if class_id not in WANTED_CLASSES:
            continue

        # Bounding box
        x1, y1, x2, y2 = map(int, box.xyxy[0])

        # Confidence
        confidence = float(box.conf)

        # Class name
        class_name = model.names[class_id]

        detection = {
            "class_id": class_id,
            "class_name": class_name,
            "confidence": confidence,
            "bbox": [x1, y1, x2, y2]
        }

        detections.append(detection)

    # -----------------------------
    # 7. Print detections
    # -----------------------------
    if detections:
        for detection in detections:
            print(detection)
    else:
        print("No wanted objects detected.")