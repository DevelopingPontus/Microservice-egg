"""FastAPI routers for health diagnostics, activity blocks, daily summary, and Prometheus."""

from fastapi import APIRouter, HTTPException, Query, Response

from app.common.protocols import TelemetryGatewayBackendProtocol
from app.output.api.schemas import (
    ActivityBlockListResponse,
    ActivityBlockResponse,
    AgentStatusResponse,
    DailySummaryResponse,
    HealthCheckResponse,
)

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

__all__ = [
    "PROMETHEUS_CONTENT_TYPE",
    "build_telemetry_router",
]


def build_telemetry_router(backend: TelemetryGatewayBackendProtocol) -> APIRouter:
    """Create the FastAPI router bound to the injected TelemetryGatewayBackendProtocol."""
    router = APIRouter()

    @router.get("/health", response_model=HealthCheckResponse, tags=["observability"])
    async def get_health() -> HealthCheckResponse:
        """Return daemon liveness and scheduler status."""
        diag = backend.get_diagnostics()
        return HealthCheckResponse(
            status="ok",
            scheduler_running=diag.is_running,
            epochs_flushed_total=diag.epochs_flushed_total,
        )

    @router.get("/metrics", tags=["observability"])
    async def get_prometheus_metrics() -> Response:
        """Expose Prometheus text-format telemetry gauges and counters."""
        payload = backend.render_prometheus_metrics()
        return Response(content=payload, media_type=PROMETHEUS_CONTENT_TYPE)

    @router.get("/api/v1/status", response_model=AgentStatusResponse, tags=["status"])
    async def get_agent_status() -> AgentStatusResponse:
        """Return detailed scheduler and 60s/90s hysteresis chunker diagnostics."""
        diag = backend.get_diagnostics()
        chunker_state = backend.get_chunker_state()
        return AgentStatusResponse.from_diagnostics(diag, chunker_state)

    @router.get("/api/v1/blocks", response_model=ActivityBlockListResponse, tags=["telemetry"])
    async def get_activity_blocks(
        start: float | None = Query(default=None, description="Start timestamp (epoch seconds)"),
        end: float | None = Query(default=None, description="End timestamp (epoch seconds)"),
        limit: int = Query(default=20, ge=1, le=500, description="Max recent blocks when no range"),
    ) -> ActivityBlockListResponse:
        """Query sealed 60s/90s debounced activity blocks by time range or recent limit."""
        if (start is None) != (end is None):
            raise HTTPException(
                status_code=422,
                detail="Both 'start' and 'end' query parameters must be provided together.",
            )
        if start is not None and end is not None and start > end:
            raise HTTPException(
                status_code=422,
                detail="'start' timestamp must be less than or equal to 'end' timestamp.",
            )

        blocks = await backend.get_activity_blocks(
            start_time=start,
            end_time=end,
            limit=limit,
        )
        items = [ActivityBlockResponse.from_dto(block) for block in blocks]
        return ActivityBlockListResponse(count=len(items), blocks=items)

    @router.get("/api/v1/summary/today", response_model=DailySummaryResponse, tags=["telemetry"])
    async def get_daily_summary(
        reference_timestamp: float | None = Query(
            default=None,
            description="Optional unix timestamp to anchor the local calendar day (for testing).",
        ),
    ) -> DailySummaryResponse:
        """Return today's aggregated 4-dimension cognitive telemetry and SRE Golden Signals."""
        summary_payload = await backend.get_daily_summary(
            reference_timestamp=reference_timestamp,
        )
        return DailySummaryResponse.from_payload(summary_payload)

    return router
