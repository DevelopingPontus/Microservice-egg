"""Shared pure-data domain value objects (DTOs) and lossless epoch pooling math.

This module is part of the LCA Crossroads Contract (`app.common`). It must never
import from `intake/`, `storage/`, `output/`, or `service.py`.
"""

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol, runtime_checkable

from app.common.config import IKI_MIN_VALID_SAMPLES

MetricValue = float | int | str | bool


@runtime_checkable
class EpochRecordProtocol(Protocol):
    """Structural contract for any 30-second epoch record persisted or pooled."""

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
    def dwell_distribution_json(self) -> str: ...

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

    def parsed_dwell_distribution(self) -> dict[str, float]: ...


@dataclass(frozen=True, slots=True)
class EpochSnapshot:
    """Immutable 30-second telemetry micro-epoch snapshot."""

    timestamp_start: float
    timestamp_end: float
    primary_process: str
    active_seconds: float
    micro_pause_count: int
    context_switch_count: int
    dwell_distribution_json: str
    total_keystrokes: int
    correction_keystrokes: int
    iki_count: int
    iki_sum_ms: float
    iki_sum_sq_ms: float
    mouse_click_count: int = 0
    scroll_count: int = 0
    id: int | None = None

    @property
    def duration_seconds(self) -> float:
        """Total elapsed wall-clock seconds covered by this epoch."""
        return max(0.0, self.timestamp_end - self.timestamp_start)

    def parsed_dwell_distribution(self) -> dict[str, float]:
        """Deserialize dwell_distribution_json into a mapping of process -> seconds."""
        raw = json.loads(self.dwell_distribution_json)
        if not isinstance(raw, dict):
            raise ValueError("dwell_distribution_json must encode a JSON object")
        return {str(proc): float(seconds) for proc, seconds in raw.items()}

    def with_id(self, row_id: int) -> "EpochSnapshot":
        """Return a copy of this snapshot stamped with its persisted database id."""
        return replace(self, id=row_id)


# Canonical alias so both EpochSnapshot and EpochMetricsDTO refer to the exact same type.
EpochMetricsDTO = EpochSnapshot


@runtime_checkable
class ActivityBlockRecordProtocol(Protocol):
    """Structural contract for any sealed activity block persisted or queried."""

    @property
    def start_time(self) -> float: ...

    @property
    def end_time(self) -> float: ...

    @property
    def duration_seconds(self) -> float: ...

    @property
    def primary_process(self) -> str: ...

    @property
    def epoch_count(self) -> int: ...

    @property
    def duty_cycle(self) -> float: ...

    @property
    def shannon_entropy(self) -> float: ...

    @property
    def switches_per_minute(self) -> float: ...

    @property
    def iki_cv(self) -> float: ...

    @property
    def correction_ratio(self) -> float: ...

    @property
    def overall_strain_score(self) -> float: ...

    @property
    def dominant_state_label(self) -> str: ...

    @property
    def sre_status(self) -> str: ...

    @property
    def sre_alert_reason(self) -> str: ...

    @property
    def dimensions_json(self) -> str: ...


@dataclass(frozen=True, slots=True)
class ActivityBlockDTO:
    """Immutable representation of a sealed cognitive activity block."""

    start_time: float
    end_time: float
    duration_seconds: float
    primary_process: str
    epoch_count: int
    duty_cycle: float
    shannon_entropy: float
    switches_per_minute: float
    iki_cv: float
    correction_ratio: float
    overall_strain_score: float
    dominant_state_label: str
    sre_status: str
    sre_alert_reason: str
    dimensions_json: str
    id: int | None = None

    def parsed_dimensions(self) -> dict[str, Any]:
        """Deserialize dimensions_json into a dictionary of evaluated dimension payloads."""
        raw = json.loads(self.dimensions_json)
        if not isinstance(raw, dict):
            raise ValueError("dimensions_json must encode a JSON object")
        return dict(raw)

    def with_id(self, row_id: int) -> "ActivityBlockDTO":
        """Return a copy of this block stamped with its persisted database row id."""
        return replace(self, id=row_id)


# Canonical alias so SealedActivityBlock and ActivityBlockDTO refer to the exact same type.
SealedActivityBlock = ActivityBlockDTO


@dataclass(frozen=True, slots=True)
class PooledTelemetryMetrics:
    """Losslessly pooled metrics computed across N 30-second micro-epochs."""

    epoch_count: int
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
class SchedulerDiagnostics:
    """Privacy-safe operational health metrics for SRE monitoring (/health & Prometheus)."""

    is_running: bool
    epochs_flushed_total: int
    window_ticks_total: int
    last_flush_duration_ms: float
    last_flush_timestamp: float | None


