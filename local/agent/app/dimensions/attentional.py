"""Dimension 2: Attentional Fragmentation (Shannon Entropy, Primary Dwell Ratio & Switch Rate)."""

from app.dimensions.base import (
    BaseDimension,
    DimensionContext,
    DimensionEvaluation,
    clamp_score,
)


class AttentionalFragmentationDimension(BaseDimension):
    """Evaluates Shannon entropy H, primary process ratio p_max, and context switches per minute."""

    @property
    def name(self) -> str:
        """Canonical identifier for the Attentional Fragmentation dimension."""
        return "attentional_fragmentation"

    def evaluate(self, context: DimensionContext) -> DimensionEvaluation:
        """Evaluate window-dwell dispersion and context-switch rate across pooled epochs."""
        pooled = context.pooled
        entropy = pooled.shannon_entropy
        primary_ratio = pooled.primary_process_ratio
        switches_per_min = pooled.switches_per_minute
        distinct_processes = len(pooled.merged_dwell_seconds)

        if pooled.total_duration_seconds <= 0.0 or distinct_processes == 0:
            state_label = "idle_unallocated"
            strain_score = 0.0
            blameless_summary = "No active window dwell distribution recorded in this interval."
        elif switches_per_min >= 4.0 or (entropy >= 1.10 and primary_ratio < 0.55):
            state_label = "context_switch_thrashing"
            raw_score = 0.75 + min(0.25, (switches_per_min / 20.0) + max(0.0, entropy - 1.0) * 0.15)
            strain_score = clamp_score(raw_score)
            blameless_summary = (
                f"High window oscillation ({switches_per_min:.1f} switches/min, H={entropy:.2f}) "
                f"across {distinct_processes} tools creates working-memory attention residue."
            )
        elif primary_ratio >= 0.85 and entropy <= 0.45 and switches_per_min < 1.5:
            state_label = "locked_single_app_focus"
            strain_score = clamp_score(0.05 + (1.0 - primary_ratio) * 0.5 + switches_per_min * 0.05)
            blameless_summary = (
                f"Attention anchored in {pooled.primary_process} ({primary_ratio:.0%} dwell share, "
                f"H={entropy:.2f}) with minimal context switching."
            )
        elif primary_ratio >= 0.60 and switches_per_min < 4.0:
            state_label = "structured_multi_tool_flow"
            strain_score = clamp_score(0.25 + entropy * 0.15 + switches_per_min * 0.04)
            blameless_summary = (
                f"Coordinated multi-tool workflow centered on {pooled.primary_process} "
                f"({primary_ratio:.0%} dwell share, {switches_per_min:.1f} switches/min)."
            )
        else:
            state_label = "dispersed_attention"
            strain_score = clamp_score(0.50 + min(0.24, entropy * 0.12 + switches_per_min * 0.03))
            blameless_summary = (
                f"Attention split across {distinct_processes} processes (H={entropy:.2f}, "
                f"primary share {primary_ratio:.0%})—consolidating open windows may reduce load."
            )

        return DimensionEvaluation(
            dimension_name=self.name,
            strain_score=strain_score,
            state_label=state_label,
            metrics={
                "shannon_entropy": round(entropy, 4),
                "primary_process": pooled.primary_process,
                "primary_process_ratio": round(primary_ratio, 4),
                "switches_per_minute": round(switches_per_min, 2),
                "distinct_processes": distinct_processes,
            },
            blameless_summary=blameless_summary,
        )
