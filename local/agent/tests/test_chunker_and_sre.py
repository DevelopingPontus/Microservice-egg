"""Tests for the 60s/90s Hysteresis Activity Block Chunker, SQLite persistence, and SRE layer."""

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.common import (
    ActivityBlockDTO,
    BlockEvaluatorProtocol,
    DaemonConfig,
    DimensionEvaluation,
    EpochSnapshot,
    PooledTelemetryMetrics,
    SealedActivityBlock,
)
from app.intake.engine import (
    ActivityBlockChunker,
    SREObservabilityRecorder,
    evaluate_sre_health,
    is_zero_input_epoch,
)
from app.output.dimensions import DimensionContext, create_default_registry
from app.service import TelemetryService
from app.storage import EpochRepository


def _make_snapshot(
    index: int,
    *,
    primary_process: str = "Code.exe",
    active_seconds: float = 24.0,
    micro_pause_count: int = 1,
    context_switch_count: int = 0,
    dwell: dict[str, float] | None = None,
    total_keystrokes: int = 40,
    correction_keystrokes: int = 1,
    iki_count: int = 35,
    iki_sum_ms: float = 5250.0,
    iki_sum_sq_ms: float = 820000.0,
    mouse_click_count: int = 2,
    scroll_count: int = 4,
    base_ts: float = 1_762_074_000.0,
) -> EpochSnapshot:
    """Create a deterministic 30-second EpochSnapshot for chunker and SRE tests."""
    start = base_ts + (index * 30.0)
    end = start + 30.0
    resolved_dwell = dwell if dwell is not None else {primary_process: 30.0}
    return EpochSnapshot(
        timestamp_start=start,
        timestamp_end=end,
        primary_process=primary_process,
        active_seconds=active_seconds,
        micro_pause_count=micro_pause_count,
        context_switch_count=context_switch_count,
        dwell_distribution_json=json.dumps(resolved_dwell),
        total_keystrokes=total_keystrokes,
        correction_keystrokes=correction_keystrokes,
        iki_count=iki_count,
        iki_sum_ms=iki_sum_ms,
        iki_sum_sq_ms=iki_sum_sq_ms,
        mouse_click_count=mouse_click_count,
        scroll_count=scroll_count,
        id=index + 1,
    )


def _build_evaluator(storage: EpochRepository) -> BlockEvaluatorProtocol:
    """Create a BlockEvaluatorProtocol function backed by EpochRepository and Dimensions."""
    registry = create_default_registry()

    def _eval(
        epochs: Sequence[EpochSnapshot],
        *,
        prior_epochs_today: Sequence[EpochSnapshot] = (),
    ) -> tuple[PooledTelemetryMetrics, dict[str, DimensionEvaluation]]:
        pooled = storage.pool_epochs(epochs)
        ctx = DimensionContext.from_epochs(
            epochs,
            prior_epochs_today=prior_epochs_today,
            pooled=pooled,
        )
        return pooled, registry.evaluate_all(ctx)

    return _eval


