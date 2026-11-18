"""Data models for keystroke timing metrics."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RawKeystrokeTimingMetrics:
    """Independent raw keystroke timing metrics in native ms and counts (no normalization)."""

    iki_values_ms: tuple[float, ...] = ()
    hold_times_ms: tuple[float, ...] = ()
    flight_times_ms: tuple[float, ...] = ()
    iki_count: int = 0
    iki_mean_ms: float = 0.0
    iki_std_dev_ms: float = 0.0
    iki_mad_ms: float = 0.0
    hold_time_median_ms: float = 0.0
    flight_time_median_ms: float = 0.0
    total_keystrokes: int = 0
