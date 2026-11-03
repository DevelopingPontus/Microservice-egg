"""Unit and integration tests for EpochScheduler, TelemetryService, and CLI runner."""

import asyncio
from pathlib import Path

import pytest
from run_daemon import main as daemon_main

from app.collectors.input_listener import SyntheticInputListener
from app.collectors.window_resolver import SyntheticWindowResolver
from app.config import DaemonConfig
from app.engine.buffer import EpochBuffer
from app.engine.scheduler import EpochScheduler
from app.service import TelemetryService, build_arg_parser, run_from_cli
from app.storage.database import init_database
from app.storage.repository import EpochMetricsDTO, EpochRepository


def test_scheduler_rejects_non_positive_intervals(tmp_path: Path) -> None:
    """EpochScheduler must reject zero or negative epoch or poll intervals."""
    buffer = EpochBuffer()
    repo = EpochRepository(tmp_path / "invalid.db")
    resolver = SyntheticWindowResolver()

    with pytest.raises(ValueError, match="epoch_duration_seconds"):
        EpochScheduler(
            buffer=buffer,
            repository=repo,
            window_resolver=resolver,
            epoch_duration_seconds=0.0,
        )

    with pytest.raises(ValueError, match="window_poll_interval_seconds"):
        EpochScheduler(
            buffer=buffer,
            repository=repo,
            window_resolver=resolver,
            window_poll_interval_seconds=-0.1,
        )


def test_daemon_config_from_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """DaemonConfig.from_env must honor TELEMETRY_DB_PATH and TELEMETRY_EPOCH_SECONDS."""
    custom_db = tmp_path / "env_custom.db"
    monkeypatch.setenv("TELEMETRY_DB_PATH", str(custom_db))
    monkeypatch.setenv("TELEMETRY_EPOCH_SECONDS", "15.0")

    cfg = DaemonConfig.from_env(simulate=True)
    assert cfg.database_path == custom_db
    assert cfg.epoch_duration_seconds == 15.0
    assert cfg.simulate is True

    monkeypatch.setenv("TELEMETRY_EPOCH_SECONDS", "0")
    with pytest.raises(ValueError, match="epoch_duration_seconds"):
        DaemonConfig.from_env()


async def test_scheduler_poll_and_flush_with_async_callback(tmp_path: Path) -> None:
    """poll_window_once and flush_now must persist epochs and invoke async callbacks."""
    db_path = tmp_path / "scheduler_callback.db"
    await init_database(db_path)

    buffer = EpochBuffer()
    repo = EpochRepository(db_path)
    resolver = SyntheticWindowResolver(schedule=[("Code.exe", 2), ("Firefox.app", 1)])
    flushed_dtos: list[EpochMetricsDTO] = []

    async def on_flushed(dto: EpochMetricsDTO) -> None:
        await asyncio.sleep(0.001)
        flushed_dtos.append(dto)

    scheduler = EpochScheduler(
        buffer=buffer,
        repository=repo,
        window_resolver=resolver,
        epoch_duration_seconds=1.0,
        window_poll_interval_seconds=0.25,
        on_epoch_flushed=on_flushed,
    )

    assert scheduler.poll_window_once(0.25) == "Code.exe"
    assert scheduler.poll_window_once(0.25) == "Code.exe"
    assert scheduler.poll_window_once(0.25) == "Firefox.app"

    persisted = await scheduler.flush_now()
    assert persisted.id == 1
    assert persisted.primary_process == "Code.exe"
    assert persisted.context_switch_count == 1
    assert len(flushed_dtos) == 1

    diag = scheduler.diagnostics()
    assert diag.is_running is False
    assert diag.epochs_flushed_total == 1
    assert diag.window_ticks_total == 3
    assert diag.last_flush_timestamp is not None
    assert diag.last_flush_duration_ms >= 0.0


