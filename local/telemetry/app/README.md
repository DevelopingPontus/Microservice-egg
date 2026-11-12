# `local/telemetry/app` — Standalone Cognitive Telemetry Daemon

Lightweight Python 3.12 cognitive telemetry daemon that runs **standalone without Docker**. It samples 60-second hardware and window activity (`collector/`), evaluates the pure cognitive strain and workflow pipelines (`analysis/`), emits **universal OpenTelemetry (OTLP) and Prometheus signals** (`exporters/`), and serves the localhost REST gateway on `127.0.0.1:8765` (`api/`).

> For the full containerized SRE observability suite (Grafana, Prometheus, Loki, Tempo, OTel Collector), see [`../README.md`](../README.md) (`uv run run.py`).

---

## 1. Run Standalone

From `local/telemetry/`:

```bash
# Run with live OS input/window hooks (serves http://127.0.0.1:8765)
uv run python -m app

# Run with deterministic synthetic telemetry (headless / CI / no OS permissions)
uv run python -m app --simulate

# Run purely in-memory without OTLP network export (ideal when developing local/ui/)
uv run python -m app --simulate --no-otlp
```

---

## 2. Localhost Endpoints (`127.0.0.1:8765`)

| Endpoint | Description |
| :--- | :--- |
| `http://127.0.0.1:8765/docs` | Interactive Swagger OpenAPI explorer |
| `http://127.0.0.1:8765/health` | Liveness and sampling health probe |
| `http://127.0.0.1:8765/metrics` | Universal Prometheus text-format metrics (`egg_user_*`, `egg_overview_*`) |
| `http://127.0.0.1:8765/api/v1/status` | Scheduler diagnostics (`samples_emitted_total`, `window_ticks_total`) |
| `http://127.0.0.1:8765/api/v1/state` | Live cognitive strain & workflow focus state consumed by `local/ui/` |

---

## 3. One-Way Internal Pipeline

`app/` is organized into 4 internal packages connected in a strict one-way pipeline (`config` $\rightarrow$ `collector` $\rightarrow$ `analysis` $\rightarrow$ `exporters` / `api` $\rightarrow$ `service`):

1. **`collector/`**: Combines `input_hook.py`, `window_probe.py`, and `sliding_window.py` into `ActivityCollector` $\rightarrow$ outputs `ActivitySnapshot`.
2. **`analysis/`**: Pure functional core (zero I/O) combining `strain/` (4 SRE dimensions) and `workflow/` (6 Overview dimensions & work categories) into `CognitiveAnalyzer` $\rightarrow$ outputs `CognitiveState`.
3. **`exporters/`**: Universal OpenTelemetry (`otel.py`, `metrics.py`, `logs.py`, `traces.py`) & Prometheus emitter (`TelemetryExporter.publish()`).
4. **`api/`**: Loopback-validated (`127.0.0.1`) FastAPI gateway (`create_api_app`, `create_uvicorn_server`).
