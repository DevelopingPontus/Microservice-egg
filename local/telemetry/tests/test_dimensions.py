"""Unit tests for `app/analysis/` (`strain/` and `workflow/`)."""

from app.analysis import (
    StatefulOverviewEngine,
    classify_app_category,
    evaluate_all_dimensions,
    evaluate_attentional,
    evaluate_psychomotor,
    evaluate_temporal,
    evaluate_uptime,
    resolve_keystroke_bucket,
    resolve_session_length_bucket,
    resolve_time_block,
)
from app.collector import PooledTelemetryMetrics


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
    total_scroll_events: int = 1,
) -> PooledTelemetryMetrics:
    return PooledTelemetryMetrics(
        sample_count=1,
        total_duration_seconds=total_duration_seconds,
        total_active_seconds=total_active_seconds,
        duty_cycle=duty_cycle,
        total_micro_pauses=2,
        total_mouse_clicks=5,
        total_scroll_events=total_scroll_events,
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
    metrics = _make_dummy_metrics(duty_cycle=0.75)
    eval_res = evaluate_temporal(metrics)
    assert eval_res.dimension_name == "temporal_dynamics"
    assert eval_res.state_label == "deep_sustained_flow"
    assert eval_res.strain_score <= 0.40

    metrics_idle = _make_dummy_metrics(duty_cycle=0.05)
    eval_idle = evaluate_temporal(metrics_idle)
    assert eval_idle.state_label == "idle_recovery"

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
    eval_reading = evaluate_temporal(metrics_reading)
    assert eval_reading.state_label == "active_reading"

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
    eval_hesitant = evaluate_temporal(metrics_hesitant)
    assert eval_hesitant.state_label == "hesitant_fragmented_pacing"

    metrics_mod = _make_dummy_metrics(duty_cycle=0.50)
    eval_mod = evaluate_temporal(metrics_mod)
    assert eval_mod.state_label == "moderate_engagement"


def test_attentional_fragmentation_dimension() -> None:
    metrics = _make_dummy_metrics(
        shannon_entropy=0.10,
        primary_process_ratio=0.90,
        switches_per_minute=0.5,
    )
    eval_res = evaluate_attentional(metrics)
    assert eval_res.dimension_name == "attentional_fragmentation"
    assert eval_res.state_label == "locked_single_app_focus"
    assert eval_res.strain_score <= 0.30

    metrics_thrash = _make_dummy_metrics(
        shannon_entropy=1.20,
        primary_process_ratio=0.40,
        switches_per_minute=6.0,
    )
    eval_thrash = evaluate_attentional(metrics_thrash)
    assert eval_thrash.state_label == "context_switch_thrashing"
    assert eval_thrash.strain_score >= 0.75

    metrics_multi = _make_dummy_metrics(
        shannon_entropy=0.50,
        primary_process_ratio=0.65,
        switches_per_minute=2.0,
    )
    eval_multi = evaluate_attentional(metrics_multi)
    assert eval_multi.state_label == "structured_multi_tool_flow"

    metrics_disp = _make_dummy_metrics(
        shannon_entropy=0.85,
        primary_process_ratio=0.45,
        switches_per_minute=2.0,
    )
    eval_disp = evaluate_attentional(metrics_disp)
    assert eval_disp.state_label == "dispersed_attention"


def test_psychomotor_mechanics_dimension() -> None:
    metrics = _make_dummy_metrics(correction_ratio=0.04, iki_cv=0.45, is_psychomotor_valid=True)
    eval_res = evaluate_psychomotor(metrics)
    assert eval_res.dimension_name == "psychomotor_mechanics"
    assert eval_res.state_label == "steady_psychomotor_rhythm"
    assert eval_res.strain_score <= 0.40

    metrics_fatigue = _make_dummy_metrics(
        correction_ratio=0.22,
        iki_cv=0.85,
        is_psychomotor_valid=True,
    )
    eval_fatigue = evaluate_psychomotor(metrics_fatigue)
    assert eval_fatigue.state_label == "motor_fatigue_high_error"
    assert eval_fatigue.strain_score >= 0.75

    metrics_burst = _make_dummy_metrics(
        correction_ratio=0.05, iki_cv=0.75, is_psychomotor_valid=True
    )
    eval_burst = evaluate_psychomotor(metrics_burst)
    assert eval_burst.state_label == "irregular_burst_typing"

    metrics_corr = _make_dummy_metrics(
        correction_ratio=0.12, iki_cv=0.50, is_psychomotor_valid=True
    )
    eval_corr = evaluate_psychomotor(metrics_corr)
    assert eval_corr.state_label == "elevated_correction_friction"

    metrics_invalid = _make_dummy_metrics(is_psychomotor_valid=False, iki_count=3)
    eval_invalid = evaluate_psychomotor(metrics_invalid)
    assert eval_invalid.state_label == "insufficient_keystroke_sample"
    assert eval_invalid.strain_score == 0.0


def test_session_uptime_dimension() -> None:
    eval_ramp = evaluate_uptime(300.0)
    assert eval_ramp.dimension_name == "session_uptime"
    assert eval_ramp.state_label == "session_ramp_up"
    assert eval_ramp.strain_score <= 0.20

    eval_opt = evaluate_uptime(1800.0)
    assert eval_opt.state_label == "optimal_focus_window"

    eval_ext = evaluate_uptime(3600.0)
    assert eval_ext.state_label == "elevated_continuous_load"

    eval_over = evaluate_uptime(6000.0)
    assert eval_over.state_label == "session_fatigue_ceiling"
    assert eval_over.strain_score >= 0.80


def test_evaluate_all_dimensions() -> None:
    metrics = _make_dummy_metrics()
    results = evaluate_all_dimensions(metrics, session_uptime_seconds=1200.0)
    assert set(results.keys()) == {
        "temporal_dynamics",
        "attentional_fragmentation",
        "psychomotor_mechanics",
        "session_uptime",
    }


def test_overview_helpers_and_work_category_order() -> None:
    assert classify_app_category("Code.exe") == "editor_terminal"
    assert classify_app_category("Slack.app") == "comms"
    assert classify_app_category("Firefox.app") == "browser_viewer"
    assert classify_app_category("idle") == "system_other"
    assert classify_app_category("CustomTool.exe") == "system_other"

    assert resolve_time_block(8) == "morning"
    assert resolve_time_block(12) == "midday"
    assert resolve_time_block(15) == "afternoon"
    assert resolve_time_block(20) == "evening"
    assert resolve_time_block(2) == "night"

    assert resolve_session_length_bucket(120.0) == "lt_5m"
    assert resolve_session_length_bucket(600.0) == "5m_15m"
    assert resolve_session_length_bucket(1200.0) == "15m_25m"
    assert resolve_session_length_bucket(1800.0) == "25m_plus"

    assert resolve_keystroke_bucket(0.0) == "0_kpm"
    assert resolve_keystroke_bucket(10.0) == "1_14_kpm"
    assert resolve_keystroke_bucket(20.0) == "15_29_kpm"
    assert resolve_keystroke_bucket(50.0) == "30_79_kpm"
    assert resolve_keystroke_bucket(120.0) == "80_plus_kpm"

    engine = StatefulOverviewEngine(device_label="test-mac")
    t0 = 1_700_000_000.0

    prod_metrics = _make_dummy_metrics(primary_process="Code.exe", total_keystrokes=60)
    snap_prod = engine.evaluate_tick(prod_metrics, now_timestamp=t0, switch_delta=0)
    assert snap_prod.classification.activity == "producing"
    assert snap_prod.classification.app_category == "editor_terminal"
    assert snap_prod.typing_mode in ("composing", "transcribing")

    comms_metrics = _make_dummy_metrics(primary_process="Slack.app", total_keystrokes=15)
    snap_comms = engine.evaluate_tick(comms_metrics, now_timestamp=t0 + 10.0, switch_delta=1)
    assert snap_comms.classification.activity == "communicating"
    assert snap_comms.in_interruption is True
    assert snap_comms.interruptions_total == 1
    assert any(ev.get("event") == "interruption" for ev in snap_comms.discrete_events)

    snap_resumed = engine.evaluate_tick(prod_metrics, now_timestamp=t0 + 25.0, switch_delta=1)
    assert snap_resumed.in_interruption is False
    assert snap_resumed.residue_return_count >= 1
    assert snap_resumed.last_residue_gap_seconds > 0.0
    assert any(ev.get("event") == "resumed" for ev in snap_resumed.discrete_events)

    cons_metrics = PooledTelemetryMetrics(
        sample_count=1,
        total_duration_seconds=60.0,
        total_active_seconds=30.0,
        duty_cycle=0.50,
        total_micro_pauses=1,
        total_mouse_clicks=2,
        total_scroll_events=12,
        total_context_switches=1,
        switches_per_minute=1.0,
        merged_dwell_seconds={"Firefox.app": 60.0},
        primary_process="Firefox.app",
        primary_process_ratio=1.0,
        shannon_entropy=0.0,
        total_keystrokes=4,
        correction_keystrokes=0,
        correction_ratio=0.0,
        iki_count=0,
        is_psychomotor_valid=False,
        iki_mean_ms=0.0,
        iki_variance_ms2=0.0,
        iki_std_dev_ms=0.0,
        iki_cv=0.0,
    )
    snap_cons = engine.evaluate_tick(cons_metrics, now_timestamp=t0 + 95.0, switch_delta=1)
    assert snap_cons.classification.activity == "consuming"
    assert snap_cons.typing_mode == "inactive"

    unclass_metrics = _make_dummy_metrics(
        primary_process="Code.exe",
        total_keystrokes=8,
        total_scroll_events=0,
    )
    snap_unclass = engine.evaluate_tick(unclass_metrics, now_timestamp=t0 + 110.0, switch_delta=0)
    assert snap_unclass.classification.activity == "unclassified"
    assert any(ev.get("event") == "unclassified_segment" for ev in snap_unclass.discrete_events)

    snap_nav = engine.evaluate_tick(prod_metrics, now_timestamp=t0 + 120.0, switch_delta=7)
    assert snap_nav.classification.activity == "navigating"
    assert snap_nav.classification.switches_in_5m > 6

    snap_idle = engine.evaluate_tick(
        prod_metrics,
        idle_seconds=350.0,
        now_timestamp=t0 + 130.0,
        switch_delta=0,
    )
    assert snap_idle.classification.activity == "idle"
    assert any(ev.get("event") == "idle_start" for ev in snap_idle.discrete_events)


def test_overview_deep_work_ultradian_and_chronotype() -> None:
    engine = StatefulOverviewEngine(
        session_close_switch_seconds=60.0,
        deep_work_threshold_seconds=1500.0,
    )
    t0 = 1_700_000_000.0
    prod_metrics = _make_dummy_metrics(
        primary_process="Code.exe",
        total_keystrokes=80,
        iki_cv=0.25,
        correction_ratio=0.02,
    )

    engine.evaluate_tick(prod_metrics, now_timestamp=t0, switch_delta=0)

    for minute in range(1, 9):
        snap_m = engine.evaluate_tick(
            prod_metrics,
            now_timestamp=t0 + minute * 65.0,
            switch_delta=0,
            pauses_gt_2s_delta=1 if minute % 2 == 0 else 0,
        )
        assert snap_m.dominant_ultradian_period_minutes > 0.0

    snap_deep = engine.evaluate_tick(prod_metrics, now_timestamp=t0 + 1600.0, switch_delta=0)
    assert snap_deep.deep_work_blocks_total == 1
    assert snap_deep.chronotype_center_of_mass_hour >= 0.0
    assert snap_deep.typing_mode == "transcribing"

    firefox_metrics = _make_dummy_metrics(primary_process="Firefox.app", total_keystrokes=60)
    engine.evaluate_tick(firefox_metrics, now_timestamp=t0 + 1610.0, switch_delta=1)
    snap_closed = engine.evaluate_tick(firefox_metrics, now_timestamp=t0 + 1680.0, switch_delta=0)
    assert snap_closed.current_focus_app == "Firefox.app"
    assert any(ev.get("event") == "focus_end" for ev in snap_closed.discrete_events)
