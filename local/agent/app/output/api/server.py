"""Loopback-validated FastAPI application and Uvicorn ASGI server builder (`127.0.0.1:8765`)."""

from collections.abc import Sequence

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.common.config import DEFAULT_API_HOST, DEFAULT_API_PORT
from app.common.protocols import TelemetryGatewayBackendProtocol
from app.output.api.routes import build_telemetry_router

ALLOWED_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8765",
    "http://localhost:8765",
)

__all__ = [
    "ALLOWED_LOOPBACK_HOSTS",
    "DEFAULT_CORS_ORIGINS",
    "build_uvicorn_config",
    "create_api_app",
    "create_uvicorn_server",
    "validate_loopback_host",
    "validate_port",
]


def validate_loopback_host(host: str) -> str:
    """Enforce that the API gateway binds strictly to a loopback interface (never 0.0.0.0)."""
    cleaned = host.strip()
    if cleaned not in ALLOWED_LOOPBACK_HOSTS:
        allowed_str = sorted(ALLOWED_LOOPBACK_HOSTS)
        raise ValueError(
            f"Privacy invariant violation: API host '{host}' is not a loopback address "
            f"{allowed_str}. Binding to 0.0.0.0 or public interfaces is forbidden."
        )
    return cleaned


def validate_port(port: int) -> int:
    """Enforce that the TCP port is within valid [1, 65535] bounds."""
    if not (1 <= port <= 65535):
        raise ValueError("API port must be between 1 and 65535")
    return port


def create_api_app(
    backend: TelemetryGatewayBackendProtocol,
    *,
    cors_origins: Sequence[str] = DEFAULT_CORS_ORIGINS,
) -> FastAPI:
    """Construct the FastAPI application wired to TelemetryGatewayBackendProtocol."""
    app = FastAPI(
        title="EGG Local Cognitive Telemetry Gateway",
        description=(
            "Local-first privacy-by-construction REST gateway serving 60s/90s debounced "
            "activity blocks, 4-dimension cognitive strain scores, and SRE Golden Signals."
        ),
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(build_telemetry_router(backend))
    return app


def build_uvicorn_config(
    app: FastAPI,
    *,
    host: str = DEFAULT_API_HOST,
    port: int = DEFAULT_API_PORT,
) -> uvicorn.Config:
    """Create a Uvicorn configuration bound strictly to the validated loopback host/port."""
    validated_host = validate_loopback_host(host)
    validated_port = validate_port(port)
    return uvicorn.Config(
        app=app,
        host=validated_host,
        port=validated_port,
        log_level="warning",
        access_log=False,
    )


def create_uvicorn_server(
    app: FastAPI,
    *,
    host: str = DEFAULT_API_HOST,
    port: int = DEFAULT_API_PORT,
) -> uvicorn.Server:
    """Instantiate a uvicorn.Server bound strictly to the validated loopback config."""
    return uvicorn.Server(build_uvicorn_config(app, host=host, port=port))
