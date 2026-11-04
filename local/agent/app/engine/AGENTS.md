# `local/agent/app/engine/` Context & Interface Contract

> **Thread-safe in-memory 30s epoch accumulation, drift-free monotonic scheduling, and activity chunking.**

---

## 1. What, Why, When & How

### What (Scope)

This package is the core execution coordination engine of `local/agent`. It provides:

1. Thread-safe in-memory accumulation of high-frequency input and window dwell ticks over 30-second windows.
2. Drift-free monotonic event loop coordination for 4Hz window polling and periodic SQLite WAL flushes.
3. Activity block debouncing and segmentation across 60s/90s cognitive boundaries (Phase 2).

### Why (Rationale)

1. **Zero Raw Ticks in SQLite**: Storing raw millisecond timestamps or continuous 4Hz polls in SQLite would cause disk I/O thrashing and unbounded WAL growth. Accumulating in volatile RAM (`EpochBuffer`) and snapshotting every 30 seconds ensures constant $\mathcal{O}(1)$ storage footprint.
2. **Drift-Free Timing**: Standard `asyncio.sleep()` or wall-clock timers drift significantly under system load. `EpochScheduler` uses monotonic clock tracking (`time.monotonic()`) to ensure exact scheduling intervals.
3. **Lossless Metric Capture**: Computes additive mathematical primitives ($N$, $\sum x$, $\sum x^2$) in memory so downstream callers can compute exact pooled statistics across arbitrary intervals without retaining individual raw samples.

### When (Lifecycle)

- **EpochBuffer**: Continuously accepts asynchronous event callbacks from `app.collectors`.
- **EpochScheduler**: Runs as the primary async event loop while `local/agent` daemon is alive, orchestrating polling every 250ms and flushing every 30s.

### How (Mechanics)

- **Thread Synchronization**: `EpochBuffer` wraps all metric updates in a `threading.Lock` because OS input listeners fire on separate threads.
- **Micro-Pause Tracking**: Gaps between consecutive user inputs in the range $[1.0\text{s}, 5.0\text{s}]$ increment `micro_pause_count`. Gaps $> 5.0\text{s}$ are classified as idle and excluded from active dwell time.
- **Dwell Time Accumulation**: Tracks elapsed seconds per sanitized process name. Resolves the dominant application as `primary_process`.
- **Atomic Harvest**: On flush, `harvest_and_reset()` compiles an immutable `EpochMetricsDTO`, resets all accumulators to zero, preserves process continuity, and hands the DTO to `EpochRepository.insert_epoch()`.

---

## 2. Interface Contract (Inputs & Outputs)

```mermaid
flowchart LR
    subgraph Inputs["Inbound Ticks (Inputs)"]
        COL["app.collectors<br/>(Keyboard, Mouse, Window)"]
        CFG["app.config<br/>(EPOCH_DURATION, INTERVALS)"]
    end

    subgraph Engine["app/engine/"]
        BUF["EpochBuffer<br/>(Volatile RAM Accumulator)"]
        SCH["EpochScheduler<br/>(Monotonic Loop Coordinator)"]
    end

    subgraph Outputs["Downstream Targets (Outputs)"]
        REPO["app.storage.repository.EpochRepository<br/>• insert_epoch(EpochMetricsDTO)"]
        DIAG["SchedulerDiagnostics<br/>• /health endpoint & telemetry"]
    end

    COL -->|Ticks & Events| BUF
    CFG --> SCH
    SCH -->|Triggers harvest_and_reset()| BUF
    SCH -->|Persists DTO| REPO
    SCH -->|Emits Health State| DIAG
```

### Inputs (Parameters & Inbound Signals)

- Anonymous input ticks (`record_key`, `record_mouse_*`, `record_window_tick`) from `app.collectors`.
- Configuration constants (`EPOCH_DURATION_SECONDS`, `WINDOW_POLL_INTERVAL_SECONDS`) from `app.config`.
- `EpochRepository` instance for database persistence.
- Optional async `on_epoch_flushed` callback for event subscription (e.g. Activity Block Chunker).

### Outputs (Exported Public API)

- `EngineOrchestrator`: Folder orchestrator coordinating `EpochBuffer` and `EpochScheduler`.
- `EpochBuffer`: Thread-safe volatile accumulator.
- `EpochScheduler`: Async coordinator running `run()` and `flush_now()`.
- `EpochSnapshot`: Self-contained immutable 30s epoch snapshot harvested by `EpochBuffer`.
- `SchedulerDiagnostics`: Immutable health snapshot (`is_running`, `epochs_flushed_total`, `last_flush_duration_ms`).
- `EpochFlushCallback`, `EpochPersistenceProtocol`, `WindowSourceProtocol`, `InputLifecycleProtocol`, `SyntheticBurstSourceProtocol`: Structural contracts for external dependencies injected from `app/service.py`.

### Invariants & Safety Guarantees

- **Zero Upward or Sibling Imports**: `app/engine/` must **never** import from `app.config`, `app.service`, `app.collectors`, `app.storage`, `app.dimensions`, or `app.api`. All external collaborators are typed via structural protocols in [`protocols.py`](./protocols.py).
- **Thread Safety**: All writes to `EpochBuffer` must acquire `_lock`.
- **Active Time Clamping**: `active_seconds` can never exceed the total epoch duration (`timestamp_end - timestamp_start`).
- **Clean Signal Shutdown**: `EpochScheduler.request_stop()` cleanly finishes the active tick and flushes remaining buffer contents before terminating.

---

## 3. File Inventory

| File | Primary Exports & Classes | Responsibility |
| :--- | :--- | :--- |
| [`orchestrator.py`](./orchestrator.py) | `EngineOrchestrator` | Folder orchestrator wiring `EpochBuffer` and `EpochScheduler` into a unified engine interface. |
| [`protocols.py`](./protocols.py) | `EpochSnapshot`, `EpochPersistenceProtocol`, `WindowSourceProtocol`, `InputLifecycleProtocol`, `SyntheticBurstSourceProtocol` | Self-contained snapshot model, default constants, and structural protocols for injected collaborators. |
| [`buffer.py`](./buffer.py) | `EpochBuffer` | Thread-safe in-memory ring accumulator collecting input gaps, IKI sums, and dwell distributions over 30s. |
| [`scheduler.py`](./scheduler.py) | `EpochScheduler`, `SchedulerDiagnostics`, `EpochFlushCallback` | Monotonic asyncio loop running 4Hz window polls, 30s flushes, and SRE health monitoring. |
| [`__init__.py`](./__init__.py) | Re-exports `EngineOrchestrator`, buffer, scheduler, and protocols | Clean public interface for the `engine` package. |

---

## 4. Subfolder Routing

*This package has no child subdirectories. It delegates persistence to sibling [`app/storage/`](../storage/AGENTS.md) and consumes hardware events from [`app/collectors/`](../collectors/AGENTS.md).*
