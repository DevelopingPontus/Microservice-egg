"""Pydantic v2 response schemas for the localhost FastAPI gateway (`127.0.0.1:8765`)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.common.models import (
    ActivityBlockDTO,
    DailySummaryPayload,
    DimensionEvaluation,
    SchedulerDiagnostics,
)

__all__ = [
    "ActivityBlockListResponse",
    "ActivityBlockResponse",
    "AgentStatusResponse",
    "ChunkerStateResponse",
    "DailySummaryResponse",
    "DimensionEvaluationResponse",
    "HealthCheckResponse",
]


class HealthCheckResponse(BaseModel):
    """Minimal operational health probe response for /health."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="Service liveness status ('ok').")
    service: str = Field(default="egg-local-agent", description="Service identifier.")
    scheduler_running: bool = Field(description="Whether the 30s monotonic scheduler is running.")
    epochs_flushed_total: int = Field(description="Total 30s epochs persisted since startup.")


class ChunkerStateResponse(BaseModel):
    """Real-time state of the 60s/90s Hysteresis Activity Block Chunker."""

    model_config = ConfigDict(extra="forbid")

    active_primary_process: str | None = Field(
        description="Sanitized executable/bundle of the currently open activity block, if any."
    )
    active_epoch_count: int = Field(description="Committed 30s epochs in the current work block.")
    pending_excursion_epoch_count: int = Field(
        description="Uncommitted excursion epochs held inside the 60s hysteresis buffer."
    )
    blocks_sealed_total: int = Field(description="Total activity blocks sealed since startup.")
    excursions_absorbed_total: int = Field(
        description="Total transient (<90s) excursions absorbed without fragmenting flow."
    )


