from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shutil
import sqlite3
import threading
import time
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger("edge.storage.evidence_buffer")

# Matched directly to backend/app/core/config.py (EVIDENCE_TTL_DAYS: int = 30)
DEFAULT_EVIDENCE_TTL_DAYS = 30
DEFAULT_BUFFER_DIR = Path(__file__).resolve().parent / "data" / "evidence"


class EvidenceBuffer:
    """Local clip ring buffer storing evidence media with time-to-live (TTL) expiration.

    Guarantees:
    - Retains footage around candidate violation moments, indexed by event_nonce.
    - Matches backend evidence TTL policy (30 days default).
    - Supports video files (.mp4), image frames (.jpg), raw bytes, and numpy frame sequences.
    - Automated background and on-demand TTL pruning to prevent unbounded disk growth.
    - Direct integration with uplink client upload_evidence().
    """

    def __init__(
        self,
        buffer_dir: str | Path | None = None,
        default_ttl_days: float = DEFAULT_EVIDENCE_TTL_DAYS,
    ):
        self.buffer_dir = Path(buffer_dir) if buffer_dir else DEFAULT_BUFFER_DIR
        self.buffer_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl_days = default_ttl_days
        self.db_path = self.buffer_dir / "evidence_index.db"

        self._lock = threading.Lock()
        self._init_db()

        self._cleanup_thread: threading.Thread | None = None
        self._stop_cleanup_event = threading.Event()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_clips (
                    event_nonce TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    format TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    metadata TEXT
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_evidence_expires ON evidence_clips(expires_at);"
            )
            conn.commit()

    def store_clip(
        self,
        event_nonce: str,
        data: str | Path | bytes | np.ndarray | list[np.ndarray],
        fps: float = 10.0,
        ttl_days: float | None = None,
        ttl_seconds: float | None = None,
        current_time: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Stores media for an event nonce with TTL expiration.

        Args:
            event_nonce: The unique event identifier for the candidate violation.
            data: Video/image file path, raw bytes, single frame array, or sequence of frame arrays.
            fps: Frame rate if encoding a sequence of numpy images to MP4.
            ttl_days: Custom TTL in days (defaults to 30 days).
            ttl_seconds: Custom TTL in seconds (overrides ttl_days if specified).
            current_time: Optional explicit timestamp for deterministic testing.
            metadata: Optional dictionary of associated metadata (violation type, speed, etc.).

        Returns:
            Path object pointing to the locally stored evidence media file.
        """
        now = current_time if current_time is not None else time.time()
        if ttl_seconds is not None:
            effective_ttl = float(ttl_seconds)
        else:
            days = ttl_days if ttl_days is not None else self.default_ttl_days
            effective_ttl = float(days) * 86400.0

        expires_at = now + effective_ttl
        meta_json = json.dumps(metadata or {})

        # 1. Determine destination and save data
        if isinstance(data, (str, Path)):
            src_path = Path(data)
            if not src_path.exists():
                raise FileNotFoundError(f"Source evidence media not found at: {src_path}")
            suffix = src_path.suffix.lower() or ".mp4"
            dest_path = self.buffer_dir / f"{event_nonce}{suffix}"
            shutil.copy2(src_path, dest_path)
            fmt = suffix.lstrip(".")

        elif isinstance(data, bytes):
            # Raw bytes, default to .mp4 or check magic header
            suffix = ".jpg" if data.startswith(b"\xff\xd8\xff") else ".mp4"
            dest_path = self.buffer_dir / f"{event_nonce}{suffix}"
            dest_path.write_bytes(data)
            fmt = suffix.lstrip(".")

        elif isinstance(data, np.ndarray):
            # Single frame image
            dest_path = self.buffer_dir / f"{event_nonce}.jpg"
            cv2.imwrite(str(dest_path), data)
            fmt = "jpg"

        elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], np.ndarray):
            # Sequence of numpy frames -> encode into MP4 video clip
            dest_path = self.buffer_dir / f"{event_nonce}.mp4"
            h, w = data[0].shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(dest_path), fourcc, fps, (w, h))
            for frame in data:
                writer.write(frame)
            writer.release()
            fmt = "mp4"

        else:
            raise ValueError(f"Unsupported evidence data format: {type(data)}")

        size_bytes = dest_path.stat().st_size

        # 2. Record index in SQLite
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO evidence_clips (
                    event_nonce, file_path, format, size_bytes, created_at, expires_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_nonce, str(dest_path.resolve()), fmt, size_bytes, now, expires_at, meta_json),
            )
            conn.commit()

        logger.info(
            "Buffered evidence clip for nonce %s (size: %.1f KB, TTL: %.1f hours)",
            event_nonce,
            size_bytes / 1024.0,
            effective_ttl / 3600.0,
        )
        return dest_path

    def get_clip(self, event_nonce: str, current_time: float | None = None) -> Path | None:
        """Retrieves path to buffered evidence clip if present and unexpired.

        Args:
            event_nonce: The unique incident event identifier.
            current_time: Optional explicit timestamp for deterministic testing.

        Returns:
            Path to evidence file if available and valid; None if expired or non-existent.
        """
        now = current_time if current_time is not None else time.time()

        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                "SELECT file_path, expires_at FROM evidence_clips WHERE event_nonce = ?",
                (event_nonce,),
            )
            row = cur.fetchone()
            if not row:
                return None

            if row["expires_at"] <= now:
                logger.info("Evidence for nonce '%s' has expired (TTL passed); returning None.", event_nonce)
                return None

            clip_path = Path(row["file_path"])
            if not clip_path.exists():
                logger.warning("Evidence file missing from disk: %s", clip_path)
                return None

            return clip_path

    def cleanup_expired(self, current_time: float | None = None) -> int:
        """Prunes clips that have exceeded their TTL expiration timestamp.

        Removes files from disk and purges records from the database index.

        Returns:
            Number of expired evidence clips pruned.
        """
        now = current_time if current_time is not None else time.time()
        pruned_count = 0

        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                "SELECT event_nonce, file_path FROM evidence_clips WHERE expires_at <= ?",
                (now,),
            )
            expired_rows = cur.fetchall()

            for row in expired_rows:
                nonce = row["event_nonce"]
                file_path = Path(row["file_path"])
                try:
                    if file_path.exists():
                        file_path.unlink()
                        logger.info("Deleted expired evidence file: %s", file_path)
                except Exception as del_err:
                    logger.error("Failed to delete expired file %s: %s", file_path, del_err)

                conn.execute("DELETE FROM evidence_clips WHERE event_nonce = ?", (nonce,))
                pruned_count += 1

            conn.commit()

        if pruned_count > 0:
            logger.info("EvidenceBuffer cleanup completed: pruned %d expired clip(s)", pruned_count)
        return pruned_count

    def start_periodic_cleanup(self, interval_seconds: float = 3600.0) -> None:
        """Starts a background daemon thread that runs cleanup_expired at regular intervals."""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            return

        self._stop_cleanup_event.clear()

        def _cleanup_loop():
            logger.info("Started periodic evidence cleanup thread (interval: %.1fs)", interval_seconds)
            while not self._stop_cleanup_event.is_set():
                try:
                    self.cleanup_expired()
                except Exception as err:
                    logger.error("Error during scheduled evidence cleanup: %s", err)
                self._stop_cleanup_event.wait(interval_seconds)

        self._cleanup_thread = threading.Thread(target=_cleanup_loop, daemon=True, name="EvidenceCleanupThread")
        self._cleanup_thread.start()

    def stop_periodic_cleanup(self) -> None:
        """Stops the background periodic cleanup thread."""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._stop_cleanup_event.set()
            self._cleanup_thread.join(timeout=2.0)
            self._cleanup_thread = None
            logger.info("Stopped periodic evidence cleanup thread.")

    def get_stats(self, current_time: float | None = None) -> dict[str, Any]:
        """Returns buffer status and disk usage statistics."""
        now = current_time if current_time is not None else time.time()
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_clips,
                    SUM(CASE WHEN expires_at > ? THEN 1 ELSE 0 END) AS active_clips,
                    SUM(CASE WHEN expires_at <= ? THEN 1 ELSE 0 END) AS expired_clips,
                    COALESCE(SUM(size_bytes), 0) AS total_size_bytes
                FROM evidence_clips
                """,
                (now, now),
            )
            row = cur.fetchone()
            return {
                "total_clips": row["total_clips"] or 0,
                "active_clips": row["active_clips"] or 0,
                "expired_clips": row["expired_clips"] or 0,
                "total_size_bytes": row["total_size_bytes"] or 0,
            }

    def clear(self) -> None:
        """Purges all clips and clears database index. Primarily for testing."""
        with self._lock, self._get_connection() as conn:
            cur = conn.execute("SELECT file_path FROM evidence_clips")
            for r in cur.fetchall():
                p = Path(r["file_path"])
                if p.exists():
                    p.unlink(missing_ok=True)
            conn.execute("DELETE FROM evidence_clips;")
            conn.commit()
