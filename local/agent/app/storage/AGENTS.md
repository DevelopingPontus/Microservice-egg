# `local/agent/app/storage/` Context & Interface Contract

> **SQLite WAL persistence, schema management, and lossless mathematical epoch pooling.**

---

## 1. What, Why, When & How

### What (Scope)
This package owns the local persistence boundary and all mathematical pooling routines for telemetry data. It manages:
1. SQLite connection lifecycle and schema initialization (`epoch_metrics_30s`, `activity_blocks`, `cached_topic_trees`).
2. Asynchronous CRUD operations via `EpochRepository` and `aiosqlite`.
3. Lossless algebraic aggregation of $N$ micro-epochs into unified 4-dimension telemetry metrics (`pool_epoch_metrics`).

### Why (Rationale)
1. **100% Local Privacy**: The user's cognitive telemetry never leaves their machine. SQLite WAL on the local disk is the ultimate storage destination.
2. **Lossless Multi-Scale Aggregation**: Different consumers require different time scales (e.g., 30s epochs, 90s activity blocks, 1-hour focus summaries). By storing additive algebraic components ($N$, $\sum x$, $\sum x^2$), downstream queries can pool variance, standard deviation, and CV with zero precision loss and without storing raw time-series data.
3. **High-Concurrency Reads/Writes**: SQLite WAL mode allows concurrent readers (e.g. FastAPI localhost queries from `local/ui`) without blocking the background scheduler write transactions.

### When (Lifecycle)
- **Database Init**: Triggered during service startup by `service.py` to ensure schema tables and indexes exist.
- **Writes**: Invoked every 30 seconds by `EpochScheduler.flush_now()`.
- **Reads & Pooling**: Invoked on-demand by the Activity Block Chunker or FastAPI status endpoints.

### How (Mechanics)
- **WAL Pragmas**: Every connection executes `journal_mode = WAL`, `synchronous = NORMAL`, `foreign_keys = ON`, and `busy_timeout = 5000`.
- **Shannon Entropy Calculation**: Computes $H = -\sum_{k} p_k \ln(p_k)$ over merged process dwell distributions, normalizing fractional dwell times to measure attentional dispersion.
- **Pooled IKI Variance**: Computes exact pooled variance:
  $$\sigma^2_{\text{pooled}} = \max\left(0.0, \frac{\sum x^2}{N} - \mu^2_{\text{pooled}}\right)$$
  Guarded by `is_psychomotor_valid = (N \ge 10)` to prevent noise from small sample sizes.

---

## 2. Interface Contract (Inputs & Outputs)

```mermaid
flowchart LR
    subgraph Inputs["Inbound Calls (Inputs)"]
        SCH["app.engine.scheduler<br/>(EpochMetricsDTO flush)"]
        API["app.api / dimensions<br/>(Time range query)"]
    end

    subgraph Storage["app/storage/"]
        DB["database.py<br/>(aiosqlite + WAL Pragmas)"]
        REPO["repository.py<br/>(EpochRepository)"]
        MATH["pool_epoch_metrics()<br/>(Lossless Math Engine)"]
    end

    subgraph Outputs["Outputs & Returns"]
        SQLITE[("local_agent.db<br/>• epoch_metrics_30s<br/>• activity_blocks<br/>• cached_topic_trees")]
        POOLED["PooledTelemetryMetrics<br/>(Duty cycle, Shannon H, IKI CV)"]
    end

    SCH -->|insert_epoch()| REPO
    API -->|query_epochs_in_range()| REPO
    REPO <--> DB
    DB <--> SQLITE
    REPO -->|epochs Sequence| MATH
    MATH --> POOLED
```

### Inputs (Parameters & Queries)
- `EpochMetricsDTO` instances to persist.
- `(timestamp_start, timestamp_end)` epoch ranges for retrieval.
- SQLite database file path from `app.config.DB_PATH`.

### Outputs (Exported Public API)
- `get_db_connection(db_path) -> aiosqlite.Connection`: Async connection factory with WAL pragmas applied.
- `init_db(db_path)`: Schema migration & index creator.
- `EpochRepository`: Async repository with `insert_epoch`, `query_epochs_in_range`, and `query_latest_epochs`.
- `EpochMetricsDTO`: Immutable representation of a 30s epoch.
- `PooledTelemetryMetrics`: Aggregated metrics across $N$ epochs.
- `pool_epoch_metrics(epochs: Sequence[EpochMetricsDTO]) -> PooledTelemetryMetrics`: Pure mathematical pooling function.
- `compute_shannon_entropy(dwell_seconds: Mapping[str, float]) -> float`: Pure entropy calculation.

### Invariants & Safety Guarantees
- **Atomic Operations**: Ingestion queries use parameterized SQL to prevent injection.
- **Zero Raw Samples**: The database table stores only sum and squared sum, never individual keystroke intervals.
- **Numerical Stability**: Standard deviation and variance calculations are clamped to `0.0` to eliminate floating-point precision underflow.

---

## 3. File Inventory

| File | Primary Exports & Classes | Responsibility |
| :--- | :--- | :--- |
| [`database.py`](./database.py) | `get_db_connection`, `init_db` | Async database connection management, WAL pragma enforcement, and table initialization. |
| [`repository.py`](./repository.py) | `EpochRepository`, `EpochMetricsDTO`, `PooledTelemetryMetrics`, `pool_epoch_metrics`, `compute_shannon_entropy`, `merge_dwell_distributions` | SQLite CRUD operations, DTO specifications, and lossless algebraic metric pooling. |
| [`__init__.py`](./__init__.py) | Re-exports all public storage classes and math functions | Clean entry point for database and pooling utilities. |

---

## 4. Subfolder Routing
*This package has no child subdirectories. It serves persistence requests from [`app/engine/`](../engine/AGENTS.md) and analytical queries from [`app/dimensions/`](../dimensions/AGENTS.md).*
