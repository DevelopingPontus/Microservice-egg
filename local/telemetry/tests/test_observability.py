"""Unit tests for `app/exporters/` and `evaluate_cognitive_sre_health`."""

from app.analysis import (
    CognitiveStrainReport,
    DimensionEvaluation,
    evaluate_cognitive_sre_health,
)
from app.collector import PooledTelemetryMetrics
from app.exporters import (
    CognitiveMetricsRecorder,
    FocusSessionTracer,
    OTelTelemetryManager,
    SREEventLogger,
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

    dummy_metrics = PooledTelemetryMetrics(
        sample_count=1,
        total_duration_seconds=60.0,
        total_active_seconds=45.0,
        duty_cycle=0.75,
        total_micro_pauses=2,
        total_mouse_clicks=10,
        total_scroll_events=2,
        total_context_switches=1,
        switches_per_minute=1.0,
        merged_dwell_seconds={"Code.exe": 45.0},
        primary_process="Code.exe",
        primary_process_ratio=1.0,
        shannon_entropy=0.0,
        total_keystrokes=50,
        correction_keystrokes=2,
        correction_ratio=0.04,
        iki_count=45,
        is_psychomotor_valid=True,
        iki_mean_ms=150.0,
        iki_variance_ms2=2500.0,
        iki_std_dev_ms=50.0,
        iki_cv=0.33,
    )

    report = CognitiveStrainReport(
        overall_strain_score=0.25,
        dominant_state_label="nominal",
        sre_status="nominal",
        sre_alert_reason="Nominal",
        triggered_dimensions=(),
        dimension_scores={"temporal_dynamics": 0.25},
    )

    recorder.record_tick(
        metrics=dummy_metrics,
        session_uptime_seconds=300.0,
        active_work_seconds=120.0,
        evaluations={"temporal_dynamics": _dummy_eval("temporal_dynamics", 0.25)},
        report=report,
        keystroke_delta=50,
        correction_delta=2,
        context_switch_delta=1,
        mouse_click_delta=10,
        scroll_delta=2,
    )

    prom_text = recorder.render_prometheus_metrics()
    assert "egg_user_duty_cycle_ratio 0.75" in prom_text
    assert "egg_user_keystrokes_total 50.0" in prom_text
    assert "egg_user_mouse_clicks_total 10.0" in prom_text
    assert "egg_user_scroll_events_total 2.0" in prom_text
    assert "egg_user_active_work_seconds 120.0" in prom_text
    assert 'egg_user_process_dwell_seconds{process="Code.exe"} 45.0' in prom_text

    import logging

    assert logging.getLogger("egg.sre").isEnabledFor(logging.INFO)

    otel.shutdown()


def test_focus_session_tracer() -> None:
    otel = OTelTelemetryManager(enable_otlp=False)
    tracer = FocusSessionTracer(otel.tracer)

    tracer.start_or_switch_focus("Code.exe")
    tracer.record_excursion("Slack.app", 30.0)
    tracer.start_or_switch_focus("Slack.app")
    tracer.end_current_focus()

    otel.shutdown()


def test_sre_event_logger() -> None:
    logger = SREEventLogger()
    dummy_metrics = PooledTelemetryMetrics(
        sample_count=1,
        total_duration_seconds=60.0,
        total_active_seconds=45.0,
        duty_cycle=0.75,
        total_micro_pauses=2,
        total_mouse_clicks=10,
        total_scroll_events=2,
        total_context_switches=1,
        switches_per_minute=1.0,
        merged_dwell_seconds={"Code.exe": 45.0},
        primary_process="Code.exe",
        primary_process_ratio=1.0,
        shannon_entropy=0.0,
        total_keystrokes=50,
        correction_keystrokes=2,
        correction_ratio=0.04,
        iki_count=45,
        is_psychomotor_valid=True,
        iki_mean_ms=150.0,
        iki_variance_ms2=2500.0,
        iki_std_dev_ms=50.0,
        iki_cv=0.33,
    )
    report = CognitiveStrainReport(
        overall_strain_score=0.85,
        dominant_state_label="critical",
        sre_status="critical",
        sre_alert_reason="Attention fragmented",
        triggered_dimensions=("attentional_fragmentation",),
        dimension_scores={"attentional_fragmentation": 0.85},
    )

    logger.log_state_tick(dummy_metrics, report, 300.0)
    logger.log_session_heartbeat(dummy_metrics, report, 300.0, 180.0)
    logger.log_focus_switch("Code.exe", "Firefox.app")
    logger.log_excursion_absorbed("Code.exe", "Slack.app", 25.0)
    logger.log_sre_alert("critical", report, "Code.exe")
