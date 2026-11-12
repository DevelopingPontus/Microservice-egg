"""Dimension 1: Temporal Dynamics (Duty Cycle, Flow Duration, Micro-Pauses & Reading)."""

from app.analysis.strain import DimensionEvaluation, clamp_score
from app.collector import PooledTelemetryMetrics


def evaluate_temporal(metrics: PooledTelemetryMetrics) -> DimensionEvaluation:
    """Evaluate temporal pacing and interaction modality across the 60s sliding window."""
    duration_minutes = metrics.total_duration_seconds / 60.0
    duty_cycle = metrics.duty_cycle

    if duration_minutes > 0.0:
        effective_rate_minutes = max(duration_minutes, 0.25)
        micro_pauses_per_min = metrics.total_micro_pauses / effective_rate_minutes
        scrolls_per_min = metrics.total_scroll_events / effective_rate_minutes
        keystrokes_per_min = metrics.total_keystrokes / effective_rate_minutes
    else:
        micro_pauses_per_min = 0.0
        scrolls_per_min = 0.0
        keystrokes_per_min = 0.0

    is_active_reading = (
        duration_minutes > 0.0
        and scrolls_per_min >= 1.0
        and keystrokes_per_min < 25.0
        and metrics.primary_process_ratio >= 0.70
    )

    if duration_minutes <= 0.0 or (duty_cycle < 0.15 and not is_active_reading):
        state_label = "idle_recovery"
        strain_score = 0.10
        blameless_summary = (
            "Low interaction density indicates an off-screen recovery pause or transition."
        )
    elif is_active_reading:
        state_label = "active_reading"
        strain_score = clamp_score(0.15 + min(0.15, duration_minutes / 60.0))
        blameless_summary = (
            f"Steady scroll progression ({scrolls_per_min:.1f}/min) in "
            f"{metrics.primary_process} reflects active reading and information intake."
        )
    elif micro_pauses_per_min >= 6.0 or (0.15 <= duty_cycle < 0.40):
        state_label = "hesitant_fragmented_pacing"
        pause_penalty = min(0.30, max(0.0, (micro_pauses_per_min - 4.0) * 0.04))
        strain_score = clamp_score(0.55 + pause_penalty)
        blameless_summary = (
            f"Frequent 1-5s micro-pauses ({micro_pauses_per_min:.1f}/min) observed—consider "
            "breaking the current step into smaller sub-tasks if encountering friction."
        )
    elif duty_cycle >= 0.65:
        state_label = "deep_sustained_flow"
        strain_score = clamp_score(0.20 + min(0.15, duration_minutes / 60.0))
        blameless_summary = (
            f"Consistent cadence ({duty_cycle:.0%} duty cycle) with steady momentum."
        )
    else:
        state_label = "moderate_engagement"
        strain_score = clamp_score(0.35 + min(0.15, micro_pauses_per_min * 0.025))
        blameless_summary = (
            f"Balanced working cadence ({duty_cycle:.0%} duty cycle) across "
            f"{duration_minutes:.1f} minutes."
        )

    return DimensionEvaluation(
        dimension_name="temporal_dynamics",
        strain_score=strain_score,
        state_label=state_label,
        metrics={
            "duty_cycle": round(duty_cycle, 4),
            "duration_minutes": round(duration_minutes, 2),
            "micro_pauses_per_minute": round(micro_pauses_per_min, 2),
            "scroll_events_per_minute": round(scrolls_per_min, 2),
            "keystrokes_per_minute": round(keystrokes_per_min, 2),
            "is_active_reading": is_active_reading,
        },
        blameless_summary=blameless_summary,
    )
