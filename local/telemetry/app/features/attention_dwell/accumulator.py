"""Accumulator for active window process dwell and context switch events."""

import threading

from app.features.attention_dwell.math import compute_shannon_entropy
from app.features.attention_dwell.models import RawAttentionWindowMetrics


class AttentionDwellAccumulator:
    """Thread-safe accumulator for window process dwell times and context switches."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._dwell: dict[str, float] = {}
        self._context_switches: int = 0
        self._switch_delta: int = 0
        self._last_process: str | None = None
        self._last_window_id: int | None = None

    def record_window_tick(
        self,
        process_name: str,
        delta_seconds: float,
        *,
        window_id: int | None = None,
    ) -> None:
        """Record active window process dwell time and window context switches."""
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
                self._context_switches += 1
                self._switch_delta += 1

            self._last_process = sanitized
            self._last_window_id = window_id
            self._dwell[sanitized] = self._dwell.get(sanitized, 0.0) + delta_seconds

    def has_good_sample(self) -> bool:
        """Return True if a context switch occurred or at least 15s dwell recorded."""
        with self._lock:
            return self._context_switches > 0 or sum(self._dwell.values()) >= 15.0

    def consume(self) -> tuple[RawAttentionWindowMetrics, int]:
        """Consume and reset accumulated process dwell & switch metrics."""
        with self._lock:
            dwell = dict(self._dwell)
            switches = self._context_switches
            delta = self._switch_delta
            primary = self._last_process or "idle"

            self._dwell.clear()
            self._context_switches = 0
            self._switch_delta = 0

        total_dwell = sum(dwell.values())
        if dwell and total_dwell > 0.0:
            primary = max(dwell.items(), key=lambda item: item[1])[0]
            primary_sec = round(dwell[primary], 4)
        else:
            primary_sec = 0.0

        metrics = RawAttentionWindowMetrics(
            shannon_entropy_bits=compute_shannon_entropy(dwell),
            merged_dwell_seconds=dwell,
            primary_process=primary,
            primary_process_dwell_seconds=primary_sec,
            distinct_processes_count=len(dwell),
            context_switches=switches,
        )
        return metrics, delta
