"""Pydantic v2 response schemas for the localhost FastAPI gateway (`127.0.0.1:8765`)."""

from pydantic import BaseModel, ConfigDict, Field

from app.common.models import SchedulerDiagnostics

__all__ = [
    "AgentStatusResponse",
    "HealthCheckResponse",
]


class HealthCheckResponse(BaseModel):
    """Minimal operational health probe response for /health."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="Service liveness status ('ok').")
    service: str = Field(default="egg-telemetry", description="Service identifier.")
    is_running: bool = Field(description="Whether the telemetry daemon loop is active.")
    samples_emitted_total: int = Field(description="Total telemetry ticks emitted.")


class AgentStatusResponse(BaseModel):
    """Daemon and SRE pipeline status returned by /api/v1/status."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="ok")
    is_running: bool
    samples_emitted_total: int
    window_ticks_total: int
    last_emit_timestamp: float | None

    @classmethod
    def from_diagnostics(cls, diagnostics: SchedulerDiagnostics) -> "AgentStatusResponse":
        """Build an AgentStatusResponse from SchedulerDiagnostics."""
        return cls(
            status="ok",
            is_running=diagnostics.is_running,
            samples_emitted_total=diagnostics.samples_emitted_total,
            window_ticks_total=diagnostics.window_ticks_total,
            last_emit_timestamp=diagnostics.last_emit_timestamp,
        )
