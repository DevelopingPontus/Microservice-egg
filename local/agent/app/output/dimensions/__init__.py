"""Pluggable 4-Dimension Scientific Engine (`app/output/dimensions/`)."""

from datetime import tzinfo

from app.output.dimensions.attentional import AttentionalFragmentationDimension
from app.output.dimensions.base import (
    BaseDimension,
    DimensionContext,
    DimensionEpochProtocol,
    DimensionEvaluation,
    DimensionPooledMetrics,
    DimensionPooledMetricsProtocol,
    DimensionRegistry,
    MetricValue,
    clamp_score,
    pool_dimension_epochs,
)
from app.output.dimensions.circadian import (
    CircadianLoadDimension,
    compute_continuous_load_minutes,
)
from app.output.dimensions.psychomotor import PsychomotorMechanicsDimension
from app.output.dimensions.temporal import TemporalDynamicsDimension


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
    "DimensionEpochProtocol",
    "DimensionEvaluation",
    "DimensionPooledMetrics",
    "DimensionPooledMetricsProtocol",
    "DimensionRegistry",
    "MetricValue",
    "PsychomotorMechanicsDimension",
    "TemporalDynamicsDimension",
    "clamp_score",
    "compute_continuous_load_minutes",
    "create_default_registry",
    "pool_dimension_epochs",
]
