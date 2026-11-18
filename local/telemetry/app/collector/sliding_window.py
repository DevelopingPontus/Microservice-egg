"""Thread-safe 60s sliding window, data models, and pooling math for `app/collector/`."""

import math
import statistics
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

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
from app.features import (
    RawAttentionWindowMetrics as RawAttentionWindowMetrics,
)
from app.features import (
    RawCorrectionPauseMetrics as RawCorrectionPauseMetrics,
)
from app.features import (
    RawKeystrokeTimingMetrics as RawKeystrokeTimingMetrics,
)
from app.features import (
    RawMouseKinematicsMetrics as RawMouseKinematicsMetrics,
)
from app.features import (
    RawTemporalSessionMetrics as RawTemporalSessionMetrics,
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
    iki_values_ms: tuple[float, ...] = ()
    hold_times_ms: tuple[float, ...] = ()
    flight_times_ms: tuple[float, ...] = ()
    pre_correction_pauses_ms: tuple[float, ...] = ()
    post_correction_pauses_ms: tuple[float, ...] = ()
    mouse_points: tuple[tuple[float, float, float], ...] = ()

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
    iki_mad_ms: float = 0.0
    hold_time_median_ms: float = 0.0
    flight_time_median_ms: float = 0.0
    pre_correction_pause_ms: float = 0.0
    post_correction_pause_ms: float = 0.0
    mouse_sample_entropy: float = 0.0
    mouse_submovements: int = 0
    mouse_curvature_auc: float = 0.0
    mouse_x_flips: int = 0


@dataclass(frozen=True, slots=True)
class RawMetricsBundle:
    """Container grouping the 5 independent raw metric contracts."""

    keystroke_timing: RawKeystrokeTimingMetrics = field(default_factory=RawKeystrokeTimingMetrics)
    correction_pauses: RawCorrectionPauseMetrics = field(default_factory=RawCorrectionPauseMetrics)
    mouse_kinematics: RawMouseKinematicsMetrics = field(default_factory=RawMouseKinematicsMetrics)
    attention_window: RawAttentionWindowMetrics = field(default_factory=RawAttentionWindowMetrics)
    temporal_session: RawTemporalSessionMetrics = field(default_factory=RawTemporalSessionMetrics)


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
    raw: RawMetricsBundle = field(default_factory=RawMetricsBundle)


def compute_shannon_entropy(dwell_seconds: Mapping[str, float]) -> float:
    """Compute Shannon entropy H = -sum(p_k * log2(p_k)) in bits over process dwell times."""
    positive_dwells = [sec for sec in dwell_seconds.values() if sec > 0.0]
    total_dwell = sum(positive_dwells)
    if total_dwell <= 0.0 or len(positive_dwells) <= 1:
        return 0.0

    entropy = 0.0
    for sec in positive_dwells:
        prob = sec / total_dwell
        entropy -= prob * math.log2(prob)
    return max(0.0, round(entropy, 4))


def compute_median_abs_deviation(values: Sequence[float]) -> float:
    """Compute Median Absolute Deviation (MAD) = median(|x_i - median(x)|)."""
    if len(values) < 2:
        return 0.0
    med = statistics.median(values)
    abs_devs = [abs(v - med) for v in values]
    return round(float(statistics.median(abs_devs)), 2)


def compute_sample_entropy(series: Sequence[float], m: int = 2, r_factor: float = 0.2) -> float:
    """Compute Sample Entropy SampEn(m, r) on a 1D kinematic series (pure Python, bounded)."""
    capped = list(series[-120:])
    n = len(capped)
    if n <= m + 2:
        return 0.0
    mean_val = sum(capped) / n
    variance = sum((x - mean_val) ** 2 for x in capped) / n
    std_val = math.sqrt(variance)
    if std_val <= 1e-9:
        return 0.0
    tolerance = r_factor * std_val

    def _template_matches(length: int) -> int:
        count = 0
        limit = n - length
        for i in range(limit):
            tpl_i = capped[i : i + length]
            for j in range(i + 1, limit):
                if max(abs(tpl_i[k] - capped[j + k]) for k in range(length)) <= tolerance:
                    count += 1
        return count

    matches_m = _template_matches(m)
    matches_m1 = _template_matches(m + 1)
    if matches_m == 0 or matches_m1 == 0:
        return 0.0
    return max(0.0, round(-math.log(matches_m1 / matches_m), 4))


def compute_mouse_kinematics(
    points: Sequence[tuple[float, float, float]],
) -> tuple[float, int, float, int]:
    """Compute (sample_entropy, submovements, curvature_auc, x_flips) from (x, y, t) points."""
    if len(points) < 4:
        return 0.0, 0, 0.0, 0

    dx_list: list[float] = []
    speeds: list[float] = []
    path_length = 0.0
    for idx in range(1, len(points)):
        x0, y0, t0 = points[idx - 1]
        x1, y1, t1 = points[idx]
        dt = max(1e-4, t1 - t0)
        dx = x1 - x0
        dy = y1 - y0
        dist = math.hypot(dx, dy)
        path_length += dist
        if abs(dx) > 1.0:
            dx_list.append(dx)
        speeds.append(dist / dt)

    x_flips = 0
    for idx in range(1, len(dx_list)):
        if (dx_list[idx] > 0.0) != (dx_list[idx - 1] > 0.0):
            x_flips += 1

    accelerations: list[float] = []
    for idx in range(1, len(speeds)):
        dt = max(1e-4, points[idx + 1][2] - points[idx][2])
        accelerations.append((speeds[idx] - speeds[idx - 1]) / dt)

    submovements = 0
    for idx in range(1, len(accelerations)):
        if (accelerations[idx] > 0.0) != (accelerations[idx - 1] > 0.0):
            submovements += 1

    start_x, start_y, _ = points[0]
    end_x, end_y, _ = points[-1]
    chord = math.hypot(end_x - start_x, end_y - start_y)
    curvature_auc = round(max(0.0, (path_length / chord) - 1.0), 4) if chord > 5.0 else 0.0

    sample_entropy = compute_sample_entropy(speeds)
    return sample_entropy, submovements, curvature_auc, x_flips


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

    pooled_ikis = [v for s in samples for v in s.iki_values_ms]
    pooled_holds = [v for s in samples for v in s.hold_times_ms]
    pooled_flights = [v for s in samples for v in s.flight_times_ms]
    pooled_pre_corr = [v for s in samples for v in s.pre_correction_pauses_ms]
    pooled_post_corr = [v for s in samples for v in s.post_correction_pauses_ms]
    pooled_mouse = [pt for s in samples for pt in s.mouse_points]

    iki_mad_ms = compute_median_abs_deviation(pooled_ikis)
    hold_time_median_ms = round(float(statistics.median(pooled_holds)), 2) if pooled_holds else 0.0
    flight_time_median_ms = (
        round(float(statistics.median(pooled_flights)), 2) if pooled_flights else 0.0
    )
    pre_corr_ms = round(float(statistics.median(pooled_pre_corr)), 2) if pooled_pre_corr else 0.0
    post_corr_ms = round(float(statistics.median(pooled_post_corr)), 2) if pooled_post_corr else 0.0
    mouse_sampen, mouse_submov, mouse_auc, mouse_xflips = compute_mouse_kinematics(pooled_mouse)

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
        iki_mad_ms=iki_mad_ms,
        hold_time_median_ms=hold_time_median_ms,
        flight_time_median_ms=flight_time_median_ms,
        pre_correction_pause_ms=pre_corr_ms,
        post_correction_pause_ms=post_corr_ms,
        mouse_sample_entropy=mouse_sampen,
        mouse_submovements=mouse_submov,
        mouse_curvature_auc=mouse_auc,
        mouse_x_flips=mouse_xflips,
    )


