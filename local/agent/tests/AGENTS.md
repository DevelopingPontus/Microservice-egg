# `local/agent/tests/` Context & Interface Contract

> **Comprehensive test suite: Hourglass + LCA AST boundary verification, math pooling proof, collector tests, and $\ge 90\%$ coverage quality gate.**

---

## 1. What, Why, When & How

### What (Scope)

This directory houses the automated test suite for `local/agent`. It verifies:

1. **Hourglass + LCA Architecture Boundaries**: AST verification that leaf packages (`intake/collectors`, `intake/engine`, `storage`, `output/dimensions`, `output/api`) only import from themselves or `app.common.*`, and `app/common/` has zero behavioral imports.
2. **Exact Mathematical Pooling**: Equivalence against raw unchunked sample streams within $10^{-9}$.
3. **In-Memory `EpochBuffer`**: Concurrency, pause thresholds, and outlier clamping.
4. **Collectors**: Native and synthetic collector protocols, including strict process name sanitization.
5. **SQLite WAL Storage**: Connection lifecycle, pragmas, and `EpochRepository` CRUD operations.
6. **Scheduler, Chunker, SRE & API**: Monotonic timing, 60s/90s hysteresis block sealing, Prometheus metrics, and `127.0.0.1:8765` FastAPI routes.

---

## 2. Test Execution & Quality Gates

```bash
# Inside local/agent/
.venv/bin/pytest --cov=app --cov-fail-under=90
```

---

## 3. File Inventory

| File | Tested Target | Key Test Cases & Invariants |
| :--- | :--- | :--- |
| [`test_architecture_boundaries.py`](./test_architecture_boundaries.py) | `app/*` AST & `TelemetryService` | Parses Python AST across all leaf packages and `app/common/` to enforce the Hourglass + LCA rule, and verifies `TelemetryService` wiring. |
| [`test_math_pooling.py`](./test_math_pooling.py) | `app.common.models.pool_epoch_metrics` | Proves pooled mean, variance, and CV match raw stream within $10^{-9}$. Tests Shannon entropy $H$, uniform distributions, and reading vs stalled modalities. |
| [`test_buffer.py`](./test_buffer.py) | `app.intake.engine.buffer.EpochBuffer` | Micro-pause detection ($1.0\text{--}5.0\text{s}$), IKI outlier filtering ($>5000\text{ms}$), active seconds clamping, and reset continuity. |
| [`test_collectors.py`](./test_collectors.py) | `app.intake.collectors` | Sanitization regex (strips URLs, window titles, query parameters), synthetic schedule stepping, correction key detection. |
| [`test_storage.py`](./test_storage.py) | `app.storage.database`, `EpochRepository` | WAL mode pragma enforcement, async table initialization, range queries, and JSON dwell serialization. |
| [`test_scheduler_and_service.py`](./test_scheduler_and_service.py) | `app.intake.engine.scheduler`, `app.service` | Monotonic loop execution, tick counts, flush timing, signal trapping, and clean shutdown. |
| [`test_dimensions.py`](./test_dimensions.py) | `app.output.dimensions` | Verifies `DimensionRegistry` Open-Closed extension and all 4 scientific dimensions (Temporal, Attentional, Psychomotor $N \ge 10$ guard, Circadian 30m reset). |
| [`test_chunker_and_sre.py`](./test_chunker_and_sre.py) | `app.intake.engine.chunker`, `app.intake.engine.sre`, `app.storage` | Verifies 60s/90s hysteresis for app switches and zero-input pauses, `activity_blocks` SQLite persistence, SRE status rules, JSON event logs, and Prometheus metrics exposition. |
| [`test_api.py`](./test_api.py) | `app.output.api`, `app.service` | Verifies loopback-only host validation (`127.0.0.1` vs `0.0.0.0` rejection), `/health`, `/metrics`, `/api/v1/status`, `/api/v1/blocks`, and `/api/v1/summary/today`. |
| [`test_config.py`](./test_config.py) | `app.common.config` | Default fallback values and environment variable overrides. |
| [`__init__.py`](./__init__.py) | Test package marker | Package initialization. |
