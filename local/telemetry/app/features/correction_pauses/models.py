"""Data models for correction and pause metrics."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RawCorrectionPauseMetrics:
    """Independent raw correction and typing-pause metrics in native ms and counts."""

    pre_correction_pauses_ms: tuple[float, ...] = ()
    post_correction_pauses_ms: tuple[float, ...] = ()
    pre_correction_pause_median_ms: float = 0.0
    post_correction_pause_median_ms: float = 0.0
    correction_keystrokes: int = 0
    micro_pauses_count: int = 0
    pauses_gt_2s_count: int = 0
    burst_count: int = 0