async def test_hysteresis_absorbs_transient_app_switch_and_seals_at_90s(
    tmp_path: Path,
) -> None:
    """Verify <90s app excursions are absorbed and >=90s excursions seal cleanly."""
    storage = EpochRepository(tmp_path / "hysteresis_app.db")
    await storage.initialize()
    recorder = SREObservabilityRecorder(max_recent_events=50)
    sealed_callback_blocks: list[SealedActivityBlock] = []

    async def _on_sealed(block: SealedActivityBlock) -> None:
        sealed_callback_blocks.append(block)

    chunker = ActivityBlockChunker(
        block_repository=storage,
        block_evaluator=_build_evaluator(storage),
        observability=recorder,
        on_block_sealed=_on_sealed,
    )

    # 1. Start active block in Code.exe (2 epochs = 60s)
    assert await chunker.ingest_epoch(_make_snapshot(0, primary_process="Code.exe")) is None
    assert await chunker.ingest_epoch(_make_snapshot(1, primary_process="Code.exe")) is None
    assert chunker.active_primary_process == "Code.exe"
    assert len(chunker.active_epochs) == 2

    # 2. Switch to Slack.app for 2 epochs (60s <= transient threshold), then return to Code.exe
    assert await chunker.ingest_epoch(_make_snapshot(2, primary_process="Slack.app")) is None
    assert await chunker.ingest_epoch(_make_snapshot(3, primary_process="Slack.app")) is None
    assert len(chunker.pending_excursion_epochs) == 2
    assert chunker.blocks_sealed_total == 0

    # Return to Code.exe on epoch 4 -> absorbs the 2 Slack epochs into the Code.exe block!
    assert await chunker.ingest_epoch(_make_snapshot(4, primary_process="Code.exe")) is None
    assert chunker.excursions_absorbed_total == 1
    assert len(chunker.pending_excursion_epochs) == 0
    assert len(chunker.active_epochs) == 5

    # 3. Now switch to firefox for 3 consecutive epochs (90s -> definitive block seal)
    assert await chunker.ingest_epoch(_make_snapshot(5, primary_process="firefox")) is None
    assert await chunker.ingest_epoch(_make_snapshot(6, primary_process="firefox")) is None
    sealed = await chunker.ingest_epoch(_make_snapshot(7, primary_process="firefox"))

    assert sealed is not None
    assert sealed.id == 1
    assert sealed.primary_process == "Code.exe"
    # Sealed cleanly at the moment they left Code.exe (epochs 0..4 = 5 epochs, 150s)
    assert sealed.epoch_count == 5
    assert sealed.duration_seconds == 150.0
    assert len(sealed_callback_blocks) == 1

    # And the 3 firefox epochs (5, 6, 7) are now the active block!
    assert chunker.active_primary_process == "firefox"
    assert len(chunker.active_epochs) == 3
    assert [e.id for e in chunker.active_epochs] == [6, 7, 8]

    # Verify SQLite persistence and DTO helpers
    assert await storage.count_activity_blocks() == 1
    in_range = await storage.fetch_activity_blocks_in_range(0.0, float("inf"))
    assert len(in_range) == 1
    dto: ActivityBlockDTO = in_range[0]
    assert dto.primary_process == "Code.exe"
    assert dto.epoch_count == 5
    assert "temporal_dynamics" in dto.parsed_dimensions()
    assert dto.with_id(99).id == 99
    assert "temporal_dynamics" in sealed.parsed_dimensions()


async def test_hysteresis_zero_input_pause_absorbed_and_150s_idle_seals_without_dilution(
    tmp_path: Path,
) -> None:
    """Verify <=120s zero-input pauses are absorbed and >=150s idle seals cutting off tail."""
    storage = EpochRepository(tmp_path / "hysteresis_idle.db")
    await storage.initialize()
    recorder = SREObservabilityRecorder(max_recent_events=10)
    chunker = ActivityBlockChunker(
        block_repository=storage,
        block_evaluator=_build_evaluator(storage),
        observability=recorder,
    )

    # Leading idle epoch does not open a work block and is cut off from history_epochs_today
    idle_0 = _make_snapshot(
        0,
        primary_process="Code.exe",
        active_seconds=0.0,
        total_keystrokes=0,
        mouse_click_count=0,
        scroll_count=0,
    )
    assert is_zero_input_epoch(idle_0) is True
    assert is_zero_input_epoch(_make_snapshot(0, primary_process="idle")) is True
    assert await chunker.ingest_epoch(idle_0) is None
    assert chunker.active_primary_process is None
    assert chunker.discarded_idle_epochs_total == 1
    assert len(chunker.history_epochs_today) == 0
    assert await chunker.flush_active_block() is None

    # Active work in Code.exe (epochs 1 and 2, duty_cycle = 24/30 = 0.80)
    await chunker.ingest_epoch(_make_snapshot(1, primary_process="Code.exe", active_seconds=24.0))
    await chunker.ingest_epoch(_make_snapshot(2, primary_process="Code.exe", active_seconds=24.0))

    # 4 zero-input epochs (120s reading/thinking pause) followed by active Code.exe epoch
    for idx in (3, 4, 5, 6):
        idle_bridge = _make_snapshot(
            idx,
            primary_process="Code.exe",
            active_seconds=0.0,
            total_keystrokes=0,
            mouse_click_count=0,
            scroll_count=0,
        )
        assert await chunker.ingest_epoch(idle_bridge) is None

    assert (
        await chunker.ingest_epoch(
            _make_snapshot(7, primary_process="Code.exe", active_seconds=24.0)
        )
        is None
    )
    assert chunker.excursions_absorbed_total == 1
    assert len(chunker.active_epochs) == 7
    assert len(chunker.history_epochs_today) == 7

    # Now 5 consecutive zero-input epochs (150s walk-away) -> seals and cuts off all 5 idle epochs
    for idx in (8, 9, 10, 11):
        idle_ep = _make_snapshot(
            idx,
            primary_process="Code.exe",
            active_seconds=0.0,
            total_keystrokes=0,
            mouse_click_count=0,
            scroll_count=0,
        )
        assert await chunker.ingest_epoch(idle_ep) is None

    idle_12 = _make_snapshot(
        12,
        primary_process="idle",
        active_seconds=0.0,
        total_keystrokes=0,
        mouse_click_count=0,
        scroll_count=0,
    )
    sealed = await chunker.ingest_epoch(idle_12)
    assert sealed is not None
    # Sealed block contains only epochs 1..7 (210s), cutting off the 5 trailing idle epochs!
    assert sealed.epoch_count == 7
    assert sealed.duration_seconds == 210.0
    assert sealed.duty_cycle == pytest.approx(72.0 / 210.0, abs=1e-4)

    # Chunker is now idle and the 5 trailing idle epochs were cut off from history_epochs_today!
    assert chunker.active_primary_process is None
    assert len(chunker.active_epochs) == 0
    assert len(chunker.history_epochs_today) == 7
    assert chunker.discarded_idle_epochs_total == 6


