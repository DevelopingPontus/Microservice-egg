"""Pluggable 4-Dimension Scientific Engine for passive cognitive telemetry."""

from datetime import tzinfo

from app.dimensions.attentional import AttentionalFragmentationDimension
from app.dimensions.base import (
    BaseDimension,
    DimensionContext,
    DimensionEvaluation,
    DimensionRegistry,
    MetricValue,
    clamp_score,
)
from app.dimensions.circadian import (
    CircadianLoadDimension,
    compute_continuous_load_minutes,
)
from app.dimensions.psychomotor import PsychomotorMechanicsDimension
from app.dimensions.temporal import TemporalDynamicsDimension


def create_default_registry(*, tz: tzinfo | None = None) -> DimensionRegistry:
    """Create a DimensionRegistry pre-populated with all 4 core scientific dimensions."""
    return DimensionRegistry(
        dimensions=(
            TemporalDynamicsDimension(),
            AttentionalFragmentationDimension(),
            PsychomotorMechanicsDimension(),
            CircadianLoadDimension(tz=tz),
        )
    )


__all__ = [
    "AttentionalFragmentationDimension",
    "BaseDimension",
    "CircadianLoadDimension",
    "DimensionContext",
    "DimensionEvaluation",
    "DimensionRegistry",
    "MetricValue",
    "PsychomotorMechanicsDimension",
    "TemporalDynamicsDimension",
    "clamp_score",
    "compute_continuous_load_minutes",
    "create_default_registry",
]
