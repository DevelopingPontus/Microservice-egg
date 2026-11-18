"""Accumulator and math for keystroke timing metrics."""

import math
import statistics
import threading
from collections.abc import Sequence

from app.core import IKI_MAX_OUTLIER_MS, IKI_MIN_OUTLIER_MS, IKI_MIN_VALID_SAMPLES
from app.features.keystroke_timing.models import RawKeystrokeTimingMetrics


def compute_median_abs_deviation(values: Sequence[float]) -> float:
    """Compute Median Absolute Deviation (MAD) in milliseconds."""
    clean = [v for v in values if not math.isnan(v)]
    if not clean:
        return 0.0
    med = float(statistics.median(clean))
    devs = [abs(v - med) for v in clean]
    return round(float(statistics.median(devs)), 2)


class KeystrokeTimingAccumulator:
    """Thread-safe accumulator for anonymous keystroke timings."""

    def __init__(
        self,
        *,
        iki_min_outlier_ms: float = IKI_MIN_OUTLIER_MS,
        iki_max_outlier_ms: float = IKI_MAX_OUTLIER_MS,
        min_valid_samples: int = IKI_MIN_VALID_SAMPLES,
    ) -> None:
        self._iki_min_outlier = iki_min_outlier_ms
        self._iki_max_outlier = iki_max_outlier_ms
        self._min_valid_samples = min_valid_samples

        self._lock = threading.Lock()
        self._iki_values: list[float] = []
        self._hold_times: list[float] = []
        self._flight_times: list[float] = []
        self._keystrokes_count: int = 0
        self._keystroke_delta: int = 0

        self._active_keys: dict[int, float] = {}
        self._last_key_time: float | None = None
        self._last_release_time: float | None = None

    def record_key(
        self,
        *,
        key_slot: int | None = None,
        delta_ms: float | None = None,
        event_time: float | None = None,
    ) -> None:
        """Record KeyDown event."""
        import time

        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            self._keystrokes_count += 1
            self._keystroke_delta += 1

            if key_slot is not None:
                self._active_keys[key_slot] = now

            if self._last_release_time is not None:
                flight_ms = (now - self._last_release_time) * 1000.0
                if -200.0 <= flight_ms <= self._iki_max_outlier:
                    self._flight_times.append(flight_ms)

            computed_delta = delta_ms
            if computed_delta is None and self._last_key_time is not None:
                computed_delta = (now - self._last_key_time) * 1000.0
            self._last_key_time = now

            if (
                computed_delta is not None
                and self._iki_min_outlier <= computed_delta <= self._iki_max_outlier
            ):
                self._iki_values.append(computed_delta)

    def record_key_release(
        self,
        *,
        key_slot: int | None = None,
        hold_time_ms: float | None = None,
        event_time: float | None = None,
    ) -> None:
        """Record KeyUp event."""
        import time

        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            pressed_at = self._active_keys.pop(key_slot, None) if key_slot is not None else None
            computed_hold = hold_time_ms
            if computed_hold is None and pressed_at is not None:
                computed_hold = (now - pressed_at) * 1000.0
            if computed_hold is not None and 5.0 <= computed_hold <= 2000.0:
                self._hold_times.append(computed_hold)
            self._last_release_time = now

    def has_good_sample(self) -> bool:
        """Return True if at least min_valid_samples have accumulated."""
        with self._lock:
            return len(self._iki_values) >= self._min_valid_samples

    def consume(self) -> tuple[RawKeystrokeTimingMetrics, int]:
        """Consume and reset accumulated keystroke timing metrics."""
        with self._lock:
            ikis = list(self._iki_values)
            holds = list(self._hold_times)
            flights = list(self._flight_times)
            total_keys = self._keystrokes_count
            delta_keys = self._keystroke_delta

            self._iki_values.clear()
            self._hold_times.clear()
            self._flight_times.clear()
            self._keystroke_delta = 0

        iki_count = len(ikis)
        if iki_count > 0:
            iki_mean = sum(ikis) / iki_count
            iki_var = max(0.0, (sum(x * x for x in ikis) / iki_count) - (iki_mean * iki_mean))
            iki_std = math.sqrt(iki_var)
        else:
            iki_mean = 0.0
            iki_std = 0.0

        metrics = RawKeystrokeTimingMetrics(
            iki_values_ms=tuple(ikis),
            hold_times_ms=tuple(holds),
            flight_times_ms=tuple(flights),
            iki_count=iki_count,
            iki_mean_ms=round(iki_mean, 2),
            iki_std_dev_ms=round(iki_std, 2),
            iki_mad_ms=compute_median_abs_deviation(ikis),
            hold_time_median_ms=round(float(statistics.median(holds)), 2) if holds else 0.0,
            flight_time_median_ms=round(float(statistics.median(flights)), 2) if flights else 0.0,
            total_keystrokes=total_keys,
        )
        return metrics, delta_keys
