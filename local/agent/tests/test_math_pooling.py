"""Unit tests proving lossless mathematical pooling across 30-second telemetry epochs."""

import json
import math

import pytest

from app.storage import (
    EpochMetricsDTO,
    compute_shannon_entropy,
    merge_dwell_distributions,
    pool_epoch_metrics,
)


def _make_epoch(
    *,
    start: float = 0.0,
    end: float = 30.0,
    primary_process: str = "Code.exe",
    active_seconds: float = 20.0,
    micro_pause_count: int = 2,
    mouse_click_count: int = 0,
    scroll_count: int = 0,
    context_switch_count: int = 1,
    dwell: dict[str, float] | None = None,
    total_keystrokes: int = 50,
    correction_keystrokes: int = 4,
    iki_samples_ms: list[float] | None = None,
) -> EpochMetricsDTO:
    """Build an EpochMetricsDTO from raw IKI samples for mathematical verification."""
    samples = iki_samples_ms if iki_samples_ms is not None else [120.0, 150.0, 180.0, 210.0]
    dwell_map = dwell if dwell is not None else {primary_process: end - start}
    return EpochMetricsDTO(
        timestamp_start=start,
        timestamp_end=end,
        primary_process=primary_process,
        active_seconds=active_seconds,
        micro_pause_count=micro_pause_count,
        mouse_click_count=mouse_click_count,
        scroll_count=scroll_count,
        context_switch_count=context_switch_count,
        dwell_distribution_json=json.dumps(dwell_map),
        total_keystrokes=total_keystrokes,
        correction_keystrokes=correction_keystrokes,
        iki_count=len(samples),
        iki_sum_ms=float(sum(samples)),
        iki_sum_sq_ms=float(sum(x * x for x in samples)),
    )


def test_pooled_iki_variance_and_cv_matches_raw_stream_within_1e9() -> None:
    """Prove pooled mean, population variance, std dev, and CV match unchunked raw stream."""
    epoch_1_ikis = [95.5, 110.2, 145.8, 210.0, 88.4, 312.7]
    epoch_2_ikis = [130.0, 125.5]
    epoch_3_ikis = [410.2, 195.0, 102.3, 115.9, 160.4, 175.1, 205.8, 99.0]
    epoch_4_ikis: list[float] = []

    all_raw_ikis = epoch_1_ikis + epoch_2_ikis + epoch_3_ikis + epoch_4_ikis
    raw_n = len(all_raw_ikis)
    raw_mean = sum(all_raw_ikis) / raw_n
    raw_variance = sum((x - raw_mean) ** 2 for x in all_raw_ikis) / raw_n
    raw_std_dev = math.sqrt(raw_variance)
    raw_cv = raw_std_dev / raw_mean

    epochs = [
        _make_epoch(start=0.0, end=30.0, iki_samples_ms=epoch_1_ikis),
        _make_epoch(start=30.0, end=60.0, iki_samples_ms=epoch_2_ikis),
        _make_epoch(start=60.0, end=90.0, iki_samples_ms=epoch_3_ikis),
        _make_epoch(start=90.0, end=120.0, iki_samples_ms=epoch_4_ikis),
    ]

    pooled = pool_epoch_metrics(epochs)

    assert pooled.iki_count == raw_n
    assert pooled.is_psychomotor_valid is True
    assert pooled.iki_mean_ms == pytest.approx(raw_mean, rel=1e-9, abs=1e-9)
    assert pooled.iki_variance_ms2 == pytest.approx(raw_variance, rel=1e-9, abs=1e-9)
    assert pooled.iki_std_dev_ms == pytest.approx(raw_std_dev, rel=1e-9, abs=1e-9)
    assert pooled.iki_cv == pytest.approx(raw_cv, rel=1e-9, abs=1e-9)


