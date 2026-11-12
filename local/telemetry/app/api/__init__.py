"""Localhost HTTP & Prometheus Gateway Module (`app/api/` — `127.0.0.1:8765`).

Provides loopback-validated FastAPI endpoints (`/health`, `/metrics`, `/api/v1/status`,
`/api/v1/state`) and Uvicorn server configuration for `local/ui/` and Prometheus.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import uvicorn
from fastapi import APIRouter, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from app.analysis import CognitiveState
from app.config import DEFAULT_API_HOST, DEFAULT_API_PORT

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
ALLOWED_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
ALLOWED_HOST_HEADERS: tuple[str, ...] = ("127.0.0.1", "localhost", "::1", "testserver")
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


@dataclass(frozen=True, slots=True)
class SchedulerDiagnostics:
    """Privacy-safe operational health metrics for SRE monitoring (/health)."""

    is_running: bool
    samples_emitted_total: int
    window_ticks_total: int
    last_emit_timestamp: float | None


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


class CognitiveStateResponse(BaseModel):
    """Live cognitive strain and workflow focus state returned by /api/v1/state for `local/ui/`."""

    model_config = ConfigDict(extra="forbid")

    overall_strain_score: float = Field(default=0.0)
    sre_status: str = Field(default="nominal")
    dominant_state_label: str = Field(default="idle_baseline")
    sre_alert_reason: str = Field(default="No active telemetry dimensions evaluated.")
    activity: str = Field(default="idle")
    current_focus_app: str = Field(default="idle")
    focus_session_length_seconds: float = Field(default=0.0)
    typing_mode: str = Field(default="inactive")


@runtime_checkable
class TelemetryGatewayBackendProtocol(Protocol):
    """Contract for querying daemon diagnostics, cognitive state, and Prometheus metrics."""

    def get_diagnostics(self) -> SchedulerDiagnostics:
        """Return operational scheduler diagnostics."""

    def render_prometheus_metrics(self) -> str:
        """Render Prometheus text exposition metrics."""

    @property
    def last_state(self) -> CognitiveState | None:
        """Return the most recently evaluated CognitiveState, if available."""


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

    @router.get("/api/v1/state", response_model=CognitiveStateResponse, tags=["cognition"])
    async def get_cognitive_state() -> CognitiveStateResponse:
        """Return the latest cognitive strain and workflow focus state for `local/ui/`."""
        state = getattr(backend, "last_state", None)
        if state is None:
            return CognitiveStateResponse()
        return CognitiveStateResponse(
            overall_strain_score=state.strain.overall_strain_score,
            sre_status=state.strain.sre_status,
            dominant_state_label=state.strain.dominant_state_label,
            sre_alert_reason=state.strain.sre_alert_reason,
            activity=state.workflow.classification.activity,
            current_focus_app=state.workflow.current_focus_app,
            focus_session_length_seconds=state.workflow.focus_session_length_seconds,
            typing_mode=state.workflow.typing_mode,
        )

    return router


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
            "Local-first privacy-by-construction REST gateway serving sliding-window "
            "telemetry, 4-dimension SRE strain scores, and 6-dimension Overview metrics."
        ),
        version="0.2.0",
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(ALLOWED_HOST_HEADERS),
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
