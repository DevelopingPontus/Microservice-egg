"""Repository and lossless mathematical pooling for 30-second telemetry epochs."""

from collections.abc import Sequence
from pathlib import Path

import aiosqlite

from app.common.config import IKI_MIN_VALID_SAMPLES as DEFAULT_IKI_MIN_VALID_SAMPLES
from app.common.models import (
    ActivityBlockDTO,
    ActivityBlockRecordProtocol,
    EpochMetricsDTO,
    EpochRecordProtocol,
    PooledTelemetryMetrics,
    compute_shannon_entropy,
    merge_dwell_distributions,
    pool_epoch_metrics,
)
from app.storage.database import get_db_connection, init_database

__all__ = [
    "ActivityBlockDTO",
    "ActivityBlockRecordProtocol",
    "DEFAULT_IKI_MIN_VALID_SAMPLES",
    "EpochMetricsDTO",
    "EpochRecordProtocol",
    "EpochRepository",
    "PooledTelemetryMetrics",
    "compute_shannon_entropy",
    "merge_dwell_distributions",
    "pool_epoch_metrics",
]

_INSERT_EPOCH_SQL = """
INSERT INTO epoch_metrics_30s (
    timestamp_start,
    timestamp_end,
    primary_process,
    active_seconds,
    micro_pause_count,
    mouse_click_count,
    scroll_count,
    context_switch_count,
    dwell_distribution_json,
    total_keystrokes,
    correction_keystrokes,
    iki_count,
    iki_sum_ms,
    iki_sum_sq_ms
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

_SELECT_RANGE_SQL = """
SELECT
    id,
    timestamp_start,
    timestamp_end,
    primary_process,
    active_seconds,
    micro_pause_count,
    mouse_click_count,
    scroll_count,
    context_switch_count,
    dwell_distribution_json,
    total_keystrokes,
    correction_keystrokes,
    iki_count,
    iki_sum_ms,
    iki_sum_sq_ms