def test_shannon_entropy_and_primary_process_ratio() -> None:
    """Verify Shannon entropy H and primary_process_ratio across dwell distributions."""
    assert compute_shannon_entropy({}) == 0.0
    assert compute_shannon_entropy({"Code.exe": 0.0}) == 0.0
    assert compute_shannon_entropy({"Code.exe": 60.0}) == 0.0

    # Uniform 2-process split -> H = ln(2)
    two_proc = compute_shannon_entropy({"Code.exe": 30.0, "Firefox": 30.0})
    assert two_proc == pytest.approx(math.log(2.0), rel=1e-9, abs=1e-9)

    # Uniform 4-process split -> H = ln(4)
    four_proc = compute_shannon_entropy(
        {"Code.exe": 15.0, "Firefox": 15.0, "Slack": 15.0, "Terminal": 15.0}
    )
    assert four_proc == pytest.approx(math.log(4.0), rel=1e-9, abs=1e-9)

    # Pooled across 2 epochs with dominant process (45s Code.exe, 15s Slack = 75% / 25%)
    e1 = _make_epoch(start=0.0, end=30.0, dwell={"Code.exe": 25.0, "Slack": 5.0})
    e2 = _make_epoch(start=30.0, end=60.0, dwell={"Code.exe": 20.0, "Slack": 10.0, "Idle": 0.0})
    merged = merge_dwell_distributions([e1, e2])
    assert merged == {"Code.exe": 45.0, "Slack": 15.0}

    pooled = pool_epoch_metrics([e1, e2])
    expected_entropy = -(0.75 * math.log(0.75) + 0.25 * math.log(0.25))
    assert pooled.primary_process == "Code.exe"
    assert pooled.primary_process_ratio == pytest.approx(0.75, rel=1e-9, abs=1e-9)
    assert pooled.shannon_entropy == pytest.approx(expected_entropy, rel=1e-9, abs=1e-9)


def test_reading_vs_stalled_modality_aggregation() -> None:
    """Verify scroll_count and mouse_click_count pool accurately for reading vs stalled states."""
    reading_epoch_1 = _make_epoch(
        start=0.0,
        end=30.0,
        primary_process="Preview.app",
        active_seconds=8.0,
        mouse_click_count=1,
        scroll_count=14,
        total_keystrokes=0,
        correction_keystrokes=0,
        iki_samples_ms=[],
    )
    reading_epoch_2 = _make_epoch(
        start=30.0,
        end=60.0,
        primary_process="Preview.app",
        active_seconds=7.0,
        mouse_click_count=0,
        scroll_count=11,
        total_keystrokes=0,
        correction_keystrokes=0,
        iki_samples_ms=[],
    )

    pooled = pool_epoch_metrics([reading_epoch_1, reading_epoch_2])
    assert pooled.total_duration_seconds == pytest.approx(60.0)
    assert pooled.total_active_seconds == pytest.approx(15.0)
    assert pooled.duty_cycle == pytest.approx(0.25)
    assert pooled.total_mouse_clicks == 1
    assert pooled.total_scroll_events == 25
    assert pooled.total_keystrokes == 0
    assert pooled.is_psychomotor_valid is False


def test_pool_epoch_metrics_edge_cases() -> None:
    """Verify empty epochs, zero duration, constant IKI, and invalid dwell JSON handling."""
    empty_pooled = pool_epoch_metrics([])
    assert empty_pooled.epoch_count == 0
    assert empty_pooled.primary_process == "idle"
    assert empty_pooled.duty_cycle == 0.0
    assert empty_pooled.is_psychomotor_valid is False

    # Constant IKI (zero variance) and empty dwell distribution
    const_epoch = _make_epoch(
        start=100.0,
        end=100.0,
        primary_process="Terminal.app",
        active_seconds=0.0,
        dwell={},
        total_keystrokes=5,
        correction_keystrokes=1,
        iki_samples_ms=[200.0, 200.0, 200.0, 200.0],
    )
    pooled_const = pool_epoch_metrics([const_epoch])
    assert pooled_const.total_duration_seconds == 0.0
    assert pooled_const.duty_cycle == 0.0
    assert pooled_const.switches_per_minute == 0.0
    assert pooled_const.primary_process == "Terminal.app"
    assert pooled_const.primary_process_ratio == 0.0
    assert pooled_const.correction_ratio == pytest.approx(0.2)
    assert pooled_const.iki_mean_ms == pytest.approx(200.0)
    assert pooled_const.iki_variance_ms2 == 0.0
    assert pooled_const.iki_cv == 0.0
    assert pooled_const.is_psychomotor_valid is False

    # Non-dict JSON in dwell_distribution_json raises ValueError
    bad_epoch = EpochMetricsDTO(
        timestamp_start=0.0,
        timestamp_end=30.0,
        primary_process="Code.exe",
        active_seconds=10.0,
        micro_pause_count=1,
        context_switch_count=0,
        dwell_distribution_json="[1, 2, 3]",
        total_keystrokes=0,
        correction_keystrokes=0,
        iki_count=0,
        iki_sum_ms=0.0,
        iki_sum_sq_ms=0.0,
    )
    with pytest.raises(ValueError, match="dwell_distribution_json must encode a JSON object"):
        bad_epoch.parsed_dwell_distribution()
