# `local/telemetry/app/output/api/` Context & Interface Contract

> **Localhost FastAPI & Prometheus Gateway (`127.0.0.1:8765`): Serves health probes, daemon status, and Prometheus metrics to local clients and Grafana.**

---

## 1. Scope & Loopback Invariant

- **Strict Loopback Binding (`validate_loopback_host`)**: Only `127.0.0.1`, `localhost`, and `::1` are permitted. Attempting to bind to `0.0.0.0` or a non-loopback address raises `ValueError("Privacy invariant violation...")`.
- **LCA Contract Decoupling**: Communicates with the daemon strictly via `TelemetryGatewayBackendProtocol` from `app/common/protocols.py`.

---

## 2. HTTP Endpoints

| Method & Path | Response Schema / Format | Purpose |
| :--- | :--- | :--- |
| `GET /` | Redirect (`307`) | Redirects root to Swagger UI (`/docs`). |
| `GET /health` | `HealthCheckResponse` (`application/json`) | Liveness probe and total sample emission counter. |
| `GET /metrics` | Prometheus text exposition (`text/plain; version=0.0.4`) | Direct Prometheus metrics scrape endpoint (`http://127.0.0.1:8765/metrics`). |
| `GET /api/v1/status` | `AgentStatusResponse` (`application/json`) | Operational diagnostics and sample emission counters. |
| `GET /docs` | Swagger UI (`text/html`) | Interactive OpenAPI API playground. |

---

## 3. File Inventory

| File | Primary Exports | Responsibility |
| :--- | :--- | :--- |
| [`routes.py`](./routes.py) | `build_telemetry_router`, `PROMETHEUS_CONTENT_TYPE` | FastAPI route handlers for `/health`, `/metrics`, and `/api/v1/*`. |
| [`schemas.py`](./schemas.py) | `HealthCheckResponse`, `AgentStatusResponse` | Strict `extra="forbid"` Pydantic v2 response models. |
| [`server.py`](./server.py) | `create_api_app`, `build_uvicorn_config`, `create_uvicorn_server`, `validate_loopback_host`, `validate_port` | FastAPI application factory, CORS configuration, and loopback-validated Uvicorn server builder. |
| [`__init__.py`](./__init__.py) | Re-exports all API functions and schemas | Clean package facade. |
