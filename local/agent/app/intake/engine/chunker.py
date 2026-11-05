"""60s/90s Hysteresis Activity Block Chunker for debounced cognitive state segmentation."""

import json
from collections.abc import Callable, Coroutine, Sequence
from typing import Any

from app.common.config import (
    HYSTERESIS_SEAL_EPOCHS as DEFAULT_HYSTERESIS_SEAL_EPOCHS,
)
from app.common.config import (
    HYSTERESIS_TRANSIENT_MAX_EPOCHS as DEFAULT_HYSTERESIS_TRANSIENT_MAX_EPOCHS,
)
from app.common.config import (
    SRE_CRITICAL_THRESHOLD as DEFAULT_SRE_CRITICAL_THRESHOLD,
)
from app.common.config import (
    SRE_WARNING_THRESHOLD as DEFAULT_SRE_WARNING_THRESHOLD,
)
from app.common.config import (
    ZERO_INPUT_SEAL_EPOCHS as DEFAULT_ZERO_INPUT_SEAL_EPOCHS,
)
from app.common.models import EpochSnapshot, SealedActivityBlock, is_engaged_epoch
from app.common.protocols import (
    ActivityBlockPersistenceProtocol,
    BlockEvaluatorProtocol,
)
from app.intake.engine.sre import SREObservabilityRecorder, evaluate_sre_health

BlockSealedCallback = Callable[[SealedActivityBlock], Coroutine[Any, Any, None] | None]


def is_zero_input_epoch(epoch: EpochSnapshot) -> bool:
    """Return True if an epoch had zero user interaction or resolved to 'idle'."""
    return not is_engaged_epoch(epoch)


