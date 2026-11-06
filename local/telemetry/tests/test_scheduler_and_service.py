"""Unit and integration tests for TelemetryService and CLI runner."""

import asyncio

import pytest
from run import main as daemon_main

from app.common import DaemonConfig
from app.service import TelemetryService, build_arg_parser, run_from_cli


async def test_telemetry_service_bounded_run() -> None:
    """Verify TelemetryService runs bounded time in simulation mode without errors."""
    config = DaemonConfig(
        sliding_window_seconds=2.0,
        emit_interval_seconds=0.05,
        window_poll_interval_seconds=0.02,
        simulate=True,
        enable_api=False,
        enable_otlp=False,
    )
    service = TelemetryService(config)

    diag = await service.run(max_duration_seconds=0.15, install_signals=False)
    assert diag.is_running is False
    assert diag.window_ticks_total >= 3
    assert diag.samples_emitted_total >= 1
    assert service.buffer.lifetime_keystrokes == 12


async def test_telemetry_service_graceful_stop() -> None:
    """Verify requesting stop gracefully halts the service."""
    config = DaemonConfig(
        sliding_window_seconds=10.0,
        emit_interval_seconds=1.0,
        window_poll_interval_seconds=0.02,
        simulate=True,
        enable_api=False,
        enable_otlp=False,
    )
    service = TelemetryService(config)

    async def trigger_stop() -> None:
        await asyncio.sleep(0.05)
        service.request_stop()

    stopper = asyncio.create_task(trigger_stop())
    diag = await service.run(install_signals=False)
    await stopper

    assert diag.is_running is False


async def test_cli_runner_end_to_end() -> None:
    """Verify run_from_cli parses arguments and runs simulation."""
    parser = build_arg_parser()
    parsed = parser.parse_args(
        [
            "--simulate",
            "--no-api",
            "--no-otlp",
            "--duration-seconds",
            "0.08",
        ]
    )
    assert parsed.simulate is True
    assert parsed.no_api is True
    assert parsed.no_otlp is True

    diag = await run_from_cli(
        [
            "--simulate",
            "--no-api",
            "--no-otlp",
            "--duration-seconds",
            "0.08",
        ]
    )
    assert diag.window_ticks_total >= 1


def test_run_daemon_main_entry_point(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify run_daemon.main runs bounded simulation and returns 0."""
    exit_code = daemon_main(
        [
            "--simulate",
            "--no-api",
            "--no-otlp",
            "--duration-seconds",
            "0.06",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "EGG telemetry daemon exited cleanly" in captured.out
