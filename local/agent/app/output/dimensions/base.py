"""Base contracts, structural protocols, and Open-Closed registry for `app/output/dimensions/`."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from app.common.config import IKI_MIN_VALID_SAMPLES as DEFAULT_DIMENSION_IKI_MIN_SAMPLES
from app.common.models import (
    DimensionEvaluation,
    EpochRecordProtocol,
    MetricValue,
    PooledTelemetryMetrics,
    pool_epoch_metrics,
)
from app.common.protocols import PooledMetricsProtocol

__all__ = [
    "BaseDimension",
    "DEFAULT_DIMENSION_IKI_MIN_SAMPLES",
    "DimensionContext",
    "DimensionEpochProtocol",
    "DimensionEvaluation",
    "DimensionPooledMetrics",
    "DimensionPooledMetricsProtocol",
    "DimensionRegistry",
    "MetricValue",
    "clamp_score",
    "pool_dimension_epochs",
]

DimensionEpochProtocol = EpochRecordProtocol
DimensionPooledMetrics = PooledTelemetryMetrics
DimensionPooledMetricsProtocol = PooledMetricsProtocol


def clamp_score(value: float) -> float:
    """Clamp a normalized strain score into the closed interval [0.0, 1.0]."""
    return min(1.0, max(0.0, round(value, 4)))


def pool_dimension_epochs(
    epochs: Sequence[DimensionEpochProtocol],
    *,
    iki_min_valid_samples: int = DEFAULT_DIMENSION_IKI_MIN_SAMPLES,
) -> DimensionPooledMetrics:
    """Pool a sequence of DimensionEpochProtocol records using canonical pooling math."""
    return pool_epoch_metrics(epochs, iki_min_valid_samples=iki_min_valid_samples)


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
    """Evaluates all registered scientific dimensions deterministically."""

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
