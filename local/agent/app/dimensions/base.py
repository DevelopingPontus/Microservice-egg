"""Base contracts and Open-Closed registry for the 4-Dimension Scientific Engine."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from app.storage.repository import EpochMetricsDTO, PooledTelemetryMetrics, pool_epoch_metrics

MetricValue = float | int | str | bool


def clamp_score(value: float) -> float:
    """Clamp a normalized strain score into the closed interval [0.0, 1.0]."""
    return min(1.0, max(0.0, round(value, 4)))


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

    epochs: Sequence[EpochMetricsDTO]
    pooled: PooledTelemetryMetrics
    prior_epochs_today: Sequence[EpochMetricsDTO] = ()

    @classmethod
    def from_epochs(
        cls,
        epochs: Sequence[EpochMetricsDTO],
        *,
        prior_epochs_today: Sequence[EpochMetricsDTO] = (),
    ) -> "DimensionContext":
        """Construct a DimensionContext by losslessly pooling the target epochs."""
        return cls(
            epochs=tuple(epochs),
            pooled=pool_epoch_metrics(epochs),
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
    """Open-Closed registry that evaluates all registered dimensions deterministically."""

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
