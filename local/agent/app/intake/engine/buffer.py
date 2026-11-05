"""Thread-safe 30-second in-memory accumulator for ephemeral hardware and window ticks."""

import json
import threading
import time

from app.common.config import (
    IDLE_EVENT_THRESHOLD_SECONDS as DEFAULT_IDLE_EVENT_THRESHOLD_SECONDS,
)
from app.common.config import (
    IKI_MAX_OUTLIER_MS as DEFAULT_IKI_MAX_OUTLIER_MS,
)
from app.common.config import (
    MICRO_PAUSE_MAX_SECONDS as DEFAULT_MICRO_PAUSE_MAX_SECONDS,
)
from app.common.config import (
    MICRO_PAUSE_MIN_SECONDS as DEFAULT_MICRO_PAUSE_MIN_SECONDS,
)
from app.common.config import (
    MOUSE_MOVE_THROTTLE_SECONDS as DEFAULT_MOUSE_MOVE_THROTTLE_SECONDS,
)
from app.common.models import EpochSnapshot


class EpochBuffer:
    """Thread-safe volatile ring accumulator flushed every 30 seconds into SQLite WAL."""

    def __init__(
        self,
        *,
        idle_threshold_seconds: float = DEFAULT_IDLE_EVENT_THRESHOLD_SECONDS,
        micro_pause_min_seconds: float = DEFAULT_MICRO_PAUSE_MIN_SECONDS,
        micro_pause_max_seconds: float = DEFAULT_MICRO_PAUSE_MAX_SECONDS,
        iki_max_outlier_ms: float = DEFAULT_IKI_MAX_OUTLIER_MS,
        mouse_move_throttle_seconds: float = DEFAULT_MOUSE_MOVE_THROTTLE_SECONDS,
    ) -> None:
        self._idle_threshold = idle_threshold_seconds
        self._micro_pause_min = micro_pause_min_seconds
        self._micro_pause_max = micro_pause_max_seconds
        self._iki_max_outlier_ms = iki_max_outlier_ms
        self._mouse_move_throttle = mouse_move_throttle_seconds

        self._lock = threading.Lock()
        self._active_seconds: float = 0.0
        self._micro_pause_count: int = 0
        self._mouse_click_count: int = 0
        self._scroll_count: int = 0
        self._context_switch_count: int = 0
        self._dwell_by_process: dict[str, float] = {}
        self._last_process: str | None = None

        self._total_keystrokes: int = 0
        self._correction_keystrokes: int = 0
        self._iki_count: int = 0
        self._iki_sum_ms: float = 0.0
        self._iki_sum_sq_ms: float = 0.0

        self._last_input_time: float | None = None
        self._last_key_time: float | None = None
        self._last_mouse_move_time: float | None = None

    def _register_input_timestamp_unlocked(self, now: float) -> None:
        """Update active_seconds and micro_pause_count from inter-event gap delta_t."""
        if self._last_input_time is not None:
            delta_sec = now - self._last_input_time
            if delta_sec > 0.0:
                if delta_sec <= self._idle_threshold:
                    self._active_seconds += delta_sec
                if self._micro_pause_min <= delta_sec <= self._micro_pause_max:
                    self._micro_pause_count += 1
        self._last_input_time = now

    def record_key(
        self,
        *,
        is_correction: bool,
        delta_ms: float | None = None,
        event_time: float | None = None,
    ) -> None:
        """Record a keydown event without storing any character or keycode content."""
        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            self._register_input_timestamp_unlocked(now)
            self._total_keystrokes += 1
            if is_correction:
                self._correction_keystrokes += 1

            computed_delta_ms = delta_ms
            if computed_delta_ms is None and self._last_key_time is not None:
                computed_delta_ms = (now - self._last_key_time) * 1000.0
            self._last_key_time = now

            if (
                computed_delta_ms is not None
                and 0.0 < computed_delta_ms <= self._iki_max_outlier_ms
            ):
                self._iki_count += 1
                self._iki_sum_ms += computed_delta_ms
                self._iki_sum_sq_ms += computed_delta_ms * computed_delta_ms

    def record_mouse_click(self, *, event_time: float | None = None) -> None:
        """Record a mouse button press event."""
        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            self._mouse_click_count += 1
            self._register_input_timestamp_unlocked(now)

    def record_mouse_scroll(self, *, event_time: float | None = None) -> None:
        """Record a mouse wheel or trackpad scroll event (active reading progression)."""
        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            self._scroll_count += 1
            self._register_input_timestamp_unlocked(now)

    def record_mouse_move(self, *, event_time: float | None = None) -> None:
        """Record a mouse movement tick throttled to 4Hz (250ms)."""
        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            if (
                self._last_mouse_move_time is not None
                and (now - self._last_mouse_move_time) < self._mouse_move_throttle
            ):
                return
            self._last_mouse_move_time = now
            self._register_input_timestamp_unlocked(now)

    def record_window_tick(self, process_name: str, duration_seconds: float) -> None:
        """Accumulate foreground dwell time and context switches for a sanitized process."""
        if duration_seconds <= 0.0:
            return
        clean_proc = process_name.strip() or "unknown"
        with self._lock:
            if self._last_process is not None and self._last_process != clean_proc:
                self._context_switch_count += 1
            self._last_process = clean_proc
            self._dwell_by_process[clean_proc] = (
                self._dwell_by_process.get(clean_proc, 0.0) + duration_seconds
            )

    def harvest_and_reset(
        self,
        timestamp_start: float,
        timestamp_end: float,
    ) -> EpochSnapshot:
        """Atomically snapshot the current 30s epoch into an EpochSnapshot and reset."""
        epoch_span = max(0.0, timestamp_end - timestamp_start)
        with self._lock:
            clamped_active = min(epoch_span, max(0.0, self._active_seconds))
            if self._dwell_by_process:
                primary_process = max(
                    self._dwell_by_process.items(),
                    key=lambda item: item[1],
                )[0]
            else:
                primary_process = self._last_process or "idle"

            dwell_json = json.dumps(
                {proc: round(sec, 4) for proc, sec in self._dwell_by_process.items()},
                sort_keys=True,
            )

            dto = EpochSnapshot(
                timestamp_start=timestamp_start,
                timestamp_end=timestamp_end,
                primary_process=primary_process,
                active_seconds=round(clamped_active, 4),
                micro_pause_count=self._micro_pause_count,
                mouse_click_count=self._mouse_click_count,
                scroll_count=self._scroll_count,
                context_switch_count=self._context_switch_count,
                dwell_distribution_json=dwell_json,
                total_keystrokes=self._total_keystrokes,
                correction_keystrokes=self._correction_keystrokes,
                iki_count=self._iki_count,
                iki_sum_ms=round(self._iki_sum_ms, 4),
                iki_sum_sq_ms=round(self._iki_sum_sq_ms, 4),
            )

            # Reset per-epoch accumulators while keeping last_process continuity
            self._active_seconds = 0.0
            self._micro_pause_count = 0
            self._mouse_click_count = 0
            self._scroll_count = 0
            self._context_switch_count = 0
            self._dwell_by_process.clear()
            self._total_keystrokes = 0
            self._correction_keystrokes = 0
            self._iki_count = 0
            self._iki_sum_ms = 0.0
            self._iki_sum_sq_ms = 0.0
            self._last_input_time = None
            self._last_key_time = None
            self._last_mouse_move_time = None

            return dto
