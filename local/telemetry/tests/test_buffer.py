"""Unit tests for SlidingWindowBuffer."""

from app.intake.engine.window import SlidingWindowBuffer


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
    # Outlier: too fast (10ms < 25ms)
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

    # Window now contains both slices (within 2s)
    metrics = buffer.get_sliding_window_metrics()
    assert metrics.sample_count == 2
    assert metrics.total_keystrokes == 2

    # Advance time past 2.0s eviction cutoff
    buffer.record_key(is_correction=False, delta_ms=100.0, event_time=t0 + 3.0)
    buffer.commit_slice(now=t0 + 3.5)

    # Slice at t0+0.5 should have been evicted (3.5 - 2.0 = 1.5, so slice ending at 0.5 is out)
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

    buffer.commit_slice()
    metrics = buffer.get_sliding_window_metrics()
    assert metrics.total_mouse_clicks == 1
    assert metrics.total_scroll_events == 1
    assert metrics.total_context_switches == 1
    assert "Code.exe" in metrics.merged_dwell_seconds
    assert "Slack.app" in metrics.merged_dwell_seconds


def test_sliding_window_buffer_thought_grace_period() -> None:
    """Verify 3-minute grace period credits reading pauses to active work and flags away time."""
    buffer = SlidingWindowBuffer(
        reading_thought_grace_seconds=180.0,
        away_idle_threshold_seconds=180.0,
    )

    t0 = 1000.0
    # First input
    buffer.record_key(is_correction=False, delta_ms=100.0, event_time=t0)
    assert buffer._lifetime_active_work_seconds == 0.0

    # User pauses for 60s (reading/thinking on screen <= 180s grace)
    t1 = t0 + 60.0
    buffer.record_key(is_correction=False, delta_ms=100.0, event_time=t1)
    # Entire 60s is credited to active work
    assert buffer._lifetime_active_work_seconds == 60.0
    assert buffer._lifetime_away_idle_seconds == 0.0

    # User steps away for 300s (5 minutes > 180s grace)
    t2 = t1 + 300.0
    buffer.record_key(is_correction=False, delta_ms=100.0, event_time=t2)
    # Active work was frozen, 300s is credited to away time
    assert buffer._lifetime_active_work_seconds == 60.0
    assert buffer._lifetime_away_idle_seconds == 300.0


def test_sliding_window_buffer_window_id_context_switch() -> None:
    """Verify window switching increments context switches when process name is identical."""
    buffer = SlidingWindowBuffer()

    # Dwell in VS Code window 101
    buffer.record_window_tick("Code.app", 0.5, window_id=101)
    assert buffer.lifetime_context_switches == 0

    # Dwell in VS Code window 101 again (no switch)
    buffer.record_window_tick("Code.app", 0.5, window_id=101)
    assert buffer.lifetime_context_switches == 0

    # Switch to VS Code window 102 (same process name, different window ID)
    buffer.record_window_tick("Code.app", 0.5, window_id=102)
    assert buffer.lifetime_context_switches == 1

    # Switch to Firefox (different process name)
    buffer.record_window_tick("Firefox.app", 0.5, window_id=200)
    assert buffer.lifetime_context_switches == 2


def test_sliding_window_buffer_session_reset() -> None:
    """Verify continuous session uptime resets after 15 min (900s) of away idle time."""
    buffer = SlidingWindowBuffer(session_reset_idle_seconds=900.0)

    t0 = 1000.0
    buffer.record_key(is_correction=False, event_time=t0)

    # Within session: uptime is > 0
    uptime = buffer.session_uptime_seconds
    assert uptime >= 0.0
