"""Unit tests for the Pluggable 4-Dimension Scientific Engine (app.dimensions)."""

import json
from datetime import UTC, datetime

import pytest

from app.output.dimensions import (
    AttentionalFragmentationDimension,
    BaseDimension,
    CircadianLoadDimension,
    DimensionContext,
    DimensionEvaluation,
    PsychomotorMechanicsDimension,
    TemporalDynamicsDimension,
    compute_continuous_load_minutes,
    create_default_registry,
)
from app.storage.repository import EpochMetricsDTO


def _make_epoch(
    *,
    timestamp_start: float = 1_700_000_000.0,
    duration: float = 30.0,
    primary_process: str = "Code",
    active_seconds: float = 24.0,
    micro_pause_count: int = 1,
    mouse_click_count: int = 2,
    scroll_count: int = 0,
    context_switch_count: int = 0,
    dwell: dict[str, float] | None = None,
    total_keystrokes: int = 60,
    correction_keystrokes: int = 2,
    iki_count: int = 50,
    iki_mean_ms: float = 180.0,
    iki_std_ms: float = 40.0,
) -> EpochMetricsDTO:
    """Construct a synthetic 30s EpochMetricsDTO with exact IKI sum and sum-of-squares."""
    dwell_map = dwell if dwell is not None else {primary_process: duration}
    iki_sum = iki_count * iki_mean_ms
    iki_sum_sq = iki_count * ((iki_std_ms * iki_std_ms) + (iki_mean_ms * iki_mean_ms))
    return EpochMetricsDTO(
        timestamp_start=timestamp_start,
        timestamp_end=timestamp_start + duration,
        primary_process=primary_process,
        active_seconds=active_seconds,
        micro_pause_count=micro_pause_count,
        mouse_click_count=mouse_click_count,
        scroll_count=scroll_count,
        context_switch_count=context_switch_count,
        dwell_distribution_json=json.dumps(dwell_map),
        total_keystrokes=total_keystrokes,
        correction_keystrokes=correction_keystrokes,
        iki_count=iki_count,
        iki_sum_ms=iki_sum,
        iki_sum_sq_ms=iki_sum_sq,
    )


def test_dimension_registry_open_closed_and_duplicate_guard() -> None:
    """Verify DimensionRegistry evaluates all 4 default dimensions and rejects duplicate names."""
    registry = create_default_registry(tz=UTC)
    assert len(registry.dimensions) == 4

    with pytest.raises(ValueError, match="already registered"):
        registry.register(TemporalDynamicsDimension())

    class CustomExperimentalDimension(BaseDimension):
        @property
        def name(self) -> str:
            return "custom_experimental"

        def evaluate(self, context: DimensionContext) -> DimensionEvaluation:
            return DimensionEvaluation(
                dimension_name=self.name,
                strain_score=0.42,
                state_label="custom_state",
                metrics={"epoch_count": context.pooled.epoch_count},
                blameless_summary="Custom experimental dimension.",
            )

    registry.register(CustomExperimentalDimension())
    ctx = DimensionContext.from_epochs([_make_epoch()])
    results = registry.evaluate_all(ctx)

    assert set(results.keys()) == {
        "temporal_dynamics",
        "attentional_fragmentation",
        "psychomotor_mechanics",
        "circadian_load",
        "custom_experimental",
    }
    assert results["custom_experimental"].strain_score == 0.42


def test_temporal_dynamics_states() -> None:
    """Verify TemporalDynamicsDimension distinguishes reading, flow, hesitation, and idle."""
    dim = TemporalDynamicsDimension()

    # 1. Empty / Idle recovery
    idle_ctx = DimensionContext.from_epochs(
        [_make_epoch(active_seconds=1.5, scroll_count=0, total_keystrokes=0, iki_count=0)]
    )
    idle_eval = dim.evaluate(idle_ctx)
    assert idle_eval.state_label == "idle_recovery"
    assert idle_eval.strain_score == 0.10

    # 2. Active Reading ("Taking In Input": scrolling with low keystrokes and high primary ratio)
    reading_ctx = DimensionContext.from_epochs(
        [
            _make_epoch(
                primary_process="Firefox",
                active_seconds=4.0,
                scroll_count=6,
                total_keystrokes=2,
                iki_count=1,
            ),
            _make_epoch(
                timestamp_start=1_700_000_030.0,
                primary_process="Firefox",
                active_seconds=3.5,
                scroll_count=5,
                total_keystrokes=0,
                iki_count=0,
            ),
        ]
    )
    reading_eval = dim.evaluate(reading_ctx)
    assert reading_eval.state_label == "active_reading"
    assert reading_eval.metrics["is_active_reading"] is True
    assert reading_eval.strain_score <= 0.30

    # 3. Deep Sustained Flow
    flow_ctx = DimensionContext.from_epochs([_make_epoch(active_seconds=25.0, micro_pause_count=1)])
    flow_eval = dim.evaluate(flow_ctx)
    assert flow_eval.state_label == "deep_sustained_flow"
    assert 0.20 <= flow_eval.strain_score <= 0.35

    # 4. Hesitant / Fragmented Pacing (high micro-pauses)
    hesitant_ctx = DimensionContext.from_epochs(
        [_make_epoch(active_seconds=15.0, micro_pause_count=5)]
    )
    hesitant_eval = dim.evaluate(hesitant_ctx)
    assert hesitant_eval.state_label == "hesitant_fragmented_pacing"
    assert hesitant_eval.strain_score >= 0.55

    # 5. Moderate Engagement (duty cycle 50%, low micro-pauses)
    moderate_ctx = DimensionContext.from_epochs(
        [_make_epoch(active_seconds=15.0, micro_pause_count=1)]
    )
    moderate_eval = dim.evaluate(moderate_ctx)
    assert moderate_eval.state_label == "moderate_engagement"
    assert 0.35 <= moderate_eval.strain_score <= 0.50

    # 6. Over-Extended Focus (>= 90 minutes at high duty cycle)
    long_epochs = [
        _make_epoch(timestamp_start=1_700_000_000.0 + i * 30.0, active_seconds=24.0)
        for i in range(190)  # 95 minutes
    ]
    over_eval = dim.evaluate(DimensionContext.from_epochs(long_epochs))
    assert over_eval.state_label == "over_extended_focus"
    assert over_eval.strain_score >= 0.75


