"""Ultradian rhythms, 24h chronotype center-of-mass, and typing burst classification."""

from __future__ import annotations

import datetime
import math
from collections import deque

from app.collector import PooledTelemetryMetrics


class RhythmTracker:
    """Tracks Dimension 4 (Ultradian), Dimension 5 (Chronotype), and Dimension 6 (Typing Rhythm)."""

    def __init__(self) -> None:
        # Dimension 4: Ultradian rhythms (per-minute input intensity history)
        self._minute_bucket_start_ts: float | None = None
        self._current_minute_actions: float = 0.0
        self._minute_intensities: deque[float] = deque(maxlen=720)
        self.dominant_ultradian_period_min: float = 90.0

        # Dimension 5: Chronotype (hourly deep-work minutes "00".."23")
        self.deep_work_minutes_by_hour: dict[str, float] = {f"{h:02d}": 0.0 for h in range(24)}

        # Dimension 6: Typing rhythm and pauses
        self.composing_pauses_total: int = 0
        self._prev_window_pauses: int = 0

    def update_ultradian(self, *, now: float, minute_intensity: float) -> None:
        """Accumulate per-minute input intensity and update autocorrelation period estimate."""
        if self._minute_bucket_start_ts is None:
            self._minute_bucket_start_ts = now
            self._current_minute_actions = minute_intensity
            return

        if (now - self._minute_bucket_start_ts) >= 60.0:
            self._minute_intensities.append(self._current_minute_actions)
            self._minute_bucket_start_ts = now
            self._current_minute_actions = minute_intensity
            if len(self._minute_intensities) >= 6:
                self.dominant_ultradian_period_min = self.estimate_period_minutes(
                    list(self._minute_intensities)
                )
        else:
            self._current_minute_actions = (self._current_minute_actions + minute_intensity) / 2.0

    @staticmethod
    def estimate_period_minutes(series: list[float]) -> float:
        """Estimate dominant periodicity via normalized lag autocorrelation."""
        n = len(series)
        if n < 6:
            return 90.0
        mean_val = sum(series) / n
        centered = [x - mean_val for x in series]
        var = sum(c * c for c in centered)
        if var <= 1e-9:
            return 90.0

        min_lag = 2 if n < 90 else 45
        max_lag = min(n // 2, 135)
        if max_lag < min_lag:
            return 90.0

        best_lag = 90
        best_corr = -1.0
        for lag in range(min_lag, max_lag + 1):
            cov = sum(centered[i] * centered[i - lag] for i in range(lag, n))
            corr = cov / var
            if corr > best_corr:
                best_corr = corr
                best_lag = lag
        return float(best_lag) if best_corr > 0.05 else 90.0

    def update_chronotype(
        self,
        *,
        now: float,
        dt_sec: float,
        activity: str,
        focus_len_sec: float,
    ) -> float:
        """Update hourly deep-work minutes and return circular centre-of-mass hour [0.0, 24.0)."""
        dt_obj = datetime.datetime.fromtimestamp(now, tz=datetime.UTC)
        hour_key = f"{dt_obj.hour:02d}"
        if activity in ("producing", "consuming") and focus_len_sec >= 60.0:
            self.deep_work_minutes_by_hour[hour_key] = round(
                self.deep_work_minutes_by_hour.get(hour_key, 0.0) + (dt_sec / 60.0),
                3,
            )
        return self._compute_chronotype_center_of_mass(default_hour=float(dt_obj.hour))

    def _compute_chronotype_center_of_mass(self, *, default_hour: float) -> float:
        total_min = sum(self.deep_work_minutes_by_hour.values())
        if total_min <= 0.0:
            return default_hour
        sin_sum = 0.0
        cos_sum = 0.0
        for hour_str, mins in self.deep_work_minutes_by_hour.items():
            if mins > 0.0:
                angle = (int(hour_str) + 0.5) * (2.0 * math.pi / 24.0)
                sin_sum += mins * math.sin(angle)
                cos_sum += mins * math.cos(angle)
        mean_angle = math.atan2(sin_sum, cos_sum)
        if mean_angle < 0.0:
            mean_angle += 2.0 * math.pi
        return (mean_angle * 24.0) / (2.0 * math.pi)

    def update_typing_rhythm(
        self,
        metrics: PooledTelemetryMetrics,
        *,
        pauses_gt_2s_delta: int | None = None,
    ) -> tuple[str, int, float]:
        """Update composing pause totals and return (typing_mode, window_pauses_2s, mean_burst)."""
        window_pauses_2s = metrics.total_pauses_gt_2s
        if pauses_gt_2s_delta is not None:
            self.composing_pauses_total += max(0, pauses_gt_2s_delta)
        elif window_pauses_2s > self._prev_window_pauses:
            self.composing_pauses_total += window_pauses_2s - self._prev_window_pauses
        self._prev_window_pauses = window_pauses_2s

        bursts = max(1, metrics.total_bursts or (window_pauses_2s + 1))
        mean_burst_keys = (
            round(metrics.total_keystrokes / bursts, 2) if metrics.total_keystrokes > 0 else 0.0
        )
        typing_mode = self.classify_typing_mode(
            total_keystrokes=metrics.total_keystrokes,
            window_pauses_2s=window_pauses_2s,
            iki_cv=metrics.iki_cv,
            correction_ratio=metrics.correction_ratio,
        )
        return typing_mode, window_pauses_2s, mean_burst_keys

    @staticmethod
    def classify_typing_mode(
        *,
        total_keystrokes: int,
        window_pauses_2s: int,
        iki_cv: float,
        correction_ratio: float,
    ) -> str:
        """Distinguish composing (thought pauses & edits) vs transcribing (steady stream)."""
        if total_keystrokes < 5:
            return "inactive"
        if window_pauses_2s >= 1 or iki_cv >= 0.45 or correction_ratio >= 0.08:
            return "composing"
        return "transcribing"
