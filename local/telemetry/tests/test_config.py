"""Unit tests for DaemonConfig."""

import os
from unittest.mock import patch

from app.config import (
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DEFAULT_OTLP_ENDPOINT,
    SLIDING_WINDOW_SECONDS,
    DaemonConfig,
)


def test_daemon_config_defaults() -> None:
    config = DaemonConfig()
    assert config.sliding_window_seconds == SLIDING_WINDOW_SECONDS
    assert config.api_host == DEFAULT_API_HOST
    assert config.api_port == DEFAULT_API_PORT
    assert config.otlp_endpoint == DEFAULT_OTLP_ENDPOINT
    assert config.enable_api is True
    assert config.enable_otlp is True
    assert config.simulate is False


def test_daemon_config_from_env() -> None:
    env = {
        "TELEMETRY_API_HOST": "127.0.0.1",
        "TELEMETRY_API_PORT": "9999",
        "TELEMETRY_ENABLE_API": "0",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:5555",
        "TELEMETRY_ENABLE_OTLP": "false",
    }
    with patch.dict(os.environ, env):
        config = DaemonConfig.from_env(simulate=True)
        assert config.api_port == 9999
        assert config.enable_api is False
        assert config.otlp_endpoint == "http://127.0.0.1:5555"
        assert config.enable_otlp is False
        assert config.simulate is True
