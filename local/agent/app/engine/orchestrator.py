"""Folder orchestrator for the 30s EpochBuffer, monotonic EpochScheduler, and 60s/90s Chunker."""

from app.engine.buffer import EpochBuffer
from app.engine.chunker import ActivityBlockChunker, BlockSealedCallback
from app.engine.protocols import (
    DEFAULT_EPOCH_DURATION_SECONDS,
    DEFAULT_HYSTERESIS_SEAL_EPOCHS,
    DEFAULT_HYSTERESIS_TRANSIENT_MAX_EPOCHS,
    DEFAULT_WINDOW_POLL_INTERVAL_SECONDS,
    ActivityBlockPersistenceProtocol,
    BlockEvaluatorProtocol,
    EpochPersistenceProtocol,
    EpochSnapshot,
    InputLifecycleProtocol,
    SealedActivityBlock,
    WindowSourceProtocol,
)
from app.engine.scheduler import EpochFlushCallback, EpochScheduler, SchedulerDiagnostics
from app.engine.sre import SREObservabilityRecorder


class EngineOrchestrator:
    """Folder orchestrator coordinating accumulation, scheduling, chunking, and SRE metrics."""

    def __init__(
        self,
        *,
        buffer: EpochBuffer,
        scheduler: EpochScheduler,
        chunker: ActivityBlockChunker | None = None,
    ) -> None:
        self._buffer = buffer
        self._scheduler = scheduler
        self._chunker = chunker

    @classmethod
    def create(
        cls,
        *,
        buffer: EpochBuffer,
        repository: EpochPersistenceProtocol,
        window_resolver: WindowSourceProtocol,
        input_listener: InputLifecycleProtocol | None = None,
        block_repository: ActivityBlockPersistenceProtocol | None = None,
        block_evaluator: BlockEvaluatorProtocol | None = None,
        observability: SREObservabilityRecorder | None = None,
        transient_max_epochs: int = DEFAULT_HYSTERESIS_TRANSIENT_MAX_EPOCHS,
        seal_epochs: int = DEFAULT_HYSTERESIS_SEAL_EPOCHS,
        epoch_duration_seconds: float = DEFAULT_EPOCH_DURATION_SECONDS,
        window_poll_interval_seconds: float = DEFAULT_WINDOW_POLL_INTERVAL_SECONDS,
        on_epoch_flushed: EpochFlushCallback | None = None,
        on_block_sealed: BlockSealedCallback | None = None,
    ) -> "EngineOrchestrator":
        """Build an EngineOrchestrator wiring EpochBuffer, EpochScheduler, and Chunker."""
        chunker: ActivityBlockChunker | None = None
        if block_repository is not None and block_evaluator is not None:
            chunker = ActivityBlockChunker(
                block_repository=block_repository,
                block_evaluator=block_evaluator,
                observability=observability,
                transient_max_epochs=transient_max_epochs,
                seal_epochs=seal_epochs,
                on_block_sealed=on_block_sealed,
            )

        async def _combined_flush_hook(snapshot: EpochSnapshot) -> None:
            if chunker is not None:
                await chunker.ingest_epoch(snapshot)
            if on_epoch_flushed is not None:
                maybe_coro = on_epoch_flushed(snapshot)
                if maybe_coro is not None:
                    await maybe_coro

        effective_callback: EpochFlushCallback | None = (
            _combined_flush_hook if (chunker is not None or on_epoch_flushed is not None) else None
        )

        scheduler = EpochScheduler(
            buffer=buffer,
            repository=repository,
            window_resolver=window_resolver,
            input_listener=input_listener,
            epoch_duration_seconds=epoch_duration_seconds,
            window_poll_interval_seconds=window_poll_interval_seconds,
            on_epoch_flushed=effective_callback,
        )
        return cls(buffer=buffer, scheduler=scheduler, chunker=chunker)

    @property
    def buffer(self) -> EpochBuffer:
        """Volatile 30-second accumulator managed by this orchestrator."""
        return self._buffer

    @property
    def scheduler(self) -> EpochScheduler:
        """Monotonic 30-second scheduler managed by this orchestrator."""
        return self._scheduler

    @property
    def chunker(self) -> ActivityBlockChunker | None:
        """60s/90s Hysteresis Activity Block Chunker managed by this orchestrator."""
        return self._chunker

    def diagnostics(self) -> SchedulerDiagnostics:
        """Return operational health metrics from the underlying scheduler."""
        return self._scheduler.diagnostics()

    def request_stop(self) -> None:
        """Signal the monotonic scheduler loop to stop cleanly."""
        self._scheduler.request_stop()

    async def flush_now(self, *, timestamp_end: float | None = None) -> EpochSnapshot:
        """Force an immediate harvest and persistence flush of the active buffer."""
        return await self._scheduler.flush_now(timestamp_end=timestamp_end)

    async def flush_active_block(self) -> SealedActivityBlock | None:
        """Force-seal any open activity block in the hysteresis chunker."""
        if self._chunker is None:
            return None
        return await self._chunker.flush_active_block()

    async def run(self, *, max_duration_seconds: float | None = None) -> None:
        """Run the monotonic polling and flushing loop until stopped."""
        await self._scheduler.run(max_duration_seconds=max_duration_seconds)
