"""Root lifecycle supervisor ('I'll say when') wiring intake -> storage -> output."""

import argparse
import asyncio
import signal
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.common import (
    DEFAULT_API_PORT,
    DEFAULT_DATABASE_PATH,
    EPOCH_DURATION_SECONDS,
    ActivityBlockDTO,
    DaemonConfig,
    DailySummaryPayload,
    DimensionEvaluation,
    EpochSnapshot,
    InputListenerProtocol,
    PooledTelemetryMetrics,
    SchedulerDiagnostics,
    WindowResolverProtocol,
)
from app.intake.collectors import (
    create_input_listener,
    create_window_resolver,
)
from app.intake.engine import (
    ActivityBlockChunker,
    BlockSealedCallback,
    EpochBuffer,
    EpochFlushCallback,
    EpochScheduler,
    SREObservabilityRecorder,
    evaluate_sre_health,
)
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
from app.storage import EpochRepository


def compute_local_day_bounds(reference_timestamp: float | None = None) -> tuple[float, float]:
    """Compute local calendar midnight start and 23:59:59.999999 end unix timestamps."""
    ref = reference_timestamp if reference_timestamp is not None else time.time()
    local_dt = datetime.fromtimestamp(ref).astimezone()
    midnight = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = midnight.timestamp()
    day_end = day_start + 86400.0
    return day_start, day_end


