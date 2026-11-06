"""Base contracts, structural protocols, and Open-Closed registry for `app/output/dimensions/`."""

import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from app.common.models import (
    DimensionEvaluation,
    MetricValue,
)
from app.common.protocols import PooledMetricsProtocol

__all__ = [
    "BaseDimension",
    "DimensionContext",
    "DimensionEvaluation",
    "DimensionRegistry",
    "MetricValue",
    "clamp_score",
]


def clamp_score(value: float) -> float:
    """Clamp a normalized strain score into the closed interval [0.0, 1.0]."""
    return min(1.0, max(0.0, round(value, 4)))


@dataclass(frozen=True, slots=True)
class DimensionContext:
    """Immutable input context shared across all registered scientific dimensions."""

    metrics: PooledMetricsProtocol
    session_uptime_seconds: float = 0.0
    now_timestamp: float = 0.0

    @classmethod
    def create(
        cls,
        metrics: PooledMetricsProtocol,
        *,
        session_uptime_seconds: float = 0.0,
        now_timestamp: float | None = None,
    ) -> "DimensionContext":
        """Construct a DimensionContext."""
        ts = now_timestamp if now_timestamp is not None else time.time()
        return cls(
            metrics=metrics,
            session_uptime_seconds=session_uptime_seconds,
            now_timestamp=ts,
        )


class BaseDimension(ABC):
    """Abstract base contract for pluggable cognitive telemetry dimensions."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique canonical snake_case identifier for this dimension."""

    @abstractmethod
    def evaluate(self, context: DimensionContext) -> DimensionEvaluation:
        """Evaluate the sliding window metrics and return an immutable DimensionEvaluation."""


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
