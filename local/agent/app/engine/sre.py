"""DevOps/SRE 'User-as-a-Server' health evaluator, JSON event logger, and Prometheus metrics."""

import json
import logging
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest

from app.engine.protocols import (
    DEFAULT_SRE_CRITICAL_THRESHOLD,
    DEFAULT_SRE_WARNING_THRESHOLD,
    EngineDimensionEvalProtocol,
    EpochSnapshot,
    SealedActivityBlock,
)

DEFAULT_DIMENSION_WEIGHTS: dict[str, float] = {
    "temporal_dynamics": 0.30,
    "attentional_fragmentation": 0.30,
    "psychomotor_mechanics": 0.20,
    "circadian_load": 0.20,
}

GOLDEN_SIGNAL_LABELS: dict[str, str] = {
    "temporal_dynamics": "utilization",
    "attentional_fragmentation": "saturation_thrashing",
    "psychomotor_mechanics": "error_rate_jitter",
    "circadian_load": "uptime_budget_burn",
}


def _compute_snapshot_entropy(epoch: EpochSnapshot) -> float:
    """Compute Shannon entropy H = -sum(p_k * ln(p_k)) for a single 30s EpochSnapshot."""
    dwell = epoch.parsed_dwell_distribution()
    positive = [sec for sec in dwell.values() if sec > 0.0]
    total = sum(positive)
    if total <= 0.0 or len(positive) <= 1:
        return 0.0
    entropy = 0.0
    for sec in positive:
        prob = sec / total
        entropy -= prob * math.log(prob)
    return max(0.0, round(entropy, 4))


@dataclass(frozen=True, slots=True)
class SREHealthReport:
    """Immutable 'User-as-a-Server' SRE health evaluation for a sealed activity block."""

    overall_strain_score: float
    dominant_state_label: str
    sre_status: str
    sre_alert_reason: str
    triggered_dimensions: tuple[str, ...]
    golden_signals: dict[str, dict[str, Any]]


def evaluate_sre_health(
    evaluations: Mapping[str, EngineDimensionEvalProtocol],
    *,
    warning_threshold: float = DEFAULT_SRE_WARNING_THRESHOLD,
    critical_threshold: float = DEFAULT_SRE_CRITICAL_THRESHOLD,
    weights: Mapping[str, float] | None = None,
) -> SREHealthReport:
    """Evaluate 4-dimension outputs using the Weighted + Max-Severity SRE rule."""
    if not evaluations:
        return SREHealthReport(
            overall_strain_score=0.0,
            dominant_state_label="idle_buffer",
            sre_status="nominal",
            sre_alert_reason="No active dimensions evaluated.",
            triggered_dimensions=(),
            golden_signals={},
        )

    weight_map = dict(weights) if weights is not None else dict(DEFAULT_DIMENSION_WEIGHTS)
    weighted_sum = 0.0
    active_weight_total = 0.0
    active_evals: list[EngineDimensionEvalProtocol] = []
    golden_signals: dict[str, dict[str, Any]] = {}

    for name, eval_res in evaluations.items():
        signal_name = GOLDEN_SIGNAL_LABELS.get(name, name)
        is_excluded = (
            name == "psychomotor_mechanics"
            and eval_res.state_label == "insufficient_keystroke_sample"
        )
        golden_signals[name] = {
            "golden_signal": signal_name,
            "strain_score": eval_res.strain_score,
            "state_label": eval_res.state_label,
            "active_in_composite": not is_excluded,
            "metrics": dict(eval_res.metrics),
            "blameless_summary": eval_res.blameless_summary,
        }
        if not is_excluded:
            w = weight_map.get(name, 0.25)
            weighted_sum += eval_res.strain_score * w
            active_weight_total += w
            active_evals.append(eval_res)

    overall_strain = (
        min(1.0, max(0.0, round(weighted_sum / active_weight_total, 4)))
        if active_weight_total > 0.0
        else 0.0
    )

    candidate_evals = active_evals if active_evals else list(evaluations.values())
    highest_eval = max(candidate_evals, key=lambda item: item.strain_score)

    critical_dims = [item for item in candidate_evals if item.strain_score >= critical_threshold]
    warning_dims = [item for item in candidate_evals if item.strain_score >= warning_threshold]

    if critical_dims or overall_strain >= critical_threshold:
        triggered = tuple(item.dimension_name for item in critical_dims) or (
            highest_eval.dimension_name,
        )
        signals_str = ", ".join(
            f"{dim} ({GOLDEN_SIGNAL_LABELS.get(dim, dim)}={evaluations[dim].strain_score:.2f})"
            for dim in triggered
        )
        reason = f"CRITICAL cognitive saturation on {signals_str}. {highest_eval.blameless_summary}"
        return SREHealthReport(
            overall_strain_score=overall_strain,
            dominant_state_label=highest_eval.state_label,
            sre_status="critical",
            sre_alert_reason=reason,
            triggered_dimensions=triggered,
            golden_signals=golden_signals,
        )

    if warning_dims or overall_strain >= warning_threshold:
        triggered = tuple(item.dimension_name for item in warning_dims) or (
            highest_eval.dimension_name,
        )
        signals_str = ", ".join(
            f"{dim} ({GOLDEN_SIGNAL_LABELS.get(dim, dim)}={evaluations[dim].strain_score:.2f})"
            for dim in triggered
        )
        reason = (
            f"WARNING elevated cognitive load on {signals_str}. {highest_eval.blameless_summary}"
        )
        return SREHealthReport(
            overall_strain_score=overall_strain,
            dominant_state_label=highest_eval.state_label,
            sre_status="warning",
            sre_alert_reason=reason,
            triggered_dimensions=triggered,
            golden_signals=golden_signals,
        )

    temporal_eval = evaluations.get("temporal_dynamics")
    attentional_eval = evaluations.get("attentional_fragmentation")
    is_flow = (
        temporal_eval is not None
        and temporal_eval.state_label in ("deep_sustained_flow", "sustained_flow", "active_reading")
        and (
            attentional_eval is None
            or attentional_eval.state_label
            in ("locked_single_app_focus", "structured_multi_tool_flow", "focused")
        )
        and highest_eval.strain_score < 0.45
    )
    if is_flow and temporal_eval is not None:
        return SREHealthReport(
            overall_strain_score=overall_strain,
            dominant_state_label=temporal_eval.state_label,
            sre_status="flow_optimal",
            sre_alert_reason="All cognitive golden signals nominal; sustained flow state.",
            triggered_dimensions=(),
            golden_signals=golden_signals,
        )

    return SREHealthReport(
        overall_strain_score=overall_strain,
        dominant_state_label=highest_eval.state_label,
        sre_status="nominal",
        sre_alert_reason="All cognitive golden signals within nominal operating bounds.",
        triggered_dimensions=(),
        golden_signals=golden_signals,
    )


