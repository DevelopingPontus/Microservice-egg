"""Dimension 4: Session Uptime & Continuity (Continuous Load Duration & Fatigue)."""

from app.analysis.strain import DimensionEvaluation, clamp_score


def evaluate_uptime(session_uptime_seconds: float) -> DimensionEvaluation:
    """Evaluate continuous session uptime and fatigue thresholds."""
    uptime_minutes = session_uptime_seconds / 60.0

    if uptime_minutes >= 90.0:
        state_label = "session_fatigue_ceiling"
        over_90 = min(1.0, (uptime_minutes - 90.0) / 90.0)
        strain_score = clamp_score(0.80 + over_90 * 0.20)
        blameless_summary = (
            f"Continuous unbroken load has reached {uptime_minutes:.0f} minutes "
            "— schedule a restorative break to reset executive fatigue."
        )
    elif uptime_minutes >= 45.0:
        state_label = "elevated_continuous_load"
        progress_45_to_90 = (uptime_minutes - 45.0) / 45.0
        strain_score = clamp_score(0.40 + progress_45_to_90 * 0.35)
        blameless_summary = (
            f"Active session duration is {uptime_minutes:.0f} minutes "
            "— approaching optimal single-session focus ceiling."
        )
    elif uptime_minutes >= 10.0:
        state_label = "optimal_focus_window"
        strain_score = clamp_score(0.15 + (uptime_minutes / 45.0) * 0.20)
        blameless_summary = (
            f"Operating inside the optimal focus window ({uptime_minutes:.0f}m continuous uptime)."
        )
    else:
        state_label = "session_ramp_up"
        strain_score = 0.10
        blameless_summary = f"Session recently initiated ({uptime_minutes:.1f}m continuous uptime)."

    return DimensionEvaluation(
        dimension_name="session_uptime",
        strain_score=strain_score,
        state_label=state_label,
        metrics={
            "session_uptime_seconds": round(session_uptime_seconds, 1),
            "session_uptime_minutes": round(uptime_minutes, 1),
            "is_extended_session": uptime_minutes >= 45.0,
            "is_critical_session": uptime_minutes >= 90.0,
        },
        blameless_summary=blameless_summary,
    )