FROM epoch_metrics_30s
WHERE timestamp_start >= ? AND timestamp_end <= ?
ORDER BY timestamp_start ASC;
"""

_INSERT_ACTIVITY_BLOCK_SQL = """
INSERT INTO activity_blocks (
    start_time,
    end_time,
    duration_seconds,
    primary_process,
    epoch_count,
    duty_cycle,
    shannon_entropy,
    switches_per_minute,
    iki_cv,
    correction_ratio,
    overall_strain_score,
    dominant_state_label,
    sre_status,
    sre_alert_reason,
    dimensions_json
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

_SELECT_ACTIVITY_BLOCKS_RANGE_SQL = """
SELECT
    id,
    start_time,
    end_time,
    duration_seconds,
    primary_process,
    epoch_count,
    duty_cycle,
    shannon_entropy,
    switches_per_minute,
    iki_cv,
    correction_ratio,
    overall_strain_score,
    dominant_state_label,
    sre_status,
    sre_alert_reason,
    dimensions_json
FROM activity_blocks
WHERE start_time >= ? AND end_time <= ?
ORDER BY start_time ASC;
"""

_SELECT_RECENT_ACTIVITY_BLOCKS_SQL = """
SELECT
    id,
    start_time,
    end_time,
    duration_seconds,
    primary_process,
    epoch_count,
    duty_cycle,
    shannon_entropy,
    switches_per_minute,
    iki_cv,
    correction_ratio,
    overall_strain_score,
    dominant_state_label,
    sre_status,
    sre_alert_reason,
    dimensions_json
FROM activity_blocks
ORDER BY end_time DESC, id DESC
LIMIT ?;
"""


def _row_to_dto(row: aiosqlite.Row) -> EpochMetricsDTO:
    """Convert an aiosqlite.Row into an immutable EpochMetricsDTO."""
    return EpochMetricsDTO(
        id=int(row["id"]),
        timestamp_start=float(row["timestamp_start"]),
        timestamp_end=float(row["timestamp_end"]),
        primary_process=str(row["primary_process"]),
        active_seconds=float(row["active_seconds"]),
        micro_pause_count=int(row["micro_pause_count"]),
        mouse_click_count=int(row["mouse_click_count"]),
        scroll_count=int(row["scroll_count"]),
        context_switch_count=int(row["context_switch_count"]),
        dwell_distribution_json=str(row["dwell_distribution_json"]),
        total_keystrokes=int(row["total_keystrokes"]),
        correction_keystrokes=int(row["correction_keystrokes"]),
        iki_count=int(row["iki_count"]),
        iki_sum_ms=float(row["iki_sum_ms"]),
        iki_sum_sq_ms=float(row["iki_sum_sq_ms"]),
    )


def _row_to_activity_block_dto(row: aiosqlite.Row) -> ActivityBlockDTO:
    """Convert an aiosqlite.Row into an immutable ActivityBlockDTO."""
    return ActivityBlockDTO(
        id=int(row["id"]),
        start_time=float(row["start_time"]),
        end_time=float(row["end_time"]),
        duration_seconds=float(row["duration_seconds"]),
        primary_process=str(row["primary_process"]),
        epoch_count=int(row["epoch_count"]),
        duty_cycle=float(row["duty_cycle"]),
        shannon_entropy=float(row["shannon_entropy"]),
        switches_per_minute=float(row["switches_per_minute"]),
        iki_cv=float(row["iki_cv"]),
        correction_ratio=float(row["correction_ratio"]),
        overall_strain_score=float(row["overall_strain_score"]),
        dominant_state_label=str(row["dominant_state_label"]),
        sre_status=str(row["sre_status"]),
        sre_alert_reason=str(row["sre_alert_reason"]),
        dimensions_json=str(row["dimensions_json"]),
    )


class EpochRepository:
    """Async repository for writing and querying 30-second telemetry epochs and activity blocks."""

    def __init__(
        self,
        db_path: Path | str,
        *,
        iki_min_valid_samples: int = DEFAULT_IKI_MIN_VALID_SAMPLES,
    ) -> None:
        self._db_path = Path(db_path)
        self._iki_min_valid_samples = iki_min_valid_samples

    @property
    def db_path(self) -> Path:
        """Database file path managed by this repository."""
        return self._db_path

    async def initialize(self) -> None:
        """Ensure SQLite WAL pragmas, tables, and indexes exist."""
        await init_database(self._db_path)

    def pool_epochs(self, epochs: Sequence[EpochRecordProtocol]) -> PooledTelemetryMetrics:
        """Losslessly pool a sequence of epochs using the configured IKI sample threshold."""
        return pool_epoch_metrics(
            epochs,
            iki_min_valid_samples=self._iki_min_valid_samples,
        )

    async def insert_epoch(self, epoch: EpochRecordProtocol) -> int:
        """Insert a single 30-second epoch record and return its primary key id."""
        async with get_db_connection(self._db_path) as conn:
            cursor = await conn.execute(
                _INSERT_EPOCH_SQL,
                (
                    epoch.timestamp_start,
                    epoch.timestamp_end,
                    epoch.primary_process,
                    epoch.active_seconds,
                    epoch.micro_pause_count,
                    epoch.mouse_click_count,
                    epoch.scroll_count,
                    epoch.context_switch_count,
                    epoch.dwell_distribution_json,
                    epoch.total_keystrokes,
                    epoch.correction_keystrokes,
                    epoch.iki_count,
                    epoch.iki_sum_ms,
                    epoch.iki_sum_sq_ms,
                ),
            )
            await conn.commit()
            return int(cursor.lastrowid or 0)

    async def insert_epochs_batch(self, epochs: Sequence[EpochRecordProtocol]) -> int:
        """Insert a batch of epochs inside a single transaction and return inserted count."""
        if not epochs:
            return 0

        params = [
            (
                e.timestamp_start,
                e.timestamp_end,
                e.primary_process,
                e.active_seconds,
                e.micro_pause_count,
                e.mouse_click_count,
                e.scroll_count,
                e.context_switch_count,
                e.dwell_distribution_json,
                e.total_keystrokes,
                e.correction_keystrokes,
                e.iki_count,
                e.iki_sum_ms,
                e.iki_sum_sq_ms,
            )
            for e in epochs
        ]
        async with get_db_connection(self._db_path) as conn:
            await conn.executemany(_INSERT_EPOCH_SQL, params)
            await conn.commit()
            return len(params)

    async def fetch_epochs_in_range(
        self,
        start_time: float,
        end_time: float,
    ) -> list[EpochMetricsDTO]:
        """Fetch all epochs bounded within [start_time, end_time] ordered chronologically."""
        async with get_db_connection(self._db_path) as conn:
            cursor = await conn.execute(_SELECT_RANGE_SQL, (start_time, end_time))
            rows = await cursor.fetchall()
            return [_row_to_dto(row) for row in rows]

    async def count_epochs(self) -> int:
        """Return total number of rows stored in epoch_metrics_30s."""
        async with get_db_connection(self._db_path) as conn:
            cursor = await conn.execute("SELECT COUNT(*) AS cnt FROM epoch_metrics_30s;")
            row = await cursor.fetchone()
            return int(row["cnt"]) if row is not None else 0

    async def insert_activity_block(self, block: ActivityBlockRecordProtocol) -> int:
        """Insert a sealed activity block record and return its primary key id."""
        async with get_db_connection(self._db_path) as conn:
            cursor = await conn.execute(
                _INSERT_ACTIVITY_BLOCK_SQL,
                (
                    block.start_time,
                    block.end_time,
                    block.duration_seconds,
                    block.primary_process,
                    block.epoch_count,
                    block.duty_cycle,
                    block.shannon_entropy,
                    block.switches_per_minute,
                    block.iki_cv,
                    block.correction_ratio,
                    block.overall_strain_score,
                    block.dominant_state_label,
                    block.sre_status,
                    block.sre_alert_reason,
                    block.dimensions_json,
                ),
            )
            await conn.commit()
            return int(cursor.lastrowid or 0)

    async def fetch_activity_blocks_in_range(
        self,
        start_time: float,
        end_time: float,
    ) -> list[ActivityBlockDTO]:
        """Fetch all activity blocks within [start_time, end_time] ordered chronologically."""
        async with get_db_connection(self._db_path) as conn:
            cursor = await conn.execute(_SELECT_ACTIVITY_BLOCKS_RANGE_SQL, (start_time, end_time))
            rows = await cursor.fetchall()
            return [_row_to_activity_block_dto(row) for row in rows]

    async def fetch_recent_activity_blocks(self, limit: int = 10) -> list[ActivityBlockDTO]:
        """Fetch the most recent N sealed activity blocks ordered newest first."""
        async with get_db_connection(self._db_path) as conn:
            cursor = await conn.execute(_SELECT_RECENT_ACTIVITY_BLOCKS_SQL, (max(1, limit),))
            rows = await cursor.fetchall()
            return [_row_to_activity_block_dto(row) for row in rows]

    async def count_activity_blocks(self) -> int:
        """Return total number of rows stored in activity_blocks."""
        async with get_db_connection(self._db_path) as conn:
            cursor = await conn.execute("SELECT COUNT(*) AS cnt FROM activity_blocks;")
            row = await cursor.fetchone()
            return int(row["cnt"]) if row is not None else 0
