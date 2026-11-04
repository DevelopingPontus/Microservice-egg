"""Dimension 4: Circadian & Cumulative Load (Diurnal Phase, Post-Prandial Dip & Unbroken Load)."""

from collections.abc import Sequence
from datetime import datetime, tzinfo

from app.dimensions.base import (
    BaseDimension,
    DimensionContext,
    DimensionEpochProtocol,
    DimensionEvaluation,
    clamp_score,
)

RECOVERY_RESET_SECONDS: float = 1800.0  # 30 minutes off-screen resets cumulative active load
MIN_ACTIVE_SECONDS_PER_EPOCH: float = 3.0


def compute_continuous_load_minutes(
    epochs_chronological: Sequence[DimensionEpochProtocol],
) -> float:
    """Compute cumulative active screen minutes since the last >= 30-minute recovery gap."""
    if not epochs_chronological:
        return 0.0

    ordered = sorted(epochs_chronological, key=lambda epoch: epoch.timestamp_start)
    cumulative_seconds = 0.0
    idle_streak_seconds = 0.0
    last_active_end: float | None = None

    for epoch in ordered:
        is_epoch_active = epoch.active_seconds >= MIN_ACTIVE_SECONDS_PER_EPOCH or (
            epoch.scroll_count > 0 or epoch.mouse_click_count > 0
        )

        if last_active_end is not None:
            wall_gap = max(0.0, epoch.timestamp_start - last_active_end)
            if wall_gap >= RECOVERY_RESET_SECONDS:
                cumulative_seconds = 0.0
                idle_streak_seconds = 0.0

        if is_epoch_active:
            cumulative_seconds += epoch.duration_seconds
            idle_streak_seconds = 0.0
            last_active_end = epoch.timestamp_end
        else:
            idle_streak_seconds += epoch.duration_seconds
            if idle_streak_seconds >= RECOVERY_RESET_SECONDS:
                cumulative_seconds = 0.0
                last_active_end = None

    return cumulative_seconds / 60.0


class CircadianLoadDimension(BaseDimension):
    """Evaluates diurnal phase, post-prandial dip (13:00-15:00), and unbroken screen load."""

    def __init__(self, tz: tzinfo | None = None) -> None:
        self._tz = tz

    @property
    def name(self) -> str:
        """Canonical identifier for the Circadian & Cumulative Load dimension."""
        return "circadian_load"

    def evaluate(self, context: DimensionContext) -> DimensionEvaluation:
        """Evaluate biological diurnal window and cumulative unbroken load without a 30m reset."""
        if not context.epochs:
            return DimensionEvaluation(
                dimension_name=self.name,
                strain_score=0.0,
                state_label="rested_baseline",
                metrics={
                    "hour_of_day": 0,
                    "is_post_prandial_window": False,
                    "is_late_night_window": False,
                    "continuous_load_minutes": 0.0,
                },
                blameless_summary="No active epochs in window; cumulative load is at baseline.",
            )

        midpoint_ts = (context.epochs[0].timestamp_start + context.epochs[-1].timestamp_end) / 2.0
        local_dt = (
            datetime.fromtimestamp(midpoint_ts, tz=self._tz)
            if self._tz is not None
            else datetime.fromtimestamp(midpoint_ts).astimezone()
        )
        hour = local_dt.hour
        is_post_prandial = 13 <= hour < 15
        is_late_night = hour >= 22 or hour < 6

        combined_epochs = [*context.prior_epochs_today, *context.epochs]
        continuous_minutes = compute_continuous_load_minutes(combined_epochs)

        if continuous_minutes >= 120.0:
            state_label = "cumulative_load_depletion"
            over_hours = (continuous_minutes - 120.0) / 120.0
            dip_bonus = 0.10 if (is_post_prandial or is_late_night) else 0.0
            strain_score = clamp_score(0.75 + min(0.25, over_hours * 0.20 + dip_bonus))
            blameless_summary = (
                f"Continuous screen load has reached {continuous_minutes:.0f} minutes without "
                "a 30-minute recovery reset—schedule a restorative break or down-scope the task."
            )
        elif is_post_prandial:
            state_label = "post_prandial_biological_dip"
            load_factor = min(0.20, continuous_minutes / 450.0)
            strain_score = clamp_score(0.50 + load_factor)
            blameless_summary = (
                f"Operating inside the 13:00-15:00 post-prandial circadian trough "
                f"({continuous_minutes:.0f}m continuous load)—favor low-friction micro-steps."
            )
        elif is_late_night:
            state_label = "late_night_circadian_debt"
            load_factor = min(0.20, continuous_minutes / 360.0)
            strain_score = clamp_score(0.60 + load_factor)
            blameless_summary = (
                f"Late-hour session ({local_dt.strftime('%H:%M')}) increases executive depletion "
                f"after {continuous_minutes:.0f} minutes of continuous load."
            )
        else:
            state_label = "aligned_diurnal_window"
            strain_score = clamp_score(0.10 + min(0.35, continuous_minutes / 300.0))
            blameless_summary = (
                f"Aligned diurnal window ({local_dt.strftime('%H:%M')}) with "
                f"{continuous_minutes:.0f} minutes of cumulative active load since last reset."
            )

        return DimensionEvaluation(
            dimension_name=self.name,
            strain_score=strain_score,
            state_label=state_label,
            metrics={
                "hour_of_day": hour,
                "is_post_prandial_window": is_post_prandial,
                "is_late_night_window": is_late_night,
                "continuous_load_minutes": round(continuous_minutes, 2),
            },
            blameless_summary=blameless_summary,
        )
