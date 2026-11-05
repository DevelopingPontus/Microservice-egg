# `local/agent/app/common/` Context & Interface Contract

> **Lowest Common Ancestor (LCA) Crossroads Contracts ("What do you want?"): immutable configuration, domain value objects, lossless pooling math, and structural protocols.**

---

## 1. What, Why, When & How

### What (Scope)

`app/common/` is the **Crossroads Contract** package at the Lowest Common Ancestor of `intake/`, `storage/`, and `output/`. It contains strictly passive, zero-I/O definitions:

1. [`config.py`](./config.py): Immutable operational constants and `DaemonConfig`.
2. [`models.py`](./models.py): Shared immutable value objects (`EpochSnapshot` / `EpochMetricsDTO`, `ActivityBlockDTO` / `SealedActivityBlock`, `PooledTelemetryMetrics`, `DimensionEvaluation`, `SchedulerDiagnostics`, `DailySummaryPayload`) and pure lossless pooling math (`pool_epoch_metrics`, `compute_shannon_entropy`).
3. [`protocols.py`](./protocols.py): Structural `typing.Protocol` contracts (`InputTickSinkProtocol`, `InputListenerProtocol`, `WindowResolverProtocol`, `EpochPersistenceProtocol`, `ActivityBlockPersistenceProtocol`, `BlockEvaluatorProtocol`, `TelemetryGatewayBackendProtocol`).

### Why (Rationale)

- **"Upward = What do you want?"**: Multiple sibling packages (`intake/collectors`, `intake/engine`, `storage`, `output/dimensions`, `output/api`) operate on the same domain concepts (`EpochSnapshot`, `ActivityBlockDTO`, `PooledTelemetryMetrics`). Defining those shapes and protocols once at their Lowest Common Ancestor (`app/common/`) eliminates mirror-type duplication while keeping zero behavioral coupling between siblings.
- **Zero Side Effects**: Because `app/common/` contains zero I/O and is forbidden from importing `intake/`, `storage/`, `output/`, or `service.py`, importing from `app/common/` never pulls in external side effects or circular dependencies.

---

## 2. File Inventory

| File | Primary Exports | Responsibility |
| :--- | :--- | :--- |
| [`config.py`](./config.py) | `DaemonConfig`, `EPOCH_DURATION_SECONDS`, `WINDOW_POLL_INTERVAL_SECONDS`, `DEFAULT_DATABASE_PATH`, `HYSTERESIS_*`, `SRE_*`, `DEFAULT_API_*` | Immutable system constants and environment configuration. |
| [`models.py`](./models.py) | `EpochSnapshot`, `EpochMetricsDTO`, `ActivityBlockDTO`, `SealedActivityBlock`, `PooledTelemetryMetrics`, `DimensionEvaluation`, `SchedulerDiagnostics`, `DailySummaryPayload`, `pool_epoch_metrics` | Shared immutable domain DTOs and lossless algebraic pooling math. |
| [`protocols.py`](./protocols.py) | `InputTickSinkProtocol`, `InputListenerProtocol`, `WindowResolverProtocol`, `EpochPersistenceProtocol`, `ActivityBlockPersistenceProtocol`, `BlockEvaluatorProtocol`, `TelemetryGatewayBackendProtocol` | Cross-package structural `Protocol` contracts. |
| [`__init__.py`](./__init__.py) | Re-exports all `config`, `models`, and `protocols` symbols | Clean package entry point. |
