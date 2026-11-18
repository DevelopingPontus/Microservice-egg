"""Operational configuration constants for the cognitive host observability daemon."""

import os
from dataclasses import dataclass

MetricValue = float | int | str | bool

# Sliding window and sampling constants
SLIDING_WINDOW_SECONDS: float = 60.0
EMIT_INTERVAL_SECONDS: float = 2.0
IDLE_EVENT_THRESHOLD_SECONDS: float = 1.5
MICRO_PAUSE_MIN_SECONDS: float = 1.0
MICRO_PAUSE_MAX_SECONDS: float = 5.0
IKI_MIN_OUTLIER_MS: float = 25.0
IKI_MAX_OUTLIER_MS: float = 5000.0
IKI_MIN_VALID_SAMPLES: int = 10
MOUSE_MOVE_THROTTLE_SECONDS: float = 0.25
WINDOW_POLL_INTERVAL_SECONDS: float = 0.25
SESSION_RESET_IDLE_SECONDS: float = 900.0  # 15 min idle resets session uptime

# Active working time and calm telemetry pacing constants
READING_THOUGHT_GRACE_SECONDS: float = 180.0  # 3 min thinking/reading grace credited to active work
AWAY_IDLE_THRESHOLD_SECONDS: float = 180.0  # >3 min gap pauses active work and credits away time
HEARTBEAT_LOG_INTERVAL_SECONDS: float = 60.0  # Calm 60s periodic session heartbeat in Loki

NON_WORK_PROCESS_NAMES: frozenset[str] = frozenset(
    {
        "idle",
        "unknown",
        "loginwindow.app",
        "screensaverengine.app",
        "lockapp.exe",
    }
)

SRE_WARNING_THRESHOLD: float = 0.60
SRE_CRITICAL_THRESHOLD: float = 0.80

DEFAULT_API_HOST: str = "127.0.0.1"
DEFAULT_API_PORT: int = 8765

DEFAULT_OTLP_ENDPOINT: str = "http://127.0.0.1:4317"


@dataclass(frozen=True, slots=True)
class DaemonConfig:
    """Immutable runtime configuration for the cognitive host observability daemon."""

    sliding_window_seconds: float = SLIDING_WINDOW_SECONDS
    emit_interval_seconds: float = EMIT_INTERVAL_SECONDS
    idle_event_threshold_seconds: float = IDLE_EVENT_THRESHOLD_SECONDS
    micro_pause_min_seconds: float = MICRO_PAUSE_MIN_SECONDS
    micro_pause_max_seconds: float = MICRO_PAUSE_MAX_SECONDS
    iki_min_outlier_ms: float = IKI_MIN_OUTLIER_MS
    iki_max_outlier_ms: float = IKI_MAX_OUTLIER_MS
    mouse_move_throttle_seconds: float = MOUSE_MOVE_THROTTLE_SECONDS
    window_poll_interval_seconds: float = WINDOW_POLL_INTERVAL_SECONDS
    session_reset_idle_seconds: float = SESSION_RESET_IDLE_SECONDS
    reading_thought_grace_seconds: float = READING_THOUGHT_GRACE_SECONDS
    away_idle_threshold_seconds: float = AWAY_IDLE_THRESHOLD_SECONDS
    heartbeat_log_interval_seconds: float = HEARTBEAT_LOG_INTERVAL_SECONDS
    simulate: bool = False
    api_host: str = DEFAULT_API_HOST
    api_port: int = DEFAULT_API_PORT
    enable_api: bool = True
    otlp_endpoint: str = DEFAULT_OTLP_ENDPOINT
    enable_otlp: bool = True

    @classmethod
    def from_env(cls, *, simulate: bool = False) -> "DaemonConfig":
        """Build a DaemonConfig overriding defaults from environment variables."""
        api_host_raw = os.environ.get("TELEMETRY_API_HOST", DEFAULT_API_HOST)
        api_port_raw = os.environ.get("TELEMETRY_API_PORT")
        enable_api_raw = os.environ.get("TELEMETRY_ENABLE_API", "1").strip().lower()
        otlp_endpoint_raw = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", DEFAULT_OTLP_ENDPOINT)
        enable_otlp_raw = os.environ.get("TELEMETRY_ENABLE_OTLP", "1").strip().lower()

        api_port = int(api_port_raw) if api_port_raw is not None else DEFAULT_API_PORT
        enable_api = enable_api_raw not in ("0", "false", "no")
        enable_otlp = enable_otlp_raw not in ("0", "false", "no")

        return cls(
            simulate=simulate,
            api_host=api_host_raw,
            api_port=api_port,
            enable_api=enable_api,
            otlp_endpoint=otlp_endpoint_raw,
            enable_otlp=enable_otlp,
        )
