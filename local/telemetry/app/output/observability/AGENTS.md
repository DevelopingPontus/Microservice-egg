# `local/telemetry/app/output/observability/` Context & Interface Contract

> **OpenTelemetry, Prometheus, Loki, and Tempo observability pipeline for the "User-as-a-Server" SRE platform.**

---

## 1. Scope & Responsibilities

1. **[`metrics.py`](./metrics.py) (`CognitiveMetricsRecorder`)**:
   - Maintains Prometheus counters (lifetime keystrokes, corrections, mouse clicks, scrolls, context switches) and gauges (duty cycle, Shannon entropy, switch rate, correction ratio, IKI CV, continuous session uptime, overall cognitive strain).
   - Registers OpenTelemetry `ObservableGauge` callbacks that dynamically bridge cached metrics into the OTel metric pipeline so Prometheus scrapes from `otel-collector:8889` stream all gauges.
2. **[`otel_setup.py`](./otel_setup.py) (`OTelTelemetryManager`)**:
   - Configures OpenTelemetry `MeterProvider`, `TracerProvider`, and `LoggerProvider`.
   - Attaches `OTLPMetricExporter`, `OTLPSpanExporter`, and `OTLPLogExporter` (over HTTP `:4318/v1/logs`) to push telemetry into the containerized stack.
   - Attaches `LoggingHandler` to Python root/sre loggers.
3. **[`traces.py`](./traces.py) (`FocusSessionTracer`)**:
   - Emits OpenTelemetry distributed trace spans for active application focus intervals and context switches.
4. **[`logs.py`](./logs.py) (`SREEventLogger`)**:
   - Emits structured JSON events (`cognitive_state_tick`, `excursion_absorbed`, `sre_alert`) formatted for Grafana Loki ingestion.
5. **[`evaluator.py`](./evaluator.py) (`evaluate_cognitive_sre_health`)**:
   - Evaluates active dimension strain scores into a composite SRE status (`flow_optimal`, `nominal`, `warning`, `critical`), blameless alert descriptions, and triggered dimensions.

---

## 2. File Inventory

| File | Primary Exports | Responsibility |
| :--- | :--- | :--- |
| [`metrics.py`](./metrics.py) | `CognitiveMetricsRecorder` | OpenTelemetry & Prometheus dual-pipeline metrics recorder. |
| [`otel_setup.py`](./otel_setup.py) | `OTelTelemetryManager` | Lifecycle manager for OpenTelemetry Meter, Tracer, and Logger providers. |
| [`traces.py`](./traces.py) | `FocusSessionTracer` | Context-switch focus span tracing via OpenTelemetry Tracer. |
| [`logs.py`](./logs.py) | `SREEventLogger` | Structured JSON log event emitter for Grafana Loki. |
| [`evaluator.py`](./evaluator.py) | `evaluate_cognitive_sre_health` | Multi-dimension SRE health aggregator and alert debouncer. |
| [`__init__.py`](./__init__.py) | Re-exports all observability classes and helpers | Clean package facade. |
