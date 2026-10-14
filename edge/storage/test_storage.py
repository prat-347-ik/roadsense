from __future__ import annotations

import json
from pathlib import Path
import time
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from edge.storage.evidence_buffer import DEFAULT_EVIDENCE_TTL_DAYS, EvidenceBuffer
from edge.storage.observation_queue import ObservationQueue
from edge.uplink.client import (
    DuplicateNonceError,
    RoadSenseUplinkClient,
    UplinkConnectionError,
    UplinkError,
    UplinkValidationError,
)


@pytest.fixture
def temp_storage_dirs(tmp_path: Path):
    queue_db = tmp_path / "test_queue.db"
    buffer_dir = tmp_path / "test_evidence"
    return queue_db, buffer_dir


def _make_sample_burst(nonce: str, plate: str = "MH12AB1234", violation: str = "wrong_side") -> dict:
    return {
        "event_nonce": nonce,
        "device_id": "test-device-01",
        "violation_type": violation,
        "plate_no": plate,
        "lat": 18.5204,
        "lon": 73.8567,
        "timestamp": "2026-10-13T05:00:00Z",
        "sig": "stub_sig",
    }


# ==============================================================================
# OBSERVATION QUEUE UNIT TESTS
# ==============================================================================

def test_queue_enqueue_and_operational_counts(temp_storage_dirs):
    queue_db, _ = temp_storage_dirs
    q = ObservationQueue(db_path=queue_db)

    assert q.get_queue_depth() == 0
    assert q.get_failed_count() == 0
    assert q.get_sent_count() == 0

    nonce1 = q.enqueue(_make_sample_burst("nonce-1"))
    nonce2 = q.enqueue(_make_sample_burst("nonce-2"))
    assert nonce1 == "nonce-1"
    assert nonce2 == "nonce-2"

    assert q.get_queue_depth() == 2
    stats = q.get_stats()
    assert stats["pending"] == 2
    assert stats["total"] == 2

    # Idempotent re-enqueue of same nonce does not duplicate row
    q.enqueue(_make_sample_burst("nonce-1"))
    assert q.get_queue_depth() == 2


def test_queue_connection_error_and_exponential_backoff(temp_storage_dirs):
    queue_db, _ = temp_storage_dirs
    q = ObservationQueue(db_path=queue_db, base_delay=2.0, max_delay=30.0, backoff_factor=2.0)

    t0 = 1000.0
    q.enqueue(_make_sample_burst("nonce-err-1"), current_time=t0)
    q.enqueue(_make_sample_burst("nonce-err-2"), current_time=t0)

    mock_client = MagicMock()
    mock_client.send_observation.side_effect = UplinkConnectionError("Network connection unreachable")

    # 1. First flush at t0: fails with connection error
    stats1 = q.flush(mock_client, current_time=t0)
    assert stats1["retry_pending"] == 2
    assert stats1["sent"] == 0
    assert stats1["failed"] == 0

    # Queue depth remains 2 (nothing lost!)
    assert q.get_queue_depth() == 2

    pending = q.get_pending_observations()
    assert len(pending) == 2
    for p in pending:
        assert p["retry_count"] == 1
        # Delay = base_delay * (2 ** 0) = 2.0s -> next_attempt_at = 1002.0
        assert p["next_attempt_at"] == pytest.approx(1002.0)
        assert "Network connection unreachable" in p["error_message"]

    # 2. Immediate flush at t0 + 1.0s (delay not elapsed): should skip both
    stats2 = q.flush(mock_client, current_time=t0 + 1.0)
    assert stats2["skipped_backoff"] == 2
    assert stats2["retry_pending"] == 0

    # 3. Flush at t0 + 2.5s (backoff window elapsed): attempts retry and increases backoff
    stats3 = q.flush(mock_client, current_time=t0 + 2.5)
    assert stats3["retry_pending"] == 2

    pending_after = q.get_pending_observations()
    for p in pending_after:
        assert p["retry_count"] == 2
        # Delay = base_delay * (2 ** 1) = 4.0s -> next_attempt_at = 1002.5 + 4.0 = 1006.5
        assert p["next_attempt_at"] == pytest.approx(1006.5)


