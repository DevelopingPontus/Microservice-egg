"""Unit tests for SQLite WAL initialization and EpochRepository operations."""

import json
from pathlib import Path

from app.storage import (
    EpochMetricsDTO,
    EpochRepository,
    get_db_connection,
    init_database,
    pool_epoch_metrics,
)


def _sample_epoch(
    start: float,
    end: float,
    process: str = "Code.exe",
    scroll_count: int = 5,
    mouse_click_count: int = 2,
) -> EpochMetricsDTO:
    """Create a sample EpochMetricsDTO for persistence tests."""
    return EpochMetricsDTO(
        timestamp_start=start,
        timestamp_end=end,
        primary_process=process,
        active_seconds=22.5,
        micro_pause_count=3,
        mouse_click_count=mouse_click_count,
        scroll_count=scroll_count,
        context_switch_count=1,
        dwell_distribution_json=json.dumps({process: 25.0, "Slack.app": 5.0}),
        total_keystrokes=80,
        correction_keystrokes=6,
        iki_count=12,
        iki_sum_ms=1800.0,
        iki_sum_sq_ms=295000.0,
    )


async def test_init_database_enables_wal_and_creates_index(tmp_path: Path) -> None:
    """Verify init_database sets WAL mode, foreign keys, and creates idx_epochs_time_range."""
    db_file = tmp_path / "test_wal.db"
    await init_database(db_file)

    async with get_db_connection(db_file) as conn:
        cursor = await conn.execute("PRAGMA journal_mode;")
        journal_row = await cursor.fetchone()
        assert journal_row is not None
        assert str(journal_row[0]).lower() == "wal"

        fk_cursor = await conn.execute("PRAGMA foreign_keys;")
        fk_row = await fk_cursor.fetchone()
        assert fk_row is not None
        assert int(fk_row[0]) == 1

        idx_cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_epochs_time_range';"
        )
        idx_row = await idx_cursor.fetchone()
        assert idx_row is not None
        assert idx_row["name"] == "idx_epochs_time_range"


async def test_repository_insert_batch_and_range_query(tmp_path: Path) -> None:
    """Verify single insert, batch insert, empty batch no-op, and range queries."""
    db_file = tmp_path / "epochs.db"
    await init_database(db_file)
    repo = EpochRepository(db_file)

    assert repo.db_path == db_file
    assert await repo.count_epochs() == 0
    assert await repo.insert_epochs_batch([]) == 0

    first_id = await repo.insert_epoch(_sample_epoch(1000.0, 1030.0, scroll_count=8))
    assert first_id == 1
    assert await repo.count_epochs() == 1

    batch = [
        _sample_epoch(1030.0, 1060.0, process="Code.exe", scroll_count=4),
        _sample_epoch(1060.0, 1090.0, process="Firefox.app", scroll_count=12),
        _sample_epoch(1090.0, 1120.0, process="Code.exe", scroll_count=2),
    ]
    inserted = await repo.insert_epochs_batch(batch)
    assert inserted == 3
    assert await repo.count_epochs() == 4

    # Query middle 2 epochs [1030.0, 1090.0]
    window_epochs = await repo.fetch_epochs_in_range(1030.0, 1090.0)
    assert len(window_epochs) == 2
    assert window_epochs[0].timestamp_start == 1030.0
    assert window_epochs[0].scroll_count == 4
    assert window_epochs[1].primary_process == "Firefox.app"
    assert window_epochs[1].scroll_count == 12

    pooled = pool_epoch_metrics(window_epochs)
    assert pooled.epoch_count == 2
    assert pooled.total_scroll_events == 16
    assert pooled.total_mouse_clicks == 4
    assert pooled.is_psychomotor_valid is True
