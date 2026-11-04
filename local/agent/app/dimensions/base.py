"""Base contracts, structural protocols, and Open-Closed registry for app/dimensions/."""

import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

MetricValue = float | int | str | bool
DEFAULT_DIMENSION_IKI_MIN_SAMPLES: int = 10


def clamp_score(value: float) -> float:
    """Clamp a normalized strain score into the closed interval [0.0, 1.0]."""
    return min(1.0, max(0.0, round(value, 4)))


@runtime_checkable
class DimensionEpochProtocol(Protocol):
    """Structural contract for a 30-second epoch evaluated by scientific dimensions."""

    @property
    def timestamp_start(self) -> float: ...

    @property
    def timestamp_end(self) -> float: ...

    @property
    def primary_process(self) -> str: ...

    @property
    def active_seconds(self) -> float: ...

    @property
    def micro_pause_count(self) -> int: ...

    @property
    def mouse_click_count(self) -> int: ...

    @property
    def scroll_count(self) -> int: ...

    @property
    def context_switch_count(self) -> int: ...

    @property
    def dwell_distribution_json(self) -> str: ...

    @property
    def total_keystrokes(self) -> int: ...

    @property
    def correction_keystrokes(self) -> int: ...

    @property
    def iki_count(self) -> int: ...

    @property
    def iki_sum_ms(self) -> float: ...

    @property
    def iki_sum_sq_ms(self) -> float: ...

    @property
    def duration_seconds(self) -> float: ...

    def parsed_dwell_distribution(self) -> dict[str, float]: ...


@runtime_checkable
class DimensionPooledMetricsProtocol(Protocol):
    """Structural contract for pooled telemetry metrics consumed by dimensions."""

    @property
    def epoch_count(self) -> int: ...

    @property
    def total_duration_seconds(self) -> float: ...

    @property
    def total_active_seconds(self) -> float: ...

    @property
    def duty_cycle(self) -> float: ...

    @property
    def total_micro_pauses(self) -> int: ...

    @property
    def total_mouse_clicks(self) -> int: ...

    @property
    def total_scroll_events(self) -> int: ...

    @property
    def total_context_switches(self) -> int: ...

    @property
    def switches_per_minute(self) -> float: ...

    @property
    def merged_dwell_seconds(self) -> dict[str, float]: ...

    @property
    def primary_process(self) -> str: ...

    @property
    def primary_process_ratio(self) -> float: ...

    @property
    def shannon_entropy(self) -> float: ...

    @property
    def total_keystrokes(self) -> int: ...

    @property
    def correction_keystrokes(self) -> int: ...

    @property
    def correction_ratio(self) -> float: ...

    @property
    def iki_count(self) -> int: ...

    @property
    def is_psychomotor_valid(self) -> bool: ...

    @property
    def iki_mean_ms(self) -> float: ...

    @property
    def iki_variance_ms2(self) -> float: ...

    @property
    def iki_std_dev_ms(self) -> float: ...

    @property
    def iki_cv(self) -> float: ...


@dataclass(frozen=True, slots=True)
class DimensionPooledMetrics:
    """Self-contained pooled metrics representation inside app/dimensions/."""

    epoch_count: int
    total_duration_seconds: float
    total_active_seconds: float
    duty_cycle: float
    total_micro_pauses: int
    total_mouse_clicks: int
    total_scroll_events: int
    total_context_switches: int
    switches_per_minute: float
    merged_dwell_seconds: dict[str, float]
    primary_process: str
    primary_process_ratio: float
    shannon_entropy: float
    total_keystrokes: int
    correction_keystrokes: int
    correction_ratio: float
    iki_count: int
    is_psychomotor_valid: bool
    iki_mean_ms: float
    iki_variance_ms2: float
    iki_std_dev_ms: float
    iki_cv: float


