"""Localhost FastAPI Gateway (`app/output/api/` — strictly `127.0.0.1:8765`)."""

from app.common.models import DailySummaryPayload
from app.common.protocols import TelemetryGatewayBackendProtocol
from app.output.api.routes import PROMETHEUS_CONTENT_TYPE, build_telemetry_router
from app.output.api.schemas import (
    ActivityBlockListResponse,
    ActivityBlockResponse,
    AgentStatusResponse,
    ChunkerStateResponse,
    DailySummaryResponse,
    DimensionEvaluationResponse,
    HealthCheckResponse,
)
from app.output.api.server import (
    ALLOWED_LOOPBACK_HOSTS,
    DEFAULT_CORS_ORIGINS,
    build_uvicorn_config,
    create_api_app,
    create_uvicorn_server,
    validate_loopback_host,
    validate_port,
)

__all__ = [
    "ALLOWED_LOOPBACK_HOSTS",
    "ActivityBlockListResponse",
    "ActivityBlockResponse",
    "AgentStatusResponse",
    "ChunkerStateResponse",
    "DEFAULT_CORS_ORIGINS",
    "DailySummaryPayload",
    "DailySummaryResponse",
    "DimensionEvaluationResponse",
    "HealthCheckResponse",
    "PROMETHEUS_CONTENT_TYPE",
    "TelemetryGatewayBackendProtocol",
    "build_telemetry_router",
    "build_uvicorn_config",
    "create_api_app",
    "create_uvicorn_server",
    "validate_loopback_host",
    "validate_port",
]
