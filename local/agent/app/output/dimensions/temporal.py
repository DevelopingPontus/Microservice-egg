"""Dimension 1: Temporal Dynamics (Duty Cycle, Flow Duration, Micro-Pauses & Active Reading)."""

from app.common.config import MIN_RATE_DURATION_SECONDS
from app.output.dimensions.base import (
    BaseDimension,
    DimensionContext,
    DimensionEvaluation,
    clamp_score,
)


class TemporalDynamicsDimension(BaseDimension):
    """Evaluates duty cycle, focus duration, micro-pause rate, and reading vs stalling."""

    @property
    def name(self) -> str:
        """Canonical identifier for the Temporal Dynamics dimension."""
        return "temporal_dynamics"

    def evaluate(self, context: DimensionContext) -> DimensionEvaluation:
        """Evaluate temporal pacing and interaction modality across pooled epochs."""
        pooled = context.pooled
        duration_minutes = pooled.total_duration_seconds / 60.0
        duty_cycle = pooled.duty_cycle

        if duration_minutes > 0.0:
            effective_rate_minutes = max(duration_minutes, MIN_RATE_DURATION_SECONDS / 60.0)
            micro_pauses_per_min = pooled.total_micro_pauses / effective_rate_minutes
            scrolls_per_min = pooled.total_scroll_events / effective_rate_minutes
            keystrokes_per_min = pooled.total_keystrokes / effective_rate_minutes
        else:
            micro_pauses_per_min = 0.0
            scrolls_per_min = 0.0
            keystrokes_per_min = 0.0

        is_active_reading = (
            duration_minutes > 0.0
            and scrolls_per_min >= 1.5
            and keystrokes_per_min < 25.0
            and pooled.primary_process_ratio >= 0.70
        )

        if duration_minutes <= 0.0 or (duty_cycle < 0.15 and not is_active_reading):
            state_label = "idle_recovery"
            strain_score = 0.10
            blameless_summary = (
                "Low interaction density indicates an off-screen recovery pause or transition."
            )
        elif is_active_reading:
            state_label = "active_reading"
            strain_score = clamp_score(0.15 + min(0.15, duration_minutes / 360.0))
            blameless_summary = (
                f"Steady scroll progression ({scrolls_per_min:.1f}/min) in "
                f"{pooled.primary_process} reflects active reading and information intake."
            )
        elif duration_minutes >= 90.0 and duty_cycle >= 0.65:
            state_label = "over_extended_focus"
            overrun_factor = min(0.25, (duration_minutes - 90.0) / 180.0)
            strain_score = clamp_score(0.75 + overrun_factor)
            blameless_summary = (
                f"Sustained high utilization ({duty_cycle:.0%} duty cycle) for "
                f"{duration_minutes:.0f} minutes exceeds optimal single-block capacity."
            )
        elif micro_pauses_per_min >= 6.0 or (0.15 <= duty_cycle < 0.40):
            state_label = "hesitant_fragmented_pacing"
            pause_penalty = min(0.30, max(0.0, (micro_pauses_per_min - 4.0) * 0.04))
            strain_score = clamp_score(0.55 + pause_penalty)
            blameless_summary = (
                f"Frequent 1-5s micro-pauses ({micro_pauses_per_min:.1f}/min) suggest high "
                "cognitive friction—consider breaking the current step into smaller sub-tasks."
            )
        elif duty_cycle >= 0.65:
            state_label = "deep_sustained_flow"
            strain_score = clamp_score(0.20 + min(0.15, duration_minutes / 300.0))
            blameless_summary = (
                f"Consistent interaction cadence ({duty_cycle:.0%} duty cycle) with low "
                f"hesitation ({micro_pauses_per_min:.1f} micro-pauses/min)."
            )
        else:
            state_label = "moderate_engagement"
            strain_score = clamp_score(0.35 + min(0.15, micro_pauses_per_min * 0.025))
            blameless_summary = (
                f"Balanced working cadence ({duty_cycle:.0%} duty cycle) across "
                f"{duration_minutes:.1f} minutes."
            )

        return DimensionEvaluation(
            dimension_name=self.name,
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
