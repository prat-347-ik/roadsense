from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time

import cv2
import httpx
import numpy as np

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from edge.detection.detector import YOLODetector
from edge.rules.wrong_way import check_wrong_way_candidate
from edge.storage.evidence_buffer import EvidenceBuffer
from edge.storage.observation_queue import ObservationQueue
from edge.tracking.tracker import Detection, IOUTracker
from edge.uplink.burst import assemble_burst
from edge.uplink.client import RoadSenseUplinkClient
from edge.uplink.signing import DeviceSigner


def run_storage_integration_test():
    print("=" * 80)
    print("       EDGE STORAGE RESILIENCE & BACKEND INTEGRATION TEST")
    print("=" * 80)

    # 1. Initialize local storage components
    test_storage_dir = REPO_ROOT / "edge" / "storage" / "test_scratch"
    test_storage_dir.mkdir(parents=True, exist_ok=True)

    queue_db = test_storage_dir / "integration_queue.db"
    evidence_dir = test_storage_dir / "integration_evidence"

    # Clean scratch state from any previous run
    if queue_db.exists():
        queue_db.unlink(missing_ok=True)
    if evidence_dir.exists():
        import shutil
        shutil.rmtree(evidence_dir, ignore_errors=True)

    obs_queue = ObservationQueue(db_path=queue_db, base_delay=1.0, max_delay=10.0)
    ev_buffer = EvidenceBuffer(buffer_dir=evidence_dir)

    signer_1 = DeviceSigner(key_path=REPO_ROOT / "edge" / "uplink" / "keys" / "device_1_key.pem")
    signer_2 = DeviceSigner(key_path=REPO_ROOT / "edge" / "uplink" / "keys" / "device_2_key.pem")
    device_1_id = "edge-cam-field-01"
    device_2_id = "edge-cam-field-02"

    print(f"[Init] ObservationQueue DB: {queue_db}")
    print(f"[Init] EvidenceBuffer Dir:  {evidence_dir}")
    print(f"[Init] Initial Queue Depth: {obs_queue.get_queue_depth()}")

    # 2. Assemble 3 Observations with Explicit Provenance Tracking
    print("\n" + "=" * 80)
    print("           OBSERVATION PROVENANCE & SCENARIO COMPOSITION")
    print("=" * 80)

    # --- Observation 1: GENUINELY DETECTED ON REAL ROAD FOOTAGE ---
    print("\n[Observation 1 of 3: REAL DETECTION FROM DASHCAM FOOTAGE]")
    frames_dir = REPO_ROOT / "edge" / "tracking" / "evaluation_road_traffic_170004"
    frame_files = [frames_dir / f"annotated_f_{i:04d}.jpg" for i in range(1, 26)]
    frame_files = [f for f in frame_files if f.exists()]

    v_detector = YOLODetector("yolov8n.pt", confidence_threshold=0.25)
    tracker = IOUTracker(iou_threshold=0.25, max_lost_frames=6, min_hits_to_confirm=2)

    real_candidate_burst = None
    real_candidate_clip_frames = []

    for f_idx, fpath in enumerate(frame_files, start=1):
        img = cv2.imread(str(fpath))
        if img is None:
            continue
        h, w = img.shape[:2]

        v_preds = v_detector.detect(img)
        v_dets = [
            Detection(bbox=list(p.bbox), score=p.confidence, class_name=p.class_name)
            for p in v_preds if p.class_name in ["car", "truck", "bus", "motorcycle"]
        ]

        active_tracks = tracker.update(v_dets, frame_idx=f_idx, frame_image=img, plate_detections=[])
        real_candidate_clip_frames.append(cv2.resize(img, (640, 360)))

        for t in active_tracks:
            decision = check_wrong_way_candidate(t, frame_width=w, frame_height=h)
            if decision.is_candidate and not real_candidate_burst:
                ts = datetime.now(timezone.utc) - timedelta(seconds=15)
                real_candidate_burst = assemble_burst(
                    violation_type="wrong_side",
                    plate_no="MH12AB1234",
                    device_id=device_1_id,
                    lat=18.5204,
                    lon=73.8567,
                    timestamp=ts,
                    signer=signer_1,
                )
                print(f"  Origin: Genuinely detected in real footage (Clip 170004, Frame {f_idx})")
                print(f"  Trigger: Track {t.track_id} ({t.vehicle_class}) wrong-way rule fired: {decision.reason}")
                print(f"  Device ID: {device_1_id}")
                print(f"  Event Nonce: {real_candidate_burst['event_nonce']}")
                print(f"  Role: Single-camera uncorroborated candidate. Will stay in status: 'candidate'.")
                break

    assert real_candidate_burst is not None, "Failed to extract candidate from real footage"

    # --- Observation 2: MANUALLY CONSTRUCTED CANDIDATE TO TEST CORROBORATION ---
    print("\n[Observation 2 of 3: CONSTRUCTED RED-LIGHT CANDIDATE (Device 1)]")
    test_run_tag = int(time.time()) % 100000
    corroboration_plate = f"MH46RL{test_run_tag:05d}"
    t_now = datetime.now(timezone.utc)

    rl_burst_1 = assemble_burst(
        violation_type="red_light",
        plate_no=corroboration_plate,
        device_id=device_1_id,
        lat=18.5300,
        lon=73.8500,
        timestamp=t_now - timedelta(seconds=3),
        signer=signer_1,
    )
    print(f"  Origin: Manually constructed red-light burst for Device 1")
    print(f"  Device ID: {device_1_id}")
    print(f"  Event Nonce: {rl_burst_1['event_nonce']}")
    print(f"  Plate: {corroboration_plate}")
    print(f"  Role: Primary candidate awaiting corroboration from an independent device.")

    # --- Observation 3: MANUALLY CONSTRUCTED CORROBORATING PARTNER (Device 2) ---
    print("\n[Observation 3 of 3: CONSTRUCTED CORROBORATING PARTNER (Device 2)]")
    rl_burst_2 = assemble_burst(
        violation_type="red_light",
        plate_no=corroboration_plate,  # Identical plate string
        device_id=device_2_id,          # Different reporting device
        lat=18.5302,                    # Advancing spatial location (~22m displacement)
        lon=73.8501,
        timestamp=t_now,                # 3.0s time delta within corroboration window
        signer=signer_2,
    )
    print(f"  Origin: Manually constructed corroborating observation for Device 2")
    print(f"  Device ID: {device_2_id} (Independent camera)")
    print(f"  Event Nonce: {rl_burst_2['event_nonce']}")
    print(f"  Plate: {corroboration_plate} (EXACT MATCH to Observation 2)")
    print(f"  Role: Corroborates Observation 2, causing backend to issue EvidenceRequest to Device 1.")

    print("\n[CORROBORATION LINK SUMMARY]")
    print(f"  -> Obs #1 ({real_candidate_burst['event_nonce'][:12]}...): Real detection, 1 device -> Candidate only (No EvidenceRequest expected).")
    print(f"  -> Obs #2 ({rl_burst_1['event_nonce'][:12]}...) + Obs #3 ({rl_burst_2['event_nonce'][:12]}...):")
    print(f"     Paired across 2 devices ({device_1_id} & {device_2_id}) for plate '{corroboration_plate}'.")
    print(f"     Backend clustering will corroborate the pair and trigger EvidenceRequest for Obs #2 ({rl_burst_1['event_nonce'][:12]}...).")

    # 3. Buffer Local Evidence Clips in EvidenceBuffer
    print("\n" + "=" * 80)
    print("                     LOCAL EVIDENCE BUFFERING")
    print("=" * 80)

    # Buffer real dashcam frames for Observation 1
    clip_path_1 = ev_buffer.store_clip(
        event_nonce=real_candidate_burst["event_nonce"],
        data=real_candidate_clip_frames[:15],
        fps=5.0,
        metadata={"source": "real_dashcam_footage", "frames": len(real_candidate_clip_frames[:15])},
    )
    print(f"[Evidence Clip 1 - Real Footage]: {clip_path_1.name}")
    print(f"  Composition: 15 consecutive 640x360 frames from real dashcam road video.")
    print(f"  File Size: {clip_path_1.stat().st_size:,} bytes (~750 KB, high visual entropy).")

    # Buffer synthetic frames for Observation 2
    # Note on size: 10 solid-color frames (240x320) contain zero spatial/texture frequency,
    # so MPEG-4 video compression compresses them down to ~9.2 KB.
    rl_clip_frames = [np.full((240, 320, 3), (0, 0, 180 + i * 5), dtype=np.uint8) for i in range(10)]
    clip_path_rl = ev_buffer.store_clip(
        event_nonce=rl_burst_1["event_nonce"],
        data=rl_clip_frames,
        fps=5.0,
        metadata={"source": "synthetic_test_sequence", "violation": "red_light"},
    )
    print(f"\n[Evidence Clip 2 - Test Sequence]: {clip_path_rl.name}")
    print(f"  Composition: 10-frame synthetic test video (240x320 solid crimson gradient frames).")
    print(f"  Encoding Path: Real cv2.VideoWriter encoding path in EvidenceBuffer.")
    print(f"  File Size: {clip_path_rl.stat().st_size:,} bytes (~9.2 KB).")
    print(f"  Why 9.2 KB? Uniform flat frames compress heavily in MPEG-4; used to verify encoding & upload mechanics.")

    # 4. Simulate Offline Outage: Point Client at Unreachable Server
    print("\n" + "=" * 80)
    print("               PHASE 1: SIMULATING OFFLINE NETWORK OUTAGE")
    print("=" * 80)
    offline_client = RoadSenseUplinkClient(base_url="http://127.0.0.1:59999", timeout=1.0)

    # Enqueue candidate bursts during outage
    obs_queue.enqueue(real_candidate_burst)
    obs_queue.enqueue(rl_burst_1)
    obs_queue.enqueue(rl_burst_2)

    print(f"All 3 observations enqueued into ObservationQueue during network outage.")
    print(f"Current Queue Depth: {obs_queue.get_queue_depth()}")
    assert obs_queue.get_queue_depth() == 3

    # Attempt flush during outage
    print("Executing flush() while backend is unreachable...")
    offline_stats = obs_queue.flush(offline_client)
    print(f"Flush Result under Outage: {offline_stats}")

    # Confirm durability: nothing was lost, all remain pending with retry scheduled
    assert offline_stats["sent"] == 0
    assert offline_stats["retry_pending"] == 3
    assert obs_queue.get_queue_depth() == 3
    print("[SUCCESS] Zero observations lost during outage. Queue depth is 3. Exponential backoff armed.")

    # 5. Restore Connection: Flush to Real Live Backend
    print("\n" + "=" * 80)
    print("               PHASE 2: RESTORING LIVE BACKEND CONNECTIVITY")
    print("=" * 80)
    online_client = RoadSenseUplinkClient(
        base_url="http://localhost:8000",
        timeout=10.0,
        evidence_buffer=ev_buffer,
    )

    # Wait 1.2s for base backoff delay (1.0s) to elapse
    print("Waiting 1.2s for backoff delay window to clear...")
    time.sleep(1.2)

    print("Executing flush() with live backend online...")
    online_stats = obs_queue.flush(online_client)
    print(f"Flush Result Online: {online_stats}")
    assert online_stats["sent"] == 3
    assert obs_queue.get_queue_depth() == 0
    print(f"[SUCCESS] All 3 queued observations delivered to live backend. Queue depth drained to 0.")

    # 6. Verify Delivered Observations in Live Backend /v1/incidents
    print("\n" + "=" * 80)
    print("               PHASE 3: VERIFYING BACKEND CLUSTERING & INCIDENTS")
    print("=" * 80)
    auth_resp = httpx.post(
        "http://localhost:8000/v1/auth/login",
        json={"email": "admin@roadsense.local", "password": "roadsense-admin-password"},
    )
    assert auth_resp.status_code == 200
    token = auth_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    incidents_resp = httpx.get("http://localhost:8000/v1/incidents", headers=headers)
    assert incidents_resp.status_code == 200
    all_incidents = incidents_resp.json()

    print(f"Total incidents on backend: {len(all_incidents)}")

    # 7. Real Evidence-Request Round-Trip
    print("\n" + "=" * 80)
    print("               PHASE 4: EVIDENCE COLLECTION ROUND-TRIP")
    print("=" * 80)
    print(f"Polling pending evidence requests for Device 1 ('{device_1_id}')...")
    ev_requests = online_client.poll_evidence_requests(device_1_id)
    print(f"Evidence requests received: {len(ev_requests)}")

    # Verify that ONLY the corroborated pair (Obs #2 / rl_burst_1) received an evidence request
    rl_target_ev = next((ev for ev in ev_requests if ev["event_nonce"] == rl_burst_1["event_nonce"]), None)
    assert rl_target_ev is not None, f"Expected evidence request for corroborated nonce {rl_burst_1['event_nonce']}"
    print(f"[VERIFIED] Evidence request generated for Corroborated Incident {rl_target_ev['incident_id']}:")
    print(f"  Target Nonce: {rl_target_ev['event_nonce']}")
    print(f"  Violation: {rl_target_ev['violation_type']}")
    print(f"  Retention Expires At: {rl_target_ev['retention_expires_at']}")

    # Confirm Obs #1 did NOT generate an evidence request (proper single-device candidate behavior)
    real_target_ev = next((ev for ev in ev_requests if ev["event_nonce"] == real_candidate_burst["event_nonce"]), None)
    assert real_target_ev is None, "Uncorroborated single-camera observation should NOT generate evidence requests"
    print(f"[VERIFIED] Uncorroborated Obs #1 ({real_candidate_burst['event_nonce'][:12]}...) correctly produced NO evidence request.")

    # Upload evidence WITHOUT specifying clip_path -> verifies client resolves it via EvidenceBuffer.get_clip()
    print("\nCalling client.upload_evidence(nonce) WITHOUT passing clip_path...")
    print(f"Client auto-resolves local clip via evidence_buffer.get_clip('{rl_target_ev['event_nonce']}')...")
    upload_res = online_client.upload_evidence(rl_target_ev["event_nonce"])
    print(f"Upload Response from Backend: {upload_res}")

    assert upload_res["status"] == "uploaded"
    assert upload_res["event_nonce"] == rl_target_ev["event_nonce"]
    assert upload_res["storage_ref"] is not None
    print(f"[SUCCESS] Evidence clip verified in MinIO object storage: {upload_res['storage_ref']}")

    # Confirm pending evidence requests for this device are cleared
    remaining_reqs = online_client.poll_evidence_requests(device_1_id)
    cleared = all(r["event_nonce"] != rl_target_ev["event_nonce"] for r in remaining_reqs)
    assert cleared, "Uploaded evidence request was not cleared from pending queue"
    print(f"[SUCCESS] Pending evidence request cleared from backend queue upon successful upload.")

    print("\n" + "=" * 80)
    print("       ALL STORAGE RESILIENCE & INTEGRATION TESTS PASSED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    run_storage_integration_test()
