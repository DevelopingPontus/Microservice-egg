"""Attention and Window Dwell Feature Package (`app/features/attention_dwell/`)."""

from app.features.attention_dwell.accumulator import AttentionDwellAccumulator
from app.features.attention_dwell.math import compute_shannon_entropy
from app.features.attention_dwell.models import RawAttentionWindowMetrics
from app.features.attention_dwell.recorder import AttentionDwellRecorder

__all__ = [
    "AttentionDwellAccumulator",
    "AttentionDwellRecorder",
    "RawAttentionWindowMetrics",
    "compute_shannon_entropy",
]
