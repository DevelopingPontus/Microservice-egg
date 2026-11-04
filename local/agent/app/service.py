"""Root orchestrator and lifecycle supervisor for the 30-second cognitive telemetry daemon."""

import argparse
import asyncio
import signal
from collections.abc import Sequence
from pathlib import Path

from app.collectors import (
    CollectorCoordinator,
    InputListenerProtocol,
    WindowResolverProtocol,
)
from app.config import (
    DEFAULT_DATABASE_PATH,
    EPOCH_DURATION_SECONDS,
    DaemonConfig,
)
from app.dimensions import (
    DimensionContext,
    DimensionEvaluation,
    DimensionRegistry,
    create_default_registry,
)
from app.engine import (
    ActivityBlockChunker,
    BlockSealedCallback,
    EngineOrchestrator,
    EpochBuffer,
    EpochFlushCallback,
    EpochScheduler,
    EpochSnapshot,
    SchedulerDiagnostics,
    SREObservabilityRecorder,
)
from app.storage import (
    EpochRepository,
    PooledTelemetryMetrics,
    StorageOrchestrator,
)


class TelemetryService:
    """Root orchestrator wiring collectors, engine, storage, and scientific dimensions."""

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

        resolved_buffer = (
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
        self._storage = StorageOrchestrator(
            config.database_path,
            repository=repository,
        )
        self._collectors = CollectorCoordinator.create(
            resolved_buffer,
            simulate=config.simulate,
            input_listener=input_listener,
            window_resolver=window_resolver,
        )
        self._dimensions = (
            dimension_registry if dimension_registry is not None else create_default_registry()
        )

        def _evaluate_block(
            epochs: Sequence[EpochSnapshot],
            *,
            prior_epochs_today: Sequence[EpochSnapshot] = (),
        ) -> tuple[PooledTelemetryMetrics, dict[str, DimensionEvaluation]]:
            pooled = self._storage.pool_epochs(epochs)
            ctx = DimensionContext.from_epochs(
                epochs,
                prior_epochs_today=prior_epochs_today,
                pooled=pooled,
            )
            return pooled, self._dimensions.evaluate_all(ctx)

        self._engine = EngineOrchestrator.create(
            buffer=resolved_buffer,
            repository=self._storage,
            window_resolver=self._collectors.window_resolver,
            input_listener=self._collectors.input_listener,
            block_repository=self._storage,
            block_evaluator=_evaluate_block,
            observability=observability,
            epoch_duration_seconds=config.epoch_duration_seconds,
            window_poll_interval_seconds=config.window_poll_interval_seconds,
            on_epoch_flushed=on_epoch_flushed,
            on_block_sealed=on_block_sealed,
        )

    @property
    def config(self) -> DaemonConfig:
        """Active immutable daemon configuration."""
        return self._config

    @property
    def collectors(self) -> CollectorCoordinator:
        """Folder orchestrator for hardware and window collectors."""
        return self._collectors

    @property
    def engine(self) -> EngineOrchestrator:
        """Folder orchestrator for the 30s buffer and monotonic scheduler."""
        return self._engine

    @property
    def storage(self) -> StorageOrchestrator:
        """Folder orchestrator for SQLite WAL persistence and math pooling."""
        return self._storage

    @property
    def dimensions(self) -> DimensionRegistry:
        """Folder orchestrator for the 4-Dimension Scientific Engine."""
        return self._dimensions

    @property
    def buffer(self) -> EpochBuffer:
        """In-memory 30s epoch buffer managed by this service."""
        return self._engine.buffer

    @property
    def repository(self) -> EpochRepository:
        """SQLite WAL epoch repository managed by this service."""
        return self._storage.repository

    @property
    def scheduler(self) -> EpochScheduler:
        """Monotonic 30s scheduler managed by this service."""
        return self._engine.scheduler

    @property
    def chunker(self) -> ActivityBlockChunker | None:
        """60s/90s Hysteresis Activity Block Chunker managed by this service."""
        return self._engine.chunker

    def diagnostics(self) -> SchedulerDiagnostics:
        """Return privacy-safe operational diagnostics from the underlying engine."""
        return self._engine.diagnostics()

    def request_stop(self) -> None:
        """Trigger a graceful stop of the engine loop."""
        self._engine.request_stop()

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
    ) -> EpochSnapshot | None:
        """Initialize SQLite WAL, run the telemetry loop, and flush in-flight data on exit."""
        await self._storage.initialize()
        installed_signals = self._install_signal_handlers() if install_signals else []
        self._collectors.start()
        shutdown_dto: EpochSnapshot | None = None

        try:
            await self._engine.run(max_duration_seconds=max_duration_seconds)
        finally:
            self._collectors.stop()
            if self._flush_on_shutdown:
                shutdown_dto = await self._engine.flush_now()
                await self._engine.flush_active_block()
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
        help="Use deterministic synthetic input/window collectors for headless CI or Docker.",
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
    return parser


async def run_from_cli(argv: Sequence[str] | None = None) -> SchedulerDiagnostics:
    """Parse CLI arguments, execute TelemetryService, and return final diagnostics."""
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    base_config = DaemonConfig.from_env(simulate=bool(args.simulate))
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
    )

    service = TelemetryService(config)
    max_duration: float | None = (
        float(args.duration_seconds) if args.duration_seconds is not None else None
    )
    await service.run(max_duration_seconds=max_duration)
    return service.diagnostics()
