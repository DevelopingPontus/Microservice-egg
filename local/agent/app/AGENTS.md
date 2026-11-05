# `local/agent/app/` Context & Interface Contract

> **Core Python application package: Hourglass Data Architecture (`intake/` $\rightarrow$ `storage/` $\rightarrow$ `output/`), LCA Crossroads Contracts (`common/`), and Root Supervisor (`service.py`).**

---

## 1. What, Why, When & How

### What (Scope)

This package is the top-level Python application module for `local/agent`. It is structured around the **Hourglass Data Architecture** and the **Lowest Common Ancestor (LCA) "When vs. What" Rule**:

1. **`service.py` ("I'll say WHEN" — Root Supervisor)**: Controls the runtime lifecycle and timing, wiring `intake/` $\rightarrow$ `storage/` $\rightarrow$ `output/`.
2. **`common/` ("What do you want?" — LCA Crossroads Contracts)**: Shared immutable constants (`config.py`), domain value objects and lossless pooling math (`models.py`), and cross-package structural interfaces (`protocols.py`).
3. **`intake/` (Converges Raw Signals)**: Collects anonymous OS/hardware signals (`collectors/`) and accumulates/chunks them into 30s epochs and 60s/90s activity blocks (`engine/`).
4. **`storage/` (The Raw Material Store)**: Persists normalized 30s epochs and sealed activity blocks in local SQLite WAL (`database.py`, `repository.py`).
5. **`output/` (Value Creation Branches)**: Branches out from stored raw material to compute the 4 scientific dimensions (`dimensions/`) and serve the localhost FastAPI + Prometheus gateway (`api/`).

### Why (Rationale)

1. **Self-Documenting Folder Tree**: Opening `app/` immediately communicates how data flows through the system (`intake/` $\rightarrow$ `storage/` $\rightarrow$ `output/`), with shared contracts in `common/` and lifecycle timing in `service.py`.
2. **Clean Dependency Graph**:
   - **Downward ("I'll say when")**: Only `service.py` imports across `intake/`, `storage/`, and `output/`.
   - **Upward ("What do you want?")**: Leaf packages (`intake/collectors`, `intake/engine`, `storage`, `output/dimensions`, `output/api`) import shared types, constants, and protocols from `app/common/` without ever importing sibling packages.
3. **Zero Middleman Boilerplate**: Each leaf package exposes its public API directly through `__init__.py` and worker modules without redundant wrapper classes.

### When (Lifecycle)

- Initialized by `run_daemon.py` when starting `local/agent`.
- Remains alive for the entire duration of the background service.

### How (Mechanics)

- **Startup**:
  1. Resolves configuration from `app.common.config`.
  2. Ensures the SQLite WAL database and schema exist via `EpochRepository.initialize()`.
  3. Instantiates `EpochBuffer` and creates collectors via `create_input_listener` and `create_window_resolver` (using `--simulate` flag if provided).
  4. Launches `EpochScheduler.run()` and concurrent `uvicorn.Server` on `127.0.0.1:8765`.
- **Shutdown**: Intercepts OS signals (`SIGINT`, `SIGTERM`), halts listener hooks, and forces a final `flush_now()` + `flush_active_block()` before closing.

---

## 2. Interface Contract (Hourglass & LCA Architecture)

```mermaid
flowchart TD
    SVC["app/service.py<br/>Root Supervisor ('I'll say WHEN')"]

    subgraph COMMON["app/common/ ('What do you want?' — LCA Contracts)"]
        CFG["config.py"]
        MOD["models.py"]
        PRO["protocols.py"]
    end

    subgraph INTAKE["app/intake/ (Converges Raw Signals)"]
        COL["collectors/<br/>input_listener.py, window_resolver.py"]
        ENG["engine/<br/>buffer.py, scheduler.py, chunker.py, sre.py"]
    end

    subgraph STORAGE["app/storage/ (Raw Material Store)"]
        STO["database.py, repository.py"]
    end

    subgraph OUTPUT["app/output/ (Value Creation Branches)"]
        DIM["dimensions/<br/>base.py, temporal.py, attentional.py, psychomotor.py, circadian.py"]
        API["api/<br/>routes.py, schemas.py, server.py"]
    end

    SVC -->|controls| INTAKE
    SVC -->|controls| STORAGE
    SVC -->|controls| OUTPUT

    INTAKE -.->|imports contracts| COMMON
    STORAGE -.->|imports contracts| COMMON
    OUTPUT -.->|imports contracts| COMMON
```

### Invariants & Safety Guarantees

- **Hourglass + LCA Isolation**: `app/service.py` is the **only** module permitted to import across `intake/`, `storage/`, and `output/`. Leaf packages must never import from each other or from `app/service.py`, and may only import from themselves or upward from `app/common/*`, enforced via AST inspection in `tests/test_architecture_boundaries.py`.
- **No Unpersisted Data on Shutdown**: `TelemetryService` always executes a final `flush_now()` and `flush_active_block()` when stopped.
- **Strict Typing**: All internal modules pass `mypy --strict`.

---

## 3. File & Pillar Inventory

| Path | Role | Primary Exports & Responsibility |
| :--- | :--- | :--- |
| [`service.py`](./service.py) | Root Supervisor (*"Says WHEN"*) | `TelemetryService`, `build_arg_parser`, `run_from_cli`. Wires `intake` $\rightarrow$ `storage` $\rightarrow$ `output` and manages graceful teardown. |
| [`common/`](./common/AGENTS.md) | LCA Crossroads (*"Says WHAT"*) | `DaemonConfig`, `EpochSnapshot`, `ActivityBlockDTO`, `PooledTelemetryMetrics`, `DimensionEvaluation`, `SchedulerDiagnostics`, `DailySummaryPayload`, and shared `Protocol` definitions. |
| [`intake/`](./intake/AGENTS.md) | Intake Pillar | `collectors/` (hardware/window hooks) and `engine/` (30s `EpochBuffer`, `EpochScheduler`, 60s/90s `ActivityBlockChunker`, `SREObservabilityRecorder`). |
| [`storage/`](./storage/AGENTS.md) | Raw Material Store | `EpochRepository`, `init_database`, `get_db_connection`. SQLite WAL persistence (`epoch_metrics_30s`, `activity_blocks`). |
| [`output/`](./output/AGENTS.md) | Value Creation Pillar | `dimensions/` (4-Dimension Scientific Engine) and `api/` (FastAPI `127.0.0.1:8765` + Prometheus `/metrics`). |
| [`__init__.py`](./__init__.py) | Package marker | Package identity. |

---

## 4. Subfolder Routing

- [`common/`](./common/AGENTS.md): Shared configuration, immutable DTOs, lossless pooling math, and structural protocols.
- [`intake/`](./intake/AGENTS.md): Raw signal collection (`collectors/`) and 30s epoch/block accumulation (`engine/`).
- [`storage/`](./storage/AGENTS.md): SQLite WAL persistence (`database.py`, `repository.py`).
- [`output/`](./output/AGENTS.md): Scientific dimension evaluators (`dimensions/`) and localhost HTTP gateway (`api/`).