def produce_keystroke_timing_metrics(
    samples: Sequence[TelemetrySample],
    *,
    latest_slice: TelemetrySample | None = None,
) -> RawKeystrokeTimingMetrics:
    """Independently compute raw keystroke timing metrics in ms and counts (no normalization)."""
    if not samples:
        return RawKeystrokeTimingMetrics()

    total_keys = sum(s.total_keystrokes for s in samples)
    total_iki_count = sum(s.iki_count for s in samples)
    if total_iki_count > 0:
        total_iki_sum = sum(s.iki_sum_ms for s in samples)
        total_iki_sum_sq = sum(s.iki_sum_sq_ms for s in samples)
        iki_mean = total_iki_sum / total_iki_count
        iki_variance = max(0.0, (total_iki_sum_sq / total_iki_count) - (iki_mean * iki_mean))
        iki_std_dev = math.sqrt(iki_variance)
    else:
        iki_mean = 0.0
        iki_std_dev = 0.0

    pooled_ikis = [v for s in samples for v in s.iki_values_ms]
    pooled_holds = [v for s in samples for v in s.hold_times_ms]
    pooled_flights = [v for s in samples for v in s.flight_times_ms]

    raw_source = latest_slice if latest_slice is not None else samples[-1]
    return RawKeystrokeTimingMetrics(
        iki_values_ms=tuple(raw_source.iki_values_ms),
        hold_times_ms=tuple(raw_source.hold_times_ms),
        flight_times_ms=tuple(raw_source.flight_times_ms),
        iki_count=total_iki_count,
        iki_mean_ms=round(iki_mean, 2),
        iki_std_dev_ms=round(iki_std_dev, 2),
        iki_mad_ms=compute_median_abs_deviation(pooled_ikis),
        hold_time_median_ms=(
            round(float(statistics.median(pooled_holds)), 2) if pooled_holds else 0.0
        ),
        flight_time_median_ms=(
            round(float(statistics.median(pooled_flights)), 2) if pooled_flights else 0.0
        ),
        total_keystrokes=total_keys,
    )