def pool_dimension_epochs(
    epochs: Sequence[DimensionEpochProtocol],
    *,
    iki_min_valid_samples: int = DEFAULT_DIMENSION_IKI_MIN_SAMPLES,
) -> DimensionPooledMetrics:
    """Pool a sequence of DimensionEpochProtocol records without cross-folder imports."""
    epoch_count = len(epochs)
    if epoch_count == 0:
        return DimensionPooledMetrics(
            epoch_count=0,
            total_duration_seconds=0.0,
            total_active_seconds=0.0,
            duty_cycle=0.0,
            total_micro_pauses=0,
            total_mouse_clicks=0,
            total_scroll_events=0,
            total_context_switches=0,
            switches_per_minute=0.0,
            merged_dwell_seconds={},
            primary_process="idle",
            primary_process_ratio=0.0,
            shannon_entropy=0.0,
            total_keystrokes=0,
            correction_keystrokes=0,
            correction_ratio=0.0,
            iki_count=0,
            is_psychomotor_valid=False,
            iki_mean_ms=0.0,
            iki_variance_ms2=0.0,
            iki_std_dev_ms=0.0,
            iki_cv=0.0,
        )

    total_duration = sum(e.duration_seconds for e in epochs)
    total_active = sum(max(0.0, e.active_seconds) for e in epochs)
    duty_cycle = min(1.0, max(0.0, total_active / total_duration)) if total_duration > 0.0 else 0.0

    total_micro_pauses = sum(e.micro_pause_count for e in epochs)
    total_mouse_clicks = sum(e.mouse_click_count for e in epochs)
    total_scroll_events = sum(e.scroll_count for e in epochs)
    total_switches = sum(e.context_switch_count for e in epochs)
    switches_per_min = (total_switches / (total_duration / 60.0)) if total_duration > 0.0 else 0.0

    merged_dwell: dict[str, float] = {}
    for epoch in epochs:
        for proc, seconds in epoch.parsed_dwell_distribution().items():
            if seconds > 0.0:
                merged_dwell[proc] = merged_dwell.get(proc, 0.0) + seconds

    total_dwell = sum(merged_dwell.values())
    if merged_dwell and total_dwell > 0.0:
        primary_process = max(merged_dwell.items(), key=lambda item: item[1])[0]
        primary_process_ratio = min(1.0, max(0.0, merged_dwell[primary_process] / total_dwell))
    else:
        primary_process = epochs[-1].primary_process
        primary_process_ratio = 0.0

    positive_dwells = [sec for sec in merged_dwell.values() if sec > 0.0]
    if total_dwell <= 0.0 or len(positive_dwells) <= 1:
        shannon_entropy = 0.0
    else:
        entropy_acc = 0.0
        for sec in positive_dwells:
            prob = sec / total_dwell
            entropy_acc -= prob * math.log(prob)
        shannon_entropy = max(0.0, entropy_acc)

    total_keys = sum(e.total_keystrokes for e in epochs)
    corr_keys = sum(e.correction_keystrokes for e in epochs)
    correction_ratio = min(1.0, max(0.0, corr_keys / total_keys)) if total_keys > 0 else 0.0

    total_iki_count = sum(e.iki_count for e in epochs)
    is_psychomotor_valid = total_iki_count >= iki_min_valid_samples
    if total_iki_count > 0:
        total_iki_sum = sum(e.iki_sum_ms for e in epochs)
        total_iki_sum_sq = sum(e.iki_sum_sq_ms for e in epochs)
        iki_mean = total_iki_sum / total_iki_count
        iki_variance = max(0.0, (total_iki_sum_sq / total_iki_count) - (iki_mean * iki_mean))
        iki_std_dev = math.sqrt(iki_variance)
        iki_cv = (iki_std_dev / iki_mean) if iki_mean > 0.0 else 0.0
    else:
        iki_mean = 0.0
        iki_variance = 0.0
        iki_std_dev = 0.0
        iki_cv = 0.0

    return DimensionPooledMetrics(
        epoch_count=epoch_count,
        total_duration_seconds=total_duration,
        total_active_seconds=total_active,
        duty_cycle=duty_cycle,
        total_micro_pauses=total_micro_pauses,
        total_mouse_clicks=total_mouse_clicks,
        total_scroll_events=total_scroll_events,
        total_context_switches=total_switches,
        switches_per_minute=switches_per_min,
        merged_dwell_seconds=merged_dwell,
        primary_process=primary_process,
        primary_process_ratio=primary_process_ratio,
        shannon_entropy=shannon_entropy,
        total_keystrokes=total_keys,
        correction_keystrokes=corr_keys,
        correction_ratio=correction_ratio,
        iki_count=total_iki_count,
        is_psychomotor_valid=is_psychomotor_valid,
        iki_mean_ms=iki_mean,
        iki_variance_ms2=iki_variance,
        iki_std_dev_ms=iki_std_dev,
        iki_cv=iki_cv,
    )


@dataclass(frozen=True, slots=True)
class DimensionEvaluation:
    """Immutable evaluation result emitted by a single scientific dimension."""

    dimension_name: str
    strain_score: float
    state_label: str
    metrics: dict[str, MetricValue]
    blameless_summary: str


@dataclass(frozen=True, slots=True)
class DimensionContext:
    """Immutable input context shared across all registered scientific dimensions."""

    epochs: Sequence[DimensionEpochProtocol]
    pooled: DimensionPooledMetricsProtocol
    prior_epochs_today: Sequence[DimensionEpochProtocol] = ()

    @classmethod
    def from_epochs(
        cls,
        epochs: Sequence[DimensionEpochProtocol],
        *,
        prior_epochs_today: Sequence[DimensionEpochProtocol] = (),
        pooled: DimensionPooledMetricsProtocol | None = None,
    ) -> "DimensionContext":
        """Construct a DimensionContext from epochs and optional pre-pooled metrics."""
        resolved_pooled = pooled if pooled is not None else pool_dimension_epochs(epochs)
        return cls(
            epochs=tuple(epochs),
            pooled=resolved_pooled,
            prior_epochs_today=tuple(prior_epochs_today),
        )


class BaseDimension(ABC):
    """Abstract base contract for pluggable cognitive telemetry dimensions."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique canonical snake_case identifier for this dimension."""

    @abstractmethod
    def evaluate(self, context: DimensionContext) -> DimensionEvaluation:
        """Evaluate the pooled epoch window and return an immutable DimensionEvaluation."""


class DimensionRegistry:
    """Folder orchestrator evaluating all registered dimensions deterministically."""

    def __init__(self, dimensions: Sequence[BaseDimension] = ()) -> None:
        self._dimensions: dict[str, BaseDimension] = {}
        for dimension in dimensions:
            self.register(dimension)

    def register(self, dimension: BaseDimension) -> None:
        """Register a dimension plugin, rejecting duplicate dimension names."""
        if dimension.name in self._dimensions:
            raise ValueError(f"Dimension '{dimension.name}' is already registered")
        self._dimensions[dimension.name] = dimension

    @property
    def dimensions(self) -> tuple[BaseDimension, ...]:
        """Return registered dimensions in deterministic registration order."""
        return tuple(self._dimensions.values())

    def evaluate_all(self, context: DimensionContext) -> dict[str, DimensionEvaluation]:
        """Evaluate every registered dimension against the provided DimensionContext."""
        return {name: dimension.evaluate(context) for name, dimension in self._dimensions.items()}
