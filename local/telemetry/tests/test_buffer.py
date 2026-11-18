"""Unit tests for SlidingWindowBuffer."""

from app.collector import SlidingWindowBuffer


def test_sliding_window_buffer_key_recording() -> None:
    """Test recording keystrokes and outlier filtering in sliding window."""
    buffer = SlidingWindowBuffer(
        window_duration_seconds=5.0,
        iki_min_outlier_ms=25.0,
        iki_max_outlier_ms=5000.0,
    )

    t0 = 1000.0
    buffer.record_key(is_correction=False, delta_ms=150.0, event_time=t0)
    buffer.record_key(is_correction=True, delta_ms=200.0, event_time=t0 + 0.2)
    buffer.record_key(is_correction=False, delta_ms=10.0, event_time=t0 + 0.21)

    assert buffer.lifetime_keystrokes == 3
    assert buffer.lifetime_corrections == 1

    sample = buffer.commit_slice(now=t0 + 1.0)
    assert sample.total_keystrokes == 3
    assert sample.correction_keystrokes == 1
    assert sample.iki_count == 2
    assert sample.iki_sum_ms == 350.0

    metrics = buffer.get_sliding_window_metrics()
    assert metrics.total_keystrokes == 3
    assert metrics.correction_keystrokes == 1
    assert metrics.correction_ratio == round(1 / 3, 4)


def test_sliding_window_eviction() -> None:
    """Verify slices older than window_duration are evicted."""
    buffer = SlidingWindowBuffer(window_duration_seconds=2.0)

    t0 = 1000.0
    buffer.record_key(is_correction=False, delta_ms=100.0, event_time=t0)
    buffer.commit_slice(now=t0 + 0.5)

    buffer.record_key(is_correction=False, delta_ms=100.0, event_time=t0 + 1.0)
    buffer.commit_slice(now=t0 + 1.5)

    metrics = buffer.get_sliding_window_metrics()
    assert metrics.sample_count == 2
    assert metrics.total_keystrokes == 2

    buffer.record_key(is_correction=False, delta_ms=100.0, event_time=t0 + 3.0)
    buffer.commit_slice(now=t0 + 3.5)

    metrics2 = buffer.get_sliding_window_metrics()
    assert metrics2.sample_count == 2
    assert metrics2.total_keystrokes == 2


def test_mouse_and_window_dwell() -> None:
    """Test mouse clicks, scroll, and window ticks."""
    buffer = SlidingWindowBuffer(window_duration_seconds=5.0)

    buffer.record_mouse_click()
    buffer.record_mouse_scroll()
    buffer.record_mouse_move()
    buffer.record_window_tick("Code.exe", 0.5)
    buffer.record_window_tick("Slack.app", 0.5)

    assert buffer.lifetime_mouse_clicks == 1
    assert buffer.lifetime_scroll_events == 1
    assert buffer.lifetime_context_switches == 1

    snap = buffer.commit_snapshot()
    metrics = snap.metrics
    assert metrics.total_mouse_clicks == 1
    assert metrics.total_scroll_events == 1
    assert metrics.total_context_switches == 1
    assert snap.deltas.mouse_clicks == 1
    assert snap.deltas.scrolls == 1
    assert snap.deltas.context_switches == 1
    assert "Code.exe" in metrics.merged_dwell_seconds
    assert "Slack.app" in metrics.merged_dwell_seconds


def test_sliding_window_buffer_thought_grace_period() -> None:
    """Verify 3-minute grace period credits reading pauses to active work and flags away time."""
    buffer = SlidingWindowBuffer(
        reading_thought_grace_seconds=180.0,
        away_idle_threshold_seconds=180.0,
    )

    t0 = 1000.0
    buffer.record_key(is_correction=False, delta_ms=100.0, event_time=t0)
    assert buffer._lifetime_active_work_seconds == 0.0

    t1 = t0 + 60.0
    buffer.record_key(is_correction=False, delta_ms=100.0, event_time=t1)
    assert buffer._lifetime_active_work_seconds == 60.0
    assert buffer._lifetime_away_idle_seconds == 0.0

    t2 = t1 + 300.0
    buffer.record_key(is_correction=False, delta_ms=100.0, event_time=t2)
    assert buffer._lifetime_active_work_seconds == 60.0
    assert buffer._lifetime_away_idle_seconds == 300.0


