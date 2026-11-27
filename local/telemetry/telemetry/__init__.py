"""Local privacy-preserving fatigue telemetry package (Phases 1-6)."""

from telemetry.collectors import (
    ActivityTracker,
    KeystrokeCollector,
    MouseCollector,
    WindowFocusCollector,
    hash_app_name,
)
from telemetry.daemon import TelemetryDaemon
from telemetry.db import BatchWriter, init_db, prune_old_data
from telemetry.evaluator import (
    FatigueEvaluation,
    FatigueEvaluator,
    evaluate_once,
    refresh_app_anchors,
)
from telemetry.observability import DaemonObservability
from telemetry.webcam import (
    WebcamOculometricsCollector,
    estimate_rppg_hr_bpm,
    eye_aspect_ratio,
    head_pitch_proxy,
    lid_tightening_ratio,
    mouth_aspect_ratio,
)

__all__ = [
    "ActivityTracker",
    "BatchWriter",
    "FatigueEvaluation",
    "FatigueEvaluator",
    "KeystrokeCollector",
    "MouseCollector",
    "TelemetryDaemon",
    "WebcamOculometricsCollector",
    "WindowFocusCollector",
    "evaluate_once",
    "eye_aspect_ratio",
    "hash_app_name",
    "head_pitch_proxy",
    "init_db",
    "mouth_aspect_ratio",
    "prune_old_data",
]