async def test_sre_evaluator_weighted_max_severity_and_prometheus_exposition(
    tmp_path: Path,
) -> None:
    """Verify SRE status classifications (flow_optimal, nominal, warning, critical) and metrics."""
    storage = EpochRepository(tmp_path / "sre_eval.db")
    await storage.initialize()
    recorder = SREObservabilityRecorder(max_recent_events=5)
    evaluator = _build_evaluator(storage)

    # Empty evaluations edge case
    empty_report = evaluate_sre_health({})
    assert empty_report.sre_status == "nominal"
    assert empty_report.overall_strain_score == 0.0

    # 1. Optimal flow block (sustained_flow + focused + valid low-jitter keystrokes)
    flow_epochs = [
        _make_snapshot(
            i,
            primary_process="Code.exe",
            active_seconds=24.0,
            micro_pause_count=1,
            context_switch_count=0,
            dwell={"Code.exe": 30.0},
            total_keystrokes=45,
            correction_keystrokes=1,
            iki_count=40,
            iki_sum_ms=6000.0,
            iki_sum_sq_ms=910000.0,
        )
        for i in range(6)
    ]
    _, flow_evals = evaluator(flow_epochs)
    flow_report = evaluate_sre_health(flow_evals)
    assert flow_report.sre_status == "flow_optimal"
    assert flow_report.dominant_state_label == "deep_sustained_flow"

    # Also verify nominal status when engagement is moderate (not flow, not warning/critical)
    nominal_epochs = [
        _make_snapshot(
            i,
            primary_process="Code.exe",
            active_seconds=15.0,
            micro_pause_count=2,
            context_switch_count=1,
            dwell={"Code.exe": 20.0, "Terminal.app": 10.0},
            total_keystrokes=30,
            correction_keystrokes=1,
            iki_count=25,
            iki_sum_ms=3750.0,
            iki_sum_sq_ms=580000.0,
        )
        for i in range(4)
    ]
    _, nominal_evals = evaluator(nominal_epochs)
    nominal_report = evaluate_sre_health(nominal_evals)
    assert nominal_report.sre_status == "nominal"
    assert recorder.registry is not None

    # 2. Insufficient keystroke sample excludes psychomotor_mechanics from composite weight
    reading_epochs = [
        _make_snapshot(
            i,
            primary_process="Preview.app",
            active_seconds=15.0,
            total_keystrokes=0,
            correction_keystrokes=0,
            iki_count=0,
            iki_sum_ms=0.0,
            iki_sum_sq_ms=0.0,
            scroll_count=10,
        )
        for i in range(4)
    ]
    _, reading_evals = evaluator(reading_epochs)
    reading_report = evaluate_sre_health(reading_evals)
    assert reading_report.golden_signals["psychomotor_mechanics"]["active_in_composite"] is False

    # 3. Warning & Critical blocks via chunker + Prometheus exposition
    chunker = ActivityBlockChunker(
        block_repository=storage,
        block_evaluator=evaluator,
        observability=recorder,
    )
    # Warning epoch (elevated micro-pauses -> temporal strain = 0.71 in [0.60, 0.80))
    warn_epoch = _make_snapshot(
        0,
        primary_process="Code.exe",
        active_seconds=12.0,
        micro_pause_count=4,
        context_switch_count=0,
        dwell={"Code.exe": 30.0},
        total_keystrokes=40,
        correction_keystrokes=1,
        iki_count=35,
        iki_sum_ms=5250.0,
        iki_sum_sq_ms=800000.0,
    )
    await chunker.ingest_epoch(warn_epoch)
    warn_block = await chunker.flush_active_block()
    assert warn_block is not None
    assert warn_block.sre_status == "warning"
    assert "WARNING" in warn_block.sre_alert_reason

    # Critical epoch (severe app thrashing + erratic dysfluent motor strain)
    crit_epoch = _make_snapshot(
        1,
        primary_process="Slack.app",
        active_seconds=25.0,
        context_switch_count=9,
        dwell={"Slack.app": 8.0, "Code.exe": 8.0, "firefox": 7.0, "Terminal.app": 7.0},
        total_keystrokes=50,
        correction_keystrokes=15,
        iki_count=40,
        iki_sum_ms=6000.0,
        iki_sum_sq_ms=1500000.0,
    )
    await chunker.ingest_epoch(crit_epoch)
    crit_block = await chunker.flush_active_block()
    assert crit_block is not None
    assert crit_block.sre_status == "critical"
    assert "CRITICAL" in crit_block.sre_alert_reason

    metrics_text = recorder.render_prometheus_metrics()
    assert "egg_epochs_flushed_total 2.0" in metrics_text
    assert 'egg_activity_blocks_sealed_total{sre_status="critical"} 1.0' in metrics_text
    assert "egg_sre_alerts_total" in metrics_text
    assert "egg_block_overall_strain_score" in metrics_text
    assert len(recorder.recent_events) <= 5

    recent_blocks = await storage.fetch_recent_activity_blocks(limit=2)
    assert len(recent_blocks) == 2
    assert recent_blocks[0].id == crit_block.id