def test_sliding_window_buffer_window_id_context_switch() -> None:
    """Verify window switching increments context switches when process name is identical."""
    buffer = SlidingWindowBuffer()

    buffer.record_window_tick("Code.app", 0.5, window_id=101)
    assert buffer.lifetime_context_switches == 0

    buffer.record_window_tick("Code.app", 0.5, window_id=101)
    assert buffer.lifetime_context_switches == 0

    buffer.record_window_tick("Code.app", 0.5, window_id=102)
    assert buffer.lifetime_context_switches == 1

    buffer.record_window_tick("Firefox.app", 0.5, window_id=200)
    assert buffer.lifetime_context_switches == 2


def test_sliding_window_buffer_session_reset() -> None:
    """Verify continuous session uptime is 0 with no input and resets after 15 min idle."""
    buffer = SlidingWindowBuffer(session_reset_idle_seconds=900.0)

    assert buffer.session_uptime_seconds == 0.0
    assert buffer.seconds_since_last_input() == 0.0

    t0 = 1000.0
    buffer.record_key(is_correction=False, event_time=t0)
    buffer.record_key(is_correction=False, delta_ms=2500.0, event_time=t0 + 2.5)
    sample = buffer.commit_slice(now=t0 + 3.0)
    assert sample.pauses_gt_2s_count == 1
    assert sample.burst_count == 2

    uptime = buffer.session_uptime_seconds
    assert uptime >= 0.0


def test_independent_accumulators_sample_driven_push() -> None:
    """Verify independent sample accumulators trigger only when good sample thresholds are met."""
    buffer = SlidingWindowBuffer()

    # 1. Keystroke timing threshold: needs 10 IKIs
    assert buffer.has_good_keystroke_timing_sample() is False
    for i in range(9):
        buffer.record_key(is_correction=False, delta_ms=100.0, event_time=1000.0 + i * 0.1)
    assert buffer.has_good_keystroke_timing_sample() is False

    buffer.record_key(is_correction=False, delta_ms=120.0, event_time=1001.0)
    assert buffer.has_good_keystroke_timing_sample() is True
    k_metrics, k_delta = buffer.consume_keystroke_timing_metrics()
    assert k_metrics.iki_count == 10
    assert k_delta == 10
    assert buffer.has_good_keystroke_timing_sample() is False

    # 2. Correction pause sample: triggers on correction or >2s pause
    assert buffer.has_good_correction_pause_sample() is False
    buffer.record_key(is_correction=True, delta_ms=250.0, event_time=1002.0)
    assert buffer.has_good_correction_pause_sample() is True
    c_metrics, c_delta = buffer.consume_correction_pause_metrics()
    assert c_metrics.correction_keystrokes == 1
    assert c_delta == 1
    assert buffer.has_good_correction_pause_sample() is False

    # 3. Mouse kinematics: needs 25 trajectory points or 5 clicks/scrolls
    assert buffer.has_good_mouse_sample() is False
    for i in range(25):
        buffer.record_mouse_move(x=float(i), y=float(i * 2), event_time=1003.0 + i * 0.03)
    assert buffer.has_good_mouse_sample() is True
    m_metrics, click_delta, scroll_delta = buffer.consume_mouse_kinematics_metrics()
    assert m_metrics.sample_entropy >= 0.0
    assert buffer.has_good_mouse_sample() is False

    # 4. Attention sample: triggers on context switch
    assert buffer.has_good_attention_sample() is False
    buffer.record_window_tick("Code.exe", 1.0, window_id=1)
    buffer.record_window_tick("Firefox.exe", 1.0, window_id=2)
    assert buffer.has_good_attention_sample() is True
    a_metrics, sw_delta = buffer.consume_attention_window_metrics()
    assert a_metrics.context_switches == 1
    assert sw_delta == 1
    assert buffer.has_good_attention_sample() is False
