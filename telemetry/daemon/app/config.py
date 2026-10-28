"""Operational configuration constants for the 30-second epoch telemetry daemon."""

import os
from dataclasses import dataclass
from pathlib import Path

# Default operational constants per Section 5.1 of epoch_telemetry_plan.md
EPOCH_DURATION_SECONDS: float = 30.0
IDLE_EVENT_THRESHOLD_SECONDS: float = 1.5
MICRO_PAUSE_MIN_SECONDS: float = 1.0
MICRO_PAUSE_MAX_SECONDS: float = 5.0
IKI_MAX_OUTLIER_MS: float = 5000.0
MOUSE_MOVE_THROTTLE_SECONDS: float = 0.25
WINDOW_POLL_INTERVAL_SECONDS: float = 0.25
DEFAULT_DATABASE_PATH: str = "telemetry_epochs.db"


@dataclass(frozen=True, slots=True)
class DaemonConfig:
    """Immutable runtime configuration for the telemetry ingestion daemon."""

    epoch_duration_seconds: float = EPOCH_DURATION_SECONDS
    idle_event_threshold_seconds: float = IDLE_EVENT_THRESHOLD_SECONDS
    micro_pause_min_seconds: float = MICRO_PAUSE_MIN_SECONDS
    micro_pause_max_seconds: float = MICRO_PAUSE_MAX_SECONDS
    iki_max_outlier_ms: float = IKI_MAX_OUTLIER_MS
    mouse_move_throttle_seconds: float = MOUSE_MOVE_THROTTLE_SECONDS
    window_poll_interval_seconds: float = WINDOW_POLL_INTERVAL_SECONDS
    database_path: Path = Path(DEFAULT_DATABASE_PATH)
    simulate: bool = False

    @classmethod
    def from_env(cls, *, simulate: bool = False) -> "DaemonConfig":
        """Build a DaemonConfig overriding defaults from environment variables."""
        db_path_raw = os.environ.get("TELEMETRY_DB_PATH", DEFAULT_DATABASE_PATH)
        epoch_sec_raw = os.environ.get("TELEMETRY_EPOCH_SECONDS")
        epoch_duration = (
            float(epoch_sec_raw) if epoch_sec_raw is not None else EPOCH_DURATION_SECONDS
        )
        if epoch_duration <= 0.0:
            raise ValueError("epoch_duration_seconds must be strictly positive")

        return cls(
            epoch_duration_seconds=epoch_duration,
            database_path=Path(db_path_raw),
            simulate=simulate,
        )
