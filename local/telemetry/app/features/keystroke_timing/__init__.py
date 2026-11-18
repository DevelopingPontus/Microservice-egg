"""Keystroke Timing Feature Package (`app/features/keystroke_timing/`)."""

from app.features.keystroke_timing.accumulator import (
    KeystrokeTimingAccumulator,
    compute_median_abs_deviation,
)
from app.features.keystroke_timing.models import RawKeystrokeTimingMetrics
from app.features.keystroke_timing.recorder import KeystrokeTimingRecorder

__all__ = [
    "KeystrokeTimingAccumulator",
    "KeystrokeTimingRecorder",
    "RawKeystrokeTimingMetrics",
    "compute_median_abs_deviation",
]
