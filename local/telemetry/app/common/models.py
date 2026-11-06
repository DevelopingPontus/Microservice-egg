"""Shared pure-data domain value objects (DTOs) and statistical math.

This module is part of the LCA Crossroads Contract (`app.common`). It must never
import from `intake/`, `output/`, or `service.py`.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.common.config import (
    IKI_MIN_VALID_SAMPLES,
    NON_WORK_PROCESS_NAMES,
)

MetricValue = float | int | str | bool


@runtime_checkable
class TelemetrySampleProtocol(Protocol):
    """Structural contract for an in-memory telemetry sample slice."""

    @property
    def timestamp_start(self) -> float: ...

    @property
    def timestamp_end(self) -> float: ...

    @property
    def primary_process(self) -> str: ...

    @property
    def active_seconds(self) -> float: ...

    @property
    def micro_pause_count(self) -> int: ...

    @property
    def context_switch_count(self) -> int: ...

    @property
    def dwell_distribution(self) -> dict[str, float]: ...

    @property
    def total_keystrokes(self) -> int: ...

    @property
    def correction_keystrokes(self) -> int: ...

    @property
    def iki_count(self) -> int: ...

    @property
    def iki_sum_ms(self) -> float: ...

    @property
    def iki_sum_sq_ms(self) -> float: ...

    @property
    def mouse_click_count(self) -> int: ...

    @property
    def scroll_count(self) -> int: ...

    @property
    def duration_seconds(self) -> float: ...


@dataclass(frozen=True, slots=True)
class TelemetrySample:
    """Immutable in-memory snapshot of hardware and window events."""

    timestamp_start: float
    timestamp_end: float
    primary_process: str
    active_seconds: float
    micro_pause_count: int
    context_switch_count: int
    dwell_distribution: dict[str, float]
    total_keystrokes: int
    correction_keystrokes: int
    iki_count: int
    iki_sum_ms: float
    iki_sum_sq_ms: float
    mouse_click_count: int = 0
    scroll_count: int = 0

    @property
    def duration_seconds(self) -> float:
        """Total elapsed wall-clock seconds covered by this sample."""
        return max(0.0, self.timestamp_end - self.timestamp_start)


@dataclass(frozen=True, slots=True)
class PooledTelemetryMetrics:
    """Statistical telemetry metrics computed across the sliding window."""

    sample_count: int
    total_duration_seconds: float
    total_active_seconds: float
    duty_cycle: float
    total_micro_pauses: int
    total_mouse_clicks: int
    total_scroll_events: int
    total_context_switches: int
    switches_per_minute: float
    merged_dwell_seconds: dict[str, float]
    primary_process: str
    primary_process_ratio: float
    shannon_entropy: float
    total_keystrokes: int
    correction_keystrokes: int
    correction_ratio: float
    iki_count: int
    is_psychomotor_valid: bool
    iki_mean_ms: float
    iki_variance_ms2: float
    iki_std_dev_ms: float
    iki_cv: float


@dataclass(frozen=True, slots=True)
class DimensionEvaluation:
    """Immutable evaluation result emitted by a single scientific dimension."""

    dimension_name: str
    strain_score: float
    state_label: str
    metrics: dict[str, MetricValue]
    blameless_summary: str


@dataclass(frozen=True, slots=True)
class CognitiveStrainReport:
    """Composite 'User-as-a-Server' SRE health evaluation."""

    overall_strain_score: float
    dominant_state_label: str
    sre_status: str
    sre_alert_reason: str
    triggered_dimensions: tuple[str, ...]
    dimension_scores: dict[str, float]


@dataclass(frozen=True, slots=True)
class SchedulerDiagnostics:
    """Privacy-safe operational health metrics for SRE monitoring (/health)."""

    is_running: bool
    samples_emitted_total: int
    window_ticks_total: int
    last_emit_timestamp: float | None


def compute_shannon_entropy(dwell_seconds: Mapping[str, float]) -> float:
    """Compute Shannon entropy H = -sum(p_k * ln(p_k)) over process dwell times."""
    positive_dwells = [sec for sec in dwell_seconds.values() if sec > 0.0]
    total_dwell = sum(positive_dwells)
    if total_dwell <= 0.0 or len(positive_dwells) <= 1:
        return 0.0

    entropy = 0.0
    for sec in positive_dwells:
        prob = sec / total_dwell
        entropy -= prob * math.log(prob)
    return max(0.0, round(entropy, 4))


def merge_dwell_distributions(
    samples: Sequence[TelemetrySampleProtocol],
) -> dict[str, float]:
    """Sum positive per-process dwell times across samples, filtering non-work OS processes."""
    raw_merged: dict[str, float] = {}
    work_merged: dict[str, float] = {}
    for sample in samples:
        for proc, seconds in sample.dwell_distribution.items():
            if seconds > 0.0:
                raw_merged[proc] = raw_merged.get(proc, 0.0) + seconds
                if proc.strip().lower() not in NON_WORK_PROCESS_NAMES:
                    work_merged[proc] = work_merged.get(proc, 0.0) + seconds
    return work_merged if work_merged else raw_merged


def pool_telemetry_samples(
    samples: Sequence[TelemetrySampleProtocol],
    *,
    iki_min_valid_samples: int = IKI_MIN_VALID_SAMPLES,
) -> PooledTelemetryMetrics:
    """Pool sliding window samples into unified mathematical metrics."""
    sample_count = len(samples)
    if sample_count == 0:
        return PooledTelemetryMetrics(
            sample_count=0,
            total_duration_seconds=0.0,
            total_active_seconds=0.0,
            duty_cycle=0.0,
            total_micro_pauses=0,
            total_mouse_clicks=0,
            total_scroll_events=0,
            total_context_switches=0,
            switches_per_minute=0.0,
            merged_dwell_seconds={},
            primary_process="idle",
            primary_process_ratio=0.0,
            shannon_entropy=0.0,
            total_keystrokes=0,
            correction_keystrokes=0,
            correction_ratio=0.0,
            iki_count=0,
            is_psychomotor_valid=False,
            iki_mean_ms=0.0,
            iki_variance_ms2=0.0,
            iki_std_dev_ms=0.0,
            iki_cv=0.0,
        )

    total_duration = sum(s.duration_seconds for s in samples)
    total_active = sum(max(0.0, s.active_seconds) for s in samples)
    duty_cycle = min(1.0, max(0.0, total_active / total_duration)) if total_duration > 0.0 else 0.0

    total_micro_pauses = sum(s.micro_pause_count for s in samples)
    total_mouse_clicks = sum(s.mouse_click_count for s in samples)
    total_scroll_events = sum(s.scroll_count for s in samples)
    total_switches = sum(s.context_switch_count for s in samples)
    effective_rate_duration = max(total_duration, 1.0)
    switches_per_min = (
        (total_switches / (effective_rate_duration / 60.0))
        if effective_rate_duration > 0.0
        else 0.0
    )

    merged_dwell = merge_dwell_distributions(samples)
    total_dwell = sum(merged_dwell.values())
    if merged_dwell and total_dwell > 0.0:
        primary_process = max(merged_dwell.items(), key=lambda item: item[1])[0]
        primary_process_ratio = min(1.0, max(0.0, merged_dwell[primary_process] / total_dwell))
    else:
        primary_process = samples[-1].primary_process
        primary_process_ratio = 0.0

    shannon_entropy = compute_shannon_entropy(merged_dwell)

    total_keys = sum(s.total_keystrokes for s in samples)
    corr_keys = sum(s.correction_keystrokes for s in samples)
    correction_ratio = min(1.0, max(0.0, corr_keys / total_keys)) if total_keys > 0 else 0.0

    total_iki_count = sum(s.iki_count for s in samples)
    is_psychomotor_valid = total_iki_count >= iki_min_valid_samples
    if total_iki_count > 0:
        total_iki_sum = sum(s.iki_sum_ms for s in samples)
        total_iki_sum_sq = sum(s.iki_sum_sq_ms for s in samples)
        iki_mean = total_iki_sum / total_iki_count
        iki_variance = max(0.0, (total_iki_sum_sq / total_iki_count) - (iki_mean * iki_mean))
        iki_std_dev = math.sqrt(iki_variance)
        iki_cv = (iki_std_dev / iki_mean) if iki_mean > 0.0 else 0.0
    else:
        iki_mean = 0.0
        iki_variance = 0.0
        iki_std_dev = 0.0
        iki_cv = 0.0

    return PooledTelemetryMetrics(
        sample_count=sample_count,
        total_duration_seconds=round(total_duration, 4),
        total_active_seconds=round(total_active, 4),
        duty_cycle=round(duty_cycle, 4),
        total_micro_pauses=total_micro_pauses,
        total_mouse_clicks=total_mouse_clicks,
        total_scroll_events=total_scroll_events,
        total_context_switches=total_switches,
        switches_per_minute=round(switches_per_min, 4),
        merged_dwell_seconds=merged_dwell,
        primary_process=primary_process,
        primary_process_ratio=round(primary_process_ratio, 4),
        shannon_entropy=shannon_entropy,
        total_keystrokes=total_keys,
        correction_keystrokes=corr_keys,
        correction_ratio=round(correction_ratio, 4),
        iki_count=total_iki_count,
        is_psychomotor_valid=is_psychomotor_valid,
        iki_mean_ms=round(iki_mean, 2),
        iki_variance_ms2=round(iki_variance, 2),
        iki_std_dev_ms=round(iki_std_dev, 2),
        iki_cv=round(iki_cv, 4),
    )
