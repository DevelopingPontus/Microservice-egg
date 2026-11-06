"""Tests for the localhost FastAPI gateway (127.0.0.1:8765), routes, and loopback invariants."""

import httpx
import pytest
from httpx import ASGITransport

from app.common import DaemonConfig
from app.output.api import (
    PROMETHEUS_CONTENT_TYPE,
    build_uvicorn_config,
    create_uvicorn_server,
    validate_loopback_host,
    validate_port,
)
from app.service import TelemetryService


def test_loopback_host_validation_rejects_non_loopback() -> None:
    """API gateway must strictly reject 0.0.0.0 or public interface bindings."""
    assert validate_loopback_host("127.0.0.1") == "127.0.0.1"
    assert validate_loopback_host("localhost") == "localhost"
    assert validate_loopback_host("::1") == "::1"

    with pytest.raises(ValueError, match="Privacy invariant violation"):
        validate_loopback_host("0.0.0.0")

    with pytest.raises(ValueError, match="Privacy invariant violation"):
        validate_loopback_host("192.168.1.50")


def test_api_port_and_uvicorn_config() -> None:
    """Verify validate_port and build_uvicorn_config enforce loopback and port bounds."""
    config = DaemonConfig(simulate=True, enable_otlp=False)
    service = TelemetryService(config)

    assert service.config.api_host == "127.0.0.1"
    assert service.config.api_port == 8765

    uvi_cfg = build_uvicorn_config(
        service.api_app,
        host=service.config.api_host,
        port=service.config.api_port,
    )
    assert uvi_cfg.host == "127.0.0.1"
    assert uvi_cfg.port == 8765

    uvi_server = create_uvicorn_server(
        service.api_app, host=service.config.api_host, port=service.config.api_port
    )
    assert uvi_server.config.host == "127.0.0.1"

    with pytest.raises(ValueError, match="API port must be between"):
        validate_port(70000)


async def test_health_status_and_prometheus_metrics_endpoints() -> None:
    """Verify /health, /api/v1/status, and /metrics against a live TelemetryService."""
    config = DaemonConfig(simulate=True, enable_otlp=False)
    service = TelemetryService(config)

    transport = ASGITransport(app=service.api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
        # 0. Root URL redirects to /docs (Swagger UI) and /docs returns 200
        root_resp = await client.get("/", follow_redirects=False)
        assert root_resp.status_code == 307
        assert root_resp.headers["location"] == "/docs"
        docs_resp = await client.get("/docs")
        assert docs_resp.status_code == 200

        # 1. /health probe
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200
        health_data = health_resp.json()
        assert health_data["status"] == "ok"
        assert health_data["service"] == "egg-telemetry"
        assert health_data["is_running"] is False
        assert health_data["samples_emitted_total"] == 0

        # 2. /api/v1/status
        status_resp = await client.get("/api/v1/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["status"] == "ok"
        assert status_data["is_running"] is False

        # 3. /metrics Prometheus exposition
        metrics_resp = await client.get("/metrics")
        assert metrics_resp.status_code == 200
        assert metrics_resp.headers["content-type"] == PROMETHEUS_CONTENT_TYPE
        assert "egg_user_duty_cycle_ratio" in metrics_resp.text
