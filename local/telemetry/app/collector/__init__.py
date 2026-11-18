"""Activity Collector Module (`app/collector/`).

Combines `input_hook`, `window_probe`, and `sliding_window` into a standalone
60-second activity sensor (`ActivityCollector`) that outputs an `ActivitySnapshot`.
"""

from app.collector.input_hook import (
    InputListenerProtocol,
    InputTickSinkProtocol,
    PynputInputListener,
    SyntheticBurstEmitterProtocol,
    SyntheticInputListener,
    classify_key_category,
    create_input_listener,
    is_correction_key,
    is_macos_accessibility_trusted,
    is_macos_input_monitoring_trusted,
    key_slot_id,
)
from app.collector.sliding_window import (
    ActivitySnapshot,
    PooledTelemetryMetrics,
    RawAttentionWindowMetrics,
    RawCorrectionPauseMetrics,
    RawKeystrokeTimingMetrics,
    RawMetricsBundle,
    RawMouseKinematicsMetrics,
    RawTemporalSessionMetrics,
    SlidingWindowBuffer,
    TelemetrySample,
    TickDeltas,
    compute_median_abs_deviation,
    compute_mouse_kinematics,
    compute_sample_entropy,
    compute_shannon_entropy,
    merge_dwell_distributions,
    pool_telemetry_samples,
    produce_attention_window_metrics,
    produce_correction_pause_metrics,
    produce_keystroke_timing_metrics,
    produce_mouse_kinematics_metrics,
    produce_raw_metrics_bundle,
    produce_temporal_session_metrics,
)
from app.collector.window_probe import (
    NativeWindowResolver,
    SyntheticWindowResolver,
    WindowResolverProtocol,
    create_window_resolver,
    sanitize_process_name,
)
from app.config import DaemonConfig

__all__ = [
    "ActivityCollector",
    "ActivitySnapshot",
    "InputListenerProtocol",
    "InputTickSinkProtocol",
    "NativeWindowResolver",
    "PooledTelemetryMetrics",
    "PynputInputListener",
    "RawAttentionWindowMetrics",
    "RawCorrectionPauseMetrics",
    "RawKeystrokeTimingMetrics",
    "RawMetricsBundle",
    "RawMouseKinematicsMetrics",
    "RawTemporalSessionMetrics",
    "SlidingWindowBuffer",
    "SyntheticBurstEmitterProtocol",
    "SyntheticInputListener",
    "SyntheticWindowResolver",
    "TelemetrySample",
    "TickDeltas",
    "WindowResolverProtocol",
    "classify_key_category",
    "compute_median_abs_deviation",
    "compute_mouse_kinematics",
    "compute_sample_entropy",
    "compute_shannon_entropy",
    "create_input_listener",
    "create_window_resolver",
    "is_correction_key",
    "is_macos_accessibility_trusted",
    "is_macos_input_monitoring_trusted",
    "key_slot_id",
    "merge_dwell_distributions",
    "pool_telemetry_samples",
    "produce_attention_window_metrics",
    "produce_correction_pause_metrics",
    "produce_keystroke_timing_metrics",
    "produce_mouse_kinematics_metrics",
    "produce_raw_metrics_bundle",
    "produce_temporal_session_metrics",
    "sanitize_process_name",
]


class ActivityCollector:
    """Standalone sensor combining keyboard/mouse hooks, window probe, and 60s sliding window."""

    def __init__(
        self,
        config: DaemonConfig,
        *,
        buffer: SlidingWindowBuffer | None = None,
        input_listener: InputListenerProtocol | None = None,
        window_resolver: WindowResolverProtocol | None = None,
    ) -> None:
        self.buffer = (
            buffer
            if buffer is not None
            else SlidingWindowBuffer(
                window_duration_seconds=config.sliding_window_seconds,
                idle_threshold_seconds=config.idle_event_threshold_seconds,
                micro_pause_min_seconds=config.micro_pause_min_seconds,
                micro_pause_max_seconds=config.micro_pause_max_seconds,
                iki_min_outlier_ms=config.iki_min_outlier_ms,
                iki_max_outlier_ms=config.iki_max_outlier_ms,
                mouse_move_throttle_seconds=config.mouse_move_throttle_seconds,
                session_reset_idle_seconds=config.session_reset_idle_seconds,
                reading_thought_grace_seconds=config.reading_thought_grace_seconds,
                away_idle_threshold_seconds=config.away_idle_threshold_seconds,
            )
        )
        self.input_listener = (
            input_listener
            if input_listener is not None
            else create_input_listener(self.buffer, simulate=config.simulate)
        )
        self.window_resolver = (
            window_resolver
            if window_resolver is not None
            else create_window_resolver(simulate=config.simulate)
        )

    def start(self) -> None:
        """Start input listener and emit initial synthetic burst if in simulation mode."""
        self.input_listener.start()
        if isinstance(self.input_listener, SyntheticBurstEmitterProtocol):
            self.input_listener.emit_synthetic_burst()

    def stop(self) -> None:
        """Stop background input listener hooks."""
        self.input_listener.stop()

    def poll_window(self, poll_interval_seconds: float) -> None:
        """Poll foreground window process and window ID and record dwell time in the buffer."""
        proc_name = self.window_resolver.get_active_process_name()
        wid = self.window_resolver.get_active_window_id()
        self.buffer.record_window_tick(proc_name, poll_interval_seconds, window_id=wid)

    def has_good_keystroke_timing_sample(self, min_samples: int = 10) -> bool:
        """Check if buffer has accumulated a representative keystroke timing sample."""
        return self.buffer.has_good_keystroke_timing_sample(min_samples=min_samples)

    def consume_keystroke_timing_metrics(self) -> tuple[RawKeystrokeTimingMetrics, int]:
        """Consume and reset accumulated keystroke timing metrics."""
        return self.buffer.consume_keystroke_timing_metrics()

    def has_good_correction_pause_sample(self) -> bool:
        """Check if buffer has accumulated correction or typing pause events."""
        return self.buffer.has_good_correction_pause_sample()

    def consume_correction_pause_metrics(self) -> tuple[RawCorrectionPauseMetrics, int]:
        """Consume and reset accumulated correction/pause metrics."""
        return self.buffer.consume_correction_pause_metrics()

    def has_good_mouse_sample(self, min_points: int = 25) -> bool:
        """Check if buffer has accumulated sufficient mouse trajectory points or clicks/scrolls."""
        return self.buffer.has_good_mouse_sample(min_points=min_points)

    def consume_mouse_kinematics_metrics(self) -> tuple[RawMouseKinematicsMetrics, int, int]:
        """Consume and reset accumulated mouse kinematics metrics."""
        return self.buffer.consume_mouse_kinematics_metrics()

    def has_good_attention_sample(self) -> bool:
        """Check if buffer has accumulated a window context switch or dwell threshold."""
        return self.buffer.has_good_attention_sample()

    def consume_attention_window_metrics(self) -> tuple[RawAttentionWindowMetrics, int]:
        """Consume and reset accumulated process dwell & switch metrics."""
        return self.buffer.consume_attention_window_metrics()

    def consume_temporal_session_metrics(self) -> RawTemporalSessionMetrics:
        """Consume current temporal and session duration metrics."""
        return self.buffer.consume_temporal_session_metrics()

    def commit_snapshot(self, *, now_timestamp: float | None = None) -> ActivitySnapshot:
        """Commit the current slice and return a complete 60s ActivitySnapshot."""
        return self.buffer.commit_snapshot(now_timestamp=now_timestamp)
