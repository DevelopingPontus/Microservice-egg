"""Root lifecycle supervisor wiring intake -> output observability."""

import argparse
import asyncio
import signal
import time
from collections.abc import Sequence

from fastapi import FastAPI

from app.common.config import (
    DEFAULT_API_PORT,
    DaemonConfig,
)
from app.common.models import (
    CognitiveStrainReport,
    PooledTelemetryMetrics,
    SchedulerDiagnostics,
)
from app.common.protocols import (
    InputListenerProtocol,
    SyntheticBurstEmitterProtocol,
    TelemetryGatewayBackendProtocol,
    WindowResolverProtocol,
)
from app.intake.collectors import (
    create_input_listener,
    create_window_resolver,
)
from app.intake.engine import SlidingWindowBuffer
from app.output.api import (
    create_api_app,
    create_uvicorn_server,
    validate_loopback_host,
    validate_port,
)
from app.output.dimensions import (
    DimensionContext,
    DimensionRegistry,
    create_default_registry,
)
from app.output.observability import (
    CognitiveMetricsRecorder,
    FocusSessionTracer,
    OTelTelemetryManager,
    SREEventLogger,
    evaluate_cognitive_sre_health,
)


class TelemetryService(TelemetryGatewayBackendProtocol):
    """Root supervisor wiring intake hardware to output observability."""

    def __init__(
        self,
        config: DaemonConfig,
        *,
        buffer: SlidingWindowBuffer | None = None,
        input_listener: InputListenerProtocol | None = None,
        window_resolver: WindowResolverProtocol | None = None,
        dimensions: DimensionRegistry | None = None,
        otel_manager: OTelTelemetryManager | None = None,
        metrics_recorder: CognitiveMetricsRecorder | None = None,
        focus_tracer: FocusSessionTracer | None = None,
        sre_logger: SREEventLogger | None = None,
    ) -> None:
        self._config = config
        self._api_host = validate_loopback_host(config.api_host)
        self._api_port = validate_port(config.api_port)

        self._buffer = (
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
            )
        )
        self._input_listener = (
            input_listener
            if input_listener is not None
            else create_input_listener(self._buffer, simulate=config.simulate)
        )
        self._window_resolver = (
            window_resolver
            if window_resolver is not None
            else create_window_resolver(simulate=config.simulate)
        )
        self._dimensions = dimensions if dimensions is not None else create_default_registry()

        self._otel_manager = (
            otel_manager
            if otel_manager is not None
            else OTelTelemetryManager(
                otlp_endpoint=config.otlp_endpoint,
                enable_otlp=config.enable_otlp,
            )
        )
        self._metrics_recorder = (
            metrics_recorder
            if metrics_recorder is not None
            else CognitiveMetricsRecorder(self._otel_manager.meter)
        )
        self._focus_tracer = (
            focus_tracer
            if focus_tracer is not None
            else FocusSessionTracer(self._otel_manager.tracer)
        )
        self._sre_logger = sre_logger if sre_logger is not None else SREEventLogger()

        self._is_running = False
        self._stop_requested = False
        self._samples_emitted_total = 0
        self._window_ticks_total = 0
        self._last_emit_timestamp: float | None = None

        self._last_logged_status: str = "nominal"
        self._last_heartbeat_time: float = 0.0
        self._last_logged_process: str | None = None

        # Previous snapshot totals to compute deltas
        self._prev_keystrokes: int = 0
        self._prev_corrections: int = 0
        self._prev_switches: int = 0
        self._prev_mouse_clicks: int = 0
        self._prev_scrolls: int = 0

        self._api_app = create_api_app(self)

    @property
    def config(self) -> DaemonConfig:
        return self._config

    @property
    def buffer(self) -> SlidingWindowBuffer:
        return self._buffer

    @property
    def input_listener(self) -> InputListenerProtocol:
        return self._input_listener

    @property
    def window_resolver(self) -> WindowResolverProtocol:
        return self._window_resolver

    @property
    def dimensions(self) -> DimensionRegistry:
        return self._dimensions

    @property
    def metrics_recorder(self) -> CognitiveMetricsRecorder:
        return self._metrics_recorder

    @property
    def focus_tracer(self) -> FocusSessionTracer:
        return self._focus_tracer

    @property
    def sre_logger(self) -> SREEventLogger:
        return self._sre_logger

    @property
    def api_app(self) -> FastAPI:
        return self._api_app

    def get_diagnostics(self) -> SchedulerDiagnostics:
        return SchedulerDiagnostics(
            is_running=self._is_running,
            samples_emitted_total=self._samples_emitted_total,
            window_ticks_total=self._window_ticks_total,
            last_emit_timestamp=self._last_emit_timestamp,
        )

    def render_prometheus_metrics(self) -> str:
        return self._metrics_recorder.render_prometheus_metrics()

    def request_stop(self) -> None:
        self._stop_requested = True

    def _install_signal_handlers(self) -> list[signal.Signals]:
        installed: list[signal.Signals] = []
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, self.request_stop)
                    installed.append(sig)
                except (NotImplementedError, RuntimeError, ValueError):
                    continue
        except RuntimeError:
            pass
        return installed

    def _remove_signal_handlers(self, installed: Sequence[signal.Signals]) -> None:
        try:
            loop = asyncio.get_running_loop()
            for sig in installed:
                try:
                    loop.remove_signal_handler(sig)
                except (NotImplementedError, RuntimeError, ValueError):
                    continue
        except RuntimeError:
            pass

    def evaluate_and_emit_once(self) -> tuple[PooledTelemetryMetrics, CognitiveStrainReport]:
        """Commit current slice, evaluate dimensions, and export to OTel/Prometheus."""
        self._buffer.commit_slice()
        metrics = self._buffer.get_sliding_window_metrics()
        session_uptime = self._buffer.session_uptime_seconds
        active_work_seconds = self._buffer.active_work_seconds

        context = DimensionContext.create(
            metrics,
            session_uptime_seconds=session_uptime,
        )
        evaluations = self._dimensions.evaluate_all(context)
        report = evaluate_cognitive_sre_health(evaluations)

        # Calculate deltas for monotonic OTel counters
        curr_keys = self._buffer.lifetime_keystrokes
        curr_corrs = self._buffer.lifetime_corrections
        curr_switches = self._buffer.lifetime_context_switches
        curr_clicks = self._buffer.lifetime_mouse_clicks
        curr_scrolls = self._buffer.lifetime_scroll_events

        delta_keys = max(0, curr_keys - self._prev_keystrokes)
        delta_corrs = max(0, curr_corrs - self._prev_corrections)
        delta_switches = max(0, curr_switches - self._prev_switches)
        delta_clicks = max(0, curr_clicks - self._prev_mouse_clicks)
        delta_scrolls = max(0, curr_scrolls - self._prev_scrolls)

        self._prev_keystrokes = curr_keys
        self._prev_corrections = curr_corrs
        self._prev_switches = curr_switches
        self._prev_mouse_clicks = curr_clicks
        self._prev_scrolls = curr_scrolls

        # Record metrics in OTel and Prometheus
        self._metrics_recorder.record_tick(
            metrics=metrics,
            session_uptime_seconds=session_uptime,
            active_work_seconds=active_work_seconds,
            evaluations=evaluations,
            report=report,
            keystroke_delta=delta_keys,
            correction_delta=delta_corrs,
            context_switch_delta=delta_switches,
            mouse_click_delta=delta_clicks,
            scroll_delta=delta_scrolls,
        )

        # Update active window focus trace in Tempo
        self._focus_tracer.start_or_switch_focus(
            metrics.primary_process,
            attributes={
                "duty_cycle": metrics.duty_cycle,
                "shannon_entropy": metrics.shannon_entropy,
            },
        )

        # Focus switch event log
        if (
            self._last_logged_process is not None
            and metrics.primary_process != "idle"
            and metrics.primary_process != self._last_logged_process
        ):
            self._sre_logger.log_focus_switch(self._last_logged_process, metrics.primary_process)
        if metrics.primary_process != "idle":
            self._last_logged_process = metrics.primary_process

        # Calm periodic session heartbeat to Loki (default every 60s)
        now_mono = time.monotonic()
        if (now_mono - self._last_heartbeat_time) >= self._config.heartbeat_log_interval_seconds:
            self._sre_logger.log_session_heartbeat(
                metrics,
                report,
                session_uptime_seconds=session_uptime,
                active_work_seconds=active_work_seconds,
            )
            self._last_heartbeat_time = now_mono

        self._last_logged_status = report.sre_status

        self._samples_emitted_total += 1
        self._last_emit_timestamp = time.time()
        return metrics, report

    async def run(
        self,
        *,
        max_duration_seconds: float | None = None,
        install_signals: bool = True,
        enable_api: bool | None = None,
    ) -> SchedulerDiagnostics:
        """Run the telemetry loop and HTTP API until stopped or max_duration reached."""
        installed_signals = self._install_signal_handlers() if install_signals else []
        self._input_listener.start()
        if isinstance(self._input_listener, SyntheticBurstEmitterProtocol):
            self._input_listener.emit_synthetic_burst()
        self._is_running = True
        self._stop_requested = False

        should_serve_api = self._config.enable_api if enable_api is None else enable_api
        uvicorn_server = (
            create_uvicorn_server(
                self._api_app,
                host=self._api_host,
                port=self._api_port,
            )
            if should_serve_api
            else None
        )
        api_task: asyncio.Task[None] | None = (
            asyncio.create_task(uvicorn_server.serve()) if uvicorn_server is not None else None
        )

        poll_interval = self._config.window_poll_interval_seconds
        emit_interval = self._config.emit_interval_seconds
        start_time = time.monotonic()
        last_emit_time = start_time

        try:
            while not self._stop_requested:
                now = time.monotonic()
                if max_duration_seconds is not None and (now - start_time) >= max_duration_seconds:
                    break

                # Poll active window
                proc_name = self._window_resolver.get_active_process_name()
                wid = self._window_resolver.get_active_window_id()
                self._buffer.record_window_tick(proc_name, poll_interval, window_id=wid)
                self._window_ticks_total += 1

                # Periodic emit
                if (now - last_emit_time) >= emit_interval:
                    self.evaluate_and_emit_once()
                    last_emit_time = now

                await asyncio.sleep(poll_interval)
        finally:
            self._is_running = False
            self._input_listener.stop()
            self._focus_tracer.end_current_focus()
            self._otel_manager.shutdown()

            if uvicorn_server is not None and api_task is not None:
                uvicorn_server.should_exit = True
                try:
                    await asyncio.wait_for(api_task, timeout=3.0)
                except (TimeoutError, asyncio.CancelledError):
                    api_task.cancel()
            self._remove_signal_handlers(installed_signals)

        return self.get_diagnostics()


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser for the local cognitive telemetry daemon."""
    parser = argparse.ArgumentParser(
        prog="egg-telemetry",
        description="EGG stateless cognitive host telemetry daemon (OpenTelemetry + Prometheus).",
    )
    parser.add_argument(
        "--simulate",
        "--synthetic",
        dest="simulate",
        action="store_true",
        help="Use deterministic synthetic input/window collectors for headless CI or testing.",
    )
    parser.add_argument(
        "--duration-seconds",
        "--duration",
        dest="duration_seconds",
        type=float,
        default=None,
        help="Optional bounded runtime in seconds before graceful exit (default: unbounded).",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=None,
        help=f"Loopback HTTP API port on 127.0.0.1 (default: {DEFAULT_API_PORT}).",
    )
    parser.add_argument(
        "--no-api",
        action="store_true",
        help="Disable the embedded localhost FastAPI/Prometheus HTTP server.",
    )
    parser.add_argument(
        "--no-otlp",
        action="store_true",
        help="Disable OTLP network exporters (in-memory mode for testing).",
    )
    return parser


async def run_from_cli(argv: Sequence[str] | None = None) -> SchedulerDiagnostics:
    """Parse CLI arguments, execute TelemetryService, and return final diagnostics."""
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    base_config = DaemonConfig.from_env(simulate=bool(args.simulate))
    api_port = int(args.api_port) if args.api_port is not None else base_config.api_port
    enable_api = False if bool(args.no_api) else base_config.enable_api
    enable_otlp = False if bool(args.no_otlp) else base_config.enable_otlp

    config = DaemonConfig(
        sliding_window_seconds=base_config.sliding_window_seconds,
        emit_interval_seconds=base_config.emit_interval_seconds,
        idle_event_threshold_seconds=base_config.idle_event_threshold_seconds,
        micro_pause_min_seconds=base_config.micro_pause_min_seconds,
        micro_pause_max_seconds=base_config.micro_pause_max_seconds,
        iki_min_outlier_ms=base_config.iki_min_outlier_ms,
        iki_max_outlier_ms=base_config.iki_max_outlier_ms,
        mouse_move_throttle_seconds=base_config.mouse_move_throttle_seconds,
        window_poll_interval_seconds=base_config.window_poll_interval_seconds,
        session_reset_idle_seconds=base_config.session_reset_idle_seconds,
        simulate=bool(args.simulate),
        api_host=base_config.api_host,
        api_port=api_port,
        enable_api=enable_api,
        otlp_endpoint=base_config.otlp_endpoint,
        enable_otlp=enable_otlp,
    )

    service = TelemetryService(config)
    max_duration: float | None = (
        float(args.duration_seconds) if args.duration_seconds is not None else None
    )
    return await service.run(max_duration_seconds=max_duration)
