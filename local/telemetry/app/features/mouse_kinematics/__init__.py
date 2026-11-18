"""Mouse Kinematics Feature Package (`app/features/mouse_kinematics/`)."""

from app.features.mouse_kinematics.accumulator import MouseKinematicsAccumulator
from app.features.mouse_kinematics.math import compute_mouse_kinematics, compute_sample_entropy
from app.features.mouse_kinematics.models import RawMouseKinematicsMetrics
from app.features.mouse_kinematics.recorder import MouseKinematicsRecorder

__all__ = [
    "MouseKinematicsAccumulator",
    "MouseKinematicsRecorder",
    "RawMouseKinematicsMetrics",
    "compute_mouse_kinematics",
    "compute_sample_entropy",
]
