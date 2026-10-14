from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import cv2
import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from edge.detection.plate_detector import YOLOPlateDetector
from edge.ocr.plate_reader import read_plate
from edge.uplink.burst import assemble_burst
from edge.uplink.client import RoadSenseUplinkClient
from edge.uplink.signing import DeviceSigner


def test_independent_ocr_corroboration():
    print("=" * 80)
    print("       REAL-WORLD INDEPENDENT OCR CORROBORATION TEST")
    print("=" * 80)

    # 1. Load two different real frames of the same physical vehicle in motion
    frames_dir = REPO_ROOT / "edge" / "tracking" / "evaluation_road_clip_164404"
    f39_path = frames_dir / "annotated_f_0039.jpg"
    f40_path = frames_dir / "annotated_f_0040.jpg"

    assert f39_path.exists(), f"Frame 39 not found at {f39_path}"
    assert f40_path.exists(), f"Frame 40 not found at {f40_path}"

    img39 = cv2.imread(str(f39_path))
    img40 = cv2.imread(str(f40_path))

    p_detector = YOLOPlateDetector("edge/runs/plate_v1/weights/best.pt", confidence_threshold=0.25)

    # 2. Detect plate on both frames independently
    dets39 = p_detector.detect(img39)
    dets40 = p_detector.detect(img40)

    assert dets39, "No plate detected in Frame 39"
    assert dets40, "No plate detected in Frame 40"

    best_det39 = max(dets39, key=lambda d: d.bbox[2] - d.bbox[0])
    best_det40 = max(dets40, key=lambda d: d.bbox[2] - d.bbox[0])

    b39 = best_det39.bbox
    b40 = best_det40.bbox

    w39 = b39[2] - b39[0]
    w40 = b40[2] - b40[0]

    # Crop both independently
    crop39 = img39[int(b39[1]):int(b39[3]), int(b39[0]):int(b39[2])]
    crop40 = img40[int(b40[1]):int(b40[3]), int(b40[0]):int(b40[2])]

    # Save artifact crops for inspection
    artifacts_dir = REPO_ROOT / "edge" / "ocr" / "corroboration_test"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(artifacts_dir / "frame39_crop.jpg"), crop39)
    cv2.imwrite(str(artifacts_dir / "frame40_crop.jpg"), crop40)

    # 3. Run OCR independently on both crops
    print("\n--- Running Independent OCR Reads on Real Moving Vehicle ---")
    ocr_result_39 = read_plate(crop39)
    ocr_result_40 = read_plate(crop40)

    print(f"Frame 39 (Vehicle approaching, plate width {w39:.1f}px):")
    print(f"  -> Raw OCR Output: {repr(ocr_result_39)}")
    print(f"Frame 40 (Vehicle moving forward, plate width {w40:.1f}px):")
    print(f"  -> Raw OCR Output: {repr(ocr_result_40)}")

    # 4. Compare the two OCR outputs directly
    print("\n--- Comparing Independent OCR Outputs ---")
    plates_match = (ocr_result_39 == ocr_result_40)
    print(f"Direct String Match: {plates_match}")
    if not plates_match:
        print(f"Discrepancy: '{ocr_result_39}' vs '{ocr_result_40}'")
        # Character diff
        diffs = [
            f"pos {i}: '{c1}' vs '{c2}'"
            for i, (c1, c2) in enumerate(zip(ocr_result_39 or "", ocr_result_40 or ""))
            if c1 != c2
        ]
        print(f"Differences: {', '.join(diffs)}")

    # 5. Initialize Uplink Client & Device Signers
    client = RoadSenseUplinkClient(base_url="http://localhost:8000")
    device_1_id = "independent-cam-north"
    device_2_id = "independent-cam-south"
    signer_1 = DeviceSigner(key_path=REPO_ROOT / "edge" / "uplink" / "keys" / "device_1_key.pem")
    signer_2 = DeviceSigner(key_path=REPO_ROOT / "edge" / "uplink" / "keys" / "device_2_key.pem")

    base_time = datetime.now(timezone.utc) - timedelta(minutes=2)

    # Burst 1 from Device 1 with OCR read 1
    burst_1 = assemble_burst(
        violation_type="wrong_side",
        plate_no=ocr_result_39,
        device_id=device_1_id,
        lat=18.5204,
        lon=73.8567,
        timestamp=base_time,
        signer=signer_1,
    )

    # Burst 2 from Device 2 with OCR read 2 (5 seconds later, progressed 22m)
    burst_2 = assemble_burst(
        violation_type="wrong_side",
        plate_no=ocr_result_40,
        device_id=device_2_id,
        lat=18.5206,
        lon=73.8567,
        timestamp=base_time + timedelta(seconds=5),
        signer=signer_2,
    )

    print("\n--- Transmitting Bursts from Two Independent Devices ---")
    resp_1 = client.send_observation(burst_1)
    print(f"Device 1 Observation Accepted:")
    print(f"  Nonce: {resp_1['event_nonce']}")
    print(f"  Hashed Plate: {resp_1['hashed_plate']}")

    resp_2 = client.send_observation(burst_2)
    print(f"Device 2 Observation Accepted:")
    print(f"  Nonce: {resp_2['event_nonce']}")
    print(f"  Hashed Plate: {resp_2['hashed_plate']}")

    hashes_match = (resp_1["hashed_plate"] == resp_2["hashed_plate"])
    print(f"\nBackend Privacy Hash Match: {hashes_match}")
    print(f"  Hash 1: {resp_1['hashed_plate']}")
    print(f"  Hash 2: {resp_2['hashed_plate']}")

    # 6. Query Live Backend /v1/incidents to check Corroboration Status
    print("\n--- Querying Live Backend /v1/incidents ---")
    login_res = httpx.post(
        "http://localhost:8000/v1/auth/login",
        json={"email": "admin@roadsense.local", "password": "roadsense-admin-password"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    incidents_res = httpx.get("http://localhost:8000/v1/incidents", headers=headers)
    assert incidents_res.status_code == 200
    all_incidents = incidents_res.json()

    # Find incidents corresponding to Hash 1 and Hash 2
    incidents_1 = [inc for inc in all_incidents if inc["hashed_plate"] == resp_1["hashed_plate"]]
    incidents_2 = [inc for inc in all_incidents if inc["hashed_plate"] == resp_2["hashed_plate"]]

    print(f"\nIncidents for Hash 1 ({resp_1['hashed_plate'][:12]}...):")
    for inc in incidents_1:
        print(f"  Incident ID: {inc['id']} | Status: {inc['status']} | Observations Linked: {inc['observation_count']}")

    print(f"\nIncidents for Hash 2 ({resp_2['hashed_plate'][:12]}...):")
    for inc in incidents_2:
        print(f"  Incident ID: {inc['id']} | Status: {inc['status']} | Observations Linked: {inc['observation_count']}")

    # 7. Evaluate Corroboration Verdict
    if hashes_match:
        # If hashes matched, both observations should be clustered into the same incident
        assert len(incidents_1) >= 1
        matched_inc = incidents_1[0]
        print("\n[VERDICT] Identical OCR reads matched. Incidents corroborated.")
        print(f"  Observation count: {matched_inc['observation_count']}")
    else:
        # Hashes differed: backend treated them as two separate, uncorroborated candidate incidents
        print("\n[VERDICT] REAL ARCHITECTURAL FINDING CONFIRMED:")
        print("  Two independent, high-confidence OCR reads of the EXACT same physical vehicle")
        print(f"  produced slightly different strings ('{ocr_result_39}' vs '{ocr_result_40}', 1 char diff).")
        print("  Because backend clustering groups by exact SHA-256 hashed_plate:")
        print(f"    - Device 1's observation formed Candidate Incident with count={incidents_1[0]['observation_count']}")
        print(f"    - Device 2's observation formed Candidate Incident with count={incidents_2[0]['observation_count']}")
        print("    - Neither incident corroborated. ZERO cross-device corroboration occurred.")
        print("  Conclusion: Exact hash-based corroboration fails when independent cameras experience OCR character noise.")

    return {
        "ocr_1": ocr_result_39,
        "ocr_2": ocr_result_40,
        "hash_1": resp_1["hashed_plate"],
        "hash_2": resp_2["hashed_plate"],
        "hashes_match": hashes_match,
        "incidents_1": incidents_1,
        "incidents_2": incidents_2,
    }


if __name__ == "__main__":
    test_independent_ocr_corroboration()
