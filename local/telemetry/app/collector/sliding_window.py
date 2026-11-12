"""Thread-safe 60s sliding window, data models, and pooling math for `app/collector/`."""

import math
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.config import (
    AWAY_IDLE_THRESHOLD_SECONDS,
    IDLE_EVENT_THRESHOLD_SECONDS,
    IKI_MAX_OUTLIER_MS,
    IKI_MIN_OUTLIER_MS,
    IKI_MIN_VALID_SAMPLES,
    MICRO_PAUSE_MAX_SECONDS,
    MICRO_PAUSE_MIN_SECONDS,
    MOUSE_MOVE_THROTTLE_SECONDS,
    NON_WORK_PROCESS_NAMES,
    READING_THOUGHT_GRACE_SECONDS,
    SESSION_RESET_IDLE_SECONDS,
    SLIDING_WINDOW_SECONDS,
)


@dataclass(frozen=True, slots=True)
class TelemetrySample:
    """Immutable in-memory snapshot of hardware and window events."""

    timestamp_start: float
    timestamp_end: float
    primary_process: str
    active_seconds: float
    micro_pause_count: int
    context_switch_count: int
    dwell_distribution: dict[str, float]
    total_keystrokes: int
    correction_keystrokes: int
    iki_count: int
    iki_sum_ms: float
    iki_sum_sq_ms: float
    mouse_click_count: int = 0
    scroll_count: int = 0
    pauses_gt_2s_count: int = 0
    burst_count: int = 0

    @property
    def duration_seconds(self) -> float:
        """Total elapsed wall-clock seconds covered by this sample."""
        return max(0.0, self.timestamp_end - self.timestamp_start)


@dataclass(frozen=True, slots=True)
class TickDeltas:
    """Monotonic counter deltas observed since the previous snapshot commit."""

    keystrokes: int = 0
    corrections: int = 0
    context_switches: int = 0
    mouse_clicks: int = 0
    scrolls: int = 0
    pauses_gt_2s: int = 0


@dataclass(frozen=True, slots=True)
class PooledTelemetryMetrics:
    """Statistical telemetry metrics computed across the sliding window."""

    sample_count: int
    total_duration_seconds: float
    total_active_seconds: float
    duty_cycle: float
    total_micro_pauses: int
    total_mouse_clicks: int
    total_scroll_events: int
    total_context_switches: int
    switches_per_minute: float
    merged_dwell_seconds: dict[str, float]
    primary_process: str
    primary_process_ratio: float
    shannon_entropy: float
    total_keystrokes: int
    correction_keystrokes: int
    correction_ratio: float
    iki_count: int
    is_psychomotor_valid: bool
    iki_mean_ms: float
    iki_variance_ms2: float
    iki_std_dev_ms: float
    iki_cv: float
    total_pauses_gt_2s: int = 0
    total_bursts: int = 0


@dataclass(frozen=True, slots=True)
class ActivitySnapshot:
    """Complete 60s activity snapshot produced by `collector/` on each tick."""

    metrics: PooledTelemetryMetrics
    deltas: TickDeltas
    session_uptime_seconds: float
    active_work_seconds: float
    away_idle_seconds: float
    idle_gap_seconds: float
    now_timestamp: float


def compute_shannon_entropy(dwell_seconds: Mapping[str, float]) -> float:
    """Compute Shannon entropy H = -sum(p_k * ln(p_k)) over process dwell times."""
    positive_dwells = [sec for sec in dwell_seconds.values() if sec > 0.0]
    total_dwell = sum(positive_dwells)
    if total_dwell <= 0.0 or len(positive_dwells) <= 1:
        return 0.0

    entropy = 0.0
    for sec in positive_dwells:
        prob = sec / total_dwell
        entropy -= prob * math.log(prob)
    return max(0.0, round(entropy, 4))


def merge_dwell_distributions(
    samples: Sequence[TelemetrySample],
) -> dict[str, float]:
    """Sum positive per-process dwell times across samples, filtering non-work OS processes."""
    raw_merged: dict[str, float] = {}
    work_merged: dict[str, float] = {}
    for sample in samples:
        for proc, seconds in sample.dwell_distribution.items():
            if seconds > 0.0:
                raw_merged[proc] = raw_merged.get(proc, 0.0) + seconds
                if proc.strip().lower() not in NON_WORK_PROCESS_NAMES:
                    work_merged[proc] = work_merged.get(proc, 0.0) + seconds
    return work_merged if work_merged else raw_merged