async def test_scheduler_run_periodic_flushes_in_simulate_mode(tmp_path: Path) -> None:
    """EpochScheduler.run must emit synthetic bursts, poll windows, and flush epochs."""
    db_path = tmp_path / "scheduler_run.db"
    await init_database(db_path)

    buffer = EpochBuffer()
    repo = EpochRepository(db_path)
    listener = SyntheticInputListener(buffer)
    listener.start()
    resolver = SyntheticWindowResolver(schedule=[("Code.exe", 10)])
    sync_callbacks: list[int] = []

    scheduler = EpochScheduler(
        buffer=buffer,
        repository=repo,
        window_resolver=resolver,
        input_listener=listener,
        epoch_duration_seconds=0.08,
        window_poll_interval_seconds=0.02,
        on_epoch_flushed=lambda dto: sync_callbacks.append(dto.id or 0),
    )

    await scheduler.run(max_duration_seconds=0.20)
    listener.stop()

    diag = scheduler.diagnostics()
    assert diag.epochs_flushed_total >= 1
    assert diag.window_ticks_total >= 2
    assert len(sync_callbacks) == diag.epochs_flushed_total

    stored_count = await repo.count_epochs()
    assert stored_count == diag.epochs_flushed_total
    epochs = await repo.fetch_epochs_in_range(0.0, float("inf"))
    assert epochs[0].total_keystrokes == 12
    assert epochs[0].mouse_click_count == 1
    assert epochs[0].scroll_count == 3


async def test_telemetry_service_graceful_stop_flushes_inflight_epoch(tmp_path: Path) -> None:
    """Stopping TelemetryService mid-epoch must flush partial in-flight data to SQLite WAL."""
    db_path = tmp_path / "service_graceful.db"
    config = DaemonConfig(
        epoch_duration_seconds=10.0,  # Long epoch so only shutdown flush triggers
        window_poll_interval_seconds=0.02,
        database_path=db_path,
        simulate=True,
    )
    service = TelemetryService(config)

    assert service.config == config
    assert service.buffer is not None
    assert service.repository.db_path == db_path
    assert service.scheduler is not None

    async def stop_shortly() -> None:
        await asyncio.sleep(0.06)
        service.request_stop()

    stopper = asyncio.create_task(stop_shortly())
    shutdown_dto = await service.run()
    await stopper

    assert shutdown_dto is not None
    assert shutdown_dto.id == 1
    assert shutdown_dto.total_keystrokes == 12
    assert await service.repository.count_epochs() == 1
    assert service.diagnostics().epochs_flushed_total == 1


async def test_cli_runner_end_to_end(tmp_path: Path) -> None:
    """run_from_cli must parse flags, execute bounded simulation, and persist rows."""
    db_path = tmp_path / "cli_smoke.db"
    parser = build_arg_parser()
    parsed = parser.parse_args(
        [
            "--simulate",
            "--duration-seconds",
            "0.09",
            "--epoch-seconds",
            "0.04",
            "--db-path",
            str(db_path),
        ]
    )
    assert parsed.simulate is True
    assert parsed.db_path == db_path

    diag = await run_from_cli(
        [
            "--simulate",
            "--duration-seconds",
            "0.09",
            "--epoch-seconds",
            "0.04",
            "--db-path",
            str(db_path),
        ]
    )
    # Periodic flushes plus final shutdown flush
    assert diag.epochs_flushed_total >= 2
    repo = EpochRepository(db_path)
    assert await repo.count_epochs() == diag.epochs_flushed_total


def test_run_daemon_main_entry_point(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """run_daemon.main must execute a bounded --simulate run and return exit code 0."""
    db_path = tmp_path / "main_entry.db"
    exit_code = daemon_main(
        [
            "--simulate",
            "--duration-seconds",
            "0.07",
            "--epoch-seconds",
            "0.03",
            "--db-path",
            str(db_path),
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "EGG telemetry daemon exited cleanly" in captured.out
