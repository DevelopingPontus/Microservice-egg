"""Observability Exporters Module (`app/exporters/`).

Combines `otel.py`, `metrics.py`, `logs.py`, and `traces.py` behind a single
`TelemetryExporter.publish(snapshot, state)` facade.
"""

from app.analysis import CognitiveState
from app.collector import ActivitySnapshot
from app.config import DaemonConfig
from app.exporters.logs import SREEventLogger
from app.exporters.metrics import CognitiveMetricsRecorder
from app.exporters.otel import OTelTelemetryManager
from app.exporters.traces import FocusSessionTracer

__all__ = [
    "CognitiveMetricsRecorder",
    "FocusSessionTracer",
    "OTelTelemetryManager",
    "SREEventLogger",
    "TelemetryExporter",
]


class TelemetryExporter:
    """Combines OTel SDK, Prometheus/OTLP metrics, Loki logs, and Tempo traces."""

    def __init__(
        self,
        config: DaemonConfig,
        *,
        otel_manager: OTelTelemetryManager | None = None,
        metrics_recorder: CognitiveMetricsRecorder | None = None,
        focus_tracer: FocusSessionTracer | None = None,
        sre_logger: SREEventLogger | None = None,
    ) -> None:
        self.otel_manager = (
            otel_manager
            if otel_manager is not None
            else OTelTelemetryManager(
                otlp_endpoint=config.otlp_endpoint,
                enable_otlp=config.enable_otlp,
            )
        )
        self.metrics_recorder = (
            metrics_recorder
            if metrics_recorder is not None
            else CognitiveMetricsRecorder(self.otel_manager.meter)
        )
        self.focus_tracer = (
            focus_tracer
            if focus_tracer is not None
            else FocusSessionTracer(self.otel_manager.tracer)
        )
        self.sre_logger = (
            sre_logger
            if sre_logger is not None
            else SREEventLogger(heartbeat_interval_seconds=config.heartbeat_log_interval_seconds)
        )

    def publish(self, snapshot: ActivitySnapshot, state: CognitiveState) -> None:
        """Publish metrics, Tempo focus spans, and Loki structured logs in one call."""
        metrics = snapshot.metrics
        deltas = snapshot.deltas
        overview = state.workflow

        self.metrics_recorder.record_tick(
            metrics=metrics,
            session_uptime_seconds=snapshot.session_uptime_seconds,
            active_work_seconds=snapshot.active_work_seconds,
            away_idle_seconds=snapshot.away_idle_seconds,
            evaluations=state.evaluations,
            report=state.strain,
            overview=overview,
            keystroke_delta=deltas.keystrokes,
            correction_delta=deltas.corrections,
            context_switch_delta=deltas.context_switches,
            mouse_click_delta=deltas.mouse_clicks,
            scroll_delta=deltas.scrolls,
        )

        self.focus_tracer.start_or_switch_focus(
            metrics.primary_process,
            attributes={
                "duty_cycle": metrics.duty_cycle,
                "shannon_entropy": metrics.shannon_entropy,
                "activity": overview.classification.activity,
                "app_category": overview.classification.app_category,
                "typing_mode": overview.typing_mode,
            },
        )

        self.sre_logger.publish_tick(snapshot, state)

    def render_prometheus_metrics(self) -> str:
        """Render Prometheus text exposition metrics."""
        return self.metrics_recorder.render_prometheus_metrics()

    def shutdown(self) -> None:
        """End active focus spans and flush all OpenTelemetry providers."""
        self.focus_tracer.end_current_focus()
        self.otel_manager.shutdown()