def pool_telemetry_samples(
    samples: Sequence[TelemetrySample],
    *,
    iki_min_valid_samples: int = IKI_MIN_VALID_SAMPLES,
) -> PooledTelemetryMetrics:
    """Pool sliding window samples into unified mathematical metrics."""
    sample_count = len(samples)
    if sample_count == 0:
        return PooledTelemetryMetrics(
            sample_count=0,
            total_duration_seconds=0.0,
            total_active_seconds=0.0,
            duty_cycle=0.0,
            total_micro_pauses=0,
            total_mouse_clicks=0,
            total_scroll_events=0,
            total_context_switches=0,
            switches_per_minute=0.0,
            merged_dwell_seconds={},
            primary_process="idle",
            primary_process_ratio=0.0,
            shannon_entropy=0.0,
            total_keystrokes=0,
            correction_keystrokes=0,
            correction_ratio=0.0,
            iki_count=0,
            is_psychomotor_valid=False,
            iki_mean_ms=0.0,
            iki_variance_ms2=0.0,
            iki_std_dev_ms=0.0,
            iki_cv=0.0,
        )

    total_duration = sum(s.duration_seconds for s in samples)
    total_active = sum(max(0.0, s.active_seconds) for s in samples)
    duty_cycle = min(1.0, max(0.0, total_active / total_duration)) if total_duration > 0.0 else 0.0

    total_micro_pauses = sum(s.micro_pause_count for s in samples)
    total_mouse_clicks = sum(s.mouse_click_count for s in samples)
    total_scroll_events = sum(s.scroll_count for s in samples)
    total_switches = sum(s.context_switch_count for s in samples)
    total_pauses_gt_2s = sum(s.pauses_gt_2s_count for s in samples)
    total_bursts = sum(s.burst_count for s in samples)
    effective_rate_duration = max(total_duration, 1.0)
    switches_per_min = total_switches / (effective_rate_duration / 60.0)

    merged_dwell = merge_dwell_distributions(samples)
    total_dwell = sum(merged_dwell.values())
    if merged_dwell and total_dwell > 0.0:
        primary_process = max(merged_dwell.items(), key=lambda item: item[1])[0]
        primary_process_ratio = min(1.0, max(0.0, merged_dwell[primary_process] / total_dwell))
    else:
        primary_process = samples[-1].primary_process
        primary_process_ratio = 0.0

    shannon_entropy = compute_shannon_entropy(merged_dwell)

    total_keys = sum(s.total_keystrokes for s in samples)
    corr_keys = sum(s.correction_keystrokes for s in samples)
    correction_ratio = min(1.0, max(0.0, corr_keys / total_keys)) if total_keys > 0 else 0.0

    total_iki_count = sum(s.iki_count for s in samples)
    is_psychomotor_valid = total_iki_count >= iki_min_valid_samples
    if total_iki_count > 0:
        total_iki_sum = sum(s.iki_sum_ms for s in samples)
        total_iki_sum_sq = sum(s.iki_sum_sq_ms for s in samples)
        iki_mean = total_iki_sum / total_iki_count
        iki_variance = max(0.0, (total_iki_sum_sq / total_iki_count) - (iki_mean * iki_mean))
        iki_std_dev = math.sqrt(iki_variance)
        iki_cv = (iki_std_dev / iki_mean) if iki_mean > 0.0 else 0.0
    else:
        iki_mean = 0.0
        iki_variance = 0.0
        iki_std_dev = 0.0
        iki_cv = 0.0

    return PooledTelemetryMetrics(
        sample_count=sample_count,
        total_duration_seconds=round(total_duration, 4),
        total_active_seconds=round(total_active, 4),
        duty_cycle=round(duty_cycle, 4),
        total_micro_pauses=total_micro_pauses,
        total_mouse_clicks=total_mouse_clicks,
        total_scroll_events=total_scroll_events,
        total_context_switches=total_switches,
        switches_per_minute=round(switches_per_min, 4),
        merged_dwell_seconds=merged_dwell,
        primary_process=primary_process,
        primary_process_ratio=round(primary_process_ratio, 4),
        shannon_entropy=shannon_entropy,
        total_keystrokes=total_keys,
        correction_keystrokes=corr_keys,
        correction_ratio=round(correction_ratio, 4),
        iki_count=total_iki_count,
        is_psychomotor_valid=is_psychomotor_valid,
        iki_mean_ms=round(iki_mean, 2),
        iki_variance_ms2=round(iki_variance, 2),
        iki_std_dev_ms=round(iki_std_dev, 2),
        iki_cv=round(iki_cv, 4),
        total_pauses_gt_2s=total_pauses_gt_2s,
        total_bursts=total_bursts,
    )


