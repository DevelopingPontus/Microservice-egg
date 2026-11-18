"""Unit tests for vertical feature dimension packages (`app/features/*`)."""

from prometheus_client import CollectorRegistry

from app.core import OTelTelemetryManager
from app.features.attention_dwell import (
    AttentionDwellAccumulator,
    AttentionDwellRecorder,
    compute_shannon_entropy,
)
from app.features.correction_pauses import (
    CorrectionPauseAccumulator,
    CorrectionPauseRecorder,
)
from app.features.keystroke_timing import (
    KeystrokeTimingAccumulator,
    KeystrokeTimingRecorder,
    compute_median_abs_deviation,
)
from app.features.mouse_kinematics import (
    MouseKinematicsAccumulator,
    MouseKinematicsRecorder,
    compute_mouse_kinematics,
    compute_sample_entropy,
)
from app.features.session_duration import (
    RawTemporalSessionMetrics,
    SessionDurationAccumulator,
    SessionDurationRecorder,
)


def test_keystroke_timing_feature() -> None:
    accum = KeystrokeTimingAccumulator(min_valid_samples=3)
    assert accum.has_good_sample() is False

    accum.record_key(key_slot=1, delta_ms=100.0, event_time=1.0)
    accum.record_key_release(key_slot=1, hold_time_ms=80.0, event_time=1.08)

    accum.record_key(key_slot=2, delta_ms=120.0, event_time=1.2)
    accum.record_key_release(key_slot=2, hold_time_ms=75.0, event_time=1.275)

    accum.record_key(key_slot=3, delta_ms=140.0, event_time=1.4)
    accum.record_key_release(key_slot=3, hold_time_ms=90.0, event_time=1.49)

    assert accum.has_good_sample() is True
    metrics, delta = accum.consume()
    assert metrics.iki_count == 3
    assert delta == 3
    assert metrics.hold_time_median_ms == 80.0
    assert compute_median_abs_deviation(metrics.iki_values_ms) >= 0.0

    otel = OTelTelemetryManager(enable_otlp=False)
    reg = CollectorRegistry()
    recorder = KeystrokeTimingRecorder(otel.meter, reg)
    recorder.record(metrics, keystroke_delta=delta)
    otel.shutdown()


def test_correction_pauses_feature() -> None:
    accum = CorrectionPauseAccumulator()
    assert accum.has_good_sample() is False

    accum.record_key(is_correction=False, delta_ms=100.0, event_time=1.0)
    accum.record_key(is_correction=True, delta_ms=250.0, event_time=1.25)
    accum.record_key(is_correction=False, delta_ms=300.0, event_time=1.55)

    assert accum.has_good_sample() is True
    metrics, delta = accum.consume()
    assert metrics.correction_keystrokes == 1
    assert delta == 1
    assert len(metrics.pre_correction_pauses_ms) == 1
    assert len(metrics.post_correction_pauses_ms) == 1

    otel = OTelTelemetryManager(enable_otlp=False)
    reg = CollectorRegistry()
    recorder = CorrectionPauseRecorder(otel.meter, reg)
    recorder.record(metrics, correction_delta=delta)
    otel.shutdown()


def test_mouse_kinematics_feature() -> None:
    accum = MouseKinematicsAccumulator()
    assert accum.has_good_sample() is False

    for i in range(30):
        accum.record_mouse_move(x=float(i * 2), y=float(i * 3), event_time=10.0 + i * 0.03)

    accum.record_mouse_click()
    accum.record_mouse_scroll()
    assert accum.has_good_sample() is True

    metrics, c_delta, s_delta = accum.consume()
    assert c_delta == 1
    assert s_delta == 1
    assert metrics.curvature_auc >= 0.0

    # Test math directly
    pts = [(float(i), float(i * 2), 10.0 + i * 0.02) for i in range(10)]
    samp_en, submov, auc, xflips = compute_mouse_kinematics(pts)
    assert compute_sample_entropy([1.0, 2.0, 1.5, 2.2, 1.8]) >= 0.0

    otel = OTelTelemetryManager(enable_otlp=False)
    reg = CollectorRegistry()
    recorder = MouseKinematicsRecorder(otel.meter, reg)
    recorder.record(metrics, mouse_click_delta=c_delta, scroll_delta=s_delta)
    otel.shutdown()


def test_attention_dwell_feature() -> None:
    accum = AttentionDwellAccumulator()
    assert accum.has_good_sample() is False

    accum.record_window_tick("Code.exe", 5.0, window_id=1)
    accum.record_window_tick("Firefox.exe", 5.0, window_id=2)
    assert accum.has_good_sample() is True

    metrics, delta = accum.consume()
    assert metrics.context_switches == 1
    assert delta == 1
    assert compute_shannon_entropy({"Code.exe": 5.0, "Firefox.exe": 5.0}) > 0.0

    otel = OTelTelemetryManager(enable_otlp=False)
    reg = CollectorRegistry()
    recorder = AttentionDwellRecorder(otel.meter, reg)
    recorder.record(metrics, context_switch_delta=delta)
    otel.shutdown()


def test_session_duration_feature() -> None:
    accum = SessionDurationAccumulator(
        idle_threshold_seconds=1.5,
        reading_thought_grace_seconds=10.0,
        session_reset_idle_seconds=60.0,
    )
    accum.register_input_event(event_time=100.0)
    accum.register_input_event(event_time=101.0)

    assert accum.session_uptime_seconds >= 0.0
    assert accum.active_work_seconds >= 0.0
    assert accum.away_idle_seconds >= 0.0

    metrics = accum.consume()
    assert isinstance(metrics, RawTemporalSessionMetrics)

    otel = OTelTelemetryManager(enable_otlp=False)
    reg = CollectorRegistry()
    recorder = SessionDurationRecorder(otel.meter, reg)
    recorder.record(metrics)
    otel.shutdown()
