"""Unit tests for operational configuration constants and DaemonConfig."""

from pathlib import Path

import pytest

from app.config import (
    DEFAULT_DATABASE_PATH,
    EPOCH_DURATION_SECONDS,
    IDLE_EVENT_THRESHOLD_SECONDS,
    IKI_MAX_OUTLIER_MS,
    MICRO_PAUSE_MAX_SECONDS,
    MICRO_PAUSE_MIN_SECONDS,
    MOUSE_MOVE_THROTTLE_SECONDS,
    WINDOW_POLL_INTERVAL_SECONDS,
    DaemonConfig,
)


def test_default_constants_match_spec() -> None:
    """Verify operational constants match Section 5.1 of epoch_telemetry_plan.md."""
    assert EPOCH_DURATION_SECONDS == 30.0
    assert IDLE_EVENT_THRESHOLD_SECONDS == 1.5
    assert MICRO_PAUSE_MIN_SECONDS == 1.0
    assert MICRO_PAUSE_MAX_SECONDS == 5.0
    assert IKI_MAX_OUTLIER_MS == 5000.0
    assert MOUSE_MOVE_THROTTLE_SECONDS == 0.25
    assert WINDOW_POLL_INTERVAL_SECONDS == 0.25
    assert DEFAULT_DATABASE_PATH == "telemetry_epochs.db"


def test_daemon_config_defaults_and_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify DaemonConfig loads defaults and respects environment variable overrides."""
    monkeypatch.delenv("TELEMETRY_DB_PATH", raising=False)
    monkeypatch.delenv("TELEMETRY_EPOCH_SECONDS", raising=False)

    default_cfg = DaemonConfig.from_env()
    assert default_cfg.epoch_duration_seconds == 30.0
    assert default_cfg.database_path == Path("telemetry_epochs.db")
    assert default_cfg.simulate is False

    monkeypatch.setenv("TELEMETRY_DB_PATH", "/tmp/custom_epochs.db")
    monkeypatch.setenv("TELEMETRY_EPOCH_SECONDS", "15.0")

    custom_cfg = DaemonConfig.from_env(simulate=True)
    assert custom_cfg.epoch_duration_seconds == 15.0
    assert custom_cfg.database_path == Path("/tmp/custom_epochs.db")
    assert custom_cfg.simulate is True


def test_daemon_config_rejects_non_positive_epoch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify DaemonConfig raises ValueError for non-positive epoch duration."""
    monkeypatch.setenv("TELEMETRY_EPOCH_SECONDS", "0")
    with pytest.raises(ValueError, match="epoch_duration_seconds must be strictly positive"):
        DaemonConfig.from_env()
