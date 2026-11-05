# `local/agent/app/storage/` Context & Interface Contract

> **Raw Material Store (The Waist of the Hourglass): SQLite WAL persistence (`epoch_metrics_30s`, `activity_blocks`) and lossless epoch pooling.**

---

## 1. What, Why, When & How

### What (Scope)

`app/storage/` is the **Raw Material Store** at the center of the Hourglass Architecture:

1. **SQLite WAL Initialization (`database.py`)**: Configures `PRAGMA journal_mode = WAL;`, `PRAGMA synchronous = NORMAL;`, `PRAGMA foreign_keys = ON;`, and `PRAGMA busy_timeout = 5000;`, and initializes `epoch_metrics_30s` and `activity_blocks`.
2. **Async Repository (`repository.py` — `EpochRepository`)**: Provides async CRUD and time-range queries for 30s epochs and sealed activity blocks, plus `pool_epochs()` delegating to the lossless algebraic pooling math in `app/common/models.py`.

### Why (Rationale)

- **Decoupling Intake from Output**: Intake (`app/intake/`) writes normalized raw material into `app/storage/`. Output branches (`app/output/dimensions/`, `app/output/api/`) read from `app/storage/` without needing to know how raw signals were collected.
- **Zero Middleman Pass-Through**: `EpochRepository` directly exposes `initialize()`, `pool_epochs()`, and all CRUD methods without a redundant wrapper class.

---

## 2. File Inventory

| File | Primary Exports | Responsibility |
| :--- | :--- | :--- |
| [`database.py`](./database.py) | `SCHEMA_SQL`, `configure_connection`, `get_db_connection`, `init_database` | Async SQLite WAL connection management and DDL schema initialization. |
| [`repository.py`](./repository.py) | `EpochRepository`, `pool_epoch_metrics`, `compute_shannon_entropy`, `merge_dwell_distributions` | Async CRUD operations for `epoch_metrics_30s` and `activity_blocks` + lossless pooling convenience methods. |
| [`__init__.py`](./__init__.py) | Re-exports `EpochRepository`, `init_database`, and pooling utilities | Clean package facade. |