def test_attentional_fragmentation_states() -> None:
    """Verify AttentionalFragmentationDimension classifies focus, multi-tool, and thrashing."""
    dim = AttentionalFragmentationDimension()

    # 1. Empty / Idle unallocated
    empty_eval = dim.evaluate(DimensionContext.from_epochs([]))
    assert empty_eval.state_label == "idle_unallocated"
    assert empty_eval.strain_score == 0.0

    # 2. Locked single-app focus
    locked_ctx = DimensionContext.from_epochs(
        [_make_epoch(dwell={"Code": 30.0}, context_switch_count=0)]
    )
    locked_eval = dim.evaluate(locked_ctx)
    assert locked_eval.state_label == "locked_single_app_focus"
    assert locked_eval.strain_score <= 0.20

    # 3. Structured multi-tool flow (IDE + Browser, low switch rate)
    multi_ctx = DimensionContext.from_epochs(
        [_make_epoch(dwell={"Code": 21.0, "Firefox": 9.0}, context_switch_count=1)]
    )
    multi_eval = dim.evaluate(multi_ctx)
    assert multi_eval.state_label == "structured_multi_tool_flow"
    assert 0.25 <= multi_eval.strain_score <= 0.50

    # 4. Dispersed attention (split across 3 apps with moderate switch count)
    dispersed_ctx = DimensionContext.from_epochs(
        [
            _make_epoch(
                dwell={"Code": 14.0, "Firefox": 10.0, "Terminal": 6.0},
                context_switch_count=1,
            )
        ]
    )
    dispersed_eval = dim.evaluate(dispersed_ctx)
    assert dispersed_eval.state_label == "dispersed_attention"
    assert 0.50 <= dispersed_eval.strain_score <= 0.74

    # 5. Context-switch thrashing (high switch rate & high entropy)
    thrash_ctx = DimensionContext.from_epochs(
        [
            _make_epoch(
                dwell={"Code": 8.0, "Slack": 8.0, "Firefox": 7.0, "Mail": 7.0},
                context_switch_count=5,
            )
        ]
    )
    thrash_eval = dim.evaluate(thrash_ctx)
    assert thrash_eval.state_label == "context_switch_thrashing"
    assert thrash_eval.strain_score >= 0.75


def test_psychomotor_mechanics_states_and_sample_guard() -> None:
    """Verify PsychomotorMechanicsDimension guards small samples and detects motor strain."""
    dim = PsychomotorMechanicsDimension()

    # 1. Insufficient keystroke sample (e.g., reading block with iki_count < 10)
    reading_ctx = DimensionContext.from_epochs(
        [_make_epoch(total_keystrokes=4, correction_keystrokes=2, iki_count=3)]
    )
    invalid_eval = dim.evaluate(reading_ctx)
    assert invalid_eval.state_label == "insufficient_keystroke_sample"
    assert invalid_eval.strain_score == 0.0
    assert invalid_eval.metrics["is_psychomotor_valid"] is False

    # 2. Steady psychomotor rhythm (low CV, low correction ratio)
    steady_ctx = DimensionContext.from_epochs(
        [
            _make_epoch(
                total_keystrokes=80,
                correction_keystrokes=2,
                iki_count=75,
                iki_mean_ms=160.0,
                iki_std_ms=32.0,  # CV = 0.20
            )
        ]
    )
    steady_eval = dim.evaluate(steady_ctx)
    assert steady_eval.state_label == "steady_psychomotor_rhythm"
    assert steady_eval.strain_score <= 0.30

    # 3. Irregular burst typing (high CV >= 0.55, low correction ratio)
    burst_ctx = DimensionContext.from_epochs(
        [
            _make_epoch(
                total_keystrokes=60,
                correction_keystrokes=2,
                iki_count=55,
                iki_mean_ms=200.0,
                iki_std_ms=130.0,  # CV = 0.65
            )
        ]
    )
    burst_eval = dim.evaluate(burst_ctx)
    assert burst_eval.state_label == "irregular_burst_typing"
    assert 0.50 <= burst_eval.strain_score <= 0.75

    # 4. Elevated correction friction (steady CV, correction ratio >= 10%)
    corr_ctx = DimensionContext.from_epochs(
        [
            _make_epoch(
                total_keystrokes=80,
                correction_keystrokes=10,  # 12.5%
                iki_count=75,
                iki_mean_ms=170.0,
                iki_std_ms=40.0,  # CV = 0.235
            )
        ]
    )
    corr_eval = dim.evaluate(corr_ctx)
    assert corr_eval.state_label == "elevated_correction_friction"
    assert 0.45 <= corr_eval.strain_score <= 0.70

    # 5. Motor fatigue & high error (correction ratio >= 18%)
    fatigue_ctx = DimensionContext.from_epochs(
        [
            _make_epoch(
                total_keystrokes=100,
                correction_keystrokes=24,  # 24%
                iki_count=90,
                iki_mean_ms=220.0,
                iki_std_ms=165.0,  # CV = 0.75
            )
        ]
    )
    fatigue_eval = dim.evaluate(fatigue_ctx)
    assert fatigue_eval.state_label == "motor_fatigue_high_error"
    assert fatigue_eval.strain_score >= 0.75


