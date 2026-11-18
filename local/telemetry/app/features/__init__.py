"""Public facade for independent metric dimension features (`app/features/`)."""

from app.features.attention_dwell import (
    AttentionDwellAccumulator,
    AttentionDwellRecorder,
    RawAttentionWindowMetrics,
    compute_shannon_entropy,
)
from app.features.correction_pauses import (
    CorrectionPauseAccumulator,
    CorrectionPauseRecorder,
    RawCorrectionPauseMetrics,
)
from app.features.keystroke_timing import (
    KeystrokeTimingAccumulator,
    KeystrokeTimingRecorder,
    RawKeystrokeTimingMetrics,
    compute_median_abs_deviation,
)
from app.features.mouse_kinematics import (
    MouseKinematicsAccumulator,
    MouseKinematicsRecorder,
    RawMouseKinematicsMetrics,
    compute_mouse_kinematics,
    compute_sample_entropy,
)
from app.features.session_duration import (
    RawTemporalSessionMetrics,
    SessionDurationAccumulator,
    SessionDurationRecorder,
)

__all__ = [
    "AttentionDwellAccumulator",
    "AttentionDwellRecorder",
    "CorrectionPauseAccumulator",
    "CorrectionPauseRecorder",
    "KeystrokeTimingAccumulator",
    "KeystrokeTimingRecorder",
    "MouseKinematicsAccumulator",
    "MouseKinematicsRecorder",
    "RawAttentionWindowMetrics",
    "RawCorrectionPauseMetrics",
    "RawKeystrokeTimingMetrics",
    "RawMouseKinematicsMetrics",
    "RawTemporalSessionMetrics",
    "SessionDurationAccumulator",
    "SessionDurationRecorder",
    "compute_median_abs_deviation",
    "compute_mouse_kinematics",
    "compute_sample_entropy",
    "compute_shannon_entropy",
]
