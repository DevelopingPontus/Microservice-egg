"""Self-contained protocols, constants, and epoch snapshot model for app/engine/."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol, runtime_checkable

DEFAULT_EPOCH_DURATION_SECONDS: float = 30.0
DEFAULT_IDLE_EVENT_THRESHOLD_SECONDS: float = 1.5
DEFAULT_MICRO_PAUSE_MIN_SECONDS: float = 1.0
DEFAULT_MICRO_PAUSE_MAX_SECONDS: float = 5.0
DEFAULT_IKI_MAX_OUTLIER_MS: float = 5000.0
DEFAULT_MOUSE_MOVE_THROTTLE_SECONDS: float = 0.25
DEFAULT_WINDOW_POLL_INTERVAL_SECONDS: float = 0.25
DEFAULT_HYSTERESIS_TRANSIENT_MAX_EPOCHS: int = 2
DEFAULT_HYSTERESIS_SEAL_EPOCHS: int = 3
DEFAULT_SRE_WARNING_THRESHOLD: float = 0.60
DEFAULT_SRE_CRITICAL_THRESHOLD: float = 0.80


@dataclass(frozen=True, slots=True)
class EpochSnapshot:
    """Immutable 30-second telemetry snapshot harvested by EpochBuffer."""

    timestamp_start: float
    timestamp_end: float
    primary_process: str
    active_seconds: float
    micro_pause_count: int
    context_switch_count: int
    dwell_distribution_json: str
    total_keystrokes: int
    correction_keystrokes: int
    iki_count: int
    iki_sum_ms: float
    iki_sum_sq_ms: float
    mouse_click_count: int = 0
    scroll_count: int = 0
    id: int | None = None

    @property
    def duration_seconds(self) -> float:
        """Total elapsed wall-clock seconds covered by this epoch."""
        return max(0.0, self.timestamp_end - self.timestamp_start)

    def parsed_dwell_distribution(self) -> dict[str, float]:
        """Deserialize dwell_distribution_json into a mapping of process -> seconds."""
        raw = json.loads(self.dwell_distribution_json)
        if not isinstance(raw, dict):
            raise ValueError("dwell_distribution_json must encode a JSON object")
        return {str(proc): float(seconds) for proc, seconds in raw.items()}

    def with_id(self, row_id: int) -> "EpochSnapshot":
        """Return a copy of this snapshot stamped with its persisted database id."""
        return replace(self, id=row_id)


@runtime_checkable
class EpochPersistenceProtocol(Protocol):
    """Structural contract for persisting a harvested 30s epoch snapshot."""

    async def insert_epoch(self, epoch: Any) -> int:
        """Persist a 30-second epoch snapshot and return its row id."""


@runtime_checkable
class WindowSourceProtocol(Protocol):
    """Structural contract for sampling the sanitized active foreground process name."""

    def get_active_process_name(self) -> str:
        """Return the sanitized executable or bundle name of the active window."""


@runtime_checkable
class InputLifecycleProtocol(Protocol):
    """Structural contract for starting and stopping an input listener."""

    def start(self) -> None:
        """Start input collection."""

    def stop(self) -> None:
        """Stop input collection."""


@runtime_checkable
class SyntheticBurstSourceProtocol(InputLifecycleProtocol, Protocol):
    """Structural contract for synthetic input listeners supporting deterministic bursts."""

    @property
    def is_running(self) -> bool:
        """Whether synthetic input collection is marked active."""

    def emit_synthetic_burst(self) -> None:
        """Emit one deterministic sequence of synthetic input events."""


@runtime_checkable
class EngineDimensionEvalProtocol(Protocol):
    """Structural contract for a single evaluated scientific dimension result."""

    @property
    def dimension_name(self) -> str: ...

    @property
    def strain_score(self) -> float: ...

    @property
    def state_label(self) -> str: ...

    @property
    def metrics(self) -> dict[str, Any]: ...

    @property
    def blameless_summary(self) -> str: ...


@runtime_checkable
class EnginePooledMetricsProtocol(Protocol):
    """Structural contract for pooled telemetry metrics across an activity block."""

    @property
    def epoch_count(self) -> int: ...

    @property
    def total_duration_seconds(self) -> float: ...

    @property
    def total_active_seconds(self) -> float: ...

    @property
    def duty_cycle(self) -> float: ...

    @property
    def shannon_entropy(self) -> float: ...

    @property
    def switches_per_minute(self) -> float: ...

    @property
    def primary_process(self) -> str: ...

    @property
    def iki_cv(self) -> float: ...

    @property
    def correction_ratio(self) -> float: ...

    @property
    def is_psychomotor_valid(self) -> bool: ...


@runtime_checkable
class BlockEvaluatorProtocol(Protocol):
    """Structural contract for evaluating a sequence of epochs across all dimensions."""

    def __call__(
        self,
        epochs: Sequence[EpochSnapshot],
        *,
        prior_epochs_today: Sequence[EpochSnapshot] = (),
    ) -> tuple[EnginePooledMetricsProtocol, Mapping[str, EngineDimensionEvalProtocol]]:
        """Pool epochs and evaluate all registered scientific dimensions."""


@runtime_checkable
class ActivityBlockPersistenceProtocol(Protocol):
    """Structural contract for persisting a sealed activity block to SQLite."""

    async def insert_activity_block(self, block: Any) -> int:
        """Persist a sealed activity block and return its primary key id."""


@dataclass(frozen=True, slots=True)
class SealedActivityBlock:
    """Self-contained immutable representation of a sealed cognitive activity block."""

    start_time: float
    end_time: float
    duration_seconds: float
    primary_process: str
    epoch_count: int
    duty_cycle: float
    shannon_entropy: float
    switches_per_minute: float
    iki_cv: float
    correction_ratio: float
    overall_strain_score: float
    dominant_state_label: str
    sre_status: str
    sre_alert_reason: str
    dimensions_json: str
    id: int | None = None

    def parsed_dimensions(self) -> dict[str, Any]:
        """Deserialize dimensions_json into a dictionary of evaluated dimension payloads."""
        raw = json.loads(self.dimensions_json)
        if not isinstance(raw, dict):
            raise ValueError("dimensions_json must encode a JSON object")
        return dict(raw)

    def with_id(self, row_id: int) -> "SealedActivityBlock":
        """Return a copy of this block stamped with its persisted database id."""
        return replace(self, id=row_id)
