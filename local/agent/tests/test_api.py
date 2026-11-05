"""Tests for the localhost FastAPI gateway (127.0.0.1:8765), routes, and loopback invariants."""

import json
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from app.common import DaemonConfig, EpochSnapshot
from app.output.api import (
    PROMETHEUS_CONTENT_TYPE,
    build_uvicorn_config,
    create_uvicorn_server,
    validate_loopback_host,
    validate_port,
)
from app.service import TelemetryService


def _make_epoch(
    start: float,
    end: float,
    *,
    process: str = "Code.exe",
    active_seconds: float = 24.0,
    switches: int = 1,
    keystrokes: int = 80,
    corrections: int = 2,
    iki_count: int = 60,
    iki_sum_ms: float = 9600.0,
    iki_sum_sq_ms: float = 1650000.0,
) -> EpochSnapshot:
    """Create a deterministic EpochSnapshot for API route testing."""
    return EpochSnapshot(
        timestamp_start=start,
        timestamp_end=end,
        primary_process=process,
        active_seconds=active_seconds,
        micro_pause_count=2,
        mouse_click_count=3,
        scroll_count=4,
        context_switch_count=switches,
        dwell_distribution_json=json.dumps({process: end - start}),
        total_keystrokes=keystrokes,
        correction_keystrokes=corrections,
        iki_count=iki_count,
        iki_sum_ms=iki_sum_ms,
        iki_sum_sq_ms=iki_sum_sq_ms,
    )


def test_loopback_host_validation_rejects_non_loopback() -> None:
    """API gateway must strictly reject 0.0.0.0 or public interface bindings."""
    assert validate_loopback_host("127.0.0.1") == "127.0.0.1"
    assert validate_loopback_host("localhost") == "localhost"
    assert validate_loopback_host("::1") == "::1"

    with pytest.raises(ValueError, match="Privacy invariant violation"):
        validate_loopback_host("0.0.0.0")

    with pytest.raises(ValueError, match="Privacy invariant violation"):
        validate_loopback_host("192.168.1.50")


def test_api_port_and_uvicorn_config(tmp_path: Path) -> None:
    """Verify validate_port and build_uvicorn_config enforce loopback and port bounds."""
    config = DaemonConfig(database_path=tmp_path / "api_cfg.db", simulate=True)
    service = TelemetryService(config)

    assert service.api_host == "127.0.0.1"
    assert service.api_port == 8765

    uvi_cfg = build_uvicorn_config(service.api_app, host=service.api_host, port=service.api_port)
    assert uvi_cfg.host == "127.0.0.1"
    assert uvi_cfg.port == 8765

    uvi_server = create_uvicorn_server(
        service.api_app, host=service.api_host, port=service.api_port
    )
    assert uvi_server.config.host == "127.0.0.1"

    with pytest.raises(ValueError, match="API port must be between"):
        validate_port(70000)


