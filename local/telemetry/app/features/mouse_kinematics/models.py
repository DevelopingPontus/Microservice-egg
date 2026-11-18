"""Data models for mouse kinematics metrics."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RawMouseKinematicsMetrics:
    """Independent raw mouse kinematics metrics in native units (no scoring)."""

    sample_entropy: float = 0.0
    submovements: int = 0
    curvature_auc: float = 0.0
    x_flips: int = 0
    mouse_clicks: int = 0
    scroll_events: int = 0
