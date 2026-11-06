"""Unit tests for the 4 Ground-Truth Scientific Dimensions."""

from app.common.models import (
    PooledTelemetryMetrics,
)
from app.output.dimensions import (
    AttentionalFragmentationDimension,
    DimensionContext,
    PsychomotorMechanicsDimension,
    SessionUptimeDimension,
    TemporalDynamicsDimension,
    create_default_registry,
)


def _make_dummy_metrics(
    *,
    duty_cycle: float = 0.70,
    shannon_entropy: float = 0.20,
    switches_per_minute: float = 0.5,
    correction_ratio: float = 0.05,
    iki_cv: float = 0.50,
    is_psychomotor_valid: bool = True,
    primary_process: str = "Code.exe",
    primary_process_ratio: float = 0.85,
    total_duration_seconds: float = 60.0,
    total_active_seconds: float = 42.0,
    total_keystrokes: int = 100,
    correction_keystrokes: int = 5,
    iki_count: int = 95,
) -> PooledTelemetryMetrics:
    return PooledTelemetryMetrics(
        sample_count=1,
        total_duration_seconds=total_duration_seconds,
        total_active_seconds=total_active_seconds,
        duty_cycle=duty_cycle,
        total_micro_pauses=2,
        total_mouse_clicks=5,
        total_scroll_events=1,
        total_context_switches=1,
        switches_per_minute=switches_per_minute,
        merged_dwell_seconds={primary_process: total_active_seconds},
        primary_process=primary_process,
        primary_process_ratio=primary_process_ratio,
        shannon_entropy=shannon_entropy,
        total_keystrokes=total_keystrokes,
        correction_keystrokes=correction_keystrokes,
        correction_ratio=correction_ratio,
        iki_count=iki_count,
        is_psychomotor_valid=is_psychomotor_valid,
        iki_mean_ms=180.0,
        iki_variance_ms2=8100.0,
        iki_std_dev_ms=90.0,
        iki_cv=iki_cv,
    )


def test_temporal_dynamics_dimension() -> None:
    dim = TemporalDynamicsDimension()
    assert dim.name == "temporal_dynamics"

    # Deep flow
    metrics = _make_dummy_metrics(duty_cycle=0.75)
    ctx = DimensionContext.create(metrics)
    eval_res = dim.evaluate(ctx)
    assert eval_res.state_label == "deep_sustained_flow"
    assert eval_res.strain_score <= 0.40

    # Idle / recovery
    metrics_idle = _make_dummy_metrics(duty_cycle=0.05)
    ctx_idle = DimensionContext.create(metrics_idle)
    eval_idle = dim.evaluate(ctx_idle)
    assert eval_idle.state_label == "idle_recovery"

    # Active reading (high scroll, low keystrokes, high primary ratio)
    metrics_reading = PooledTelemetryMetrics(
        sample_count=1,
        total_duration_seconds=60.0,
        total_active_seconds=20.0,
        duty_cycle=0.33,
        total_micro_pauses=1,
        total_mouse_clicks=1,
        total_scroll_events=10,
        total_context_switches=0,
        switches_per_minute=0.0,
        merged_dwell_seconds={"Docs.app": 20.0},
        primary_process="Docs.app",
        primary_process_ratio=0.80,
        shannon_entropy=0.0,
        total_keystrokes=5,
        correction_keystrokes=0,
        correction_ratio=0.0,
        iki_count=5,
        is_psychomotor_valid=False,
        iki_mean_ms=100.0,
        iki_variance_ms2=0.0,
        iki_std_dev_ms=0.0,
        iki_cv=0.0,
    )
    eval_reading = dim.evaluate(DimensionContext.create(metrics_reading))
    assert eval_reading.state_label == "active_reading"

    # Hesitant pacing (micro pauses)
    metrics_hesitant = PooledTelemetryMetrics(
        sample_count=1,
        total_duration_seconds=60.0,
        total_active_seconds=15.0,
        duty_cycle=0.25,
        total_micro_pauses=8,
        total_mouse_clicks=1,
        total_scroll_events=0,
        total_context_switches=0,
        switches_per_minute=0.0,
        merged_dwell_seconds={"Code.exe": 15.0},
        primary_process="Code.exe",
        primary_process_ratio=1.0,
        shannon_entropy=0.0,
        total_keystrokes=20,
        correction_keystrokes=1,
        correction_ratio=0.05,
        iki_count=19,
        is_psychomotor_valid=True,
        iki_mean_ms=100.0,
        iki_variance_ms2=0.0,
        iki_std_dev_ms=0.0,
        iki_cv=0.0,
    )
    eval_hesitant = dim.evaluate(DimensionContext.create(metrics_hesitant))
    assert eval_hesitant.state_label == "hesitant_fragmented_pacing"

    # Moderate engagement
    metrics_mod = _make_dummy_metrics(duty_cycle=0.50)
    eval_mod = dim.evaluate(DimensionContext.create(metrics_mod))
    assert eval_mod.state_label == "moderate_engagement"


