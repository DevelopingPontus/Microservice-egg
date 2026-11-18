"""Unit tests for `app/exporters/` and `evaluate_cognitive_sre_health`."""

from app.analysis import (
    DimensionEvaluation,
    evaluate_cognitive_sre_health,
)
from app.collector import (
    PooledTelemetryMetrics,
    RawAttentionWindowMetrics,
    RawCorrectionPauseMetrics,
    RawKeystrokeTimingMetrics,
    RawMouseKinematicsMetrics,
    RawTemporalSessionMetrics,
)
from app.exporters import (
    CognitiveMetricsRecorder,
    OTelTelemetryManager,
    TelemetryExporter,
)


def _dummy_eval(name: str, score: float, label: str = "nominal") -> DimensionEvaluation:
    return DimensionEvaluation(
        dimension_name=name,
        strain_score=score,
        state_label=label,
        metrics={"score": score},
        blameless_summary=f"{name} evaluated at {score}",
    )


def test_evaluate_cognitive_sre_health() -> None:
    evals_nominal = {
        "temporal_dynamics": _dummy_eval("temporal_dynamics", 0.20, "moderate_engagement"),
        "attentional_fragmentation": _dummy_eval(
            "attentional_fragmentation", 0.15, "locked_single_app_focus"
        ),
        "psychomotor_mechanics": _dummy_eval(
            "psychomotor_mechanics", 0.25, "steady_psychomotor_rhythm"
        ),
        "session_uptime": _dummy_eval("session_uptime", 0.20, "optimal_focus_window"),
    }
    report_nom = evaluate_cognitive_sre_health(evals_nominal)
    assert report_nom.sre_status in ("nominal", "flow_optimal")
    assert report_nom.overall_strain_score < 0.60

    evals_crit = {
        "temporal_dynamics": _dummy_eval("temporal_dynamics", 0.30),
        "attentional_fragmentation": _dummy_eval(
            "attentional_fragmentation", 0.90, "context_switch_thrashing"
        ),
        "psychomotor_mechanics": _dummy_eval("psychomotor_mechanics", 0.25),
        "session_uptime": _dummy_eval("session_uptime", 0.30),
    }
    report_crit = evaluate_cognitive_sre_health(evals_crit)
    assert report_crit.sre_status == "critical"
    assert "attentional_fragmentation" in report_crit.triggered_dimensions

    report_empty = evaluate_cognitive_sre_health({})
    assert report_empty.sre_status == "nominal"


