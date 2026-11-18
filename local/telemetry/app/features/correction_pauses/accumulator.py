"""Accumulator for correction and pause metrics."""

import statistics
import threading

from app.core import IKI_MAX_OUTLIER_MS, IKI_MIN_OUTLIER_MS
from app.features.correction_pauses.models import RawCorrectionPauseMetrics


class CorrectionPauseAccumulator:
    """Thread-safe accumulator for typing corrections and pauses."""

    def __init__(
        self,
        *,
        iki_min_outlier_ms: float = IKI_MIN_OUTLIER_MS,
        iki_max_outlier_ms: float = IKI_MAX_OUTLIER_MS,
    ) -> None:
        self._iki_min_outlier = iki_min_outlier_ms
        self._iki_max_outlier = iki_max_outlier_ms

        self._lock = threading.Lock()
        self._pre_corrs: list[float] = []
        self._post_corrs: list[float] = []
        self._corrections_count: int = 0
        self._corrections_delta: int = 0
        self._micro_pauses: int = 0
        self._pauses_gt_2s: int = 0
        self._burst_count: int = 0

        self._last_key_time: float | None = None
        self._last_was_correction: bool = False
        self._total_keys_in_burst: int = 0

    def record_key(
        self,
        *,
        is_correction: bool,
        delta_ms: float | None = None,
        event_time: float | None = None,
    ) -> None:
        """Record KeyDown event to track corrections, micro-pauses, and bursts."""
        import time

        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            self._total_keys_in_burst += 1
            if self._total_keys_in_burst == 1:
                self._burst_count += 1

            if is_correction:
                self._corrections_count += 1
                self._corrections_delta += 1

            computed_delta = delta_ms
            if computed_delta is None and self._last_key_time is not None:
                computed_delta = (now - self._last_key_time) * 1000.0
            self._last_key_time = now

            if computed_delta is not None:
                if 1000.0 <= computed_delta <= 5000.0:
                    self._micro_pauses += 1
                if computed_delta >= 2000.0:
                    self._pauses_gt_2s += 1
                    if self._total_keys_in_burst > 1:
                        self._burst_count += 1

                if self._iki_min_outlier <= computed_delta <= self._iki_max_outlier:
                    if is_correction:
                        self._pre_corrs.append(computed_delta)
                    elif self._last_was_correction:
                        self._post_corrs.append(computed_delta)

            self._last_was_correction = is_correction

    def has_good_sample(self) -> bool:
        """Return True if any correction pauses or pauses >2s have accumulated."""
        with self._lock:
            return (
                len(self._pre_corrs) > 0
                or len(self._post_corrs) > 0
                or self._corrections_count > 0
                or self._pauses_gt_2s > 0
            )

    def consume(self) -> tuple[RawCorrectionPauseMetrics, int]:
        """Consume and reset accumulated correction/pause metrics."""
        with self._lock:
            pre_list = list(self._pre_corrs)
            post_list = list(self._post_corrs)
            corrs = self._corrections_count
            delta = self._corrections_delta
            micros = self._micro_pauses
            gt2s = self._pauses_gt_2s
            bursts = self._burst_count

            self._pre_corrs.clear()
            self._post_corrs.clear()
            self._corrections_delta = 0
            self._micro_pauses = 0
            self._pauses_gt_2s = 0
            self._burst_count = 0
            self._total_keys_in_burst = 0

        metrics = RawCorrectionPauseMetrics(
            pre_correction_pauses_ms=tuple(pre_list),
            post_correction_pauses_ms=tuple(post_list),
            pre_correction_pause_median_ms=(
                round(float(statistics.median(pre_list)), 2) if pre_list else 0.0
            ),
            post_correction_pause_median_ms=(
                round(float(statistics.median(post_list)), 2) if post_list else 0.0
            ),
            correction_keystrokes=corrs,
            micro_pauses_count=micros,
            pauses_gt_2s_count=gt2s,
            burst_count=bursts,
        )
        return metrics, delta