def produce_correction_pause_metrics(
    samples: Sequence[TelemetrySample],
    *,
    latest_slice: TelemetrySample | None = None,
) -> RawCorrectionPauseMetrics:
    """Independently compute raw correction and typing-pause metrics in ms and counts."""
    if not samples:
        return RawCorrectionPauseMetrics()

    pooled_pre = [v for s in samples for v in s.pre_correction_pauses_ms]
    pooled_post = [v for s in samples for v in s.post_correction_pauses_ms]
    raw_source = latest_slice if latest_slice is not None else samples[-1]

    return RawCorrectionPauseMetrics(
        pre_correction_pauses_ms=tuple(raw_source.pre_correction_pauses_ms),
        post_correction_pauses_ms=tuple(raw_source.post_correction_pauses_ms),
        pre_correction_pause_median_ms=(
            round(float(statistics.median(pooled_pre)), 2) if pooled_pre else 0.0
        ),
        post_correction_pause_median_ms=(
            round(float(statistics.median(pooled_post)), 2) if pooled_post else 0.0
        ),
        correction_keystrokes=sum(s.correction_keystrokes for s in samples),
        micro_pauses_count=sum(s.micro_pause_count for s in samples),
        pauses_gt_2s_count=sum(s.pauses_gt_2s_count for s in samples),
        burst_count=sum(s.burst_count for s in samples),
    )


def produce_mouse_kinematics_metrics(
    samples: Sequence[TelemetrySample],
) -> RawMouseKinematicsMetrics:
    """Independently compute raw mouse kinematics metrics in native units."""
    if not samples:
        return RawMouseKinematicsMetrics()

    pooled_mouse = [pt for s in samples for pt in s.mouse_points]
    sampen, submov, auc, xflips = compute_mouse_kinematics(pooled_mouse)
    return RawMouseKinematicsMetrics(
        sample_entropy=sampen,
        submovements=submov,
        curvature_auc=auc,
        x_flips=xflips,
        mouse_clicks=sum(s.mouse_click_count for s in samples),
        scroll_events=sum(s.scroll_count for s in samples),
    )


def produce_attention_window_metrics(
    samples: Sequence[TelemetrySample],
) -> RawAttentionWindowMetrics:
    """Independently compute raw window dwell and attentional dispersion metrics (bits, seconds)."""
    if not samples:
        return RawAttentionWindowMetrics()

    merged_dwell = merge_dwell_distributions(samples)
    total_dwell = sum(merged_dwell.values())
    if merged_dwell and total_dwell > 0.0:
        primary_process = max(merged_dwell.items(), key=lambda item: item[1])[0]
        primary_dwell_sec = round(merged_dwell[primary_process], 4)
    else:
        primary_process = samples[-1].primary_process
        primary_dwell_sec = 0.0

    return RawAttentionWindowMetrics(
        shannon_entropy_bits=compute_shannon_entropy(merged_dwell),
        merged_dwell_seconds=merged_dwell,
        primary_process=primary_process,
        primary_process_dwell_seconds=primary_dwell_sec,
        distinct_processes_count=len(merged_dwell),
        context_switches=sum(s.context_switch_count for s in samples),
    )