class SREObservabilityRecorder:
    """Emits structured JSON SRE logs and updates Prometheus gauges and counters."""

    def __init__(
        self,
        *,
        registry: CollectorRegistry | None = None,
        logger: logging.Logger | None = None,
        max_recent_events: int = 200,
    ) -> None:
        self._registry = registry if registry is not None else CollectorRegistry()
        self._logger = logger if logger is not None else logging.getLogger("egg.sre")
        self._max_recent_events = max(1, max_recent_events)
        self._recent_events: list[dict[str, Any]] = []

        self._epochs_flushed_total = Counter(
            "egg_epochs_flushed_total",
            "Total number of 30-second cognitive telemetry epochs flushed.",
            registry=self._registry,
        )
        self._excursions_absorbed_total = Counter(
            "egg_excursions_absorbed_total",
            "Total number of transient (<90s) app-switch or idle excursions absorbed.",
            labelnames=("excursion_type",),
            registry=self._registry,
        )
        self._activity_blocks_sealed_total = Counter(
            "egg_activity_blocks_sealed_total",
            "Total number of sealed cognitive activity blocks by SRE status.",
            labelnames=("sre_status",),
            registry=self._registry,
        )
        self._sre_alerts_total = Counter(
            "egg_sre_alerts_total",
            "Total number of SRE cognitive load alerts emitted by severity and dimension.",
            labelnames=("severity", "dimension"),
            registry=self._registry,
        )
        self._epoch_duty_cycle_gauge = Gauge(
            "egg_epoch_duty_cycle_ratio",
            "Active duty cycle ratio [0.0, 1.0] of the latest 30-second epoch.",
            registry=self._registry,
        )
        self._epoch_entropy_gauge = Gauge(
            "egg_epoch_shannon_entropy_nats",
            "Shannon attentional entropy (nats) of the latest 30-second epoch.",
            registry=self._registry,
        )
        self._dimension_strain_gauge = Gauge(
            "egg_dimension_strain_score",
            "Normalized strain score [0.0, 1.0] per scientific dimension on sealed block.",
            labelnames=("dimension",),
            registry=self._registry,
        )
        self._block_overall_strain_gauge = Gauge(
            "egg_block_overall_strain_score",
            "Weighted composite cognitive strain score [0.0, 1.0] of the latest sealed block.",
            registry=self._registry,
        )

    @property
    def registry(self) -> CollectorRegistry:
        """Prometheus CollectorRegistry managed by this recorder."""
        return self._registry

    @property
    def recent_events(self) -> tuple[dict[str, Any], ...]:
        """Return bounded history of emitted structured SRE event payloads."""
        return tuple(self._recent_events)

    def _emit_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Serialize payload to JSON, log it, and append to bounded recent_events."""
        self._recent_events.append(payload)
        if len(self._recent_events) > self._max_recent_events:
            self._recent_events.pop(0)
        self._logger.info(json.dumps(payload, sort_keys=True))
        return payload

    def record_epoch_flushed(self, epoch: EpochSnapshot) -> dict[str, Any]:
        """Record a 30s epoch flush in Prometheus metrics and structured JSON logs."""
        duration = epoch.duration_seconds
        duty_cycle = (
            min(1.0, max(0.0, round(epoch.active_seconds / duration, 4))) if duration > 0.0 else 0.0
        )
        entropy = _compute_snapshot_entropy(epoch)

        self._epochs_flushed_total.inc()
        self._epoch_duty_cycle_gauge.set(duty_cycle)
        self._epoch_entropy_gauge.set(entropy)

        return self._emit_event(
            {
                "event": "epoch_flushed",
                "timestamp_start": epoch.timestamp_start,
                "timestamp_end": epoch.timestamp_end,
                "primary_process": epoch.primary_process,
                "duty_cycle": duty_cycle,
                "shannon_entropy": entropy,
                "context_switch_count": epoch.context_switch_count,
                "total_keystrokes": epoch.total_keystrokes,
            }
        )

    def record_excursion_absorbed(
        self,
        *,
        primary_process: str,
        excursion_type: str,
        absorbed_epoch_count: int,
        absorbed_duration_seconds: float,
    ) -> dict[str, Any]:
        """Record a transient (<90s) excursion absorbed by the hysteresis buffer."""
        self._excursions_absorbed_total.labels(excursion_type=excursion_type).inc()
        return self._emit_event(
            {
                "event": "excursion_absorbed",
                "primary_process": primary_process,
                "excursion_type": excursion_type,
                "absorbed_epoch_count": absorbed_epoch_count,
                "absorbed_duration_seconds": round(absorbed_duration_seconds, 2),
            }
        )

    def record_block_sealed(
        self,
        block: SealedActivityBlock,
        report: SREHealthReport,
    ) -> dict[str, Any]:
        """Record a sealed activity block and emit SRE alerts if thresholds were crossed."""
        self._activity_blocks_sealed_total.labels(sre_status=block.sre_status).inc()
        self._block_overall_strain_gauge.set(block.overall_strain_score)

        for dim_name, dim_info in report.golden_signals.items():
            self._dimension_strain_gauge.labels(dimension=dim_name).set(
                float(dim_info["strain_score"])
            )

        sealed_event = self._emit_event(
            {
                "event": "activity_block_sealed",
                "block_id": block.id,
                "start_time": block.start_time,
                "end_time": block.end_time,
                "duration_seconds": block.duration_seconds,
                "primary_process": block.primary_process,
                "epoch_count": block.epoch_count,
                "duty_cycle": block.duty_cycle,
                "shannon_entropy": block.shannon_entropy,
                "overall_strain_score": block.overall_strain_score,
                "dominant_state_label": block.dominant_state_label,
                "sre_status": block.sre_status,
                "sre_alert_reason": block.sre_alert_reason,
            }
        )

        if block.sre_status in ("warning", "critical"):
            for dim_name in report.triggered_dimensions:
                self._sre_alerts_total.labels(
                    severity=block.sre_status,
                    dimension=dim_name,
                ).inc()
            self._emit_event(
                {
                    "event": "sre_alert",
                    "severity": block.sre_status,
                    "primary_process": block.primary_process,
                    "overall_strain_score": block.overall_strain_score,
                    "dominant_state_label": block.dominant_state_label,
                    "triggered_dimensions": list(report.triggered_dimensions),
                    "sre_alert_reason": block.sre_alert_reason,
                }
            )

        return sealed_event

    def render_prometheus_metrics(self) -> str:
        """Render current Prometheus metrics in standard text exposition format."""
        return generate_latest(self._registry).decode("utf-8")