async def test_health_status_and_prometheus_metrics_endpoints(tmp_path: Path) -> None:
    """Verify /health, /api/v1/status, and /metrics against a live TelemetryService."""
    db_path = tmp_path / "api_health.db"
    config = DaemonConfig(database_path=db_path, simulate=True)
    service = TelemetryService(config)
    await service.repository.initialize()

    transport = ASGITransport(app=service.api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
        # 1. /health probe
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200
        health_data = health_resp.json()
        assert health_data["status"] == "ok"
        assert health_data["service"] == "egg-local-agent"
        assert health_data["scheduler_running"] is False
        assert health_data["epochs_flushed_total"] == 0

        # 2. /api/v1/status before any epochs
        status_resp = await client.get("/api/v1/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["status"] == "ok"
        assert status_data["chunker"]["active_primary_process"] is None
        assert status_data["chunker"]["blocks_sealed_total"] == 0

        # 3. /metrics Prometheus exposition
        metrics_resp = await client.get("/metrics")
        assert metrics_resp.status_code == 200
        assert metrics_resp.headers["content-type"] == PROMETHEUS_CONTENT_TYPE
        assert "egg_epochs_flushed_total" in metrics_resp.text


async def test_blocks_and_daily_summary_routes_with_sealed_blocks(tmp_path: Path) -> None:
    """Verify /api/v1/blocks (recent & range) and /api/v1/summary/today after sealing blocks."""
    db_path = tmp_path / "api_blocks.db"
    config = DaemonConfig(database_path=db_path, simulate=True)
    service = TelemetryService(config)
    await service.repository.initialize()

    base_ts = 1762250400.0  # Fixed afternoon timestamp

    # Persist and ingest 3 active coding epochs (0..90s), then 1 transient Slack check (90..120s),
    # then return to Code.exe (120..150s), then 3 idle epochs (150..240s) to seal the block.
    epochs = [
        _make_epoch(base_ts + 0.0, base_ts + 30.0, process="Code.exe"),
        _make_epoch(base_ts + 30.0, base_ts + 60.0, process="Code.exe"),
        _make_epoch(base_ts + 60.0, base_ts + 90.0, process="Code.exe"),
        _make_epoch(base_ts + 90.0, base_ts + 120.0, process="Slack.app", active_seconds=8.0),
        _make_epoch(base_ts + 120.0, base_ts + 150.0, process="Code.exe"),
        _make_epoch(
            base_ts + 150.0,
            base_ts + 180.0,
            process="idle",
            active_seconds=0.0,
            keystrokes=0,
            corrections=0,
            iki_count=0,
            iki_sum_ms=0.0,
            iki_sum_sq_ms=0.0,
        ),
        _make_epoch(
            base_ts + 180.0,
            base_ts + 210.0,
            process="idle",
            active_seconds=0.0,
            keystrokes=0,
            corrections=0,
            iki_count=0,
            iki_sum_ms=0.0,
            iki_sum_sq_ms=0.0,
        ),
        _make_epoch(
            base_ts + 210.0,
            base_ts + 240.0,
            process="idle",
            active_seconds=0.0,
            keystrokes=0,
            corrections=0,
            iki_count=0,
            iki_sum_ms=0.0,
            iki_sum_sq_ms=0.0,
        ),
    ]

    for ep in epochs:
        row_id = await service.repository.insert_epoch(ep)
        await service.chunker.ingest_epoch(ep.with_id(row_id))

    transport = ASGITransport(app=service.api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
        # Recent blocks query
        blocks_resp = await client.get("/api/v1/blocks?limit=10")
        assert blocks_resp.status_code == 200
        blocks_payload = blocks_resp.json()
        assert blocks_payload["count"] == 1
        block = blocks_payload["blocks"][0]
        assert block["primary_process"] == "Code.exe"
        assert block["epoch_count"] == 5
        assert block["duration_seconds"] == 150.0
        assert "temporal_dynamics" in block["dimensions"]
        assert "attentional_fragmentation" in block["dimensions"]
        assert "psychomotor_mechanics" in block["dimensions"]
        assert "circadian_load" in block["dimensions"]

        # Time-range blocks query
        range_resp = await client.get(
            f"/api/v1/blocks?start={base_ts - 10.0}&end={base_ts + 300.0}"
        )
        assert range_resp.status_code == 200
        assert range_resp.json()["count"] == 1

        # Validation error when only start or end is provided
        invalid_half_range = await client.get(f"/api/v1/blocks?start={base_ts}")
        assert invalid_half_range.status_code == 422

        # Validation error when start > end
        invalid_inverted = await client.get(f"/api/v1/blocks?start={base_ts + 100.0}&end={base_ts}")
        assert invalid_inverted.status_code == 422

        # Daily summary for the reference timestamp
        summary_resp = await client.get(
            f"/api/v1/summary/today?reference_timestamp={base_ts + 60.0}"
        )
        assert summary_resp.status_code == 200
        summary = summary_resp.json()
        assert summary["epochs_count"] == 8
        assert summary["blocks_count"] == 1
        assert summary["excursions_absorbed_total"] == 1
        assert summary["primary_process"] == "Code.exe"
        assert summary["is_psychomotor_valid"] is True
        assert set(summary["dimensions"].keys()) == {
            "temporal_dynamics",
            "attentional_fragmentation",
            "psychomotor_mechanics",
            "circadian_load",
        }

        # Empty daily summary for a future day with zero epochs
        empty_summary_resp = await client.get(
            f"/api/v1/summary/today?reference_timestamp={base_ts + 86400.0 * 10}"
        )
        assert empty_summary_resp.status_code == 200
        empty_summary = empty_summary_resp.json()
        assert empty_summary["epochs_count"] == 0
        assert empty_summary["blocks_count"] == 0
        assert empty_summary["dominant_state_label"] == "idle_day"
        assert empty_summary["sre_status"] == "nominal"
        assert empty_summary["dimensions"] == {}


async def test_service_run_without_api_flag(tmp_path: Path) -> None:
    """Verify TelemetryService.run(enable_api=False) runs cleanly without binding a port."""
    config = DaemonConfig(
        epoch_duration_seconds=0.1,
        window_poll_interval_seconds=0.05,
        database_path=tmp_path / "no_api.db",
        simulate=True,
        enable_api=False,
    )
    service = TelemetryService(config)
    flushed = await service.run(max_duration_seconds=0.15, install_signals=False)
    assert flushed is not None
    assert service.diagnostics().epochs_flushed_total >= 1