def produce_temporal_session_metrics(
    samples: Sequence[TelemetrySample],
    *,
    session_uptime_seconds: float = 0.0,
    active_work_seconds: float = 0.0,
    away_idle_seconds: float = 0.0,
    idle_gap_seconds: float = 0.0,
) -> RawTemporalSessionMetrics:
    """Independently compute raw temporal and session duration metrics in seconds."""
    total_duration = sum(s.duration_seconds for s in samples) if samples else 0.0
    total_active = sum(max(0.0, s.active_seconds) for s in samples) if samples else 0.0
    return RawTemporalSessionMetrics(
        window_active_seconds=round(total_active, 4),
        window_duration_seconds=round(total_duration, 4),
        session_uptime_seconds=round(session_uptime_seconds, 4),
        active_work_seconds=round(active_work_seconds, 4),
        away_idle_seconds=round(away_idle_seconds, 4),
        idle_gap_seconds=round(idle_gap_seconds, 4),
    )


def produce_raw_metrics_bundle(
    samples: Sequence[TelemetrySample],
    *,
    latest_slice: TelemetrySample | None = None,
    session_uptime_seconds: float = 0.0,
    active_work_seconds: float = 0.0,
    away_idle_seconds: float = 0.0,
    idle_gap_seconds: float = 0.0,
) -> RawMetricsBundle:
    """Assemble all 5 independently produced raw metric contracts."""
    return RawMetricsBundle(
        keystroke_timing=produce_keystroke_timing_metrics(samples, latest_slice=latest_slice),
        correction_pauses=produce_correction_pause_metrics(samples, latest_slice=latest_slice),
        mouse_kinematics=produce_mouse_kinematics_metrics(samples),
        attention_window=produce_attention_window_metrics(samples),
        temporal_session=produce_temporal_session_metrics(
            samples,
            session_uptime_seconds=session_uptime_seconds,
            active_work_seconds=active_work_seconds,
            away_idle_seconds=away_idle_seconds,
            idle_gap_seconds=idle_gap_seconds,
        ),
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
        self._slice_iki_values_ms: list[float] = []
        self._slice_hold_times_ms: list[float] = []
        self._slice_flight_times_ms: list[float] = []
        self._slice_pre_corr_pauses_ms: list[float] = []
        self._slice_post_corr_pauses_ms: list[float] = []
        self._slice_mouse_points: list[tuple[float, float, float]] = []

        # Independent sample accumulators for event-driven / good-sample pushes
        self._accum_iki_values_ms: list[float] = []
        self._accum_hold_times_ms: list[float] = []
        self._accum_flight_times_ms: list[float] = []
        self._accum_keystrokes: int = 0
        self._accum_keystroke_delta: int = 0

        self._accum_pre_corr_ms: list[float] = []
        self._accum_post_corr_ms: list[float] = []
        self._accum_corrections: int = 0
        self._accum_correction_delta: int = 0
        self._accum_micro_pauses: int = 0
        self._accum_pauses_gt_2s: int = 0
        self._accum_bursts: int = 0

        self._accum_mouse_points: list[tuple[float, float, float]] = []
        self._accum_mouse_clicks: int = 0
        self._accum_scrolls: int = 0
        self._accum_mouse_click_delta: int = 0
        self._accum_scroll_delta: int = 0

        self._accum_dwell: dict[str, float] = {}
        self._accum_context_switches: int = 0
        self._accum_switch_delta: int = 0

        self._active_pressed_keys: dict[int, float] = {}
        self._last_key_release_time: float | None = None
        self._last_was_correction: bool = False
        self._last_input_time: float | None = None
        self._last_key_time: float | None = None
        self._last_mouse_move_time: float | None = None
        self._last_mouse_sample_time: float | None = None

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
        key_category: str = "alphanumeric",
        key_slot: int | None = None,
        delta_ms: float | None = None,
        event_time: float | None = None,
    ) -> None:
        """Record an anonymous keystroke event (character content is never stored)."""
        del key_category  # Reserved for category telemetry; zero-PII by design.
        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            self._register_input_timestamp_unlocked(now)
            self._lifetime_keystrokes += 1
            self._slice_keystrokes += 1
            self._accum_keystrokes += 1
            self._accum_keystroke_delta += 1
            if is_correction:
                self._lifetime_corrections += 1
                self._slice_corrections += 1
                self._accum_corrections += 1
                self._accum_correction_delta += 1

            if self._slice_keystrokes == 1:
                self._burst_count += 1
                self._accum_bursts += 1

            if key_slot is not None:
                self._active_pressed_keys[key_slot] = now

            if self._last_key_release_time is not None:
                flight_ms = (now - self._last_key_release_time) * 1000.0
                if -200.0 <= flight_ms <= self._iki_max_outlier_ms:
                    self._slice_flight_times_ms.append(flight_ms)
                    self._accum_flight_times_ms.append(flight_ms)

            computed_delta_ms = delta_ms
            if computed_delta_ms is None and self._last_key_time is not None:
                computed_delta_ms = (now - self._last_key_time) * 1000.0
            self._last_key_time = now

            if computed_delta_ms is not None and computed_delta_ms >= 2000.0:
                self._pauses_gt_2s_count += 1
                self._accum_pauses_gt_2s += 1
                if self._slice_keystrokes > 1:
                    self._burst_count += 1
                    self._accum_bursts += 1

            if (
                computed_delta_ms is not None
                and self._iki_min_outlier_ms <= computed_delta_ms <= self._iki_max_outlier_ms
            ):
                self._iki_count += 1
                self._iki_sum_ms += computed_delta_ms
                self._iki_sum_sq_ms += computed_delta_ms * computed_delta_ms
                self._slice_iki_values_ms.append(computed_delta_ms)
                self._accum_iki_values_ms.append(computed_delta_ms)
                if is_correction:
                    self._slice_pre_corr_pauses_ms.append(computed_delta_ms)
                    self._accum_pre_corr_ms.append(computed_delta_ms)
                elif self._last_was_correction:
                    self._slice_post_corr_pauses_ms.append(computed_delta_ms)
                    self._accum_post_corr_ms.append(computed_delta_ms)

            self._last_was_correction = is_correction

    def record_key_release(
        self,
        *,
        key_slot: int | None = None,
        hold_time_ms: float | None = None,
        event_time: float | None = None,
    ) -> None:
        """Record an anonymous keyup event to compute dwell/hold time."""
        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            pressed_at = (
                self._active_pressed_keys.pop(key_slot, None) if key_slot is not None else None
            )
            computed_hold = hold_time_ms
            if computed_hold is None and pressed_at is not None:
                computed_hold = (now - pressed_at) * 1000.0
            if computed_hold is not None and 5.0 <= computed_hold <= 2000.0:
                self._slice_hold_times_ms.append(computed_hold)
                self._accum_hold_times_ms.append(computed_hold)
            self._last_key_release_time = now

    def record_mouse_click(self, *, event_time: float | None = None) -> None:
        """Record an anonymous mouse click."""
        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            self._register_input_timestamp_unlocked(now)
            self._lifetime_mouse_clicks += 1
            self._mouse_click_count += 1
            self._accum_mouse_clicks += 1
            self._accum_mouse_click_delta += 1

    def record_mouse_scroll(self, *, event_time: float | None = None) -> None:
        """Record an anonymous mouse scroll tick."""
        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            self._register_input_timestamp_unlocked(now)
            self._lifetime_scroll_events += 1
            self._scroll_count += 1
            self._accum_scrolls += 1
            self._accum_scroll_delta += 1

    def record_mouse_move(
        self,
        *,
        x: float | None = None,
        y: float | None = None,
        event_time: float | None = None,
    ) -> None:
        """Record a throttled mouse move tick and ephemeral 50Hz trajectory sample."""
        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            if (
                x is not None
                and y is not None
                and len(self._slice_mouse_points) < 250
                and (
                    self._last_mouse_sample_time is None
                    or (now - self._last_mouse_sample_time) >= 0.02
                )
            ):
                self._slice_mouse_points.append((x, y, now))
                self._accum_mouse_points.append((x, y, now))
                self._last_mouse_sample_time = now

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
                self._accum_context_switches += 1
                self._accum_switch_delta += 1
            self._last_process = sanitized
            self._last_window_id = window_id
            self._dwell_by_process[sanitized] = (
                self._dwell_by_process.get(sanitized, 0.0) + delta_seconds
            )
            self._accum_dwell[sanitized] = self._accum_dwell.get(sanitized, 0.0) + delta_seconds

    # --------------------------------------------------------------------------
    # Independent Sample-Driven Push Predicates & Consumers
    # --------------------------------------------------------------------------
    def has_good_keystroke_timing_sample(self, min_samples: int = IKI_MIN_VALID_SAMPLES) -> bool:
        """Return True if at least min_samples valid IKIs have accumulated."""
        with self._lock:
            return len(self._accum_iki_values_ms) >= min_samples

    def consume_keystroke_timing_metrics(self) -> tuple[RawKeystrokeTimingMetrics, int]:
        """Consume and reset accumulated keystroke timing, returning (metrics, keystroke_delta)."""
        with self._lock:
            ikis = list(self._accum_iki_values_ms)
            holds = list(self._accum_hold_times_ms)
            flights = list(self._accum_flight_times_ms)
            total_keys = self._accum_keystrokes
            delta_keys = self._accum_keystroke_delta

            # Reset keystroke accumulators
            self._accum_iki_values_ms.clear()
            self._accum_hold_times_ms.clear()
            self._accum_flight_times_ms.clear()
            self._accum_keystrokes = 0
            self._accum_keystroke_delta = 0

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

    def has_good_correction_pause_sample(self) -> bool:
        """Return True if any correction pauses or pauses >2s have accumulated."""
        with self._lock:
            return (
                len(self._accum_pre_corr_ms) > 0
                or len(self._accum_post_corr_ms) > 0
                or self._accum_corrections > 0
                or self._accum_pauses_gt_2s > 0
            )

    def consume_correction_pause_metrics(self) -> tuple[RawCorrectionPauseMetrics, int]:
        """Consume and reset accumulated correction/pause metrics."""
        with self._lock:
            pre_corrs = list(self._accum_pre_corr_ms)
            post_corrs = list(self._accum_post_corr_ms)
            corrs = self._accum_corrections
            corrs_delta = self._accum_correction_delta
            micros = self._accum_micro_pauses
            gt2s = self._accum_pauses_gt_2s
            bursts = self._accum_bursts

            self._accum_pre_corr_ms.clear()
            self._accum_post_corr_ms.clear()
            self._accum_corrections = 0
            self._accum_correction_delta = 0
            self._accum_micro_pauses = 0
            self._accum_pauses_gt_2s = 0
            self._accum_bursts = 0

        metrics = RawCorrectionPauseMetrics(
            pre_correction_pauses_ms=tuple(pre_corrs),
            post_correction_pauses_ms=tuple(post_corrs),
            pre_correction_pause_median_ms=(
                round(float(statistics.median(pre_corrs)), 2) if pre_corrs else 0.0
            ),
            post_correction_pause_median_ms=(
                round(float(statistics.median(post_corrs)), 2) if post_corrs else 0.0
            ),
            correction_keystrokes=corrs,
            micro_pauses_count=micros,
            pauses_gt_2s_count=gt2s,
            burst_count=bursts,
        )
        return metrics, corrs_delta

    def has_good_mouse_sample(self, min_points: int = 25) -> bool:
        """Return True if sufficient mouse trajectory points or clicks/scrolls have accumulated."""
        with self._lock:
            return (
                len(self._accum_mouse_points) >= min_points
                or self._accum_mouse_clicks >= 5
                or self._accum_scrolls >= 5
            )

    def consume_mouse_kinematics_metrics(self) -> tuple[RawMouseKinematicsMetrics, int, int]:
        """Consume and reset accumulated mouse kinematics, returning (metrics, clicks, scrolls)."""
        with self._lock:
            pts = list(self._accum_mouse_points)
            clicks = self._accum_mouse_clicks
            scrolls = self._accum_scrolls
            click_delta = self._accum_mouse_click_delta
            scroll_delta = self._accum_scroll_delta

            self._accum_mouse_points.clear()
            self._accum_mouse_clicks = 0
            self._accum_scrolls = 0
            self._accum_mouse_click_delta = 0
            self._accum_scroll_delta = 0

        sampen, submov, auc, xflips = compute_mouse_kinematics(pts)
        metrics = RawMouseKinematicsMetrics(
            sample_entropy=sampen,
            submovements=submov,
            curvature_auc=auc,
            x_flips=xflips,
            mouse_clicks=clicks,
            scroll_events=scrolls,
        )
        return metrics, click_delta, scroll_delta

    def has_good_attention_sample(self) -> bool:
        """Return True if a context switch occurred or at least 15s dwell recorded."""
        with self._lock:
            total_dwell = sum(self._accum_dwell.values())
            return self._accum_context_switches > 0 or total_dwell >= 15.0

    def consume_attention_window_metrics(self) -> tuple[RawAttentionWindowMetrics, int]:
        """Consume and reset accumulated process dwell & switches."""
        with self._lock:
            dwell = dict(self._accum_dwell)
            switches = self._accum_context_switches
            switch_delta = self._accum_switch_delta
            primary = self._last_process or "idle"

            self._accum_dwell.clear()
            self._accum_context_switches = 0
            self._accum_switch_delta = 0

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
        return metrics, switch_delta

    def consume_temporal_session_metrics(self) -> RawTemporalSessionMetrics:
        """Read current temporal and session duration metrics."""
        now = time.monotonic()
        uptime = self.session_uptime_seconds
        active_work = self.active_work_seconds
        away_idle = self.away_idle_seconds
        idle_gap = self.seconds_since_last_input(now)
        with self._lock:
            dur = max(0.0, now - self._slice_start_time)
            active = min(dur, self._active_seconds)

        return RawTemporalSessionMetrics(
            window_active_seconds=round(active, 4),
            window_duration_seconds=round(dur, 4),
            session_uptime_seconds=round(uptime, 4),
            active_work_seconds=round(active_work, 4),
            away_idle_seconds=round(away_idle, 4),
            idle_gap_seconds=round(idle_gap, 4),
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
                iki_values_ms=tuple(self._slice_iki_values_ms),
                hold_times_ms=tuple(self._slice_hold_times_ms),
                flight_times_ms=tuple(self._slice_flight_times_ms),
                pre_correction_pauses_ms=tuple(self._slice_pre_corr_pauses_ms),
                post_correction_pauses_ms=tuple(self._slice_post_corr_pauses_ms),
                mouse_points=tuple(self._slice_mouse_points),
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
            self._slice_iki_values_ms = []
            self._slice_hold_times_ms = []
            self._slice_flight_times_ms = []
            self._slice_pre_corr_pauses_ms = []
            self._slice_post_corr_pauses_ms = []
            self._slice_mouse_points = []

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
        with self._lock:
            slices_copy = list(self._slices)
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

        metrics = pool_telemetry_samples(slices_copy)
        uptime_sec = self.session_uptime_seconds
        active_work_sec = self.active_work_seconds
        away_idle_sec = self.away_idle_seconds
        idle_gap_sec = self.seconds_since_last_input()
        raw_bundle = produce_raw_metrics_bundle(
            slices_copy,
            latest_slice=committed_slice,
            session_uptime_seconds=uptime_sec,
            active_work_seconds=active_work_sec,
            away_idle_seconds=away_idle_sec,
            idle_gap_seconds=idle_gap_sec,
        )

        return ActivitySnapshot(
            metrics=metrics,
            deltas=deltas,
            session_uptime_seconds=uptime_sec,
            active_work_seconds=active_work_sec,
            away_idle_seconds=away_idle_sec,
            idle_gap_seconds=idle_gap_sec,
            now_timestamp=now_timestamp if now_timestamp is not None else time.time(),
            raw=raw_bundle,
        )
