"""Repository and lossless mathematical pooling for 30-second telemetry epochs."""

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import aiosqlite

from app.storage.database import get_db_connection

DEFAULT_IKI_MIN_VALID_SAMPLES: int = 10


@runtime_checkable
class EpochRecordProtocol(Protocol):
    """Structural contract for any 30-second epoch record persisted or pooled by storage."""

    @property
    def timestamp_start(self) -> float: ...

    @property
    def timestamp_end(self) -> float: ...

    @property
    def primary_process(self) -> str: ...

    @property
    def active_seconds(self) -> float: ...

    @property
    def micro_pause_count(self) -> int: ...

    @property
    def context_switch_count(self) -> int: ...

    @property
    def dwell_distribution_json(self) -> str: ...

    @property
    def total_keystrokes(self) -> int: ...

    @property
    def correction_keystrokes(self) -> int: ...

    @property
    def iki_count(self) -> int: ...

    @property
    def iki_sum_ms(self) -> float: ...

    @property
    def iki_sum_sq_ms(self) -> float: ...

    @property
    def mouse_click_count(self) -> int: ...

    @property
    def scroll_count(self) -> int: ...

    @property
    def duration_seconds(self) -> float: ...

    def parsed_dwell_distribution(self) -> dict[str, float]: ...


@dataclass(frozen=True, slots=True)
class EpochMetricsDTO:
    """Immutable representation of a single 30-second telemetry micro-epoch."""

    timestamp_start: float
    timestamp_end: float
    primary_process: str
    active_seconds: float
    micro_pause_count: int
    context_switch_count: int
    dwell_distribution_json: str
    total_keystrokes: int
    correction_keystrokes: int
    iki_count: int
    iki_sum_ms: float
    iki_sum_sq_ms: float
    mouse_click_count: int = 0
    scroll_count: int = 0
    id: int | None = None

    @property
    def duration_seconds(self) -> float:
        """Total elapsed wall-clock seconds covered by this epoch."""
        return max(0.0, self.timestamp_end - self.timestamp_start)

    def parsed_dwell_distribution(self) -> dict[str, float]:
        """Deserialize dwell_distribution_json into a mapping of process -> seconds."""
        raw = json.loads(self.dwell_distribution_json)
        if not isinstance(raw, dict):
            raise ValueError("dwell_distribution_json must encode a JSON object")
        return {str(proc): float(seconds) for proc, seconds in raw.items()}


@runtime_checkable
class ActivityBlockRecordProtocol(Protocol):
    """Structural contract for any sealed activity block persisted by storage."""

    @property
    def start_time(self) -> float: ...

    @property
    def end_time(self) -> float: ...

    @property
    def duration_seconds(self) -> float: ...

    @property
    def primary_process(self) -> str: ...

    @property
    def epoch_count(self) -> int: ...

    @property
    def duty_cycle(self) -> float: ...

    @property
    def shannon_entropy(self) -> float: ...

    @property
    def switches_per_minute(self) -> float: ...

    @property
    def iki_cv(self) -> float: ...

    @property
    def correction_ratio(self) -> float: ...

    @property
    def overall_strain_score(self) -> float: ...

    @property
    def dominant_state_label(self) -> str: ...

    @property
    def sre_status(self) -> str: ...

    @property
    def sre_alert_reason(self) -> str: ...

    @property
    def dimensions_json(self) -> str: ...


@dataclass(frozen=True, slots=True)
class ActivityBlockDTO:
    """Immutable representation of a sealed cognitive activity block."""

    start_time: float
    end_time: float
    duration_seconds: float
    primary_process: str
    epoch_count: int
    duty_cycle: float
    shannon_entropy: float
    switches_per_minute: float
    iki_cv: float
    correction_ratio: float
    overall_strain_score: float
    dominant_state_label: str
    sre_status: str
    sre_alert_reason: str
    dimensions_json: str
    id: int | None = None

    def parsed_dimensions(self) -> dict[str, Any]:
        """Deserialize dimensions_json into a dictionary of evaluated dimension payloads."""
        raw = json.loads(self.dimensions_json)
        if not isinstance(raw, dict):
            raise ValueError("dimensions_json must encode a JSON object")
        return dict(raw)

    def with_id(self, row_id: int) -> "ActivityBlockDTO":
        """Return a copy of this DTO stamped with its database row id."""
        return replace(self, id=row_id)


@dataclass(frozen=True, slots=True)
class PooledTelemetryMetrics:
    """Losslessly pooled metrics computed across N 30-second micro-epochs."""

    epoch_count: int
    total_duration_seconds: float
    total_active_seconds: float
    duty_cycle: float
    total_micro_pauses: int
    total_mouse_clicks: int
    total_scroll_events: int
    total_context_switches: int
    switches_per_minute: float
    merged_dwell_seconds: dict[str, float]
    primary_process: str
    primary_process_ratio: float
    shannon_entropy: float
    total_keystrokes: int
    correction_keystrokes: int
    correction_ratio: float
    iki_count: int
    is_psychomotor_valid: bool
    iki_mean_ms: float
    iki_variance_ms2: float
    iki_std_dev_ms: float
    iki_cv: float


