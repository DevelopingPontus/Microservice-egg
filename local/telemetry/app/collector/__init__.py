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
    create_input_listener,
    is_correction_key,
    is_macos_accessibility_trusted,
    is_macos_input_monitoring_trusted,
)
from app.collector.sliding_window import (
    ActivitySnapshot,
    PooledTelemetryMetrics,
    SlidingWindowBuffer,
    TelemetrySample,
    TickDeltas,
    compute_shannon_entropy,
    merge_dwell_distributions,
    pool_telemetry_samples,
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
    "SlidingWindowBuffer",
    "SyntheticBurstEmitterProtocol",
    "SyntheticInputListener",
    "SyntheticWindowResolver",
    "TelemetrySample",
    "TickDeltas",
    "WindowResolverProtocol",
    "compute_shannon_entropy",
    "create_input_listener",
    "create_window_resolver",
    "is_correction_key",
    "is_macos_accessibility_trusted",
    "is_macos_input_monitoring_trusted",
    "merge_dwell_distributions",
    "pool_telemetry_samples",
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

    def commit_snapshot(self, *, now_timestamp: float | None = None) -> ActivitySnapshot:
        """Commit the current slice and return a complete 60s ActivitySnapshot."""
        return self.buffer.commit_snapshot(now_timestamp=now_timestamp)
