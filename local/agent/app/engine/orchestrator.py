"""Folder orchestrator for the 30-second EpochBuffer and monotonic EpochScheduler."""

from app.engine.buffer import EpochBuffer
from app.engine.protocols import (
    DEFAULT_EPOCH_DURATION_SECONDS,
    DEFAULT_WINDOW_POLL_INTERVAL_SECONDS,
    EpochPersistenceProtocol,
    EpochSnapshot,
    InputLifecycleProtocol,
    WindowSourceProtocol,
)
from app.engine.scheduler import EpochFlushCallback, EpochScheduler, SchedulerDiagnostics


class EngineOrchestrator:
    """Folder orchestrator coordinating in-memory accumulation and monotonic scheduling."""

    def __init__(
        self,
        *,
        buffer: EpochBuffer,
        scheduler: EpochScheduler,
    ) -> None:
        self._buffer = buffer
        self._scheduler = scheduler

    @classmethod
    def create(
        cls,
        *,
        buffer: EpochBuffer,
        repository: EpochPersistenceProtocol,
        window_resolver: WindowSourceProtocol,
        input_listener: InputLifecycleProtocol | None = None,
        epoch_duration_seconds: float = DEFAULT_EPOCH_DURATION_SECONDS,
        window_poll_interval_seconds: float = DEFAULT_WINDOW_POLL_INTERVAL_SECONDS,
        on_epoch_flushed: EpochFlushCallback | None = None,
    ) -> "EngineOrchestrator":
        """Build an EngineOrchestrator wiring the EpochBuffer into an EpochScheduler."""
        scheduler = EpochScheduler(
            buffer=buffer,
            repository=repository,
            window_resolver=window_resolver,
            input_listener=input_listener,
            epoch_duration_seconds=epoch_duration_seconds,
            window_poll_interval_seconds=window_poll_interval_seconds,
            on_epoch_flushed=on_epoch_flushed,
        )
        return cls(buffer=buffer, scheduler=scheduler)

    @property
    def buffer(self) -> EpochBuffer:
        """Volatile 30-second accumulator managed by this orchestrator."""
        return self._buffer

    @property
    def scheduler(self) -> EpochScheduler:
        """Monotonic 30-second scheduler managed by this orchestrator."""
        return self._scheduler

    def diagnostics(self) -> SchedulerDiagnostics:
        """Return operational health metrics from the underlying scheduler."""
        return self._scheduler.diagnostics()

    def request_stop(self) -> None:
        """Signal the monotonic scheduler loop to stop cleanly."""
        self._scheduler.request_stop()

    async def flush_now(self, *, timestamp_end: float | None = None) -> EpochSnapshot:
        """Force an immediate harvest and persistence flush of the active buffer."""
        return await self._scheduler.flush_now(timestamp_end=timestamp_end)

    async def run(self, *, max_duration_seconds: float | None = None) -> None:
        """Run the monotonic polling and flushing loop until stopped."""
        await self._scheduler.run(max_duration_seconds=max_duration_seconds)