def test_queue_flush_success_drains_queue(temp_storage_dirs):
    queue_db, _ = temp_storage_dirs
    q = ObservationQueue(db_path=queue_db)

    q.enqueue(_make_sample_burst("nonce-ok-1"))
    q.enqueue(_make_sample_burst("nonce-ok-2"))
    assert q.get_queue_depth() == 2

    mock_client = MagicMock()
    mock_client.send_observation.return_value = {
        "status": "accepted",
        "event_nonce": "test",
        "hashed_plate": "abc123",
    }

    stats = q.flush(mock_client)
    assert stats["sent"] == 2
    assert stats["failed"] == 0
    assert stats["retry_pending"] == 0

    # Queue drained
    assert q.get_queue_depth() == 0
    assert q.get_sent_count() == 2


def test_queue_409_duplicate_counts_as_sent(temp_storage_dirs):
    queue_db, _ = temp_storage_dirs
    q = ObservationQueue(db_path=queue_db)

    # Test both handled duplicate dict and DuplicateNonceError exception
    q.enqueue(_make_sample_burst("nonce-dup-dict"))
    q.enqueue(_make_sample_burst("nonce-dup-exc"))

    mock_client = MagicMock()
    def _mock_send(burst):
        if burst["event_nonce"] == "nonce-dup-dict":
            return {"status": "duplicate", "detail": "Already exists in DB"}
        raise DuplicateNonceError("HTTP 409 Conflict duplicate nonce")

    mock_client.send_observation.side_effect = _mock_send

    stats = q.flush(mock_client)
    assert stats["sent"] == 2
    assert stats["failed"] == 0
    assert stats["retry_pending"] == 0

    assert q.get_queue_depth() == 0
    assert q.get_sent_count() == 2


def test_queue_422_and_400_marks_failed_without_retry(temp_storage_dirs):
    queue_db, _ = temp_storage_dirs
    q = ObservationQueue(db_path=queue_db)

    q.enqueue(_make_sample_burst("nonce-422"))
    q.enqueue(_make_sample_burst("nonce-400"))

    mock_client = MagicMock()
    def _mock_send(burst):
        if burst["event_nonce"] == "nonce-422":
            raise UplinkValidationError("HTTP 422: plate_no missing or invalid schema")
        raise UplinkError("HTTP 400: Bad Request")

    mock_client.send_observation.side_effect = _mock_send

    stats = q.flush(mock_client)
    assert stats["failed"] == 2
    assert stats["sent"] == 0
    assert stats["retry_pending"] == 0

    assert q.get_queue_depth() == 0  # Not pending anymore!
    assert q.get_failed_count() == 2

    failed = q.get_failed_observations()
    assert len(failed) == 2
    assert any("422" in f["error_message"] for f in failed)
    assert any("400" in f["error_message"] for f in failed)

    # Next flush will NOT attempt to retry permanent failures
    mock_client.reset_mock()
    stats_next = q.flush(mock_client)
    assert stats_next["sent"] == 0
    assert stats_next["failed"] == 0
    mock_client.send_observation.assert_not_called()


# ==============================================================================
# EVIDENCE BUFFER UNIT TESTS
# ==============================================================================

def test_evidence_buffer_store_and_retrieve_formats(temp_storage_dirs):
    _, buffer_dir = temp_storage_dirs
    buf = EvidenceBuffer(buffer_dir=buffer_dir)

    # 1. Store raw video bytes
    p_bytes = buf.store_clip("nonce-bytes", b"\x00\x00\x00 fake mp4 content")
    assert p_bytes.exists()
    assert p_bytes.suffix == ".mp4"

    # 2. Store single image numpy array
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    p_img = buf.store_clip("nonce-img", dummy_img)
    assert p_img.exists()
    assert p_img.suffix == ".jpg"

    # 3. Store sequence of numpy frame arrays -> MP4 video
    frames = [np.full((64, 64, 3), i * 20, dtype=np.uint8) for i in range(5)]
    p_frames = buf.store_clip("nonce-video", frames, fps=5.0)
    assert p_frames.exists()
    assert p_frames.suffix == ".mp4"
    assert p_frames.stat().st_size > 0

    # 4. Store existing file
    sample_file = buffer_dir / "external_clip.mp4"
    sample_file.write_bytes(b"sample file data")
    p_file = buf.store_clip("nonce-file", sample_file)
    assert p_file.exists()

    # Retrieve all clips
    assert buf.get_clip("nonce-bytes") == p_bytes
    assert buf.get_clip("nonce-img") == p_img
    assert buf.get_clip("nonce-video") == p_frames
    assert buf.get_clip("nonce-file") == p_file

    # Unknown nonce returns None
    assert buf.get_clip("non-existent-nonce") is None

    stats = buf.get_stats()
    assert stats["total_clips"] == 4
    assert stats["active_clips"] == 4
    assert stats["expired_clips"] == 0