class ActivityBlockChunker:
    """Debounces 30s micro-epochs into coherent ActivityBlocks with no-input tail cut-off."""

    def __init__(
        self,
        *,
        block_repository: ActivityBlockPersistenceProtocol,
        block_evaluator: BlockEvaluatorProtocol,
        observability: SREObservabilityRecorder | None = None,
        transient_max_epochs: int = DEFAULT_HYSTERESIS_TRANSIENT_MAX_EPOCHS,
        seal_epochs: int = DEFAULT_HYSTERESIS_SEAL_EPOCHS,
        zero_input_seal_epochs: int = DEFAULT_ZERO_INPUT_SEAL_EPOCHS,
        warning_threshold: float = DEFAULT_SRE_WARNING_THRESHOLD,
        critical_threshold: float = DEFAULT_SRE_CRITICAL_THRESHOLD,
        on_block_sealed: BlockSealedCallback | None = None,
    ) -> None:
        if transient_max_epochs < 0:
            raise ValueError("transient_max_epochs must be >= 0")
        if seal_epochs <= transient_max_epochs:
            raise ValueError("seal_epochs must be > transient_max_epochs")
        if zero_input_seal_epochs < seal_epochs:
            raise ValueError("zero_input_seal_epochs must be >= seal_epochs")

        self._block_repository = block_repository
        self._block_evaluator = block_evaluator
        self._observability = (
            observability if observability is not None else SREObservabilityRecorder()
        )
        self._transient_max_epochs = transient_max_epochs
        self._seal_epoch_threshold = seal_epochs
        self._zero_input_seal_threshold = zero_input_seal_epochs
        self._warning_threshold = warning_threshold
        self._critical_threshold = critical_threshold
        self._on_block_sealed = on_block_sealed

        self._active_primary_process: str | None = None
        self._active_epochs: list[EpochSnapshot] = []
        self._pending_excursion_epochs: list[EpochSnapshot] = []
        self._history_epochs_today: list[EpochSnapshot] = []
        self._blocks_sealed_total: int = 0
        self._excursions_absorbed_total: int = 0
        self._discarded_idle_epochs_total: int = 0

    @property
    def observability(self) -> SREObservabilityRecorder:
        """SRE observability recorder emitting JSON events and Prometheus metrics."""
        return self._observability

    @property
    def active_primary_process(self) -> str | None:
        """Primary process of the currently open activity block, or None if idle."""
        return self._active_primary_process

    @property
    def active_epochs(self) -> tuple[EpochSnapshot, ...]:
        """Committed epochs in the currently open activity block."""
        return tuple(self._active_epochs)

    @property
    def pending_excursion_epochs(self) -> tuple[EpochSnapshot, ...]:
        """Uncommitted excursion epochs held inside the 60s hysteresis window."""
        return tuple(self._pending_excursion_epochs)

    @property
    def blocks_sealed_total(self) -> int:
        """Total number of activity blocks sealed since chunker startup."""
        return self._blocks_sealed_total

    @property
    def excursions_absorbed_total(self) -> int:
        """Total number of transient excursions absorbed since startup."""
        return self._excursions_absorbed_total

    @property
    def discarded_idle_epochs_total(self) -> int:
        """Total number of unanchored no-input epochs cut off from the collection."""
        return self._discarded_idle_epochs_total

    @property
    def history_epochs_today(self) -> tuple[EpochSnapshot, ...]:
        """Qualified active and bridged epochs committed today (excluding cut-off idle tails)."""
        return tuple(self._history_epochs_today)

    def _consume_epoch_into_state(self, epoch: EpochSnapshot) -> list[EpochSnapshot] | None:
        """Advance the hysteresis state machine, cutting off unanchored no-input tails."""
        zero_input = is_zero_input_epoch(epoch)

        if self._active_primary_process is None or not self._active_epochs:
            if zero_input:
                self._discarded_idle_epochs_total += 1
                return None
            self._active_primary_process = epoch.primary_process
            self._active_epochs = [epoch]
            self._history_epochs_today.append(epoch)
            self._pending_excursion_epochs = []
            return None

        if not zero_input and epoch.primary_process == self._active_primary_process:
            if self._pending_excursion_epochs:
                all_zero = all(is_zero_input_epoch(e) for e in self._pending_excursion_epochs)
                excursion_type = "zero_input" if all_zero else "app_switch"
                absorbed_duration = sum(e.duration_seconds for e in self._pending_excursion_epochs)
                self._observability.record_excursion_absorbed(
                    primary_process=self._active_primary_process,
                    excursion_type=excursion_type,
                    absorbed_epoch_count=len(self._pending_excursion_epochs),
                    absorbed_duration_seconds=absorbed_duration,
                )
                self._excursions_absorbed_total += 1
                self._active_epochs.extend(self._pending_excursion_epochs)
                self._history_epochs_today.extend(self._pending_excursion_epochs)
                self._pending_excursion_epochs = []

            self._active_epochs.append(epoch)
            self._history_epochs_today.append(epoch)
            return None

        self._pending_excursion_epochs.append(epoch)
        all_pending_zero = all(is_zero_input_epoch(e) for e in self._pending_excursion_epochs)
        required_seal_epochs = (
            self._zero_input_seal_threshold if all_pending_zero else self._seal_epoch_threshold
        )
        if len(self._pending_excursion_epochs) < required_seal_epochs:
            return None

        epochs_to_seal = list(self._active_epochs)
        pending_to_replay = list(self._pending_excursion_epochs)

        self._active_primary_process = None
        self._active_epochs = []
        self._pending_excursion_epochs = []

        for pending_epoch in pending_to_replay:
            self._consume_epoch_into_state(pending_epoch)

        return epochs_to_seal

    async def _seal_epochs(self, epochs: Sequence[EpochSnapshot]) -> SealedActivityBlock:
        """Evaluate 4 dimensions + SRE health, persist to SQLite, and emit SRE telemetry."""
        block_start = epochs[0].timestamp_start
        prior_epochs = [e for e in self._history_epochs_today if e.timestamp_end <= block_start]
        pooled, evaluations = self._block_evaluator(
            epochs,
            prior_epochs_today=prior_epochs,
        )
        sre_report = evaluate_sre_health(
            evaluations,
            warning_threshold=self._warning_threshold,
            critical_threshold=self._critical_threshold,
        )

        end_time = epochs[-1].timestamp_end
        duration_seconds = round(sum(e.duration_seconds for e in epochs), 4)
        primary_process = (
            epochs[0].primary_process
            if epochs and epochs[0].primary_process != "idle"
            else pooled.primary_process
        )

        unpersisted = SealedActivityBlock(
            start_time=block_start,
            end_time=end_time,
            duration_seconds=duration_seconds,
            primary_process=primary_process,
            epoch_count=len(epochs),
            duty_cycle=round(pooled.duty_cycle, 4),
            shannon_entropy=round(pooled.shannon_entropy, 4),
            switches_per_minute=round(pooled.switches_per_minute, 4),
            iki_cv=round(pooled.iki_cv, 4),
            correction_ratio=round(pooled.correction_ratio, 4),
            overall_strain_score=sre_report.overall_strain_score,
            dominant_state_label=sre_report.dominant_state_label,
            sre_status=sre_report.sre_status,
            sre_alert_reason=sre_report.sre_alert_reason,
            dimensions_json=json.dumps(sre_report.golden_signals, sort_keys=True),
        )
        row_id = await self._block_repository.insert_activity_block(unpersisted)
        sealed = unpersisted.with_id(row_id)
        self._blocks_sealed_total += 1
        self._observability.record_block_sealed(sealed, sre_report)

        if self._on_block_sealed is not None:
            maybe_coro = self._on_block_sealed(sealed)
            if maybe_coro is not None:
                await maybe_coro

        return sealed

    async def ingest_epoch(self, epoch: EpochSnapshot) -> SealedActivityBlock | None:
        """Process a newly flushed 30s epoch and return a SealedActivityBlock if sealed."""
        self._observability.record_epoch_flushed(epoch)

        epochs_to_seal = self._consume_epoch_into_state(epoch)
        if epochs_to_seal is None:
            return None

        return await self._seal_epochs(epochs_to_seal)

    async def flush_active_block(self) -> SealedActivityBlock | None:
        """Force-seal any active work block on shutdown, cutting off any trailing silent tail."""
        if not self._active_epochs:
            self._pending_excursion_epochs = []
            return None

        if self._pending_excursion_epochs:
            discarded_zero = sum(
                1 for ep in self._pending_excursion_epochs if is_zero_input_epoch(ep)
            )
            self._discarded_idle_epochs_total += discarded_zero

        epochs_to_seal = list(self._active_epochs)
        self._active_primary_process = None
        self._active_epochs = []
        self._pending_excursion_epochs = []
        return await self._seal_epochs(epochs_to_seal)
