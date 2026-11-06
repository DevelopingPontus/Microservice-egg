# `local/telemetry/app/output/` Context & Interface Contract

> **Value Creation Output Pillar: Evaluates the 4 physical SRE dimensions (`dimensions/`), manages the OpenTelemetry/Loki/Tempo export pipeline (`observability/`), and serves localhost HTTP/Prometheus endpoints (`api/`).**

---

## 1. What, Why, When & How

### What (Scope)

`app/output/` is the **Read / Value Creation Pillar** of the Hourglass Architecture. It branches out into three isolated packages:

1. **[`dimensions/`](./dimensions/AGENTS.md)**: The Pluggable 4-Dimension Scientific Engine (`TemporalDynamicsDimension`, `AttentionalFragmentationDimension`, `PsychomotorMechanicsDimension`, `SessionUptimeDimension`) grounded in Dr. Russell A. Barkley's 4 Prefrontal Cortex Executive Circuits.
2. **[`observability/`](./observability/AGENTS.md)**: The OpenTelemetry & SRE export pipeline (`CognitiveMetricsRecorder`, `OTelTelemetryManager`, `FocusSessionTracer`, `SREEventLogger`, `evaluate_cognitive_sre_health`).
3. **[`api/`](./api/AGENTS.md)**: The localhost FastAPI gateway (`127.0.0.1:8765`) serving `/health`, `/metrics`, and `/api/v1/status` to local consumers.

### Why (Rationale)

- **Encapsulation from Intake**: Neither `dimensions/`, `observability/`, nor `api/` knows how raw hardware ticks or window polls are collected. They operate strictly on normalized `app/common/` contracts (`PooledTelemetryMetrics`, `CognitiveStrainReport`, `DimensionEvaluation`, `TelemetryGatewayBackendProtocol`).

---

## 2. Subfolder Routing

- [`dimensions/`](./dimensions/AGENTS.md): Pluggable 4-dimension scientific strain calculators.
- [`observability/`](./observability/AGENTS.md): OpenTelemetry metrics, structured Loki logs, and Tempo focus span traces.
- [`api/`](./api/AGENTS.md): Localhost FastAPI REST & Prometheus gateway (`127.0.0.1:8765`).
