"""FastAPI routers for health diagnostics, agent status, and Prometheus metrics."""

from fastapi import APIRouter, Response
from fastapi.responses import RedirectResponse

from app.common.protocols import TelemetryGatewayBackendProtocol
from app.output.api.schemas import (
    AgentStatusResponse,
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

    @router.get("/", include_in_schema=False)
    async def redirect_root_to_docs() -> RedirectResponse:
        """Redirect the root URL (http://127.0.0.1:8765/) directly to Swagger UI (/docs)."""
        return RedirectResponse(url="/docs")

    @router.get("/health", response_model=HealthCheckResponse, tags=["observability"])
    async def get_health() -> HealthCheckResponse:
        """Return daemon liveness and sampling status."""
        diag = backend.get_diagnostics()
        return HealthCheckResponse(
            status="ok",
            is_running=diag.is_running,
            samples_emitted_total=diag.samples_emitted_total,
        )

    @router.get("/metrics", tags=["observability"])
    async def get_prometheus_metrics() -> Response:
        """Expose Prometheus text-format telemetry gauges and counters."""
        payload = backend.render_prometheus_metrics()
        return Response(content=payload, media_type=PROMETHEUS_CONTENT_TYPE)

    @router.get("/api/v1/status", response_model=AgentStatusResponse, tags=["status"])
    async def get_agent_status() -> AgentStatusResponse:
        """Return operational diagnostics for the local daemon."""
        diag = backend.get_diagnostics()
        return AgentStatusResponse.from_diagnostics(diag)

    return router
