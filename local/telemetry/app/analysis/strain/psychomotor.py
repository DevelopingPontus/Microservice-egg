"""Dimension 3: Psychomotor Mechanics (IKI CV & Correction Ratio)."""

from app.analysis.strain import DimensionEvaluation, clamp_score
from app.collector import PooledTelemetryMetrics


def evaluate_psychomotor(metrics: PooledTelemetryMetrics) -> DimensionEvaluation:
    """Evaluate typing cadence variability and correction ratio when sample is valid."""
    is_valid = metrics.is_psychomotor_valid
    iki_cv = metrics.iki_cv
    correction_ratio = metrics.correction_ratio

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
            max(0.0, correction_ratio - 0.15) * 1.2 + max(0.0, iki_cv - 0.60) * 0.3,
        )
        strain_score = clamp_score(raw_score)
        blameless_summary = (
            f"Elevated backspace/delete rate ({correction_ratio:.1%}) and keystroke "
            f"variability (CV={iki_cv:.2f}) signal psychomotor fatigue."
        )
    elif iki_cv >= 0.70 and correction_ratio < 0.18:
        state_label = "irregular_burst_typing"
        strain_score = clamp_score(0.50 + min(0.22, (iki_cv - 0.55) * 0.5 + correction_ratio))
        blameless_summary = (
            f"Stop-and-go typing cadence (IKI CV={iki_cv:.2f}, "
            f"mean={metrics.iki_mean_ms:.0f}ms) reflects high planning load between bursts."
        )
    elif correction_ratio >= 0.10:
        state_label = "elevated_correction_friction"
        strain_score = clamp_score(0.45 + min(0.25, (correction_ratio - 0.10) * 2.0))
        blameless_summary = (
            f"Moderate correction ratio ({correction_ratio:.1%}) alongside steady cadence "
            f"(IKI CV={iki_cv:.2f})."
        )
    else:
        state_label = "steady_psychomotor_rhythm"
        strain_score = clamp_score(0.10 + iki_cv * 0.25 + correction_ratio * 0.8)
        blameless_summary = (
            f"Rhythmic keystroke execution (IKI CV={iki_cv:.2f}, correction rate "
            f"{correction_ratio:.1%})."
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
            "correction_ratio": round(correction_ratio, 4),
            "total_keystrokes": metrics.total_keystrokes,
            "correction_keystrokes": metrics.correction_keystrokes,
        },
        blameless_summary=blameless_summary,
    )
