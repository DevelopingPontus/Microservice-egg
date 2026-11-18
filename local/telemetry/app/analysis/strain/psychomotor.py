"""Dimension 3: Psychomotor Mechanics (IKI MAD/CV, Hold/Flight Time, Correction Slowing & QCD)."""

import math
from dataclasses import dataclass

from app.analysis.strain import DimensionEvaluation, clamp_score
from app.collector import PooledTelemetryMetrics

# Rested baseline reference vector (ms): (iki_mad_ms, hold_time_median_ms, post_correction_pause_ms)
_RESTED_BASELINE_MAD_MS = 35.0
_RESTED_BASELINE_HOLD_MS = 90.0
_RESTED_BASELINE_POST_CORR_MS = 220.0


@dataclass(frozen=True, slots=True)
class FatigueDriftState:
    """Immutable CUSUM Quick Change Detection (QCD) state for psychomotor fatigue drift."""

    baseline_distance: float = 0.0
    cusum_score: float = 0.0
    sample_count: int = 0
    is_fatigue_shift_detected: bool = False


def compute_qcd_fatigue_cusum(
    metrics: PooledTelemetryMetrics,
    previous_state: FatigueDriftState | None = None,
    *,
    drift_allowance: float = 0.35,
    shift_threshold: float = 2.5,
) -> FatigueDriftState:
    """Pure CUSUM Quick Change Detection over rested-baseline keystroke feature distance."""
    prev = previous_state if previous_state is not None else FatigueDriftState()
    if not metrics.is_psychomotor_valid:
        return prev

    mad_norm = max(0.0, (metrics.iki_mad_ms - _RESTED_BASELINE_MAD_MS) / _RESTED_BASELINE_MAD_MS)
    hold_norm = (
        max(
            0.0, (metrics.hold_time_median_ms - _RESTED_BASELINE_HOLD_MS) / _RESTED_BASELINE_HOLD_MS
        )
        if metrics.hold_time_median_ms > 0.0
        else 0.0
    )
    corr_pause_norm = (
        max(
            0.0,
            (metrics.post_correction_pause_ms - _RESTED_BASELINE_POST_CORR_MS)
            / _RESTED_BASELINE_POST_CORR_MS,
        )
        if metrics.post_correction_pause_ms > 0.0
        else 0.0
    )

    distance = round(math.sqrt(mad_norm**2 + hold_norm**2 + corr_pause_norm**2), 4)
    next_cusum = round(max(0.0, min(10.0, prev.cusum_score + (distance - drift_allowance))), 4)
    return FatigueDriftState(
        baseline_distance=distance,
        cusum_score=next_cusum,
        sample_count=prev.sample_count + 1,
        is_fatigue_shift_detected=next_cusum >= shift_threshold,
    )


def evaluate_psychomotor(metrics: PooledTelemetryMetrics) -> DimensionEvaluation:
    """Evaluate typing cadence variability, hold time, correction slowing, and correction ratio."""
    is_valid = metrics.is_psychomotor_valid
    iki_cv = metrics.iki_cv
    iki_mad = metrics.iki_mad_ms
    hold_ms = metrics.hold_time_median_ms
    pre_corr_ms = metrics.pre_correction_pause_ms
    post_corr_ms = metrics.post_correction_pause_ms
    correction_ratio = metrics.correction_ratio

    # Elevated MAD (>75ms) or post-correction schema-recovery slowing (>450ms) adds friction.
    mad_bonus = max(0.0, (iki_mad - 60.0) / 250.0)
    recovery_bonus = max(0.0, (post_corr_ms - 400.0) / 1500.0) if post_corr_ms > 0.0 else 0.0

    if not is_valid:
        state_label = "insufficient_keystroke_sample"
        strain_score = 0.0
        blameless_summary = (
            f"Keystroke sample ({metrics.iki_count} IKIs < 10 minimum) is excluded "
            "from motor strain scoring during non-typing or reading intervals."
        )
    elif correction_ratio >= 0.18 or (iki_cv >= 0.70 and correction_ratio >= 0.12):
        state_label = "motor_fatigue_high_error"
        raw_score = 0.75 + min(
            0.25,
            max(0.0, correction_ratio - 0.15) * 1.2
            + max(0.0, iki_cv - 0.60) * 0.3
            + mad_bonus * 0.2
            + recovery_bonus * 0.2,
        )
        strain_score = clamp_score(raw_score)
        blameless_summary = (
            f"Elevated correction rate ({correction_ratio:.1%}), keystroke MAD ({iki_mad:.0f}ms), "
            f"and cadence variability (CV={iki_cv:.2f}) signal psychomotor fatigue."
        )
    elif iki_cv >= 0.70 and correction_ratio < 0.18:
        state_label = "irregular_burst_typing"
        strain_score = clamp_score(
            0.50 + min(0.22, (iki_cv - 0.55) * 0.5 + correction_ratio + mad_bonus * 0.2)
        )
        blameless_summary = (
            f"Stop-and-go typing cadence (IKI CV={iki_cv:.2f}, MAD={iki_mad:.0f}ms, "
            f"mean={metrics.iki_mean_ms:.0f}ms) reflects high planning load between bursts."
        )
    elif correction_ratio >= 0.10 or post_corr_ms >= 550.0:
        state_label = "elevated_correction_friction"
        strain_score = clamp_score(
            0.45 + min(0.25, max(0.0, correction_ratio - 0.10) * 2.0 + recovery_bonus)
        )
        blameless_summary = (
            f"Moderate correction friction ({correction_ratio:.1%}, post-correction pause "
            f"{post_corr_ms:.0f}ms) alongside cadence (IKI CV={iki_cv:.2f})."
        )
    else:
        state_label = "steady_psychomotor_rhythm"
        strain_score = clamp_score(0.10 + iki_cv * 0.25 + correction_ratio * 0.8 + mad_bonus * 0.15)
        blameless_summary = (
            f"Rhythmic keystroke execution (IKI CV={iki_cv:.2f}, MAD={iki_mad:.0f}ms, "
            f"hold={hold_ms:.0f}ms, correction rate {correction_ratio:.1%})."
        )

    return DimensionEvaluation(
        dimension_name="psychomotor_mechanics",
        strain_score=strain_score,
        state_label=state_label,
        metrics={
            "is_psychomotor_valid": is_valid,
            "iki_count": metrics.iki_count,
            "iki_mean_ms": round(metrics.iki_mean_ms, 2),
            "iki_std_dev_ms": round(metrics.iki_std_dev_ms, 2),
            "iki_cv": round(iki_cv, 4),
            "iki_mad_ms": round(iki_mad, 2),
            "hold_time_median_ms": round(hold_ms, 2),
            "flight_time_median_ms": round(metrics.flight_time_median_ms, 2),
            "pre_correction_pause_ms": round(pre_corr_ms, 2),
            "post_correction_pause_ms": round(post_corr_ms, 2),
            "correction_ratio": round(correction_ratio, 4),
            "total_keystrokes": metrics.total_keystrokes,
            "correction_keystrokes": metrics.correction_keystrokes,
        },
        blameless_summary=blameless_summary,
    )
