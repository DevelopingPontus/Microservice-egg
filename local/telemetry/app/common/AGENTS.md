# `local/telemetry/app/common/` Context & Interface Contract

> **Lowest Common Ancestor (LCA) Crossroads Contracts ("What do you want?"): immutable configuration, domain value objects, statistical pooling math, and structural protocols.**

---

## 1. What, Why, When & How

### What (Scope)

`app/common/` is the **Crossroads Contract** package at the Lowest Common Ancestor of `intake/` and `output/`. It contains strictly passive, zero-I/O definitions:

1. [`config.py`](./config.py): Immutable operational constants and `DaemonConfig`.
2. [`models.py`](./models.py): Shared immutable value objects (`TelemetrySample`, `PooledTelemetryMetrics`, `DimensionEvaluation`, `CognitiveStrainReport`, `SchedulerDiagnostics`) and pure statistical math (`pool_telemetry_samples`, `compute_shannon_entropy`, `merge_dwell_distributions`).
3. [`protocols.py`](./protocols.py): Structural `typing.Protocol` contracts (`InputTickSinkProtocol`, `InputListenerProtocol`, `SyntheticBurstEmitterProtocol`, `WindowResolverProtocol`, `DimensionProtocol`, `DimensionEvalProtocol`, `TelemetryGatewayBackendProtocol`).

### Why (Rationale)

- **"Upward = What do you want?"**: Multiple leaf packages (`intake/collectors`, `intake/engine`, `output/dimensions`, `output/observability`, `output/api`) operate on the same domain concepts (`PooledTelemetryMetrics`, `CognitiveStrainReport`). Defining those shapes and protocols once at their Lowest Common Ancestor (`app/common/`) eliminates mirror-type duplication while keeping zero behavioral coupling between siblings.
- **Zero Side Effects**: Because `app/common/` contains zero I/O and is forbidden from importing `intake/`, `output/`, or `service.py`, importing from `app/common/` never pulls in external side effects or circular dependencies.

---

## 2. File Inventory

| File | Primary Exports | Responsibility |
| :--- | :--- | :--- |
| [`config.py`](./config.py) | `DaemonConfig`, `SLIDING_WINDOW_SECONDS`, `WINDOW_POLL_INTERVAL_SECONDS`, `DEFAULT_API_PORT`, `SRE_*` | Immutable system constants and environment configuration. |
| [`models.py`](./models.py) | `TelemetrySample`, `PooledTelemetryMetrics`, `DimensionEvaluation`, `CognitiveStrainReport`, `SchedulerDiagnostics`, `pool_telemetry_samples` | Shared immutable domain DTOs and statistical pooling math. |
| [`protocols.py`](./protocols.py) | `InputTickSinkProtocol`, `InputListenerProtocol`, `SyntheticBurstEmitterProtocol`, `WindowResolverProtocol`, `DimensionProtocol`, `DimensionEvalProtocol`, `TelemetryGatewayBackendProtocol` | Cross-package structural `Protocol` contracts. |
| [`__init__.py`](./__init__.py) | Re-exports all `config`, `models`, and `protocols` symbols | Clean package entry point. |
