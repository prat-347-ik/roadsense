from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

from edge.uplink.client import (
    DuplicateNonceError,
    RoadSenseUplinkClient,
    UplinkConnectionError,
    UplinkError,
    UplinkValidationError,
)

logger = logging.getLogger("edge.storage.observation_queue")

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "queue.db"


class ObservationQueue:
    """Persistent local SQLite-backed queue for observation bursts with exponential backoff.

    Guarantees:
    - Offline durability: observations are enqueued locally before transmission.
    - Idempotency: duplicate event_nonces are detected and prevented.
    - Status lifecycle: 'pending' -> 'sent' or 'failed'.
    - 409 Conflict (duplicate nonce): marked 'sent' because backend already has it.
    - 400 / 422: marked 'failed' immediately without endless retries.
    - Connection failure: preserved as 'pending' with exponential backoff per row.
    - Operational visibility: query queue depth and failed observations.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
    ):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self._lock = threading.Lock()
        self._init_db()

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
                CREATE TABLE IF NOT EXISTS observations_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_nonce TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'sent', 'failed')),
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    last_attempt_at REAL,
                    next_attempt_at REAL,
                    error_message TEXT
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_obs_status_next ON observations_queue(status, next_attempt_at);"
            )
            conn.commit()

    def enqueue(self, burst: dict[str, Any], current_time: float | None = None) -> str:
        """Enqueues an observation burst into the persistent queue.

        Args:
            burst: Dict matching ObservationBurstRequest schema (must include event_nonce).
            current_time: Optional explicit timestamp for testing.

        Returns:
            The event_nonce of the queued burst.
        """
        nonce = burst.get("event_nonce")
        if not nonce:
            raise ValueError("Observation burst must contain 'event_nonce'")

        now = current_time if current_time is not None else time.time()
        payload_json = json.dumps(burst)

        with self._lock, self._get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO observations_queue (
                        event_nonce, payload, status, retry_count, created_at, next_attempt_at
                    ) VALUES (?, ?, 'pending', 0, ?, ?)
                    """,
                    (nonce, payload_json, now, now),
                )
                conn.commit()
                logger.info("Enqueued observation burst (nonce: %s)", nonce)
            except sqlite3.IntegrityError:
                logger.warning("Observation with nonce '%s' already exists in queue; skipping insert.", nonce)

        return nonce

    def get_queue_depth(self) -> int:
        """Returns the number of pending observations waiting to be sent."""
        with self._lock, self._get_connection() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM observations_queue WHERE status = 'pending'")
            return cur.fetchone()[0]

    def get_failed_count(self) -> int:
        """Returns the number of permanently failed observations (e.g. 400/422)."""
        with self._lock, self._get_connection() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM observations_queue WHERE status = 'failed'")
            return cur.fetchone()[0]

    def get_sent_count(self) -> int:
        """Returns the number of successfully sent observations."""
        with self._lock, self._get_connection() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM observations_queue WHERE status = 'sent'")
            return cur.fetchone()[0]

    def get_stats(self) -> dict[str, int]:
        """Returns aggregated queue statistics for operational monitoring."""
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                    SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) AS sent,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                    COUNT(*) AS total
                FROM observations_queue
                """
            )
            row = cur.fetchone()
            return {
                "pending": row["pending"] or 0,
                "sent": row["sent"] or 0,
                "failed": row["failed"] or 0,
                "total": row["total"] or 0,
            }

    def get_failed_observations(self) -> list[dict[str, Any]]:
        """Returns all failed observations for debugging and operational inspection."""
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                """
                SELECT id, event_nonce, payload, status, retry_count, created_at, last_attempt_at, error_message
                FROM observations_queue
                WHERE status = 'failed'
                ORDER BY id ASC
                """
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r["id"],
                    "event_nonce": r["event_nonce"],
                    "payload": json.loads(r["payload"]),
                    "status": r["status"],
                    "retry_count": r["retry_count"],
                    "created_at": r["created_at"],
                    "last_attempt_at": r["last_attempt_at"],
                    "error_message": r["error_message"],
                }
                for r in rows
            ]

    def get_pending_observations(self) -> list[dict[str, Any]]:
        """Returns all pending observations in the queue."""
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                """
                SELECT id, event_nonce, payload, status, retry_count, created_at, next_attempt_at, error_message
                FROM observations_queue
                WHERE status = 'pending'
                ORDER BY id ASC
                """
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r["id"],
                    "event_nonce": r["event_nonce"],
                    "payload": json.loads(r["payload"]),
                    "status": r["status"],
                    "retry_count": r["retry_count"],
                    "created_at": r["created_at"],
                    "next_attempt_at": r["next_attempt_at"],
                    "error_message": r["error_message"],
                }
                for r in rows
            ]

    def flush(
        self,
        client: RoadSenseUplinkClient,
        limit: int | None = None,
        current_time: float | None = None,
    ) -> dict[str, int]:
        """Attempts to transmit pending observations whose backoff window has elapsed.

        Policy:
        - HTTP 200/201 (Accepted): marked 'sent'.
        - HTTP 409 (Duplicate nonce): marked 'sent' (backend already persisted it).
        - HTTP 400 / 422 (Bad Request / Schema validation): marked 'failed' (do not retry forever).
        - Connection / Network error: retained as 'pending', increments retry_count,
          and schedules next_attempt_at using exponential backoff.

        Args:
            client: An initialized RoadSenseUplinkClient.
            limit: Optional maximum number of rows to process in this flush cycle.
            current_time: Optional explicit timestamp for deterministic testing.

        Returns:
            Dict containing counts of 'sent', 'failed', 'retry_pending', 'skipped_backoff'.
        """
        now = current_time if current_time is not None else time.time()
        stats = {"sent": 0, "failed": 0, "retry_pending": 0, "skipped_backoff": 0}

        with self._lock, self._get_connection() as conn:
            # Query pending rows eligible for retry
            query = """
                SELECT id, event_nonce, payload, retry_count, next_attempt_at
                FROM observations_queue
                WHERE status = 'pending'
                ORDER BY id ASC
            """
            if limit:
                query += f" LIMIT {int(limit)}"

            cur = conn.execute(query)
            candidates = cur.fetchall()

            for row in candidates:
                row_id = row["id"]
                nonce = row["event_nonce"]
                next_attempt = row["next_attempt_at"]
                retry_count = row["retry_count"]

                # Respect exponential backoff delay
                if next_attempt is not None and next_attempt > now:
                    stats["skipped_backoff"] += 1
                    continue

                try:
                    payload = json.loads(row["payload"])
                except Exception as parse_err:
                    conn.execute(
                        "UPDATE observations_queue SET status = 'failed', last_attempt_at = ?, error_message = ? WHERE id = ?",
                        (now, f"JSON parse error: {parse_err}", row_id),
                    )
                    stats["failed"] += 1
                    continue

                # Attempt sending to backend
                try:
                    response = client.send_observation(payload)
                    # Check if response was handled duplicate
                    if response.get("status") == "duplicate":
                        logger.info("Nonce '%s' already exists on backend (409); marking sent.", nonce)
                        conn.execute(
                            "UPDATE observations_queue SET status = 'sent', last_attempt_at = ?, error_message = 'Duplicate (409)' WHERE id = ?",
                            (now, row_id),
                        )
                    else:
                        logger.info("Successfully sent observation nonce '%s'", nonce)
                        conn.execute(
                            "UPDATE observations_queue SET status = 'sent', last_attempt_at = ?, error_message = NULL WHERE id = ?",
                            (now, row_id),
                        )
                    stats["sent"] += 1

                except DuplicateNonceError as dup_err:
                    logger.info("Nonce '%s' duplicate exception; marking sent.", nonce)
                    conn.execute(
                        "UPDATE observations_queue SET status = 'sent', last_attempt_at = ?, error_message = ? WHERE id = ?",
                        (now, str(dup_err), row_id),
                    )
                    stats["sent"] += 1

                except UplinkConnectionError as conn_err:
                    # Connection error: leave pending, increment retry count, compute exponential backoff
                    new_retry = retry_count + 1
                    delay = min(self.base_delay * (self.backoff_factor ** (new_retry - 1)), self.max_delay)
                    next_attempt_at = now + delay
                    logger.warning(
                        "Connection error sending nonce '%s' (retry %d, backoff delay %.1fs): %s",
                        nonce,
                        new_retry,
                        delay,
                        conn_err,
                    )
                    conn.execute(
                        """
                        UPDATE observations_queue
                        SET retry_count = ?, last_attempt_at = ?, next_attempt_at = ?, error_message = ?
                        WHERE id = ?
                        """,
                        (new_retry, now, next_attempt_at, str(conn_err), row_id),
                    )
                    stats["retry_pending"] += 1

                except (UplinkValidationError, UplinkError) as client_err:
                    # 400 or 422: unprocessable / bad payload, do not retry forever
                    logger.error("Permanent error for nonce '%s': %s; marking failed.", nonce, client_err)
                    conn.execute(
                        "UPDATE observations_queue SET status = 'failed', last_attempt_at = ?, error_message = ? WHERE id = ?",
                        (now, str(client_err), row_id),
                    )
                    stats["failed"] += 1

                except Exception as unk_err:
                    # Unexpected runtime error: treat as connection/retryable
                    new_retry = retry_count + 1
                    delay = min(self.base_delay * (self.backoff_factor ** (new_retry - 1)), self.max_delay)
                    next_attempt_at = now + delay
                    conn.execute(
                        """
                        UPDATE observations_queue
                        SET retry_count = ?, last_attempt_at = ?, next_attempt_at = ?, error_message = ?
                        WHERE id = ?
                        """,
                        (new_retry, now, next_attempt_at, str(unk_err), row_id),
                    )
                    stats["retry_pending"] += 1

            conn.commit()

        return stats

    def clear(self) -> None:
        """Clears all records in the queue. Primarily for testing."""
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM observations_queue;")
            conn.commit()
