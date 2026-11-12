"""Root coordinator combining `collector/`, `analysis/`, `exporters/`, and `api/`."""

import argparse
import asyncio
import dataclasses
import signal
import time
from collections.abc import Sequence

from fastapi import FastAPI

from app.analysis import (
    CognitiveAnalyzer,
    CognitiveState,
    CognitiveStrainReport,
    OverviewDimensionsSnapshot,
    StatefulOverviewEngine,
)
from app.api import (
    SchedulerDiagnostics,
    TelemetryGatewayBackendProtocol,
    create_api_app,
    create_uvicorn_server,
    validate_loopback_host,
    validate_port,
)
from app.collector import (
    ActivityCollector,
    InputListenerProtocol,
    PooledTelemetryMetrics,
    SlidingWindowBuffer,
    WindowResolverProtocol,
)
from app.config import DEFAULT_API_PORT, DaemonConfig
from app.exporters import (
    CognitiveMetricsRecorder,
    FocusSessionTracer,
    OTelTelemetryManager,
    SREEventLogger,
    TelemetryExporter,
)


class TelemetryService(TelemetryGatewayBackendProtocol):
    """Root coordinator combining collector, analysis, exporters, and api."""

    def __init__(
        self,
        config: DaemonConfig,
        *,
        collector: ActivityCollector | None = None,
        analyzer: CognitiveAnalyzer | None = None,
        exporter: TelemetryExporter | None = None,
        buffer: SlidingWindowBuffer | None = None,
        input_listener: InputListenerProtocol | None = None,
        window_resolver: WindowResolverProtocol | None = None,
        overview_engine: StatefulOverviewEngine | None = None,
        otel_manager: OTelTelemetryManager | None = None,
        metrics_recorder: CognitiveMetricsRecorder | None = None,
        focus_tracer: FocusSessionTracer | None = None,
        sre_logger: SREEventLogger | None = None,
    ) -> None:
        self._config = config
        self._api_host = validate_loopback_host(config.api_host)
        self._api_port = validate_port(config.api_port)

        self.collector = (
            collector
            if collector is not None
            else ActivityCollector(
                config,
                buffer=buffer,
                input_listener=input_listener,
                window_resolver=window_resolver,
            )
        )
        self.analyzer = (
            analyzer if analyzer is not None else CognitiveAnalyzer(overview_engine=overview_engine)
        )
        self.exporter = (
            exporter
            if exporter is not None
            else TelemetryExporter(
                config,
                otel_manager=otel_manager,
                metrics_recorder=metrics_recorder,
                focus_tracer=focus_tracer,
                sre_logger=sre_logger,
            )
        )

        self._is_running = False
        self._stop_requested = False
        self._samples_emitted_total = 0
        self._window_ticks_total = 0
        self._last_emit_timestamp: float | None = None

        self._api_app = create_api_app(self)

    @property
    def config(self) -> DaemonConfig:
        return self._config

    @property
    def buffer(self) -> SlidingWindowBuffer:
        return self.collector.buffer

    @property
    def input_listener(self) -> InputListenerProtocol:
        return self.collector.input_listener

    @property
    def window_resolver(self) -> WindowResolverProtocol:
        return self.collector.window_resolver

    @property
    def overview_engine(self) -> StatefulOverviewEngine:
        return self.analyzer.overview_engine

    @property
    def last_state(self) -> CognitiveState | None:
        return self.analyzer.last_state

    @property
    def last_overview_snapshot(self) -> OverviewDimensionsSnapshot | None:
        return self.analyzer.last_state.workflow if self.analyzer.last_state is not None else None

    @property
    def metrics_recorder(self) -> CognitiveMetricsRecorder:
        return self.exporter.metrics_recorder

    @property
    def focus_tracer(self) -> FocusSessionTracer:
        return self.exporter.focus_tracer

    @property
    def sre_logger(self) -> SREEventLogger:
        return self.exporter.sre_logger

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
        return self.exporter.render_prometheus_metrics()

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
        """Commit 60s snapshot, evaluate cognitive state, and publish to exporters."""
        snapshot = self.collector.commit_snapshot()
        state = self.analyzer.evaluate(snapshot)
        self.exporter.publish(snapshot, state)

        self._samples_emitted_total += 1
        self._last_emit_timestamp = snapshot.now_timestamp
        return snapshot.metrics, state.strain

    async def run(
        self,
        *,
        max_duration_seconds: float | None = None,
        install_signals: bool = True,
        enable_api: bool | None = None,
    ) -> SchedulerDiagnostics:
        """Run the telemetry loop and HTTP API until stopped or max_duration reached."""
        installed_signals = self._install_signal_handlers() if install_signals else []
        self.collector.start()
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

                self.collector.poll_window(poll_interval)
                self._window_ticks_total += 1

                if (now - last_emit_time) >= emit_interval:
                    self.evaluate_and_emit_once()
                    last_emit_time = now

                await asyncio.sleep(poll_interval)
        finally:
            self._is_running = False
            self.collector.stop()
            self.exporter.shutdown()

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

    config = dataclasses.replace(
        base_config,
        simulate=bool(args.simulate),
        api_port=api_port,
        enable_api=enable_api,
        enable_otlp=enable_otlp,
    )

    service = TelemetryService(config)
    max_duration: float | None = (
        float(args.duration_seconds) if args.duration_seconds is not None else None
    )
    return await service.run(max_duration_seconds=max_duration)
