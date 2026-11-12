"""Mathematical verification tests for pooled metrics and Shannon entropy."""

import math

from app.collector import (
    TelemetrySample,
    compute_shannon_entropy,
    merge_dwell_distributions,
    pool_telemetry_samples,
)


def test_shannon_entropy_calculation() -> None:
    assert compute_shannon_entropy({"Code": 100.0}) == 0.0

    h2 = compute_shannon_entropy({"Code": 50.0, "Chrome": 50.0})
    assert math.isclose(h2, math.log(2), rel_tol=1e-3)

    assert compute_shannon_entropy({}) == 0.0


def test_pooled_telemetry_samples_math() -> None:
    s1 = TelemetrySample(
        timestamp_start=0.0,
        timestamp_end=10.0,
        primary_process="Code.exe",
        active_seconds=8.0,
        micro_pause_count=1,
        context_switch_count=0,
        dwell_distribution={"Code.exe": 8.0},
        total_keystrokes=20,
        correction_keystrokes=2,
        iki_count=18,
        iki_sum_ms=1800.0,
        iki_sum_sq_ms=200000.0,
        mouse_click_count=2,
        scroll_count=1,
    )

    s2 = TelemetrySample(
        timestamp_start=10.0,
        timestamp_end=20.0,
        primary_process="Code.exe",
        active_seconds=6.0,
        micro_pause_count=1,
        context_switch_count=1,
        dwell_distribution={"Code.exe": 4.0, "Slack.app": 2.0},
        total_keystrokes=10,
        correction_keystrokes=1,
        iki_count=8,
        iki_sum_ms=800.0,
        iki_sum_sq_ms=90000.0,
        mouse_click_count=1,
        scroll_count=0,
    )

    pooled = pool_telemetry_samples([s1, s2])
    assert pooled.sample_count == 2
    assert pooled.total_duration_seconds == 20.0
    assert pooled.total_active_seconds == 14.0
    assert pooled.duty_cycle == 0.70
    assert pooled.total_keystrokes == 30
    assert pooled.correction_keystrokes == 3
    assert pooled.correction_ratio == 0.10
    assert pooled.iki_count == 26
    assert pooled.is_psychomotor_valid is True

    expected_mean = (1800.0 + 800.0) / 26
    assert math.isclose(pooled.iki_mean_ms, expected_mean, rel_tol=1e-2)

    merged = merge_dwell_distributions([s1, s2])
    assert merged["Code.exe"] == 12.0
    assert merged["Slack.app"] == 2.0


def test_empty_pool_handling() -> None:
    pooled = pool_telemetry_samples([])
    assert pooled.sample_count == 0
    assert pooled.duty_cycle == 0.0
    assert pooled.total_keystrokes == 0
    assert pooled.is_psychomotor_valid is False
