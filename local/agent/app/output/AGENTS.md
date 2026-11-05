# `local/agent/app/output/` Context & Interface Contract

> **Value Creation Output Pillar: Transforms stored raw material from `app/storage/` into 4-Dimension Scientific Insights (`dimensions/`) and Localhost HTTP/Prometheus Endpoints (`api/`).**

---

## 1. What, Why, When & How

### What (Scope)

`app/output/` is the **Read / Value Creation Pillar** of the Hourglass Architecture. It branches out from the stored raw material into two isolated value-generating packages:

1. **[`dimensions/`](./dimensions/AGENTS.md)**: The Pluggable 4-Dimension Scientific Engine (`TemporalDynamicsDimension`, `AttentionalFragmentationDimension`, `PsychomotorMechanicsDimension`, `CircadianLoadDimension`) grounded in Dr. Russell A. Barkley's 4 Prefrontal Cortex Executive Circuits.
2. **[`api/`](./api/AGENTS.md)**: The localhost FastAPI gateway (`127.0.0.1:8765`) serving `/health`, `/metrics`, `/api/v1/status`, `/api/v1/blocks`, and `/api/v1/summary/today` to `local/ui/` and Prometheus/Grafana.

### Why (Rationale)

- **Encapsulation from Intake**: Neither `dimensions/` nor `api/` knows how raw hardware ticks or window polls are collected. They operate strictly on normalized `app/common/` contracts (`EpochRecordProtocol`, `PooledMetricsProtocol`, `ActivityBlockDTO`, `TelemetryGatewayBackendProtocol`).

---

## 2. Subfolder Routing

- [`dimensions/`](./dimensions/AGENTS.md): Pluggable 4-dimension scientific strain calculators.
- [`api/`](./api/AGENTS.md): Localhost FastAPI REST & Prometheus gateway (`127.0.0.1:8765`).
