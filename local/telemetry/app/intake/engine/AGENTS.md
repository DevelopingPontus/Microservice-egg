# `local/telemetry/app/intake/engine/` Context & Interface Contract

> **Thread-safe in-memory sliding window accumulator (`SlidingWindowBuffer`) maintaining monotonic lifetime counters and recent telemetry slices.**

---

## 1. Scope & Responsibilities

1. **[`window.py`](./window.py) (`SlidingWindowBuffer`)**:
   - Thread-safe volatile accumulator for active telemetry slices (`active_seconds`, `micro_pause_count`, `context_switch_count`, per-process dwell times, and additive IKI sums $N, \sum x, \sum x^2$).
   - Maintains continuous monotonic counters since process startup (lifetime keystrokes, corrections, mouse clicks, scrolls, context switches, active/idle seconds) for Prometheus counters.
   - Maintains a sliding window history of recent committed slices to pool into statistical metrics for real-time SRE gauges.
   - Detects session continuity and resets continuous uptime after extended idle gaps (`session_reset_idle_seconds`).

---

## 2. File Inventory

| File | Primary Exports | Responsibility |
| :--- | :--- | :--- |
| [`window.py`](./window.py) | `SlidingWindowBuffer` | Thread-safe in-memory sliding window buffer and monotonic counter store. |
| [`__init__.py`](./__init__.py) | `SlidingWindowBuffer` | Package facade. |