def test_chunker_validation_and_dto_invalid_json(tmp_path: Path) -> None:
    """Verify chunker parameter validation and invalid JSON guards on block DTOs."""
    storage = EpochRepository(tmp_path / "val.db")
    evaluator = _build_evaluator(storage)

    with pytest.raises(ValueError, match="transient_max_epochs"):
        ActivityBlockChunker(
            block_repository=storage,
            block_evaluator=evaluator,
            transient_max_epochs=-1,
        )

    with pytest.raises(ValueError, match="seal_epochs"):
        ActivityBlockChunker(
            block_repository=storage,
            block_evaluator=evaluator,
            transient_max_epochs=2,
            seal_epochs=2,
        )

    with pytest.raises(ValueError, match="zero_input_seal_epochs"):
        ActivityBlockChunker(
            block_repository=storage,
            block_evaluator=evaluator,
            transient_max_epochs=2,
            seal_epochs=3,
            zero_input_seal_epochs=2,
        )

    bad_dto = ActivityBlockDTO(
        start_time=0.0,
        end_time=30.0,
        duration_seconds=30.0,
        primary_process="Code.exe",
        epoch_count=1,
        duty_cycle=0.5,
        shannon_entropy=0.0,
        switches_per_minute=0.0,
        iki_cv=0.1,
        correction_ratio=0.0,
        overall_strain_score=0.1,
        dominant_state_label="nominal",
        sre_status="nominal",
        sre_alert_reason="ok",
        dimensions_json="[1, 2, 3]",
    )
    with pytest.raises(ValueError, match="JSON object"):
        bad_dto.parsed_dimensions()

    bad_sealed = SealedActivityBlock(
        start_time=0.0,
        end_time=30.0,
        duration_seconds=30.0,
        primary_process="Code.exe",
        epoch_count=1,
        duty_cycle=0.5,
        shannon_entropy=0.0,
        switches_per_minute=0.0,
        iki_cv=0.1,
        correction_ratio=0.0,
        overall_strain_score=0.1,
        dominant_state_label="nominal",
        sre_status="nominal",
        sre_alert_reason="ok",
        dimensions_json="[1, 2, 3]",
    )
    with pytest.raises(ValueError, match="JSON object"):
        bad_sealed.parsed_dimensions()


async def test_telemetry_service_seals_activity_block_on_shutdown(tmp_path: Path) -> None:
    """Verify TelemetryService wires the chunker and seals the active block on shutdown."""
    db_path = tmp_path / "service_chunker.db"
    config = DaemonConfig(
        epoch_duration_seconds=0.05,
        window_poll_interval_seconds=0.02,
        database_path=db_path,
        simulate=True,
        enable_api=False,
    )
    sealed_blocks: list[SealedActivityBlock] = []

    def _on_sealed(block: SealedActivityBlock) -> None:
        sealed_blocks.append(block)

    service = TelemetryService(config, on_block_sealed=_on_sealed)
    assert service.chunker is not None

    await service.run(max_duration_seconds=0.12, install_signals=False)
    assert await service.storage.count_epochs() >= 1
    assert await service.storage.count_activity_blocks() >= 1
    assert len(sealed_blocks) >= 1
