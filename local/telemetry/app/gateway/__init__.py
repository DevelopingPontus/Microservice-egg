"""Gateway package (`app/gateway/`).

Exposes loopback-validated FastAPI HTTP endpoints and Prometheus metrics.
"""

from app.gateway.api import (
    ALLOWED_HOST_HEADERS,
    ALLOWED_LOOPBACK_HOSTS,
    DEFAULT_CORS_ORIGINS,
    PROMETHEUS_CONTENT_TYPE,
    AgentStatusResponse,
    CognitiveStateResponse,
    HealthCheckResponse,
    SchedulerDiagnostics,
    TelemetryGatewayBackendProtocol,
    build_telemetry_router,
    build_uvicorn_config,
    create_api_app,
    create_uvicorn_server,
    validate_loopback_host,
    validate_port,
)

__all__ = [
    "ALLOWED_HOST_HEADERS",
    "ALLOWED_LOOPBACK_HOSTS",
    "DEFAULT_CORS_ORIGINS",
    "PROMETHEUS_CONTENT_TYPE",
    "AgentStatusResponse",
    "CognitiveStateResponse",
    "HealthCheckResponse",
    "SchedulerDiagnostics",
    "TelemetryGatewayBackendProtocol",
    "build_telemetry_router",
    "build_uvicorn_config",
    "create_api_app",
    "create_uvicorn_server",
    "validate_loopback_host",
    "validate_port",
]