def test_otel_manager_and_metrics_recorder() -> None:
    otel = OTelTelemetryManager(enable_otlp=False)
    recorder = CognitiveMetricsRecorder(otel.meter)

    recorder.record_keystroke_timing(
        RawKeystrokeTimingMetrics(
            iki_values_ms=(120.0, 180.0),
            hold_times_ms=(85.0, 95.0),
            flight_times_ms=(35.0, 85.0),
            iki_count=45,
            iki_mean_ms=150.0,
            iki_std_dev_ms=50.0,
            iki_mad_ms=30.0,
            hold_time_median_ms=90.0,
            flight_time_median_ms=60.0,
            total_keystrokes=50,
        ),
        keystroke_delta=50,
    )
    recorder.record_correction_pauses(
        RawCorrectionPauseMetrics(
            pre_correction_pauses_ms=(210.0,),
            post_correction_pauses_ms=(340.0,),
            pre_correction_pause_median_ms=210.0,
            post_correction_pause_median_ms=340.0,
            correction_keystrokes=2,
            micro_pauses_count=2,
            pauses_gt_2s_count=1,
            burst_count=3,
        ),
        correction_delta=2,
    )
    recorder.record_mouse_kinematics(
        RawMouseKinematicsMetrics(
            sample_entropy=0.42,
            submovements=4,
            curvature_auc=1.18,
            x_flips=2,
            mouse_clicks=10,
            scroll_events=2,
        ),
        mouse_click_delta=10,
        scroll_delta=2,
    )
    recorder.record_attention_window(
        RawAttentionWindowMetrics(
            shannon_entropy_bits=0.0,
            merged_dwell_seconds={"Code.exe": 45.0},
            primary_process="Code.exe",
            primary_process_dwell_seconds=45.0,
            distinct_processes_count=1,
            context_switches=1,
        ),
        context_switch_delta=1,
    )
    recorder.record_temporal_session(
        RawTemporalSessionMetrics(
            window_active_seconds=45.0,
            window_duration_seconds=60.0,
            session_uptime_seconds=300.0,
            active_work_seconds=120.0,
            away_idle_seconds=0.0,
            idle_gap_seconds=1.0,
        )
    )

    prom_text = recorder.render_prometheus_metrics()
    assert "egg_user_window_active_seconds 45.0" in prom_text
    assert "egg_user_keystrokes_total 50.0" in prom_text
    assert "egg_user_mouse_clicks_total 10.0" in prom_text
    assert "egg_user_scroll_events_total 2.0" in prom_text
    assert "egg_user_active_work_seconds 120.0" in prom_text
    assert "egg_user_iki_ms_count 2.0" in prom_text
    assert "egg_user_hold_time_hist_ms_count 2.0" in prom_text
    assert "egg_user_primary_process_dwell_seconds 45.0" in prom_text
    assert 'egg_user_process_dwell_seconds{process="Code.exe"} 45.0' in prom_text

    # Removed composite/normalized/overview metrics must not be emitted
    for removed in (
        "egg_user_overall_strain_score",
        "egg_user_dimension_strain_score",
        "egg_user_qcd_fatigue_cusum",
        "egg_user_qcd_baseline_distance",
        "egg_user_duty_cycle_ratio",
        "egg_user_primary_process_ratio",
        "egg_user_correction_ratio",
        "egg_user_iki_jitter_cv",
        "egg_overview_",
    ):
        assert removed not in prom_text

    otel.shutdown()


def test_telemetry_exporter_publish() -> None:
    otel = OTelTelemetryManager(enable_otlp=False)
    recorder = CognitiveMetricsRecorder(otel.meter)
    from app.analysis import CognitiveAnalyzer
    from app.collector import ActivitySnapshot, RawMetricsBundle, TickDeltas
    from app.config import DaemonConfig

    exporter = TelemetryExporter(
        DaemonConfig(simulate=True, enable_otlp=False),
        otel_manager=otel,
        metrics_recorder=recorder,
    )
    raw_bundle = RawMetricsBundle(
        keystroke_timing=RawKeystrokeTimingMetrics(iki_mean_ms=120.0),
        correction_pauses=RawCorrectionPauseMetrics(),
        mouse_kinematics=RawMouseKinematicsMetrics(),
        attention_window=RawAttentionWindowMetrics(),
        temporal_session=RawTemporalSessionMetrics(),
    )
    dummy_metrics = PooledTelemetryMetrics(
        sample_count=1,
        total_duration_seconds=60.0,
        total_active_seconds=45.0,
        duty_cycle=0.75,
        total_micro_pauses=0,
        total_mouse_clicks=0,
        total_scroll_events=0,
        total_context_switches=0,
        switches_per_minute=0.0,
        merged_dwell_seconds={"Code.exe": 45.0},
        primary_process="Code.exe",
        primary_process_ratio=1.0,
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
    snapshot = ActivitySnapshot(
        metrics=dummy_metrics,
        deltas=TickDeltas(),
        session_uptime_seconds=100.0,
        active_work_seconds=100.0,
        away_idle_seconds=0.0,
        idle_gap_seconds=0.0,
        now_timestamp=1000.0,
        raw=raw_bundle,
    )
    analyzer = CognitiveAnalyzer()
    state = analyzer.evaluate(snapshot)
    exporter.publish(snapshot, state)
    metrics_text = exporter.render_prometheus_metrics()
    assert "egg_user_iki_mean_ms 120.0" in metrics_text
    exporter.shutdown()
