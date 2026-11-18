"""Accumulator for session uptime, active work, thought grace, and away idle time."""

import threading
import time

from app.core import (
    AWAY_IDLE_THRESHOLD_SECONDS,
    IDLE_EVENT_THRESHOLD_SECONDS,
    MICRO_PAUSE_MAX_SECONDS,
    MICRO_PAUSE_MIN_SECONDS,
    READING_THOUGHT_GRACE_SECONDS,
    SESSION_RESET_IDLE_SECONDS,
)
from app.features.session_duration.models import RawTemporalSessionMetrics


class SessionDurationAccumulator:
    """Thread-safe tracker for active working time, thought grace, and session uptime."""

    def __init__(
        self,
        *,
        idle_threshold_seconds: float = IDLE_EVENT_THRESHOLD_SECONDS,
        micro_pause_min_seconds: float = MICRO_PAUSE_MIN_SECONDS,
        micro_pause_max_seconds: float = MICRO_PAUSE_MAX_SECONDS,
        session_reset_idle_seconds: float = SESSION_RESET_IDLE_SECONDS,
        reading_thought_grace_seconds: float = READING_THOUGHT_GRACE_SECONDS,
        away_idle_threshold_seconds: float = AWAY_IDLE_THRESHOLD_SECONDS,
    ) -> None:
        self._idle_threshold = idle_threshold_seconds
        self._micro_pause_min = micro_pause_min_seconds
        self._micro_pause_max = micro_pause_max_seconds
        self._session_reset_idle = session_reset_idle_seconds
        self._reading_thought_grace = reading_thought_grace_seconds
        self._away_idle_threshold = away_idle_threshold_seconds

        self._lock = threading.Lock()
        self._session_start_time = time.monotonic()
        self._interval_start_time = time.monotonic()
        self._active_seconds = 0.0

        self._lifetime_active_work_seconds = 0.0
        self._lifetime_away_idle_seconds = 0.0
        self._last_input_time: float | None = None

    def register_input_event(self, event_time: float | None = None) -> None:
        """Register anonymous hardware input timestamp."""
        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            if self._last_input_time is not None:
                delta_sec = now - self._last_input_time
                if delta_sec > 0.0:
                    if delta_sec <= self._idle_threshold:
                        self._active_seconds += delta_sec

                    if delta_sec <= self._reading_thought_grace:
                        self._lifetime_active_work_seconds += delta_sec
                    else:
                        self._lifetime_away_idle_seconds += delta_sec
                        if delta_sec >= self._session_reset_idle:
                            self._session_start_time = now
            self._last_input_time = now

    @property
    def session_uptime_seconds(self) -> float:
        """Continuous active session seconds without break > session_reset_idle."""
        now = time.monotonic()
        with self._lock:
            if self._last_input_time is None:
                return 0.0
            idle_gap = now - self._last_input_time
            if idle_gap >= self._session_reset_idle:
                self._session_start_time = now
                return 0.0
            return max(0.0, now - self._session_start_time)

    @property
    def active_work_seconds(self) -> float:
        """Total active working seconds including reading/thought grace."""
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
        """Total away idle seconds exceeding reading/thought grace."""
        now = time.monotonic()
        with self._lock:
            if self._last_input_time is None:
                return self._lifetime_away_idle_seconds
            elapsed = now - self._last_input_time
            if elapsed > self._reading_thought_grace:
                return self._lifetime_away_idle_seconds + (elapsed - self._reading_thought_grace)
            return self._lifetime_away_idle_seconds

    def seconds_since_last_input(self, now: float | None = None) -> float:
        """Return elapsed seconds since last input."""
        check_time = now if now is not None else time.monotonic()
        with self._lock:
            if self._last_input_time is None:
                return 0.0
            return max(0.0, check_time - self._last_input_time)

    def consume(self) -> RawTemporalSessionMetrics:
        """Read and return current temporal session metrics."""
        now = time.monotonic()
        uptime = self.session_uptime_seconds
        active_work = self.active_work_seconds
        away_idle = self.away_idle_seconds
        idle_gap = self.seconds_since_last_input(now)

        with self._lock:
            dur = max(0.0, now - self._interval_start_time)
            active = min(dur, self._active_seconds)

        return RawTemporalSessionMetrics(
            window_active_seconds=round(active, 4),
            window_duration_seconds=round(dur, 4),
            session_uptime_seconds=round(uptime, 4),
            active_work_seconds=round(active_work, 4),
            away_idle_seconds=round(away_idle, 4),
            idle_gap_seconds=round(idle_gap, 4),
        )
