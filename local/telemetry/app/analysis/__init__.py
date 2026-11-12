"""Cognitive Analysis Module (`app/analysis/`).

Combines `strain/` (4-Dimension SRE Health) and `workflow/` (6-Dimension Overview
& Work Categories) into a pure, zero-I/O `CognitiveAnalyzer` producing a `CognitiveState`.
"""

from dataclasses import dataclass

from app.analysis.strain import (
    DEFAULT_DIMENSION_WEIGHTS,
    CognitiveStrainReport,
    DimensionEvaluation,
    clamp_score,
    evaluate_all_dimensions,
    evaluate_attentional,
    evaluate_cognitive_sre_health,
    evaluate_psychomotor,
    evaluate_strain,
    evaluate_temporal,
    evaluate_uptime,
)
from app.analysis.workflow import (
    ALL_WORK_CATEGORIES,
    FocusSessionTracker,
    OverviewDimensionsSnapshot,
    RhythmTracker,
    StatefulOverviewEngine,
    WorkCategoryClassification,
    WorkflowEngine,
    classify_app_category,
    classify_work_category,
    resolve_keystroke_bucket,
    resolve_session_length_bucket,
    resolve_time_block,
)
from app.collector import ActivitySnapshot

__all__ = [
    "ALL_WORK_CATEGORIES",
    "DEFAULT_DIMENSION_WEIGHTS",
    "CognitiveAnalyzer",
    "CognitiveState",
    "CognitiveStrainReport",
    "DimensionEvaluation",
    "FocusSessionTracker",
    "OverviewDimensionsSnapshot",
    "RhythmTracker",
    "StatefulOverviewEngine",
    "WorkCategoryClassification",
    "WorkflowEngine",
    "clamp_score",
    "classify_app_category",
    "classify_work_category",
    "evaluate_all_dimensions",
    "evaluate_attentional",
    "evaluate_cognitive_sre_health",
    "evaluate_psychomotor",
    "evaluate_strain",
    "evaluate_temporal",
    "evaluate_uptime",
    "resolve_keystroke_bucket",
    "resolve_session_length_bucket",
    "resolve_time_block",
]


@dataclass(frozen=True, slots=True)
class CognitiveState:
    """Unified cognitive analysis result combining `strain/` and `workflow/`."""

    evaluations: dict[str, DimensionEvaluation]
    strain: CognitiveStrainReport
    workflow: OverviewDimensionsSnapshot


class CognitiveAnalyzer:
    """Combines `strain/` (4 SRE dimensions) and `workflow/` (6 Overview dimensions)."""

    def __init__(self, *, overview_engine: StatefulOverviewEngine | None = None) -> None:
        self.overview_engine = (
            overview_engine if overview_engine is not None else StatefulOverviewEngine()
        )
        self.last_state: CognitiveState | None = None

    def evaluate(self, snapshot: ActivitySnapshot) -> CognitiveState:
        """Evaluate both `strain/` and `workflow/` pipelines from an ActivitySnapshot."""
        evaluations, strain_report = evaluate_strain(snapshot)
        workflow_snapshot = self.overview_engine.evaluate_tick(
            snapshot.metrics,
            idle_seconds=snapshot.idle_gap_seconds,
            now_timestamp=snapshot.now_timestamp,
            switch_delta=snapshot.deltas.context_switches,
            pauses_gt_2s_delta=snapshot.deltas.pauses_gt_2s,
        )
        state = CognitiveState(
            evaluations=evaluations,
            strain=strain_report,
            workflow=workflow_snapshot,
        )
        self.last_state = state
        return state
