"""Thread-safe in-memory sliding window accumulator for cognitive telemetry signals."""

import threading
import time

from app.common.config import (
    AWAY_IDLE_THRESHOLD_SECONDS,
    IDLE_EVENT_THRESHOLD_SECONDS,
    IKI_MAX_OUTLIER_MS,
    IKI_MIN_OUTLIER_MS,
    MICRO_PAUSE_MAX_SECONDS,
    MICRO_PAUSE_MIN_SECONDS,
    MOUSE_MOVE_THROTTLE_SECONDS,
    READING_THOUGHT_GRACE_SECONDS,
    SESSION_RESET_IDLE_SECONDS,
    SLIDING_WINDOW_SECONDS,
)
from app.common.models import (
    PooledTelemetryMetrics,
    TelemetrySample,
    pool_telemetry_samples,
)


class SlidingWindowBuffer:
    """Thread-safe in-memory sliding window accumulator for cognitive telemetry signals.

    Implements InputTickSinkProtocol. Maintains both monotonic lifetime counters
    (for Prometheus Counter metrics) and a sliding window of recent telemetry samples
    (for Gauge and calculation of instantaneous cognitive strain).
    """

    def __init__(
        self,
        *,
        window_duration_seconds: float = SLIDING_WINDOW_SECONDS,
        idle_threshold_seconds: float = IDLE_EVENT_THRESHOLD_SECONDS,
        micro_pause_min_seconds: float = MICRO_PAUSE_MIN_SECONDS,
        micro_pause_max_seconds: float = MICRO_PAUSE_MAX_SECONDS,
        iki_min_outlier_ms: float = IKI_MIN_OUTLIER_MS,
        iki_max_outlier_ms: float = IKI_MAX_OUTLIER_MS,
        mouse_move_throttle_seconds: float = MOUSE_MOVE_THROTTLE_SECONDS,
        session_reset_idle_seconds: float = SESSION_RESET_IDLE_SECONDS,
        reading_thought_grace_seconds: float = READING_THOUGHT_GRACE_SECONDS,
        away_idle_threshold_seconds: float = AWAY_IDLE_THRESHOLD_SECONDS,
    ) -> None:
        self._window_duration = window_duration_seconds
        self._idle_threshold = idle_threshold_seconds
        self._micro_pause_min = micro_pause_min_seconds
        self._micro_pause_max = micro_pause_max_seconds
        self._iki_min_outlier_ms = iki_min_outlier_ms
        self._iki_max_outlier_ms = iki_max_outlier_ms
        self._mouse_move_throttle = mouse_move_throttle_seconds
        self._session_reset_idle = session_reset_idle_seconds
        self._reading_thought_grace = reading_thought_grace_seconds
        self._away_idle_threshold = away_idle_threshold_seconds

        self._lock = threading.Lock()

        # Monotonic counters (since daemon startup)
        self._lifetime_keystrokes: int = 0
        self._lifetime_corrections: int = 0
        self._lifetime_mouse_clicks: int = 0
        self._lifetime_scroll_events: int = 0
        self._lifetime_context_switches: int = 0
        self._lifetime_active_seconds: float = 0.0
        self._lifetime_idle_seconds: float = 0.0
        self._lifetime_active_work_seconds: float = 0.0
        self._lifetime_away_idle_seconds: float = 0.0

        # Session continuity state
        self._session_start_time: float = time.monotonic()
        self._last_active_time: float = time.monotonic()

        # Active slice state
        self._slice_start_time: float = time.monotonic()
        self._active_seconds: float = 0.0
        self._micro_pause_count: int = 0
        self._mouse_click_count: int = 0
        self._scroll_count: int = 0
        self._context_switch_count: int = 0
        self._dwell_by_process: dict[str, float] = {}
        self._last_process: str | None = None
        self._last_window_id: int | None = None

        self._slice_keystrokes: int = 0
        self._slice_corrections: int = 0
        self._iki_count: int = 0
        self._iki_sum_ms: float = 0.0
        self._iki_sum_sq_ms: float = 0.0

        self._last_input_time: float | None = None
        self._last_key_time: float | None = None
        self._last_mouse_move_time: float | None = None

        # Bounded sliding history of committed slices
        self._slices: list[TelemetrySample] = []

    @property
    def lifetime_keystrokes(self) -> int:
        with self._lock:
            return self._lifetime_keystrokes

    @property
    def lifetime_corrections(self) -> int:
        with self._lock:
            return self._lifetime_corrections

    @property
    def lifetime_mouse_clicks(self) -> int:
        with self._lock:
            return self._lifetime_mouse_clicks

    @property
    def lifetime_scroll_events(self) -> int:
        with self._lock:
            return self._lifetime_scroll_events

    @property
    def lifetime_context_switches(self) -> int:
        with self._lock:
            return self._lifetime_context_switches

    @property
    def lifetime_active_seconds(self) -> float:
        with self._lock:
            return self._lifetime_active_seconds

    @property
    def lifetime_idle_seconds(self) -> float:
        with self._lock:
            return self._lifetime_idle_seconds

    @property
    def active_work_seconds(self) -> float:
        """Total active working seconds, including on-screen reading/thought grace periods."""
        now = time.monotonic()
        with self._lock:
            if self._last_input_time is None:
                return self._lifetime_active_work_seconds
            elapsed = now - self._last_input_time
            if elapsed <= self._reading_thought_grace:
                return self._lifetime_active_work_seconds + max(0.0, elapsed)
            return self._lifetime_active_work_seconds

    @property
    def away_idle_seconds(self) -> float:
        """Total away/idle seconds where pause exceeded the reading/thought grace period."""
        now = time.monotonic()
        with self._lock:
            if self._last_input_time is None:
                return self._lifetime_away_idle_seconds
            elapsed = now - self._last_input_time
            if elapsed > self._reading_thought_grace:
                return self._lifetime_away_idle_seconds + (elapsed - self._reading_thought_grace)
            return self._lifetime_away_idle_seconds

    @property
    def session_uptime_seconds(self) -> float:
        """Continuous active session seconds without an idle break > session_reset_idle_seconds."""
        now = time.monotonic()
        with self._lock:
            if self._last_input_time is not None:
                idle_gap = now - self._last_input_time
                if idle_gap >= self._session_reset_idle:
                    # Reset session after >= 15 min idle
                    self._session_start_time = now
                    self._last_active_time = now
                    return 0.0
            return max(0.0, now - self._session_start_time)

    def _register_input_timestamp_unlocked(self, now: float) -> None:
        """Update active seconds and micro pauses from input intervals."""
        if self._last_input_time is not None:
            delta_sec = now - self._last_input_time
            if delta_sec > 0.0:
                # 1. Slice-level active interaction & micro-pause tracking
                if delta_sec <= self._idle_threshold:
                    self._active_seconds += delta_sec
                    self._lifetime_active_seconds += delta_sec
                else:
                    self._lifetime_idle_seconds += delta_sec

                if self._micro_pause_min <= delta_sec <= self._micro_pause_max:
                    self._micro_pause_count += 1

                # 2. 3-minute grace period active work vs away accumulator
                if delta_sec <= self._reading_thought_grace:
                    # Within thought/reading grace period: retroactively credit entire delta
                    self._lifetime_active_work_seconds += delta_sec
                else:
                    # Stepped away: credit delta to away idle time
                    self._lifetime_away_idle_seconds += delta_sec
                    if delta_sec >= self._session_reset_idle:
                        self._session_start_time = now
                self._last_active_time = now
        else:
            self._last_active_time = now
        self._last_input_time = now

    def record_key(
        self,
        *,
        is_correction: bool,
        delta_ms: float | None = None,
        event_time: float | None = None,
    ) -> None:
        """Record an anonymous keystroke event."""
        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            self._register_input_timestamp_unlocked(now)
            self._lifetime_keystrokes += 1
            self._slice_keystrokes += 1
            if is_correction:
                self._lifetime_corrections += 1
                self._slice_corrections += 1

            computed_delta_ms = delta_ms
            if computed_delta_ms is None and self._last_key_time is not None:
                computed_delta_ms = (now - self._last_key_time) * 1000.0
            self._last_key_time = now

            if (
                computed_delta_ms is not None
                and self._iki_min_outlier_ms <= computed_delta_ms <= self._iki_max_outlier_ms
            ):
                self._iki_count += 1
                self._iki_sum_ms += computed_delta_ms
                self._iki_sum_sq_ms += computed_delta_ms * computed_delta_ms

    def record_mouse_click(self, *, event_time: float | None = None) -> None:
        """Record an anonymous mouse click."""
        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            self._register_input_timestamp_unlocked(now)
            self._lifetime_mouse_clicks += 1
            self._mouse_click_count += 1

    def record_mouse_scroll(self, *, event_time: float | None = None) -> None:
        """Record an anonymous mouse scroll tick."""
        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            self._register_input_timestamp_unlocked(now)
            self._lifetime_scroll_events += 1
            self._scroll_count += 1

    def record_mouse_move(self, *, event_time: float | None = None) -> None:
        """Record a throttled mouse move tick."""
        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            if (
                self._last_mouse_move_time is not None
                and (now - self._last_mouse_move_time) < self._mouse_move_throttle
            ):
                return
            self._last_mouse_move_time = now
            self._register_input_timestamp_unlocked(now)

    def record_window_tick(
        self,
        process_name: str,
        delta_seconds: float,
        *,
        window_id: int | None = None,
    ) -> None:
        """Record foreground active window process dwell time and window switches."""
        if delta_seconds <= 0.0:
            return
        sanitized = process_name.strip() or "unknown"
        with self._lock:
            process_changed = self._last_process is not None and self._last_process != sanitized
            window_changed = (
                self._last_window_id is not None
                and window_id is not None
                and self._last_window_id != window_id
            )
            if process_changed or window_changed:
                self._context_switch_count += 1
                self._lifetime_context_switches += 1
            self._last_process = sanitized
            self._last_window_id = window_id
            self._dwell_by_process[sanitized] = (
                self._dwell_by_process.get(sanitized, 0.0) + delta_seconds
            )

    def commit_slice(self, now: float | None = None) -> TelemetrySample:
        """Commit the current volatile state into a TelemetrySample and slide the window."""
        commit_time = now if now is not None else time.monotonic()
        with self._lock:
            sample = TelemetrySample(
                timestamp_start=self._slice_start_time,
                timestamp_end=commit_time,
                primary_process=self._last_process or "idle",
                active_seconds=self._active_seconds,
                micro_pause_count=self._micro_pause_count,
                context_switch_count=self._context_switch_count,
                dwell_distribution=dict(self._dwell_by_process),
                total_keystrokes=self._slice_keystrokes,
                correction_keystrokes=self._slice_corrections,
                iki_count=self._iki_count,
                iki_sum_ms=self._iki_sum_ms,
                iki_sum_sq_ms=self._iki_sum_sq_ms,
                mouse_click_count=self._mouse_click_count,
                scroll_count=self._scroll_count,
            )

            # Reset active slice counters
            self._slice_start_time = commit_time
            self._active_seconds = 0.0
            self._micro_pause_count = 0
            self._mouse_click_count = 0
            self._scroll_count = 0
            self._context_switch_count = 0
            self._dwell_by_process = {}
            self._slice_keystrokes = 0
            self._slice_corrections = 0
            self._iki_count = 0
            self._iki_sum_ms = 0.0
            self._iki_sum_sq_ms = 0.0

            self._slices.append(sample)

            # Evict slices older than window duration
            cutoff = commit_time - self._window_duration
            self._slices = [s for s in self._slices if s.timestamp_end >= cutoff]

            return sample

    def get_sliding_window_metrics(self) -> PooledTelemetryMetrics:
        """Compute pooled telemetry metrics over the active sliding window."""
        with self._lock:
            slices_copy = list(self._slices)
        return pool_telemetry_samples(slices_copy)