def test_circadian_load_windows_and_30min_recovery_reset() -> None:
    """Verify CircadianLoadDimension detects diurnal windows, dip, and 30m recovery resets."""
    dim = CircadianLoadDimension(tz=UTC)

    # 1. Empty baseline
    empty_eval = dim.evaluate(DimensionContext.from_epochs([]))
    assert empty_eval.state_label == "rested_baseline"
    assert empty_eval.strain_score == 0.0
    assert compute_continuous_load_minutes([]) == 0.0

    # 2. Aligned morning window (10:00 UTC)
    morning_ts = datetime(2026, 11, 3, 10, 0, 0, tzinfo=UTC).timestamp()
    morning_ctx = DimensionContext.from_epochs([_make_epoch(timestamp_start=morning_ts)])
    morning_eval = dim.evaluate(morning_ctx)
    assert morning_eval.state_label == "aligned_diurnal_window"
    assert morning_eval.metrics["is_post_prandial_window"] is False
    assert morning_eval.strain_score <= 0.35

    # 3. Post-prandial biological dip (14:00 UTC)
    dip_ts = datetime(2026, 11, 3, 14, 0, 0, tzinfo=UTC).timestamp()
    dip_ctx = DimensionContext.from_epochs([_make_epoch(timestamp_start=dip_ts)])
    dip_eval = dim.evaluate(dip_ctx)
    assert dip_eval.state_label == "post_prandial_biological_dip"
    assert dip_eval.metrics["is_post_prandial_window"] is True
    assert 0.50 <= dip_eval.strain_score <= 0.70

    # 4. Late-night circadian debt (23:15 UTC)
    night_ts = datetime(2026, 11, 3, 23, 15, 0, tzinfo=UTC).timestamp()
    night_ctx = DimensionContext.from_epochs([_make_epoch(timestamp_start=night_ts)])
    night_eval = dim.evaluate(night_ctx)
    assert night_eval.state_label == "late_night_circadian_debt"
    assert night_eval.metrics["is_late_night_window"] is True
    assert night_eval.strain_score >= 0.60

    # 5. Cumulative unbroken load >= 120 minutes (240 x 30s epochs) vs 30-min recovery reset
    prior_2h = [
        _make_epoch(timestamp_start=morning_ts + i * 30.0, active_seconds=20.0) for i in range(240)
    ]
    current_epoch = _make_epoch(timestamp_start=morning_ts + 240 * 30.0, active_seconds=22.0)
    depletion_ctx = DimensionContext.from_epochs(
        [current_epoch],
        prior_epochs_today=prior_2h,
    )
    depletion_eval = dim.evaluate(depletion_ctx)
    assert depletion_eval.state_label == "cumulative_load_depletion"
    assert depletion_eval.strain_score >= 0.75
    assert depletion_eval.metrics["continuous_load_minutes"] == 120.5

    # 6. Verify a 30-minute idle streak or wall-clock gap resets cumulative load
    idle_reset_epochs = [
        _make_epoch(
            timestamp_start=morning_ts + (240 + i) * 30.0,
            active_seconds=0.0,
            mouse_click_count=0,
            scroll_count=0,
        )
        for i in range(60)  # 30 minutes of idle epochs
    ]
    fresh_epoch = _make_epoch(timestamp_start=morning_ts + 300 * 30.0, active_seconds=20.0)
    reset_ctx = DimensionContext.from_epochs(
        [fresh_epoch],
        prior_epochs_today=[*prior_2h, *idle_reset_epochs],
    )
    reset_eval = dim.evaluate(reset_ctx)
    assert reset_eval.state_label == "aligned_diurnal_window"
    assert reset_eval.metrics["continuous_load_minutes"] == 0.5