class SlidingWindowBuffer:
    """Thread-safe 60s sliding window accumulator and monotonic tick-delta tracker."""

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

        self._lifetime_keystrokes: int = 0
        self._lifetime_corrections: int = 0
        self._lifetime_mouse_clicks: int = 0
        self._lifetime_scroll_events: int = 0
        self._lifetime_context_switches: int = 0
        self._lifetime_active_seconds: float = 0.0
        self._lifetime_idle_seconds: float = 0.0
        self._lifetime_active_work_seconds: float = 0.0
        self._lifetime_away_idle_seconds: float = 0.0

        self._prev_keystrokes: int = 0
        self._prev_corrections: int = 0
        self._prev_switches: int = 0
        self._prev_mouse_clicks: int = 0
        self._prev_scrolls: int = 0

        self._session_start_time: float = time.monotonic()
        self._last_active_time: float = time.monotonic()

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
        self._pauses_gt_2s_count: int = 0
        self._burst_count: int = 0

        self._last_input_time: float | None = None
        self._last_key_time: float | None = None
        self._last_mouse_move_time: float | None = None

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
            if self._last_input_time is None:
                return 0.0
            idle_gap = now - self._last_input_time
            if idle_gap >= self._session_reset_idle:
                self._session_start_time = now
                self._last_active_time = now
                return 0.0
            return max(0.0, now - self._session_start_time)

    def seconds_since_last_input(self, now: float | None = None) -> float:
        """Return elapsed seconds since last physical input, or 0.0 if no input yet."""
        check_time = now if now is not None else time.monotonic()
        with self._lock:
            if self._last_input_time is None:
                return 0.0
            return max(0.0, check_time - self._last_input_time)

    def _register_input_timestamp_unlocked(self, now: float) -> None:
        if self._last_input_time is not None:
            delta_sec = now - self._last_input_time
            if delta_sec > 0.0:
                if delta_sec <= self._idle_threshold:
                    self._active_seconds += delta_sec
                    self._lifetime_active_seconds += delta_sec
                else:
                    self._lifetime_idle_seconds += delta_sec

                if self._micro_pause_min <= delta_sec <= self._micro_pause_max:
                    self._micro_pause_count += 1

                if delta_sec <= self._reading_thought_grace:
                    self._lifetime_active_work_seconds += delta_sec
                else:
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

            if self._slice_keystrokes == 1:
                self._burst_count += 1

            computed_delta_ms = delta_ms
            if computed_delta_ms is None and self._last_key_time is not None:
                computed_delta_ms = (now - self._last_key_time) * 1000.0
            self._last_key_time = now

            if computed_delta_ms is not None and computed_delta_ms >= 2000.0:
                self._pauses_gt_2s_count += 1
                if self._slice_keystrokes > 1:
                    self._burst_count += 1

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
                pauses_gt_2s_count=self._pauses_gt_2s_count,
                burst_count=self._burst_count,
            )

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
            self._pauses_gt_2s_count = 0
            self._burst_count = 0

            self._slices.append(sample)
            cutoff = commit_time - self._window_duration
            self._slices = [s for s in self._slices if s.timestamp_end >= cutoff]
            return sample

    def get_sliding_window_metrics(self) -> PooledTelemetryMetrics:
        """Compute pooled telemetry metrics over the active sliding window."""
        with self._lock:
            slices_copy = list(self._slices)
        return pool_telemetry_samples(slices_copy)

    def commit_snapshot(self, *, now_timestamp: float | None = None) -> ActivitySnapshot:
        """Commit slice, pool 60s metrics, and compute tick deltas in one self-contained call."""
        committed_slice = self.commit_slice()
        metrics = self.get_sliding_window_metrics()

        with self._lock:
            curr_keys = self._lifetime_keystrokes
            curr_corrs = self._lifetime_corrections
            curr_switches = self._lifetime_context_switches
            curr_clicks = self._lifetime_mouse_clicks
            curr_scrolls = self._lifetime_scroll_events

            deltas = TickDeltas(
                keystrokes=max(0, curr_keys - self._prev_keystrokes),
                corrections=max(0, curr_corrs - self._prev_corrections),
                context_switches=max(0, curr_switches - self._prev_switches),
                mouse_clicks=max(0, curr_clicks - self._prev_mouse_clicks),
                scrolls=max(0, curr_scrolls - self._prev_scrolls),
                pauses_gt_2s=committed_slice.pauses_gt_2s_count,
            )
            self._prev_keystrokes = curr_keys
            self._prev_corrections = curr_corrs
            self._prev_switches = curr_switches
            self._prev_mouse_clicks = curr_clicks
            self._prev_scrolls = curr_scrolls

        return ActivitySnapshot(
            metrics=metrics,
            deltas=deltas,
            session_uptime_seconds=self.session_uptime_seconds,
            active_work_seconds=self.active_work_seconds,
            away_idle_seconds=self.away_idle_seconds,
            idle_gap_seconds=self.seconds_since_last_input(),
            now_timestamp=now_timestamp if now_timestamp is not None else time.time(),
        )