class AgentStatusResponse(BaseModel):
    """Comprehensive daemon and SRE pipeline status returned by /api/v1/status."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="ok")
    is_running: bool
    epochs_flushed_total: int
    window_ticks_total: int
    last_flush_duration_ms: float
    last_flush_timestamp: float | None
    chunker: ChunkerStateResponse

    @classmethod
    def from_diagnostics(
        cls,
        diagnostics: SchedulerDiagnostics,
        chunker_state: dict[str, Any],
    ) -> "AgentStatusResponse":
        """Build an AgentStatusResponse from SchedulerDiagnostics and chunker counters."""
        return cls(
            status="ok",
            is_running=diagnostics.is_running,
            epochs_flushed_total=diagnostics.epochs_flushed_total,
            window_ticks_total=diagnostics.window_ticks_total,
            last_flush_duration_ms=diagnostics.last_flush_duration_ms,
            last_flush_timestamp=diagnostics.last_flush_timestamp,
            chunker=ChunkerStateResponse(
                active_primary_process=chunker_state.get("active_primary_process"),
                active_epoch_count=int(chunker_state.get("active_epoch_count", 0)),
                pending_excursion_epoch_count=int(
                    chunker_state.get("pending_excursion_epoch_count", 0)
                ),
                blocks_sealed_total=int(chunker_state.get("blocks_sealed_total", 0)),
                excursions_absorbed_total=int(chunker_state.get("excursions_absorbed_total", 0)),
            ),
        )


class DimensionEvaluationResponse(BaseModel):
    """Evaluated scientific dimension payload."""

    model_config = ConfigDict(extra="forbid")

    dimension_name: str
    strain_score: float
    state_label: str
    metrics: dict[str, float | int | str | bool]
    blameless_summary: str

    @classmethod
    def from_dto(cls, evaluation: DimensionEvaluation) -> "DimensionEvaluationResponse":
        """Convert a DimensionEvaluation value object into its API response schema."""
        return cls(
            dimension_name=evaluation.dimension_name,
            strain_score=evaluation.strain_score,
            state_label=evaluation.state_label,
            metrics=dict(evaluation.metrics),
            blameless_summary=evaluation.blameless_summary,
        )


class ActivityBlockResponse(BaseModel):
    """Serialized representation of a sealed 60s/90s debounced cognitive ActivityBlock."""

    model_config = ConfigDict(extra="forbid")

    id: int | None
    start_time: float
    end_time: float
    duration_seconds: float
    primary_process: str
    epoch_count: int
    duty_cycle: float
    shannon_entropy: float
    switches_per_minute: float
    iki_cv: float
    correction_ratio: float
    overall_strain_score: float
    dominant_state_label: str
    sre_status: str
    sre_alert_reason: str
    dimensions: dict[str, Any]

    @classmethod
    def from_dto(cls, block: ActivityBlockDTO) -> "ActivityBlockResponse":
        """Convert an ActivityBlockDTO into an ActivityBlockResponse."""
        return cls(
            id=block.id,
            start_time=block.start_time,
            end_time=block.end_time,
            duration_seconds=block.duration_seconds,
            primary_process=block.primary_process,
            epoch_count=block.epoch_count,
            duty_cycle=block.duty_cycle,
            shannon_entropy=block.shannon_entropy,
            switches_per_minute=block.switches_per_minute,
            iki_cv=block.iki_cv,
            correction_ratio=block.correction_ratio,
            overall_strain_score=block.overall_strain_score,
            dominant_state_label=block.dominant_state_label,
            sre_status=block.sre_status,
            sre_alert_reason=block.sre_alert_reason,
            dimensions=block.parsed_dimensions(),
        )


class ActivityBlockListResponse(BaseModel):
    """Paginated/bounded list of sealed activity blocks."""

    model_config = ConfigDict(extra="forbid")

    count: int
    blocks: list[ActivityBlockResponse]


class DailySummaryResponse(BaseModel):
    """Daily aggregated cognitive telemetry and SRE 'User-as-a-Server' health summary."""

    model_config = ConfigDict(extra="forbid")

    day_start_timestamp: float
    day_end_timestamp: float
    epochs_count: int
    blocks_count: int
    excursions_absorbed_total: int
    total_duration_seconds: float
    total_active_seconds: float
    verified_work_seconds: float = 0.0
    bridged_reading_seconds: float = 0.0
    estimated_work_seconds: float = 0.0
    discarded_idle_seconds: float = 0.0
    executive_fuel_remaining: float = 1.0
    duty_cycle: float
    primary_process: str
    primary_process_ratio: float
    shannon_entropy: float
    switches_per_minute: float
    total_keystrokes: int
    correction_ratio: float
    iki_cv: float
    is_psychomotor_valid: bool
    overall_strain_score: float
    dominant_state_label: str
    sre_status: str
    sre_alert_reason: str
    triggered_dimensions: list[str]
    sre_status_breakdown: dict[str, int]
    dimensions: dict[str, DimensionEvaluationResponse]

    @classmethod
    def from_payload(cls, payload: DailySummaryPayload) -> "DailySummaryResponse":
        """Convert a DailySummaryPayload into a DailySummaryResponse."""
        pooled = payload.pooled_metrics
        tank = payload.fuel_tank
        return cls(
            day_start_timestamp=payload.day_start_timestamp,
            day_end_timestamp=payload.day_end_timestamp,
            epochs_count=payload.epochs_count,
            blocks_count=payload.blocks_count,
            excursions_absorbed_total=payload.excursions_absorbed_total,
            total_duration_seconds=round(pooled.total_duration_seconds, 4),
            total_active_seconds=round(pooled.total_active_seconds, 4),
            verified_work_seconds=tank.verified_work_seconds if tank is not None else 0.0,
            bridged_reading_seconds=tank.bridged_reading_seconds if tank is not None else 0.0,
            estimated_work_seconds=tank.estimated_work_seconds if tank is not None else 0.0,
            discarded_idle_seconds=tank.discarded_idle_seconds if tank is not None else 0.0,
            executive_fuel_remaining=tank.executive_fuel_remaining if tank is not None else 1.0,
            duty_cycle=round(pooled.duty_cycle, 4),
            primary_process=pooled.primary_process,
            primary_process_ratio=round(pooled.primary_process_ratio, 4),
            shannon_entropy=round(pooled.shannon_entropy, 4),
            switches_per_minute=round(pooled.switches_per_minute, 4),
            total_keystrokes=pooled.total_keystrokes,
            correction_ratio=round(pooled.correction_ratio, 4),
            iki_cv=round(pooled.iki_cv, 4),
            is_psychomotor_valid=pooled.is_psychomotor_valid,
            overall_strain_score=payload.overall_strain_score,
            dominant_state_label=payload.dominant_state_label,
            sre_status=payload.sre_status,
            sre_alert_reason=payload.sre_alert_reason,
            triggered_dimensions=list(payload.triggered_dimensions),
            sre_status_breakdown=dict(payload.sre_status_breakdown),
            dimensions={
                name: DimensionEvaluationResponse.from_dto(eval_dto)
                for name, eval_dto in payload.dimensions.items()
            },
        )
