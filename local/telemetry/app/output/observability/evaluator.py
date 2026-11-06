"""DevOps/SRE 'User-as-a-Server' health evaluator across ground-truth dimensions."""

from collections.abc import Mapping

from app.common.config import (
    SRE_CRITICAL_THRESHOLD as DEFAULT_SRE_CRITICAL_THRESHOLD,
)
from app.common.config import (
    SRE_WARNING_THRESHOLD as DEFAULT_SRE_WARNING_THRESHOLD,
)
from app.common.models import CognitiveStrainReport
from app.common.protocols import DimensionEvalProtocol

DEFAULT_DIMENSION_WEIGHTS: dict[str, float] = {
    "temporal_dynamics": 0.30,
    "attentional_fragmentation": 0.30,
    "psychomotor_mechanics": 0.20,
    "session_uptime": 0.20,
}

_EXCLUDED_BASELINE_LABELS: frozenset[str] = frozenset(
    {
        "insufficient_keystroke_sample",
        "idle_recovery",
        "idle_unallocated",
        "session_ramp_up",
    }
)


def evaluate_cognitive_sre_health(
    evaluations: Mapping[str, DimensionEvalProtocol],
    *,
    warning_threshold: float = DEFAULT_SRE_WARNING_THRESHOLD,
    critical_threshold: float = DEFAULT_SRE_CRITICAL_THRESHOLD,
    weights: Mapping[str, float] | None = None,
) -> CognitiveStrainReport:
    """Evaluate dimension outputs into a composite SRE health report."""
    if not evaluations:
        return CognitiveStrainReport(
            overall_strain_score=0.0,
            dominant_state_label="idle_baseline",
            sre_status="nominal",
            sre_alert_reason="No active telemetry dimensions evaluated.",
            triggered_dimensions=(),
            dimension_scores={},
        )

    weight_map = dict(weights) if weights is not None else dict(DEFAULT_DIMENSION_WEIGHTS)
    weighted_sum = 0.0
    active_weight_total = 0.0
    active_evals: list[DimensionEvalProtocol] = []
    scores: dict[str, float] = {}

    for name, eval_res in evaluations.items():
        scores[name] = eval_res.strain_score
        if eval_res.state_label not in _EXCLUDED_BASELINE_LABELS:
            w = weight_map.get(name, 0.25)
            weighted_sum += eval_res.strain_score * w
            active_weight_total += w
            active_evals.append(eval_res)

    overall_strain = (
        min(1.0, max(0.0, round(weighted_sum / active_weight_total, 4)))
        if active_weight_total > 0.0
        else 0.0
    )

    candidate_evals = active_evals if active_evals else list(evaluations.values())
    highest_eval = max(candidate_evals, key=lambda item: item.strain_score)

    critical_dims = [item for item in candidate_evals if item.strain_score >= critical_threshold]
    warning_dims = [item for item in candidate_evals if item.strain_score >= warning_threshold]

    if critical_dims or overall_strain >= critical_threshold:
        triggered = tuple(item.dimension_name for item in critical_dims) or (
            highest_eval.dimension_name,
        )
        triggered_str = ", ".join(triggered)
        reason = f"CRITICAL cognitive strain on {triggered_str}. {highest_eval.blameless_summary}"
        return CognitiveStrainReport(
            overall_strain_score=overall_strain,
            dominant_state_label=highest_eval.state_label,
            sre_status="critical",
            sre_alert_reason=reason,
            triggered_dimensions=triggered,
            dimension_scores=scores,
        )

    if warning_dims or overall_strain >= warning_threshold:
        triggered = tuple(item.dimension_name for item in warning_dims) or (
            highest_eval.dimension_name,
        )
        triggered_str = ", ".join(triggered)
        reason = f"WARNING elevated strain on {triggered_str}. {highest_eval.blameless_summary}"
        return CognitiveStrainReport(
            overall_strain_score=overall_strain,
            dominant_state_label=highest_eval.state_label,
            sre_status="warning",
            sre_alert_reason=reason,
            triggered_dimensions=triggered,
            dimension_scores=scores,
        )

    # Check for flow state
    temporal_eval = evaluations.get("temporal_dynamics")
    attentional_eval = evaluations.get("attentional_fragmentation")
    is_flow = (
        temporal_eval is not None
        and temporal_eval.state_label
        in ("deep_sustained_flow", "active_reading", "active_reading_or_review")
        and (
            attentional_eval is None
            or attentional_eval.state_label
            in (
                "anchored_single_tool_focus",
                "structured_multi_tool_flow",
                "locked_single_app_focus",
            )
        )
        and highest_eval.strain_score < 0.45
    )
    if is_flow and temporal_eval is not None:
        return CognitiveStrainReport(
            overall_strain_score=overall_strain,
            dominant_state_label=temporal_eval.state_label,
            sre_status="flow_optimal",
            sre_alert_reason="All cognitive golden signals nominal; sustained flow state.",
            triggered_dimensions=(),
            dimension_scores=scores,
        )

    return CognitiveStrainReport(
        overall_strain_score=overall_strain,
        dominant_state_label=highest_eval.state_label,
        sre_status="nominal",
        sre_alert_reason="All cognitive golden signals within nominal operating bounds.",
        triggered_dimensions=(),
        dimension_scores=scores,
    )