def test_evidence_buffer_ttl_expiration_and_cleanup(temp_storage_dirs):
    _, buffer_dir = temp_storage_dirs
    buf = EvidenceBuffer(buffer_dir=buffer_dir)

    t0 = 5000.0

    # Clip 1: TTL = 10 seconds (expires at 5010.0)
    p1 = buf.store_clip("nonce-short", b"short-lived video", ttl_seconds=10.0, current_time=t0)
    # Clip 2: TTL = 60 seconds (expires at 5060.0)
    p2 = buf.store_clip("nonce-long", b"longer-lived video", ttl_seconds=60.0, current_time=t0)

    assert p1.exists()
    assert p2.exists()

    # At t0 + 5.0s: both clips are valid and retrievable
    assert buf.get_clip("nonce-short", current_time=t0 + 5.0) == p1
    assert buf.get_clip("nonce-long", current_time=t0 + 5.0) == p2

    # At t0 + 15.0s: clip 1 has passed TTL -> get_clip returns None
    assert buf.get_clip("nonce-short", current_time=t0 + 15.0) is None
    assert buf.get_clip("nonce-long", current_time=t0 + 15.0) == p2

    # Run cleanup at t0 + 15.0s: clip 1 should be pruned from disk and DB, clip 2 preserved
    pruned = buf.cleanup_expired(current_time=t0 + 15.0)
    assert pruned == 1
    assert not p1.exists()
    assert p2.exists()

    # At t0 + 70.0s: clip 2 also expired
    pruned2 = buf.cleanup_expired(current_time=t0 + 70.0)
    assert pruned2 == 1
    assert not p2.exists()

    stats = buf.get_stats(current_time=t0 + 70.0)
    assert stats["total_clips"] == 0


def test_evidence_buffer_matches_backend_30_day_ttl(temp_storage_dirs):
    _, buffer_dir = temp_storage_dirs
    buf = EvidenceBuffer(buffer_dir=buffer_dir)

    assert buf.default_ttl_days == DEFAULT_EVIDENCE_TTL_DAYS == 30

    t0 = 10000.0
    p = buf.store_clip("nonce-30d", b"30 day clip", current_time=t0)

    # 29 days later: still active
    day_29 = t0 + (29 * 86400)
    assert buf.get_clip("nonce-30d", current_time=day_29) == p

    # 31 days later: expired
    day_31 = t0 + (31 * 86400)
    assert buf.get_clip("nonce-30d", current_time=day_31) is None


def test_evidence_buffer_background_cleanup_lifecycle(temp_storage_dirs):
    _, buffer_dir = temp_storage_dirs
    buf = EvidenceBuffer(buffer_dir=buffer_dir)

    buf.start_periodic_cleanup(interval_seconds=0.1)
    assert buf._cleanup_thread is not None
    assert buf._cleanup_thread.is_alive()

    time.sleep(0.05)
    buf.stop_periodic_cleanup()
    assert buf._cleanup_thread is None


def test_uplink_client_auto_resolves_clip_from_evidence_buffer(temp_storage_dirs):
    _, buffer_dir = temp_storage_dirs
    buf = EvidenceBuffer(buffer_dir=buffer_dir)
    client = RoadSenseUplinkClient(base_url="http://localhost:8000", evidence_buffer=buf)

    # If clip is not in buffer, upload_evidence returns pending status cleanly
    res_missing = client.upload_evidence("unknown-nonce")
    assert res_missing["status"] == "pending_local_storage"

    # Store clip in buffer
    clip_path = buf.store_clip("known-nonce", b"sample video bytes")
    # Verified get_clip works
    assert client.evidence_buffer.get_clip("known-nonce") == clip_path
