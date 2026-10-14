import numpy as np
import pytest

from edge.ocr.plate_reader import MIN_PLATE_WIDTH_GATING
from edge.tracking.tracker import Detection, IOUTracker, Track, compute_iou


def test_iou_computation():
    box1 = [0.0, 0.0, 100.0, 100.0]
    box2 = [50.0, 0.0, 150.0, 100.0]
    iou = compute_iou(box1, box2)
    assert pytest.approx(iou, 0.01) == 0.3333

    # Non-overlapping
    box3 = [200.0, 200.0, 300.0, 300.0]
    assert compute_iou(box1, box3) == 0.0

    # Exact overlap
    assert compute_iou(box1, box1) == 1.0


def test_smooth_vehicle_movement_keeps_single_track():
    """A vehicle moving smoothly across 10 frames should maintain the exact same track ID."""
    tracker = IOUTracker(iou_threshold=0.3, max_lost_frames=5, min_hits_to_confirm=2)

    track_ids_seen = []
    for frame_idx in range(1, 11):
        # Vehicle moves right by 5 pixels per frame
        x1 = 100.0 + frame_idx * 5
        y1 = 100.0
        x2 = 200.0 + frame_idx * 5
        y2 = 200.0

        det = Detection(bbox=[x1, y1, x2, y2], score=0.9, class_name="car")
        active = tracker.update([det], frame_idx=frame_idx)

        if active:
            track_ids_seen.append(active[0].track_id)

    # Frame 1 is hit 1 (not confirmed yet); frames 2 to 10 confirmed
    assert len(track_ids_seen) == 9
    assert all(tid == 1 for tid in track_ids_seen)
    assert tracker.active_tracks[1].age == 10


def test_two_vehicles_crossing_paths():
    """Two vehicles crossing paths should maintain their individual tracks."""
    tracker = IOUTracker(iou_threshold=0.2, max_lost_frames=5, min_hits_to_confirm=1)

    # Vehicle A moves Left -> Right (starts at x=50, moves +20/frame)
    # Vehicle B moves Right -> Left (starts at x=250, moves -20/frame)
    # Frame 1: A at [50, 100, 100, 150], B at [250, 100, 300, 150]
    # Frame 2: A at [70, 100, 120, 150], B at [230, 100, 280, 150]
    # Frame 3: A at [90, 100, 140, 150], B at [210, 100, 260, 150]
    # Frame 4: A at [110, 100, 160, 150], B at [190, 100, 240, 150]
    # Frame 5: A at [130, 100, 180, 150], B at [170, 100, 220, 150] (Cross near midpoint)
    # Frame 6: A at [150, 100, 200, 150], B at [150, 100, 200, 150]
    # Frame 7: A at [170, 100, 220, 150], B at [130, 100, 180, 150]

    for frame_idx in range(1, 8):
        xA1 = 50.0 + (frame_idx - 1) * 20
        xA2 = xA1 + 50.0

        xB1 = 250.0 - (frame_idx - 1) * 20
        xB2 = xB1 + 50.0

        detA = Detection(bbox=[xA1, 100.0, xA2, 150.0], score=0.9, class_name="car")
        detB = Detection(bbox=[xB1, 100.0, xB2, 150.0], score=0.9, class_name="truck")

        active = tracker.update([detA, detB], frame_idx=frame_idx)
        assert len(active) == 2

    # Verify both tracks exist and are tracked through frame 7
    active_ids = set(tracker.active_tracks.keys())
    assert len(active_ids) == 2


def test_disappearing_vehicle_and_new_vehicle():
    """A vehicle disappearing and a new one appearing elsewhere must get a different track ID."""
    tracker = IOUTracker(iou_threshold=0.3, max_lost_frames=2, min_hits_to_confirm=1)

    # Frame 1: Vehicle 1 at top-left
    det1 = Detection(bbox=[10.0, 10.0, 60.0, 60.0], score=0.9, class_name="car")
    active1 = tracker.update([det1], frame_idx=1)
    assert active1[0].track_id == 1

    # Frames 2, 3, 4: Vehicle 1 disappears (empty frames) -> pruned after frame 3
    tracker.update([], frame_idx=2)
    tracker.update([], frame_idx=3)
    tracker.update([], frame_idx=4)
    assert len(tracker.active_tracks) == 0
    assert len(tracker.lost_tracks) == 1
    assert tracker.lost_tracks[0].track_id == 1

    # Frame 5: New vehicle appears at bottom-right
    det2 = Detection(bbox=[400.0, 400.0, 450.0, 450.0], score=0.9, class_name="bus")
    active5 = tracker.update([det2], frame_idx=5)
    assert active5[0].track_id == 2
    assert active5[0].vehicle_class == "bus"


def test_best_frame_selection_shrinking_and_growing_widths():
    """Tracker must identify the frame with the largest plate width, not just the most recent."""
    tracker = IOUTracker(iou_threshold=0.3, max_lost_frames=3, min_hits_to_confirm=1)

    # Synthetic image for crops
    frame_img = np.zeros((300, 300, 3), dtype=np.uint8)

    # Plate width sequence: 40px (frame 1) -> 85px (frame 2) -> 60px (frame 3) -> 95px (frame 4) -> 70px (frame 5)
    plate_widths = [40.0, 85.0, 60.0, 95.0, 70.0]

    for frame_idx, pw in enumerate(plate_widths, start=1):
        v_box = [50.0, 50.0, 250.0, 250.0]
        p_box = [100.0, 150.0, 100.0 + pw, 180.0]

        det = Detection(
            bbox=v_box,
            score=0.9,
            class_name="car",
            plate_bbox=p_box,
            plate_score=0.95,
        )
        tracker.update([det], frame_idx=frame_idx, frame_image=frame_img)

    track = tracker.active_tracks[1]
    # Largest width seen is 95.0px at frame 4
    assert track.best_plate_width == 95.0
    assert track.best_plate_frame_idx == 4
    assert track.best_plate_crop is not None

    # Verify that OCR is NOT run on every frame update
    assert not track.ocr_attempted

    # Advance frames past max_lost_frames to simulate vehicle exiting
    tracker.update([], frame_idx=6)
    tracker.update([], frame_idx=7)
    tracker.update([], frame_idx=8)
    tracker.update([], frame_idx=9)

    # Track finalized and OCR executed on the 95px crop
    assert len(tracker.lost_tracks) == 1
    lost_track = tracker.lost_tracks[0]
    assert lost_track.ocr_attempted
    assert lost_track.best_plate_width == 95.0
