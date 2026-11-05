"""Unit tests for the thread-safe 30-second EpochBuffer accumulator."""

import pytest

from app.intake.engine import EpochBuffer
from app.storage import pool_epoch_metrics


def test_epoch_buffer_key_iki_and_outlier_filtering() -> None:
    """Verify keystrokes, corrections, IKI sums, and >5000ms outlier exclusion."""
    buf = EpochBuffer()

    # Key 1 at t=10.0s (first key has no prior key interval)
    buf.record_key(is_correction=False, event_time=10.0)
    # Key 2 at t=10.2s -> delta = 200ms (active gap 0.2s)
    buf.record_key(is_correction=False, event_time=10.2)
    # Key 3 at t=10.5s -> delta = 300ms (correction key, active gap 0.3s)
    buf.record_key(is_correction=True, event_time=10.5)
    # Key 4 at t=12.5s -> delta = 2000ms (micro-pause 2.0s, valid IKI <= 5000ms)
    buf.record_key(is_correction=False, event_time=12.5)
    # Key 5 at t=19.0s -> delta = 6500ms (> 5000ms IKI outlier, dropped from IKI)
    buf.record_key(is_correction=False, event_time=19.0)

    dto = buf.harvest_and_reset(0.0, 30.0)

    assert dto.total_keystrokes == 5
    assert dto.correction_keystrokes == 1
    assert dto.iki_count == 3
    assert dto.iki_sum_ms == pytest.approx(200.0 + 300.0 + 2000.0)
    assert dto.iki_sum_sq_ms == pytest.approx(200.0**2 + 300.0**2 + 2000.0**2)
    assert dto.active_seconds == pytest.approx(0.5)
    assert dto.micro_pause_count == 1
    assert dto.primary_process == "idle"


def test_epoch_buffer_mouse_click_scroll_and_move_throttling() -> None:
    """Verify mouse clicks, scroll events, 250ms move throttling, and micro-pauses."""
    buf = EpochBuffer()

    buf.record_mouse_click(event_time=1.0)
    # Move 0.10s later -> throttled (< 0.25s)
    buf.record_mouse_move(event_time=1.0)
    buf.record_mouse_move(event_time=1.10)
    # Move at 1.30s -> accepted (>= 0.25s since 1.0s), adds 0.30s active
    buf.record_mouse_move(event_time=1.30)
    # Scroll at 2.50s -> gap = 1.20s (<= 1.5s active AND within [1.0s, 5.0s] micro-pause)
    buf.record_mouse_scroll(event_time=2.50)
    buf.record_mouse_scroll(event_time=3.00)

    dto = buf.harvest_and_reset(0.0, 30.0)
    assert dto.mouse_click_count == 1
    assert dto.scroll_count == 2
    assert dto.micro_pause_count == 1
    assert dto.active_seconds == pytest.approx(0.30 + 1.20 + 0.50)


def test_epoch_buffer_window_ticks_and_reset_continuity() -> None:
    """Verify per-process dwell accumulation, context switches, and clean reset."""
    buf = EpochBuffer()

    # Non-positive duration is ignored
    buf.record_window_tick("Code.exe", 0.0)
    buf.record_window_tick("Code.exe", 10.0)
    buf.record_window_tick("Code.exe", 10.0)
    buf.record_window_tick("Firefox.app", 5.0)
    buf.record_window_tick("   ", 5.0)  # Sanitizes empty string to "unknown"

    dto_1 = buf.harvest_and_reset(100.0, 130.0)
    assert dto_1.primary_process == "Code.exe"
    assert dto_1.context_switch_count == 2
    assert dto_1.parsed_dwell_distribution() == {
        "Code.exe": 20.0,
        "Firefox.app": 5.0,
        "unknown": 5.0,
    }

    # Next epoch with no new window ticks retains last_process ("unknown") as fallback
    dto_2 = buf.harvest_and_reset(130.0, 160.0)
    assert dto_2.total_keystrokes == 0
    assert dto_2.mouse_click_count == 0
    assert dto_2.scroll_count == 0
    assert dto_2.context_switch_count == 0
    assert dto_2.primary_process == "unknown"

    pooled = pool_epoch_metrics([dto_1, dto_2])
    assert pooled.epoch_count == 2
    assert pooled.primary_process == "Code.exe"


def test_epoch_buffer_default_monotonic_clocks() -> None:
    """Verify record methods work when event_time is omitted (using time.monotonic)."""
    buf = EpochBuffer()
    buf.record_key(is_correction=False, delta_ms=150.0)
    buf.record_mouse_click()
    buf.record_mouse_scroll()
    buf.record_mouse_move()

    dto = buf.harvest_and_reset(0.0, 30.0)
    assert dto.total_keystrokes == 1
    assert dto.iki_count == 1
    assert dto.mouse_click_count == 1
    assert dto.scroll_count == 1
