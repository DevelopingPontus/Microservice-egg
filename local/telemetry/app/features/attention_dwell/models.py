"""Data models for attention and window dwell metrics."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RawAttentionWindowMetrics:
    """Independent raw window-dwell and attentional dispersion metrics (bits, seconds, counts)."""

    shannon_entropy_bits: float = 0.0
    merged_dwell_seconds: dict[str, float] = field(default_factory=dict)
    primary_process: str = "idle"
    primary_process_dwell_seconds: float = 0.0
    distinct_processes_count: int = 0
    context_switches: int = 0
