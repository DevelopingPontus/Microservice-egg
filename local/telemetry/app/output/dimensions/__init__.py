"""Pluggable Scientific Dimension Engine (`app/output/dimensions/`)."""

from app.output.dimensions.attentional import AttentionalFragmentationDimension
from app.output.dimensions.base import (
    BaseDimension,
    DimensionContext,
    DimensionEvaluation,
    DimensionRegistry,
    MetricValue,
    clamp_score,
)
from app.output.dimensions.psychomotor import PsychomotorMechanicsDimension
from app.output.dimensions.temporal import TemporalDynamicsDimension
from app.output.dimensions.uptime import SessionUptimeDimension

__all__ = [
    "AttentionalFragmentationDimension",
    "BaseDimension",
    "DimensionContext",
    "DimensionEvaluation",
    "DimensionRegistry",
    "MetricValue",
    "PsychomotorMechanicsDimension",
    "SessionUptimeDimension",
    "TemporalDynamicsDimension",
    "clamp_score",
    "create_default_registry",
]


def create_default_registry() -> DimensionRegistry:
    """Instantiate and populate the canonical 4 ground-truth dimensions."""
    return DimensionRegistry(
        (
            TemporalDynamicsDimension(),
            AttentionalFragmentationDimension(),
            PsychomotorMechanicsDimension(),
            SessionUptimeDimension(),
        )
    )
