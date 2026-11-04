# `local/agent/app/` Context & Interface Contract

> **Core Python application package: Service lifecycle supervisor, configuration, and domain orchestration.**

---

## 1. What, Why, When & How

### What (Scope)
This package is the top-level Python application module for `local/agent`. It wires together the collectors, the accumulation engine, SQLite storage, scientific dimensions, and localhost API into an orchestrated, resilient daemon.

### Why (Rationale)
1. **Centralized Configuration**: Ensures all operational constants (polling rates, thresholds, database paths, pause intervals) are defined in a single immutable configuration file ([`config.py`](./config.py)) and validated via environment variables.
2. **Deterministic Lifecycle & Graceful Shutdown**: `service.py` provides a unified supervisor managing startup order (DB initialization $\rightarrow$ collectors hook $\rightarrow$ scheduler loop) and graceful shutdown (`SIGINT`/`SIGTERM`), guaranteeing in-flight buffer flushes so no telemetry is lost on exit.

### When (Lifecycle)
- Initialized by `run_daemon.py` when starting `local/agent`.
- Remains alive for the entire duration of the background service.

### How (Mechanics)
- **Startup**:
  1. Resolves configuration from `app.config`.
  2. Ensures the SQLite WAL database and schema exist via `app.storage.init_db()`.
  3. Instantiates `EpochBuffer` and creates appropriate collectors via `create_input_listener` and `create_window_resolver` (using `--simulate` flag if provided).
  4. Launches `EpochScheduler.run()`.
- **Shutdown**: Intercepts OS signals (`SIGINT`, `SIGTERM`), halts listener hooks, and forces a final `EpochScheduler.flush_now()` before closing database handles.

---

## 2. Interface Contract (Inputs & Outputs)

```mermaid
flowchart TD
    CLI["run_daemon.py (--simulate, --db)"] --> SVC["app.service.TelemetryAgentService"]
    CFG["app.config"] --> SVC

    subgraph Subpackages["app/ Subpackages"]
        COL["collectors/ (Input & Window)"]
        ENG["engine/ (Buffer & Scheduler)"]
        STO["storage/ (SQLite WAL & Math)"]
        DIM["dimensions/ (Scientific Engine)"]
        API["api/ (FastAPI 127.0.0.1:8765)"]
    end

    SVC --> STO
    SVC --> ENG
    SVC --> COL
    SVC --> DIM
    SVC --> API
```

### Inputs
- CLI flags (`--simulate`, `--db-path`, `--epoch-duration`) forwarded from `run_daemon.py`.
- Environment variables (`EGG_DB_PATH`, `EGG_SIMULATE`).

### Outputs (Exported Public API)
- `TelemetryAgentService`: Lifecycle supervisor with `start()`, `stop()`, and `run()`.
- Configuration constants in `app.config`.

### Invariants & Safety Guarantees
- **No Unpersisted Data on Shutdown**: `TelemetryAgentService` must always execute a final synchronous/awaited `flush_now()` when stopped.
- **Strict Typing**: All internal modules must pass `mypy --strict`.

---

## 3. File Inventory

| File | Primary Exports & Classes | Responsibility |
| :--- | :--- | :--- |
| [`config.py`](./config.py) | `EPOCH_DURATION_SECONDS`, `WINDOW_POLL_INTERVAL_SECONDS`, `DB_PATH`, `IKI_MAX_OUTLIER_MS`, `MICRO_PAUSE_*` | Centralized system constants and environment configuration. |
| [`service.py`](./service.py) | `TelemetryAgentService` | Daemon lifecycle manager coordinating storage initialization, collector attachment, scheduler execution, and graceful teardown. |
| [`__init__.py`](./__init__.py) | `__version__`, re-exports | Package identity. |

---

## 4. Subfolder Routing (Child Packages)

Each subfolder has its own dedicated `AGENTS.md` interface contract:

- [`collectors/`](./collectors/AGENTS.md): Hardware keyboard/mouse hooks and frontmost window resolver (Protocol-driven).
- [`engine/`](./engine/AGENTS.md): 30s `EpochBuffer`, monotonic `EpochScheduler`, and activity chunking.
- [`storage/`](./storage/AGENTS.md): SQLite WAL persistence (`aiosqlite`) and lossless algebraic pooling math ($N, \sum x, \sum x^2$).
- [`dimensions/`](./dimensions/AGENTS.md): Pluggable 4-dimension scientific engine (Temporal, Attentional, Psychomotor, Circadian).
- [`api/`](./api/AGENTS.md): Localhost FastAPI gateway (`127.0.0.1:8765`) serving `local/ui`.