class TelemetryService:
    """Root supervisor ('I'll say when') wiring intake, storage, and output branches."""

    def __init__(
        self,
        config: DaemonConfig,
        *,
        buffer: EpochBuffer | None = None,
        repository: EpochRepository | None = None,
        input_listener: InputListenerProtocol | None = None,
        window_resolver: WindowResolverProtocol | None = None,
        dimension_registry: DimensionRegistry | None = None,
        observability: SREObservabilityRecorder | None = None,
        on_epoch_flushed: EpochFlushCallback | None = None,
        on_block_sealed: BlockSealedCallback | None = None,
        flush_on_shutdown: bool = True,
    ) -> None:
        self._config = config
        self._flush_on_shutdown = flush_on_shutdown
        self._api_host = validate_loopback_host(config.api_host)
        self._api_port = validate_port(config.api_port)

        self._buffer = (
            buffer
            if buffer is not None
            else EpochBuffer(
                idle_threshold_seconds=config.idle_event_threshold_seconds,
                micro_pause_min_seconds=config.micro_pause_min_seconds,
                micro_pause_max_seconds=config.micro_pause_max_seconds,
                iki_max_outlier_ms=config.iki_max_outlier_ms,
                mouse_move_throttle_seconds=config.mouse_move_throttle_seconds,
            )
        )
        self._repository = (
            repository if repository is not None else EpochRepository(config.database_path)
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
        self._dimensions = (
            dimension_registry if dimension_registry is not None else create_default_registry()
        )
        self._observability = (
            observability if observability is not None else SREObservabilityRecorder()
        )

        def _evaluate_block(
            epochs: Sequence[EpochSnapshot],
            *,
            prior_epochs_today: Sequence[EpochSnapshot] = (),
        ) -> tuple[PooledTelemetryMetrics, dict[str, DimensionEvaluation]]:
            pooled = self._repository.pool_epochs(epochs)
            ctx = DimensionContext.from_epochs(
                epochs,
                prior_epochs_today=prior_epochs_today,
                pooled=pooled,
            )
            return pooled, self._dimensions.evaluate_all(ctx)

        self._chunker = ActivityBlockChunker(
            block_repository=self._repository,
            block_evaluator=_evaluate_block,
            observability=self._observability,
            on_block_sealed=on_block_sealed,
        )

        async def _combined_flush_hook(snapshot: EpochSnapshot) -> None:
            await self._chunker.ingest_epoch(snapshot)
            if on_epoch_flushed is not None:
                maybe_coro = on_epoch_flushed(snapshot)
                if maybe_coro is not None:
                    await maybe_coro

        self._scheduler = EpochScheduler(
            buffer=self._buffer,
            repository=self._repository,
            window_resolver=self._window_resolver,
            input_listener=self._input_listener,
            epoch_duration_seconds=config.epoch_duration_seconds,
            window_poll_interval_seconds=config.window_poll_interval_seconds,
            on_epoch_flushed=_combined_flush_hook,
        )
        self._api_app = create_api_app(self)

    @property
    def config(self) -> DaemonConfig:
        """Active immutable daemon configuration."""
        return self._config

    @property
    def buffer(self) -> EpochBuffer:
        """In-memory 30s epoch buffer (Intake)."""
        return self._buffer

    @property
    def input_listener(self) -> InputListenerProtocol:
        """Hardware or synthetic keyboard/mouse listener (Intake)."""
        return self._input_listener

    @property
    def window_resolver(self) -> WindowResolverProtocol:
        """Foreground window process resolver (Intake)."""
        return self._window_resolver

    @property
    def scheduler(self) -> EpochScheduler:
        """Monotonic 30s scheduler (Intake)."""
        return self._scheduler

    @property
    def chunker(self) -> ActivityBlockChunker:
        """60s/90s Hysteresis Activity Block Chunker (Intake)."""
        return self._chunker

    @property
    def repository(self) -> EpochRepository:
        """SQLite WAL repository for raw epochs and activity blocks (Storage)."""
        return self._repository

    @property
    def storage(self) -> EpochRepository:
        """Alias for repository (Raw Material Store)."""
        return self._repository

    @property
    def dimensions(self) -> DimensionRegistry:
        """4-Dimension Scientific Engine registry (Output)."""
        return self._dimensions

    @property
    def observability(self) -> SREObservabilityRecorder:
        """SRE observability recorder emitting JSON events and Prometheus metrics."""
        return self._observability

    @property
    def api_app(self) -> FastAPI:
        """FastAPI application instance serving 127.0.0.1:8765 (Output)."""
        return self._api_app

    @property
    def api_host(self) -> str:
        """Validated loopback host address."""
        return self._api_host

    @property
    def api_port(self) -> int:
        """Validated TCP port."""
        return self._api_port

    def diagnostics(self) -> SchedulerDiagnostics:
        """Return privacy-safe operational diagnostics from the underlying scheduler."""
        return self._scheduler.diagnostics()

    # --- TelemetryGatewayBackendProtocol methods consumed by app/output/api/ ---

    def get_diagnostics(self) -> SchedulerDiagnostics:
        """Return operational scheduler diagnostics for the localhost API."""
        return self.diagnostics()

    def get_chunker_state(self) -> dict[str, Any]:
        """Return current hysteresis chunker counters for /api/v1/status."""
        return {
            "active_primary_process": self._chunker.active_primary_process,
            "active_epoch_count": len(self._chunker.active_epochs),
            "pending_excursion_epoch_count": len(self._chunker.pending_excursion_epochs),
            "blocks_sealed_total": self._chunker.blocks_sealed_total,
            "excursions_absorbed_total": self._chunker.excursions_absorbed_total,
        }

    async def get_activity_blocks(
        self,
        *,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int = 20,
    ) -> list[ActivityBlockDTO]:
        """Fetch sealed activity blocks by optional [start_time, end_time] or recent limit."""
        if start_time is not None and end_time is not None:
            return await self._repository.fetch_activity_blocks_in_range(start_time, end_time)
        return await self._repository.fetch_recent_activity_blocks(limit=limit)

    async def get_daily_summary(
        self,
        *,
        reference_timestamp: float | None = None,
    ) -> DailySummaryPayload:
        """Compute today's aggregated cognitive telemetry summary and SRE status."""
        day_start, day_end = compute_local_day_bounds(reference_timestamp)
        epochs_today = await self._repository.fetch_epochs_in_range(day_start, day_end)
        blocks_today = await self._repository.fetch_activity_blocks_in_range(day_start, day_end)

        pooled = self._repository.pool_epochs(epochs_today)
        if epochs_today:
            ctx = DimensionContext.from_epochs(epochs_today, pooled=pooled)
            evaluations = self._dimensions.evaluate_all(ctx)
            sre_report = evaluate_sre_health(evaluations)
            overall_strain = sre_report.overall_strain_score
            dominant_label = sre_report.dominant_state_label
            sre_status = sre_report.sre_status
            sre_reason = sre_report.sre_alert_reason
            triggered_dims = sre_report.triggered_dimensions
        else:
            evaluations = {}
            overall_strain = 0.0
            dominant_label = "idle_day"
            sre_status = "nominal"
            sre_reason = "No telemetry epochs recorded yet for this calendar day."
            triggered_dims = ()

        breakdown: dict[str, int] = {
            "flow_optimal": 0,
            "nominal": 0,
            "warning": 0,
            "critical": 0,
        }
        for block in blocks_today:
            breakdown[block.sre_status] = breakdown.get(block.sre_status, 0) + 1

        return DailySummaryPayload(
            day_start_timestamp=day_start,
            day_end_timestamp=day_end,
            epochs_count=len(epochs_today),
            blocks_count=len(blocks_today),
            excursions_absorbed_total=self._chunker.excursions_absorbed_total,
            pooled_metrics=pooled,
            overall_strain_score=overall_strain,
            dominant_state_label=dominant_label,
            sre_status=sre_status,
            sre_alert_reason=sre_reason,
            triggered_dimensions=triggered_dims,
            dimensions=evaluations,
            sre_status_breakdown=breakdown,
        )

    def render_prometheus_metrics(self) -> str:
        """Render Prometheus text exposition metrics."""
        return self._observability.render_prometheus_metrics()

    # --- Lifecycle & Signal Handling ---

    def request_stop(self) -> None:
        """Trigger a graceful stop of the scheduler loop."""
        self._scheduler.request_stop()

    def _install_signal_handlers(self) -> list[signal.Signals]:
        """Register SIGINT and SIGTERM handlers on the active asyncio event loop."""
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
        """Remove previously registered signal handlers on shutdown."""
        try:
            loop = asyncio.get_running_loop()
            for sig in installed:
                try:
                    loop.remove_signal_handler(sig)
                except (NotImplementedError, RuntimeError, ValueError):
                    continue
        except RuntimeError:
            pass

    async def run(
        self,
        *,
        max_duration_seconds: float | None = None,
        install_signals: bool = True,
        enable_api: bool | None = None,
    ) -> EpochSnapshot | None:
        """Initialize SQLite WAL, run telemetry + optional HTTP API, and flush data on exit."""
        await self._repository.initialize()
        installed_signals = self._install_signal_handlers() if install_signals else []
        self._input_listener.start()
        shutdown_dto: EpochSnapshot | None = None

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

        try:
            await self._scheduler.run(max_duration_seconds=max_duration_seconds)
        finally:
            self._input_listener.stop()
            if self._flush_on_shutdown:
                shutdown_dto = await self._scheduler.flush_now()
                await self._chunker.flush_active_block()
            if uvicorn_server is not None and api_task is not None:
                uvicorn_server.should_exit = True
                try:
                    await asyncio.wait_for(api_task, timeout=3.0)
                except (TimeoutError, asyncio.CancelledError):
                    api_task.cancel()
            self._remove_signal_handlers(installed_signals)

        return shutdown_dto


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser for the local cognitive telemetry daemon."""
    parser = argparse.ArgumentParser(
        prog="egg-local-agent",
        description="EGG local privacy-preserving 30-second cognitive telemetry daemon.",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Use deterministic synthetic input/window collectors for headless CI or demos.",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=None,
        help="Optional bounded runtime in seconds before graceful exit (default: unbounded).",
    )
    parser.add_argument(
        "--epoch-seconds",
        type=float,
        default=EPOCH_DURATION_SECONDS,
        help=f"Epoch flush interval in seconds (default: {EPOCH_DURATION_SECONDS}).",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(DEFAULT_DATABASE_PATH),
        help=f"Path to local SQLite WAL database (default: {DEFAULT_DATABASE_PATH}).",
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
    return parser


async def run_from_cli(argv: Sequence[str] | None = None) -> SchedulerDiagnostics:
    """Parse CLI arguments, execute TelemetryService, and return final diagnostics."""
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    base_config = DaemonConfig.from_env(simulate=bool(args.simulate))
    api_port = int(args.api_port) if args.api_port is not None else base_config.api_port
    enable_api = False if bool(args.no_api) else base_config.enable_api
    config = DaemonConfig(
        epoch_duration_seconds=float(args.epoch_seconds),
        idle_event_threshold_seconds=base_config.idle_event_threshold_seconds,
        micro_pause_min_seconds=base_config.micro_pause_min_seconds,
        micro_pause_max_seconds=base_config.micro_pause_max_seconds,
        iki_max_outlier_ms=base_config.iki_max_outlier_ms,
        mouse_move_throttle_seconds=base_config.mouse_move_throttle_seconds,
        window_poll_interval_seconds=base_config.window_poll_interval_seconds,
        database_path=Path(args.db_path),
        simulate=bool(args.simulate),
        api_host=base_config.api_host,
        api_port=api_port,
        enable_api=enable_api,
    )

    service = TelemetryService(config)
    max_duration: float | None = (
        float(args.duration_seconds) if args.duration_seconds is not None else None
    )
    await service.run(max_duration_seconds=max_duration)
    return service.diagnostics()
