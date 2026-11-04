"""Monotonic 30-second epoch scheduler, 4Hz window poller, and SRE health diagnostics."""

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.engine.buffer import EpochBuffer
from app.engine.protocols import (
    DEFAULT_EPOCH_DURATION_SECONDS,
    DEFAULT_WINDOW_POLL_INTERVAL_SECONDS,
    EpochPersistenceProtocol,
    EpochSnapshot,
    InputLifecycleProtocol,
    SyntheticBurstSourceProtocol,
    WindowSourceProtocol,
)

EpochFlushCallback = Callable[[Any], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class SchedulerDiagnostics:
    """Privacy-safe operational health metrics for SRE monitoring (/health & Prometheus)."""

    is_running: bool
    epochs_flushed_total: int
    window_ticks_total: int
    last_flush_duration_ms: float
    last_flush_timestamp: float | None


class EpochScheduler:
    """Drift-free monotonic coordinator for 4Hz window polling and 30s SQLite WAL flushes."""

    def __init__(
        self,
        *,
        buffer: EpochBuffer,
        repository: EpochPersistenceProtocol,
        window_resolver: WindowSourceProtocol,
        input_listener: InputLifecycleProtocol | None = None,
        epoch_duration_seconds: float = DEFAULT_EPOCH_DURATION_SECONDS,
        window_poll_interval_seconds: float = DEFAULT_WINDOW_POLL_INTERVAL_SECONDS,
        on_epoch_flushed: EpochFlushCallback | None = None,
    ) -> None:
        if epoch_duration_seconds <= 0.0:
            raise ValueError("epoch_duration_seconds must be strictly positive")
        if window_poll_interval_seconds <= 0.0:
            raise ValueError("window_poll_interval_seconds must be strictly positive")

        self._buffer = buffer
        self._repository = repository
        self._window_resolver = window_resolver
        self._input_listener = input_listener
        self._epoch_duration = epoch_duration_seconds
        self._poll_interval = window_poll_interval_seconds
        self._on_epoch_flushed = on_epoch_flushed

        self._stop_event = asyncio.Event()
        self._flush_lock = asyncio.Lock()
        self._is_running: bool = False
        self._epochs_flushed_total: int = 0
        self._window_ticks_total: int = 0
        self._last_flush_duration_ms: float = 0.0
        self._last_flush_timestamp: float | None = None
        self._epoch_wall_start: float = time.time()

    @property
    def is_running(self) -> bool:
        """Return True while the scheduler event loop is active."""
        return self._is_running

    def diagnostics(self) -> SchedulerDiagnostics:
        """Snapshot privacy-safe operational counters without exposing user telemetry."""
        return SchedulerDiagnostics(
            is_running=self._is_running,
            epochs_flushed_total=self._epochs_flushed_total,
            window_ticks_total=self._window_ticks_total,
            last_flush_duration_ms=round(self._last_flush_duration_ms, 4),
            last_flush_timestamp=self._last_flush_timestamp,
        )

    def request_stop(self) -> None:
        """Signal the scheduler loops to exit cleanly at the next tick boundary."""
        self._stop_event.set()

    def poll_window_once(self, elapsed_seconds: float | None = None) -> str:
        """Sample the active foreground process once and record its dwell tick."""
        duration = elapsed_seconds if elapsed_seconds is not None else self._poll_interval
        process_name = self._window_resolver.get_active_process_name()
        self._buffer.record_window_tick(process_name, duration)
        self._window_ticks_total += 1
        return process_name

    async def flush_now(self, *, timestamp_end: float | None = None) -> EpochSnapshot:
        """Atomically harvest the in-memory EpochBuffer and persist to SQLite WAL."""
        async with self._flush_lock:
            flush_mono_start = time.monotonic()
            wall_end = timestamp_end if timestamp_end is not None else time.time()
            wall_start = min(self._epoch_wall_start, wall_end)

            dto = self._buffer.harvest_and_reset(
                timestamp_start=wall_start,
                timestamp_end=wall_end,
            )
            row_id = await self._repository.insert_epoch(dto)
            persisted_dto = dto.with_id(row_id)

            self._epoch_wall_start = wall_end
            self._epochs_flushed_total += 1
            self._last_flush_timestamp = wall_end
            self._last_flush_duration_ms = (time.monotonic() - flush_mono_start) * 1000.0

            if self._on_epoch_flushed is not None:
                maybe_awaitable = self._on_epoch_flushed(persisted_dto)
                if inspect.isawaitable(maybe_awaitable):
                    await maybe_awaitable

            return persisted_dto

    async def _sleep_or_stop(self, delay_seconds: float) -> bool:
        """Wait up to delay_seconds or return True early if stop was requested."""
        if delay_seconds <= 0.0:
            return self._stop_event.is_set()
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay_seconds)
            return True
        except TimeoutError:
            return False

    async def run(self, *, max_duration_seconds: float | None = None) -> None:
        """Run the monotonic 4Hz window poll and 30s epoch flush loop until stopped."""
        self._stop_event.clear()
        self._is_running = True
        start_mono = time.monotonic()
        next_poll_mono = start_mono
        next_flush_mono = start_mono + self._epoch_duration
        self._epoch_wall_start = time.time()
        synthetic_emitted_for_epoch = False

        try:
            while not self._stop_event.is_set():
                now_mono = time.monotonic()
                if (
                    max_duration_seconds is not None
                    and (now_mono - start_mono) >= max_duration_seconds
                ):
                    break

                # Emit one deterministic synthetic input burst per epoch in --simulate mode
                if (
                    not synthetic_emitted_for_epoch
                    and isinstance(self._input_listener, SyntheticBurstSourceProtocol)
                    and self._input_listener.is_running
                ):
                    self._input_listener.emit_synthetic_burst()
                    synthetic_emitted_for_epoch = True

                # Execute due 4Hz foreground window poll
                if now_mono >= next_poll_mono:
                    self.poll_window_once(self._poll_interval)
                    next_poll_mono += self._poll_interval
                    if next_poll_mono < now_mono:
                        next_poll_mono = now_mono + self._poll_interval

                # Execute due 30s epoch flush
                now_mono = time.monotonic()
                if now_mono >= next_flush_mono:
                    await self.flush_now()
                    synthetic_emitted_for_epoch = False
                    next_flush_mono += self._epoch_duration
                    if next_flush_mono <= now_mono:
                        next_flush_mono = now_mono + self._epoch_duration

                # Compute sleep until next event (poll, flush, or max_duration deadline)
                now_mono = time.monotonic()
                next_wake_mono = min(next_poll_mono, next_flush_mono)
                if max_duration_seconds is not None:
                    deadline_mono = start_mono + max_duration_seconds
                    next_wake_mono = min(next_wake_mono, deadline_mono)

                await self._sleep_or_stop(max(0.0, next_wake_mono - now_mono))
        finally:
            self._is_running = False