def merge_dwell_distributions(epochs: Sequence[EpochRecordProtocol]) -> dict[str, float]:
    """Sum positive per-process dwell times across a sequence of epochs."""
    merged: dict[str, float] = {}
    for epoch in epochs:
        for proc, seconds in epoch.parsed_dwell_distribution().items():
            if seconds > 0.0:
                merged[proc] = merged.get(proc, 0.0) + seconds
    return merged


def compute_shannon_entropy(dwell_seconds: Mapping[str, float]) -> float:
    """Compute Shannon entropy H = -sum(p_k * ln(p_k)) over process dwell times."""
    positive_dwells = [sec for sec in dwell_seconds.values() if sec > 0.0]
    total_dwell = sum(positive_dwells)
    if total_dwell <= 0.0 or len(positive_dwells) <= 1:
        return 0.0

    entropy = 0.0
    for sec in positive_dwells:
        prob = sec / total_dwell
        entropy -= prob * math.log(prob)
    return max(0.0, entropy)


def pool_epoch_metrics(
    epochs: Sequence[EpochRecordProtocol],
    *,
    iki_min_valid_samples: int = DEFAULT_IKI_MIN_VALID_SAMPLES,
) -> PooledTelemetryMetrics:
    """Losslessly pool N 30-second epochs into unified 4-dimension telemetry metrics."""
    epoch_count = len(epochs)
    if epoch_count == 0:
        return PooledTelemetryMetrics(
            epoch_count=0,
            total_duration_seconds=0.0,
            total_active_seconds=0.0,
            duty_cycle=0.0,
            total_micro_pauses=0,
            total_mouse_clicks=0,
            total_scroll_events=0,
            total_context_switches=0,
            switches_per_minute=0.0,
            merged_dwell_seconds={},
            primary_process="idle",
            primary_process_ratio=0.0,
            shannon_entropy=0.0,
            total_keystrokes=0,
            correction_keystrokes=0,
            correction_ratio=0.0,
            iki_count=0,
            is_psychomotor_valid=False,
            iki_mean_ms=0.0,
            iki_variance_ms2=0.0,
            iki_std_dev_ms=0.0,
            iki_cv=0.0,
        )

    total_duration = sum(e.duration_seconds for e in epochs)
    total_active = sum(max(0.0, e.active_seconds) for e in epochs)
    duty_cycle = min(1.0, max(0.0, total_active / total_duration)) if total_duration > 0.0 else 0.0

    total_micro_pauses = sum(e.micro_pause_count for e in epochs)
    total_mouse_clicks = sum(e.mouse_click_count for e in epochs)
    total_scroll_events = sum(e.scroll_count for e in epochs)
    total_switches = sum(e.context_switch_count for e in epochs)
    switches_per_min = (total_switches / (total_duration / 60.0)) if total_duration > 0.0 else 0.0

    merged_dwell = merge_dwell_distributions(epochs)
    total_dwell = sum(merged_dwell.values())
    if merged_dwell and total_dwell > 0.0:
        primary_process = max(merged_dwell.items(), key=lambda item: item[1])[0]
        primary_process_ratio = min(1.0, max(0.0, merged_dwell[primary_process] / total_dwell))
    else:
        primary_process = epochs[-1].primary_process
        primary_process_ratio = 0.0

    shannon_entropy = compute_shannon_entropy(merged_dwell)

    total_keys = sum(e.total_keystrokes for e in epochs)
    corr_keys = sum(e.correction_keystrokes for e in epochs)
    correction_ratio = min(1.0, max(0.0, corr_keys / total_keys)) if total_keys > 0 else 0.0

    total_iki_count = sum(e.iki_count for e in epochs)
    is_psychomotor_valid = total_iki_count >= iki_min_valid_samples
    if total_iki_count > 0:
        total_iki_sum = sum(e.iki_sum_ms for e in epochs)
        total_iki_sum_sq = sum(e.iki_sum_sq_ms for e in epochs)
        iki_mean = total_iki_sum / total_iki_count
        iki_variance = max(0.0, (total_iki_sum_sq / total_iki_count) - (iki_mean * iki_mean))
        iki_std_dev = math.sqrt(iki_variance)
        iki_cv = (iki_std_dev / iki_mean) if iki_mean > 0.0 else 0.0
    else:
        iki_mean = 0.0
        iki_variance = 0.0
        iki_std_dev = 0.0
        iki_cv = 0.0

    return PooledTelemetryMetrics(
        epoch_count=epoch_count,
        total_duration_seconds=total_duration,
        total_active_seconds=total_active,
        duty_cycle=duty_cycle,
        total_micro_pauses=total_micro_pauses,
        total_mouse_clicks=total_mouse_clicks,
        total_scroll_events=total_scroll_events,
        total_context_switches=total_switches,
        switches_per_minute=switches_per_min,
        merged_dwell_seconds=merged_dwell,
        primary_process=primary_process,
        primary_process_ratio=primary_process_ratio,
        shannon_entropy=shannon_entropy,
        total_keystrokes=total_keys,
        correction_keystrokes=corr_keys,
        correction_ratio=correction_ratio,
        iki_count=total_iki_count,
        is_psychomotor_valid=is_psychomotor_valid,
        iki_mean_ms=iki_mean,
        iki_variance_ms2=iki_variance,
        iki_std_dev_ms=iki_std_dev,
        iki_cv=iki_cv,
    )


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
    """Async repository for writing and querying 30-second telemetry epochs."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)

    @property
    def db_path(self) -> Path:
        """Database file path managed by this repository."""
        return self._db_path

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