@dataclass(frozen=True, slots=True)
class DailySummaryPayload:
    """Aggregated daily cognitive telemetry and SRE health snapshot."""

    day_start_timestamp: float
    day_end_timestamp: float
    epochs_count: int
    blocks_count: int
    excursions_absorbed_total: int
    pooled_metrics: PooledTelemetryMetrics
    overall_strain_score: float
    dominant_state_label: str
    sre_status: str
    sre_alert_reason: str
    triggered_dimensions: tuple[str, ...]
    dimensions: dict[str, DimensionEvaluation]
    sre_status_breakdown: dict[str, int]


def merge_dwell_distributions(epochs: Sequence[EpochRecordProtocol]) -> dict[str, float]:
    """Sum positive per-process dwell times across a sequence of epochs."""
    merged: dict[str, float] = {}
    for epoch in epochs:
        for proc, seconds in epoch.parsed_dwell_distribution().items():
            if seconds > 0.0:
                merged[proc] = merged.get(proc, 0.0) + seconds
    return merged


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
    return max(0.0, entropy)


def pool_epoch_metrics(
    epochs: Sequence[EpochRecordProtocol],
    *,
    iki_min_valid_samples: int = IKI_MIN_VALID_SAMPLES,
) -> PooledTelemetryMetrics:
    """Losslessly pool N 30-second epochs into unified 4-dimension telemetry metrics."""
    epoch_count = len(epochs)
    if epoch_count == 0:
        return PooledTelemetryMetrics(
            epoch_count=0,
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

    total_duration = sum(e.duration_seconds for e in epochs)
    total_active = sum(max(0.0, e.active_seconds) for e in epochs)
    duty_cycle = min(1.0, max(0.0, total_active / total_duration)) if total_duration > 0.0 else 0.0

    total_micro_pauses = sum(e.micro_pause_count for e in epochs)
    total_mouse_clicks = sum(e.mouse_click_count for e in epochs)
    total_scroll_events = sum(e.scroll_count for e in epochs)
    total_switches = sum(e.context_switch_count for e in epochs)
    switches_per_min = (total_switches / (total_duration / 60.0)) if total_duration > 0.0 else 0.0

    merged_dwell = merge_dwell_distributions(epochs)
    total_dwell = sum(merged_dwell.values())
    if merged_dwell and total_dwell > 0.0:
        primary_process = max(merged_dwell.items(), key=lambda item: item[1])[0]
        primary_process_ratio = min(1.0, max(0.0, merged_dwell[primary_process] / total_dwell))
    else:
        primary_process = epochs[-1].primary_process
        primary_process_ratio = 0.0

    shannon_entropy = compute_shannon_entropy(merged_dwell)

    total_keys = sum(e.total_keystrokes for e in epochs)
    corr_keys = sum(e.correction_keystrokes for e in epochs)
    correction_ratio = min(1.0, max(0.0, corr_keys / total_keys)) if total_keys > 0 else 0.0

    total_iki_count = sum(e.iki_count for e in epochs)
    is_psychomotor_valid = total_iki_count >= iki_min_valid_samples
    if total_iki_count > 0:
        total_iki_sum = sum(e.iki_sum_ms for e in epochs)
        total_iki_sum_sq = sum(e.iki_sum_sq_ms for e in epochs)
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
        epoch_count=epoch_count,
        total_duration_seconds=total_duration,
        total_active_seconds=total_active,
        duty_cycle=duty_cycle,
        total_micro_pauses=total_micro_pauses,
        total_mouse_clicks=total_mouse_clicks,
        total_scroll_events=total_scroll_events,
        total_context_switches=total_switches,
        switches_per_minute=switches_per_min,
        merged_dwell_seconds=merged_dwell,
        primary_process=primary_process,
        primary_process_ratio=primary_process_ratio,
        shannon_entropy=shannon_entropy,
        total_keystrokes=total_keys,
        correction_keystrokes=corr_keys,
        correction_ratio=correction_ratio,
        iki_count=total_iki_count,
        is_psychomotor_valid=is_psychomotor_valid,
        iki_mean_ms=iki_mean,
        iki_variance_ms2=iki_variance,
        iki_std_dev_ms=iki_std_dev,
        iki_cv=iki_cv,
    )
