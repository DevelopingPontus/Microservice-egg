# `local/agent/tests/` Context & Interface Contract

> **Comprehensive test suite: Math pooling verification, collector tests, and ≥90% coverage quality gate.**

---

## 1. What, Why, When & How

### What (Scope)

This directory houses the entire automated test suite for `local/agent`. It tests:

1. Exact mathematical pooling equivalence against raw unchunked sample streams.
2. In-memory `EpochBuffer` concurrency, pause thresholds, and outlier clamping.
3. Native and synthetic collector protocols, including strict process name sanitization.
4. Async SQLite WAL connection lifecycle, pragmas, and repository CRUD operations.
5. `EpochScheduler` timing accuracy and `TelemetryAgentService` graceful shutdown handling.

### Why (Rationale)

1. **Mathematical Invariant Proof**: Proves that storing aggregated primitives ($N$, $\sum x$, $\sum x^2$) yields results identical (within $10^{-9}$ epsilon) to processing an uncompressed raw data stream.
2. **Privacy Assurance**: Validates that no keystroke content or prohibited window metadata escapes into the buffer or database.
3. **Continuous Enforcement**: Forms Gate 3 of the mandatory CI quality loop (`pytest --cov=app --cov-fail-under=90`).

### When (Lifecycle)

- Executed on every pull request via GitHub Actions (`ci-local-agent.yml`).
- Executed locally via `uv run pytest --cov=app --cov-fail-under=90` before committing changes.

### How (Mechanics)

- Built on `pytest` and `pytest-asyncio`.
- Uses deterministic synthetic fixtures (`SyntheticInputListener`, `SyntheticWindowResolver`) to run headless without hardware dependencies.
- Uses temporary in-memory or `/tmp` SQLite databases (`aiosqlite`) to isolate storage tests.

---

## 2. Test Execution & Quality Gates

```bash
# Inside local/agent/
uv run pytest --cov=app --cov-fail-under=90
```

### Invariants & Requirements

- **Headless Only**: Tests must **never** invoke real OS windowing hooks or listen on physical keyboards during test runs.
- **Coverage Floor**: Branch and line coverage across `app/` must remain **$\ge 90\%$** at all times.
- **Floating-Point Verification**: Float assertions must use `pytest.approx(..., rel=1e-9, abs=1e-9)`.

---

## 3. File Inventory

| File | Tested Target | Key Test Cases & Invariants |
| :--- | :--- | :--- |
| [`test_architecture_boundaries.py`](./test_architecture_boundaries.py) | `app/*` AST & Folder Orchestrators | Parses Python AST across all `app/<subfolder>/*.py` files to enforce zero upward or sibling imports, and verifies `CollectorCoordinator`, `EngineOrchestrator`, `StorageOrchestrator`, and `DimensionRegistry` wiring. |
| [`test_math_pooling.py`](./test_math_pooling.py) | `app.storage.repository.pool_epoch_metrics` | Proves pooled mean, variance, and CV match raw stream within $10^{-9}$. Tests Shannon entropy $H$, uniform distributions, and reading vs stalled modalities. |
| [`test_buffer.py`](./test_buffer.py) | `app.engine.buffer.EpochBuffer` | Micro-pause detection ($1.0\text{--}5.0\text{s}$), IKI outlier filtering ($>5000\text{ms}$), active seconds clamping, thread safety under concurrent writes. |
| [`test_collectors.py`](./test_collectors.py) | `app.collectors` | Sanitization regex (strips URLs, window titles, query parameters), synthetic schedule stepping, correction key detection. |
| [`test_storage.py`](./test_storage.py) | `app.storage.database`, `EpochRepository` | WAL mode pragma enforcement, async table initialization, range queries, and JSON dwell serialization. |
| [`test_scheduler_and_service.py`](./test_scheduler_and_service.py) | `app.engine.scheduler`, `app.service` | Monotonic loop execution, tick counts, flush timing, signal trapping, and clean shutdown. |
| [`test_dimensions.py`](./test_dimensions.py) | `app.dimensions` | Verifies `DimensionRegistry` Open-Closed extension and all 4 scientific dimensions (Temporal, Attentional, Psychomotor $N \ge 10$ guard, Circadian 30m reset). |
| [`test_config.py`](./test_config.py) | `app.config` | Default fallback values and environment variable overrides. |
| [`__init__.py`](./__init__.py) | Test package marker | Package initialization. |

---

## 4. Subfolder Routing

*This package has no child subdirectories. It imports and verifies all code across [`../app/`](../app/AGENTS.md).*
