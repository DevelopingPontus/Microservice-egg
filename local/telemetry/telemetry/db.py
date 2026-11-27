"""Phase 1 & 5: SQLite WAL database, batch writer, and 14-day retention pruning."""

from __future__ import annotations

import os
import queue
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS raw_keystrokes (
    ts REAL NOT NULL,
    hold_ms REAL NOT NULL,
    flight_ms REAL,
    is_backspace INTEGER NOT NULL,
    app_hash TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_raw_keystrokes_ts ON raw_keystrokes(ts);

CREATE TABLE IF NOT EXISTS raw_mouse (
    ts REAL NOT NULL,
    distance_px REAL NOT NULL,
    dt_ms REAL NOT NULL,
    is_click INTEGER NOT NULL,
    app_hash TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_raw_mouse_ts ON raw_mouse(ts);

CREATE TABLE IF NOT EXISTS raw_windows (
    ts_start REAL NOT NULL,
    ts_end REAL NOT NULL,
    app_hash TEXT NOT NULL,
    is_idle INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_windows_ts_start ON raw_windows(ts_start);

CREATE TABLE IF NOT EXISTS raw_webcam (
    ts REAL NOT NULL,
    ear REAL NOT NULL,
    mar REAL NOT NULL,
    head_pitch REAL NOT NULL,
    lid_tightening REAL NOT NULL,
    is_closed REAL NOT NULL,
    blink_duration_ms REAL,
    rppg_hr_bpm REAL,
    valid_ratio REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_raw_webcam_ts ON raw_webcam(ts);

CREATE TABLE IF NOT EXISTS fatigue_log (
    ts REAL NOT NULL,
    app_hash TEXT NOT NULL DEFAULT '',
    key_hold_ms REAL,
    key_flight_ms REAL,
    backspace_rate REAL,
    key_pause_rate REAL,
    mouse_velocity_px_per_sec REAL,
    mouse_acceleration_px_per_sec2 REAL,
    mouse_clicks_per_min REAL,
    mouse_click_latency_ms REAL,
    window_focus_duration_s REAL,
    window_switches_per_min REAL,
    webcam_valid_frame_ratio REAL,
    webcam_perclos REAL,
    webcam_ear_variance REAL,
    webcam_blink_duration_ms REAL,
    webcam_blink_rate_per_min REAL,
    webcam_microsleeps INTEGER,
    webcam_mar REAL,
    webcam_lid_tightening REAL,
    webcam_head_pitch_variance REAL,
    webcam_rppg_hr_bpm REAL
);
CREATE INDEX IF NOT EXISTS idx_fatigue_log_ts ON fatigue_log(ts);

CREATE TABLE IF NOT EXISTS app_anchors (
    app_hash TEXT PRIMARY KEY,
    updated_ts REAL NOT NULL,
    sample_count INTEGER NOT NULL,
    key_flight_ms REAL,
    key_hold_ms REAL,
    backspace_rate REAL,
    key_pause_rate REAL,
    mouse_velocity_px_per_sec REAL,
    mouse_acceleration_px_per_sec2 REAL,
    mouse_clicks_per_min REAL,
    mouse_click_latency_ms REAL,
    window_focus_duration_s REAL,
    window_switches_per_min REAL,
    webcam_ear_variance REAL,
    webcam_blink_duration_ms REAL,
    webcam_blink_rate_per_min REAL,
    webcam_mar REAL,
    webcam_lid_tightening REAL,
    webcam_head_pitch_variance REAL,
    webcam_rppg_hr_bpm REAL
);

CREATE TABLE IF NOT EXISTS app_iqrs (
    app_hash TEXT NOT NULL,
    metric TEXT NOT NULL,
    iqr REAL NOT NULL,
    PRIMARY KEY (app_hash, metric)
);
"""

INSERT_SQL = {
    "raw_keystrokes": (
        "INSERT INTO raw_keystrokes (ts, hold_ms, flight_ms, is_backspace, app_hash) "
        "VALUES (?, ?, ?, ?, ?)"
    ),
    "raw_mouse": (
        "INSERT INTO raw_mouse (ts, distance_px, dt_ms, is_click, app_hash) "
        "VALUES (?, ?, ?, ?, ?)"
    ),
    "raw_windows": (
        "INSERT INTO raw_windows (ts_start, ts_end, app_hash, is_idle) "
        "VALUES (?, ?, ?, ?)"
    ),
    "raw_webcam": (
        "INSERT INTO raw_webcam "
        "(ts, ear, mar, head_pitch, lid_tightening, is_closed, blink_duration_ms, rppg_hr_bpm, valid_ratio) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
}


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Initialize SQLite in WAL mode and ensure all tables/indexes exist."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    if path.exists():
        os.chmod(path, 0o600)
    return conn


def prune_old_data(
    conn: sqlite3.Connection,
    retention_days: int = 14,
    now: float | None = None,
) -> dict[str, int]:
    """Phase 5: Delete raw telemetry older than retention_days (keeps fatigue_log)."""
    cutoff = (now if now is not None else time.time()) - (retention_days * 86400)
    deleted: dict[str, int] = {}
    with conn:
        for table, col in (
            ("raw_keystrokes", "ts"),
            ("raw_mouse", "ts"),
            ("raw_windows", "ts_start"),
            ("raw_webcam", "ts"),
        ):
            cur = conn.execute(f"DELETE FROM {table} WHERE {col} < ?", (cutoff,))
            deleted[table] = cur.rowcount
    return deleted


class BatchWriter:
    """Thread-safe queue that flushes raw events to SQLite every flush_interval_s."""

    def __init__(
        self,
        db_path: str | Path,
        flush_interval_s: float = 5.0,
        retention_days: int = 14,
        prune_interval_s: float = 86400.0,
        observability: Any = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.flush_interval_s = flush_interval_s
        self.retention_days = retention_days
        self.prune_interval_s = prune_interval_s
        self.obs = observability
        self._queue: queue.Queue[tuple[str, tuple[Any, ...]]] = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._conn: sqlite3.Connection | None = None
        self._last_prune_ts: float = 0.0

    def enqueue(self, table: str, row: tuple[Any, ...]) -> None:
        """Non-blocking push from any input listener thread."""
        self._queue.put((table, row))
        if self.obs is not None:
            self.obs.events_enqueued.labels(table=table).inc()
            self.obs.queue_size.set(self._queue.qsize())

    def start(self) -> None:
        self._conn = init_db(self.db_path)
        prune_old_data(self._conn, self.retention_days)
        self._last_prune_ts = time.time()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="sqlite-batch-writer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
        self.flush()
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def flush(self) -> int:
        """Drain queued rows and write them in one SQLite transaction per table."""
        if self._conn is None:
            return 0
        batches: dict[str, list[tuple[Any, ...]]] = {}
        while True:
            try:
                table, row = self._queue.get_nowait()
            except queue.Empty:
                break
            batches.setdefault(table, []).append(row)

        if not batches:
            if self.obs is not None:
                self.obs.queue_size.set(0)
            return 0

        t0 = time.perf_counter()
        total = 0
        try:
            with self._conn:
                for table, rows in batches.items():
                    self._conn.executemany(INSERT_SQL[table], rows)
                    total += len(rows)
                    if self.obs is not None:
                        self.obs.events_flushed.labels(table=table).inc(len(rows))
        except Exception:
            if self.obs is not None:
                self.obs.errors_total.labels(component="writer").inc()
            raise
        finally:
            if self.obs is not None:
                self.obs.flush_duration_s.set(round(time.perf_counter() - t0, 6))
                self.obs.queue_size.set(self._queue.qsize())
        return total

    def _run(self) -> None:
        while not self._stop_event.wait(self.flush_interval_s):
            self.flush()
            now = time.time()
            if self._conn is not None and (now - self._last_prune_ts) >= self.prune_interval_s:
                prune_old_data(self._conn, self.retention_days, now=now)
                self._last_prune_ts = now
