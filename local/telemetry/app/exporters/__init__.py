"""Observability Exporters Module (`app/exporters/`).

Combines `otel.py` and `metrics.py` behind a single
`TelemetryExporter.publish(snapshot, state)` facade.
"""

from app.analysis import CognitiveState
from app.collector import (
    ActivitySnapshot,
    RawAttentionWindowMetrics,
    RawCorrectionPauseMetrics,
    RawKeystrokeTimingMetrics,
    RawMouseKinematicsMetrics,
    RawTemporalSessionMetrics,
)
from app.config import DaemonConfig
from app.exporters.metrics import CognitiveMetricsRecorder
from app.exporters.otel import OTelTelemetryManager

__all__ = [
    "CognitiveMetricsRecorder",
    "OTelTelemetryManager",
    "TelemetryExporter",
]


class TelemetryExporter:
    """Combines OTel SDK and Prometheus/OTLP metrics."""

    def __init__(
        self,
        config: DaemonConfig,
        *,
        otel_manager: OTelTelemetryManager | None = None,
        metrics_recorder: CognitiveMetricsRecorder | None = None,
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

    def publish_keystroke_timing(
        self, metrics: RawKeystrokeTimingMetrics, *, keystroke_delta: int = 0
    ) -> None:
        """Publish raw keystroke timing when a good sample is ready."""
        self.metrics_recorder.record_keystroke_timing(metrics, keystroke_delta=keystroke_delta)

    def publish_correction_pauses(
        self, metrics: RawCorrectionPauseMetrics, *, correction_delta: int = 0
    ) -> None:
        """Publish raw correction pauses when a good sample is ready."""
        self.metrics_recorder.record_correction_pauses(metrics, correction_delta=correction_delta)

    def publish_mouse_kinematics(
        self,
        metrics: RawMouseKinematicsMetrics,
        *,
        mouse_click_delta: int = 0,
        scroll_delta: int = 0,
    ) -> None:
        """Publish raw mouse kinematics when a good sample is ready."""
        self.metrics_recorder.record_mouse_kinematics(
            metrics, mouse_click_delta=mouse_click_delta, scroll_delta=scroll_delta
        )

    def publish_attention_window(
        self, metrics: RawAttentionWindowMetrics, *, context_switch_delta: int = 0
    ) -> None:
        """Publish raw attention window when a good sample is ready."""
        self.metrics_recorder.record_attention_window(
            metrics, context_switch_delta=context_switch_delta
        )

    def publish_temporal_session(self, metrics: RawTemporalSessionMetrics) -> None:
        """Publish raw temporal session when updated."""
        self.metrics_recorder.record_temporal_session(metrics)

    def publish(self, snapshot: ActivitySnapshot, _state: CognitiveState) -> None:
        """Publish independent raw metrics to OpenTelemetry and Prometheus."""
        deltas = snapshot.deltas
        raw = snapshot.raw

        self.publish_keystroke_timing(raw.keystroke_timing, keystroke_delta=deltas.keystrokes)
        self.publish_correction_pauses(raw.correction_pauses, correction_delta=deltas.corrections)
        self.publish_mouse_kinematics(
            raw.mouse_kinematics,
            mouse_click_delta=deltas.mouse_clicks,
            scroll_delta=deltas.scrolls,
        )
        self.publish_attention_window(
            raw.attention_window, context_switch_delta=deltas.context_switches
        )
        self.publish_temporal_session(raw.temporal_session)

    def render_prometheus_metrics(self) -> str:
        """Render Prometheus text exposition metrics."""
        return self.metrics_recorder.render_prometheus_metrics()

    def shutdown(self) -> None:
        """Flush and shutdown OpenTelemetry provider."""
        self.otel_manager.shutdown()
