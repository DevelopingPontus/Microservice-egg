"""OpenTelemetry & Prometheus metrics recorder for cognitive signals and strain."""

from collections.abc import Iterable, Mapping

from opentelemetry.metrics import CallbackOptions, Meter, Observation
from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest

from app.common.models import (
    CognitiveStrainReport,
    DimensionEvaluation,
    PooledTelemetryMetrics,
)


class CognitiveMetricsRecorder:
    """Records cognitive telemetry into OpenTelemetry instruments and Prometheus registry."""

    def __init__(
        self,
        meter: Meter,
        *,
        registry: CollectorRegistry | None = None,
    ) -> None:
        self._meter = meter
        self._prom_registry = registry if registry is not None else CollectorRegistry()

        # --- OpenTelemetry Instruments ---
        self._otel_keystrokes = meter.create_counter(
            "user_keystrokes_total",
            description="Total number of physical keystrokes detected.",
            unit="1",
        )
        self._otel_corrections = meter.create_counter(
            "user_corrections_total",
            description="Total number of backspace and delete keystrokes detected.",
            unit="1",
        )
        self._otel_mouse_clicks = meter.create_counter(
            "user_mouse_clicks_total",
            description="Total number of physical mouse button presses detected.",
            unit="1",
        )
        self._otel_scroll_events = meter.create_counter(
            "user_scroll_events_total",
            description="Total number of scroll events detected.",
            unit="1",
        )
        self._otel_context_switches = meter.create_counter(
            "user_context_switches_total",
            description="Total number of active application window switches.",
            unit="1",
        )

        # --- Prometheus Equivalents (for local /metrics scraping) ---
        self._prom_duty_cycle = Gauge(
            "egg_user_duty_cycle_ratio",
            "Active duty cycle ratio [0.0, 1.0] across active window.",
            registry=self._prom_registry,
        )
        self._prom_shannon_entropy = Gauge(
            "egg_user_shannon_entropy_nats",
            "Shannon attentional entropy (nats) across active apps.",
            registry=self._prom_registry,
        )
        self._prom_context_switch_rate = Gauge(
            "egg_user_context_switches_per_min",
            "Context switches per minute across active window.",
            registry=self._prom_registry,
        )
        self._prom_correction_ratio = Gauge(
            "egg_user_correction_ratio",
            "Backspace/delete ratio to total keystrokes.",
            registry=self._prom_registry,
        )
        self._prom_iki_jitter_cv = Gauge(
            "egg_user_iki_jitter_cv",
            "Inter-keystroke interval coefficient of variation (typing cadence jitter).",
            registry=self._prom_registry,
        )
        self._prom_session_uptime = Gauge(
            "egg_user_session_uptime_seconds",
            "Continuous session uptime in seconds without an extended break.",
            registry=self._prom_registry,
        )
        self._prom_active_work_seconds = Gauge(
            "egg_user_active_work_seconds",
            "Total active working time in seconds including thinking/reading grace periods.",
            registry=self._prom_registry,
        )
        self._prom_overall_strain = Gauge(
            "egg_user_overall_strain_score",
            "Composite SRE cognitive strain score [0.0, 1.0].",
            registry=self._prom_registry,
        )
        self._prom_dimension_strain = Gauge(
            "egg_user_dimension_strain_score",
            "Cognitive strain score [0.0, 1.0] by scientific dimension.",
            labelnames=("dimension",),
            registry=self._prom_registry,
        )
        self._prom_keystrokes_total = Counter(
            "egg_user_keystrokes_total",
            "Total keystrokes recorded.",
            registry=self._prom_registry,
        )
        self._prom_corrections_total = Counter(
            "egg_user_corrections_total",
            "Total backspace and delete keystrokes recorded.",
            registry=self._prom_registry,
        )
        self._prom_context_switches_total = Counter(
            "egg_user_context_switches_total",
            "Total window context switches recorded.",
            registry=self._prom_registry,
        )

        # Cached last gauge values for OTel callbacks
        self._current_metrics: dict[str, float] = {
            "duty_cycle": 0.0,
            "shannon_entropy": 0.0,
            "context_switches_per_min": 0.0,
            "correction_ratio": 0.0,
            "iki_jitter_cv": 0.0,
            "session_uptime_seconds": 0.0,
            "active_work_seconds": 0.0,
            "overall_strain_score": 0.0,
        }

        # --- OpenTelemetry Observable Gauges ---
        meter.create_observable_gauge(
            "user_duty_cycle_ratio",
            callbacks=[self._observe_duty_cycle],
            description="Active duty cycle ratio [0.0, 1.0] across active window.",
            unit="1",
        )
        meter.create_observable_gauge(
            "user_shannon_entropy_nats",
            callbacks=[self._observe_shannon_entropy],
            description="Shannon attentional entropy (nats) across active apps.",
            unit="nats",
        )
        meter.create_observable_gauge(
            "user_context_switches_per_min",
            callbacks=[self._observe_context_switch_rate],
            description="Context switches per minute across active window.",
            unit="1/min",
        )
        meter.create_observable_gauge(
            "user_correction_ratio",
            callbacks=[self._observe_correction_ratio],
            description="Backspace/delete ratio to total keystrokes.",
            unit="1",
        )
        meter.create_observable_gauge(
            "user_iki_jitter_cv",
            callbacks=[self._observe_iki_jitter_cv],
            description="Inter-keystroke interval coefficient of variation (cadence jitter).",
            unit="1",
        )
        meter.create_observable_gauge(
            "user_session_uptime_seconds",
            callbacks=[self._observe_session_uptime],
            description="Continuous session uptime in seconds without an extended break.",
            unit="s",
        )
        meter.create_observable_gauge(
            "user_active_work_seconds",
            callbacks=[self._observe_active_work_seconds],
            description="Total active working time in seconds with thought grace periods.",
            unit="s",
        )
        meter.create_observable_gauge(
            "user_overall_strain_score",
            callbacks=[self._observe_overall_strain],
            description="Composite SRE cognitive strain score [0.0, 1.0].",
            unit="1",
        )

    def _observe_duty_cycle(self, _options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(self._current_metrics.get("duty_cycle", 0.0))

    def _observe_shannon_entropy(self, _options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(self._current_metrics.get("shannon_entropy", 0.0))

    def _observe_context_switch_rate(self, _options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(self._current_metrics.get("context_switches_per_min", 0.0))

    def _observe_correction_ratio(self, _options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(self._current_metrics.get("correction_ratio", 0.0))

    def _observe_iki_jitter_cv(self, _options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(self._current_metrics.get("iki_jitter_cv", 0.0))

    def _observe_session_uptime(self, _options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(self._current_metrics.get("session_uptime_seconds", 0.0))

    def _observe_active_work_seconds(self, _options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(self._current_metrics.get("active_work_seconds", 0.0))

    def _observe_overall_strain(self, _options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(self._current_metrics.get("overall_strain_score", 0.0))

    @property
    def registry(self) -> CollectorRegistry:
        """Prometheus CollectorRegistry."""
        return self._prom_registry

    def record_tick(
        self,
        *,
        metrics: PooledTelemetryMetrics,
        session_uptime_seconds: float,
        evaluations: Mapping[str, DimensionEvaluation],
        report: CognitiveStrainReport,
        active_work_seconds: float = 0.0,
        keystroke_delta: int = 0,
        correction_delta: int = 0,
        context_switch_delta: int = 0,
        mouse_click_delta: int = 0,
        scroll_delta: int = 0,
    ) -> None:
        """Update OpenTelemetry and Prometheus gauges and counters."""
        # 1. Update OTel counters if delta > 0
        if keystroke_delta > 0:
            self._otel_keystrokes.add(keystroke_delta)
            self._prom_keystrokes_total.inc(keystroke_delta)
        if correction_delta > 0:
            self._otel_corrections.add(correction_delta)
            self._prom_corrections_total.inc(correction_delta)
        if context_switch_delta > 0:
            self._otel_context_switches.add(context_switch_delta)
            self._prom_context_switches_total.inc(context_switch_delta)
        if mouse_click_delta > 0:
            self._otel_mouse_clicks.add(mouse_click_delta)
        if scroll_delta > 0:
            self._otel_scroll_events.add(scroll_delta)

        # 2. Update Gauges in Prometheus and cache for OTel ObservableGauges
        self._current_metrics["duty_cycle"] = metrics.duty_cycle
        self._current_metrics["shannon_entropy"] = metrics.shannon_entropy
        self._current_metrics["context_switches_per_min"] = metrics.switches_per_minute
        self._current_metrics["correction_ratio"] = metrics.correction_ratio
        self._current_metrics["iki_jitter_cv"] = metrics.iki_cv
        self._current_metrics["session_uptime_seconds"] = session_uptime_seconds
        self._current_metrics["active_work_seconds"] = active_work_seconds
        self._current_metrics["overall_strain_score"] = report.overall_strain_score

        self._prom_duty_cycle.set(metrics.duty_cycle)
        self._prom_shannon_entropy.set(metrics.shannon_entropy)
        self._prom_context_switch_rate.set(metrics.switches_per_minute)
        self._prom_correction_ratio.set(metrics.correction_ratio)
        self._prom_iki_jitter_cv.set(metrics.iki_cv)
        self._prom_session_uptime.set(session_uptime_seconds)
        self._prom_active_work_seconds.set(active_work_seconds)
        self._prom_overall_strain.set(report.overall_strain_score)

        for dim_name, eval_res in evaluations.items():
            self._prom_dimension_strain.labels(dimension=dim_name).set(eval_res.strain_score)

    def render_prometheus_metrics(self) -> str:
        """Render Prometheus metrics in plain text exposition format."""
        return generate_latest(self._prom_registry).decode("utf-8")
