"""Async SQLite connection manager and schema initialization with WAL mode."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS epoch_metrics_30s (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_start REAL NOT NULL,
    timestamp_end REAL NOT NULL,
    primary_process TEXT NOT NULL,

    -- Temporal Dynamics & Interaction Modality
    active_seconds REAL NOT NULL,
    micro_pause_count INTEGER NOT NULL,
    mouse_click_count INTEGER NOT NULL DEFAULT 0,
    scroll_count INTEGER NOT NULL DEFAULT 0,

    -- Attentional Fragmentation
    context_switch_count INTEGER NOT NULL,
    dwell_distribution_json TEXT NOT NULL,

    -- Psychomotor Mechanics (Algebraic Aggregates)
    total_keystrokes INTEGER NOT NULL,
    correction_keystrokes INTEGER NOT NULL,
    iki_count INTEGER NOT NULL,
    iki_sum_ms REAL NOT NULL,
    iki_sum_sq_ms REAL NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_epochs_time_range
ON epoch_metrics_30s(timestamp_start, timestamp_end);

CREATE TABLE IF NOT EXISTS activity_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    duration_seconds REAL NOT NULL,
    primary_process TEXT NOT NULL,
    epoch_count INTEGER NOT NULL,
    duty_cycle REAL NOT NULL,
    shannon_entropy REAL NOT NULL,
    switches_per_minute REAL NOT NULL,
    iki_cv REAL NOT NULL,
    correction_ratio REAL NOT NULL,
    overall_strain_score REAL NOT NULL,
    dominant_state_label TEXT NOT NULL,
    sre_status TEXT NOT NULL,
    sre_alert_reason TEXT NOT NULL,
    dimensions_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_activity_blocks_time_range
ON activity_blocks(start_time, end_time);
"""


async def configure_connection(conn: aiosqlite.Connection) -> None:
    """Apply SQLite WAL journal mode, NORMAL sync, foreign keys, and busy timeout."""
    await conn.execute("PRAGMA journal_mode = WAL;")
    await conn.execute("PRAGMA synchronous = NORMAL;")
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA busy_timeout = 5000;")
    conn.row_factory = aiosqlite.Row


@asynccontextmanager
async def get_db_connection(
    db_path: Path | str,
) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Open an aiosqlite connection configured with WAL mode and Row factory."""
    async with aiosqlite.connect(str(db_path)) as conn:
        await configure_connection(conn)
        yield conn


async def init_database(db_path: Path | str) -> None:
    """Create the epoch_metrics_30s table and time-range index if they do not exist."""
    async with get_db_connection(db_path) as conn:
        await conn.executescript(SCHEMA_SQL)
        await conn.commit()