def test_attentional_fragmentation_dimension() -> None:
    dim = AttentionalFragmentationDimension()
    assert dim.name == "attentional_fragmentation"

    # Locked focus
    metrics = _make_dummy_metrics(
        shannon_entropy=0.10,
        primary_process_ratio=0.90,
        switches_per_minute=0.5,
    )
    ctx = DimensionContext.create(metrics)
    eval_res = dim.evaluate(ctx)
    assert eval_res.state_label == "locked_single_app_focus"
    assert eval_res.strain_score <= 0.30

    # Thrashing
    metrics_thrash = _make_dummy_metrics(
        shannon_entropy=1.20,
        primary_process_ratio=0.40,
        switches_per_minute=6.0,
    )
    ctx_thrash = DimensionContext.create(metrics_thrash)
    eval_thrash = dim.evaluate(ctx_thrash)
    assert eval_thrash.state_label == "context_switch_thrashing"
    assert eval_thrash.strain_score >= 0.75

    # Structured multi-tool
    metrics_multi = _make_dummy_metrics(
        shannon_entropy=0.50,
        primary_process_ratio=0.65,
        switches_per_minute=2.0,
    )
    eval_multi = dim.evaluate(DimensionContext.create(metrics_multi))
    assert eval_multi.state_label == "structured_multi_tool_flow"

    # Dispersed attention
    metrics_disp = _make_dummy_metrics(
        shannon_entropy=0.85,
        primary_process_ratio=0.45,
        switches_per_minute=2.0,
    )
    eval_disp = dim.evaluate(DimensionContext.create(metrics_disp))
    assert eval_disp.state_label == "dispersed_attention"


def test_psychomotor_mechanics_dimension() -> None:
    dim = PsychomotorMechanicsDimension()
    assert dim.name == "psychomotor_mechanics"

    # Steady rhythm
    metrics = _make_dummy_metrics(correction_ratio=0.04, iki_cv=0.45, is_psychomotor_valid=True)
    ctx = DimensionContext.create(metrics)
    eval_res = dim.evaluate(ctx)
    assert eval_res.state_label == "steady_psychomotor_rhythm"
    assert eval_res.strain_score <= 0.40

    # Motor fatigue
    metrics_fatigue = _make_dummy_metrics(
        correction_ratio=0.22,
        iki_cv=0.85,
        is_psychomotor_valid=True,
    )
    ctx_fatigue = DimensionContext.create(metrics_fatigue)
    eval_fatigue = dim.evaluate(ctx_fatigue)
    assert eval_fatigue.state_label == "motor_fatigue_high_error"
    assert eval_fatigue.strain_score >= 0.75

    # Irregular burst typing (high CV, low correction)
    metrics_burst = _make_dummy_metrics(
        correction_ratio=0.05, iki_cv=0.75, is_psychomotor_valid=True
    )
    eval_burst = dim.evaluate(DimensionContext.create(metrics_burst))
    assert eval_burst.state_label == "irregular_burst_typing"

    # Elevated correction friction
    metrics_corr = _make_dummy_metrics(
        correction_ratio=0.12, iki_cv=0.50, is_psychomotor_valid=True
    )
    eval_corr = dim.evaluate(DimensionContext.create(metrics_corr))
    assert eval_corr.state_label == "elevated_correction_friction"

    # Invalid sample (< 10 IKIs)
    metrics_invalid = _make_dummy_metrics(is_psychomotor_valid=False, iki_count=3)
    ctx_invalid = DimensionContext.create(metrics_invalid)
    eval_invalid = dim.evaluate(ctx_invalid)
    assert eval_invalid.state_label == "insufficient_keystroke_sample"
    assert eval_invalid.strain_score == 0.0


def test_session_uptime_dimension() -> None:
    dim = SessionUptimeDimension()
    assert dim.name == "session_uptime"

    # Ramp up (<10 min)
    metrics = _make_dummy_metrics()
    ctx_ramp = DimensionContext.create(metrics, session_uptime_seconds=300.0)
    eval_ramp = dim.evaluate(ctx_ramp)
    assert eval_ramp.state_label == "session_ramp_up"
    assert eval_ramp.strain_score <= 0.20

    # Optimal window (10-45m)
    ctx_opt = DimensionContext.create(metrics, session_uptime_seconds=1800.0)
    eval_opt = dim.evaluate(ctx_opt)
    assert eval_opt.state_label == "optimal_focus_window"

    # Over 90m
    ctx_over = DimensionContext.create(metrics, session_uptime_seconds=6000.0)
    eval_over = dim.evaluate(ctx_over)
    assert eval_over.state_label == "session_fatigue_ceiling"
    assert eval_over.strain_score >= 0.80


def test_default_registry() -> None:
    registry = create_default_registry()
    assert len(registry.dimensions) == 4
    metrics = _make_dummy_metrics()
    ctx = DimensionContext.create(metrics, session_uptime_seconds=1200.0)
    results = registry.evaluate_all(ctx)
    assert set(results.keys()) == {
        "temporal_dynamics",
        "attentional_fragmentation",
        "psychomotor_mechanics",
        "session_uptime",
    }
