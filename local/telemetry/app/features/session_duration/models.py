"""Data models for temporal session duration metrics."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RawTemporalSessionMetrics:
    """Independent raw temporal and session duration metrics in seconds."""

    window_active_seconds: float = 0.0
    window_duration_seconds: float = 0.0
    session_uptime_seconds: float = 0.0
    active_work_seconds: float = 0.0
    away_idle_seconds: float = 0.0
    idle_gap_seconds: float = 0.0
