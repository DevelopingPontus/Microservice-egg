# `local/agent/app/intake/engine/` Context & Interface Contract

> **30-second `EpochBuffer` accumulator, drift-free monotonic `EpochScheduler`, 60s/90s hysteresis `ActivityBlockChunker`, and SRE Golden Signals.**

---

## 1. Scope & Responsibilities

1. **[`buffer.py`](./buffer.py) (`EpochBuffer`)**: Thread-safe volatile accumulator for 30s micro-epochs (`active_seconds`, `micro_pause_count`, `context_switch_count`, `dwell_distribution_json`, and additive IKI sums $N, \sum x, \sum x^2$).
2. **[`scheduler.py`](./scheduler.py) (`EpochScheduler`)**: Drift-free `time.monotonic()` loop driving 4Hz window polling and 30s SQLite WAL flushes.
3. **[`chunker.py`](./chunker.py) (`ActivityBlockChunker`)**: 60s/90s hysteresis state machine that absorbs brief $<90\text{s}$ app-switch or idle excursions and seals coherent `ActivityBlock` records upon $\ge 90\text{s}$ transitions.
4. **[`sre.py`](./sre.py) (`SREObservabilityRecorder`, `evaluate_sre_health`)**: Evaluates "User-as-a-Server" SRE health (`flow_optimal`, `nominal`, `warning`, `critical`) and renders Prometheus metrics.

---

## 2. File Inventory

| File | Primary Exports | Responsibility |
| :--- | :--- | :--- |
| [`buffer.py`](./buffer.py) | `EpochBuffer` | Thread-safe in-memory 30s accumulator. |
| [`scheduler.py`](./scheduler.py) | `EpochScheduler`, `EpochFlushCallback` | Drift-free monotonic 4Hz poll and 30s flush coordinator. |
| [`chunker.py`](./chunker.py) | `ActivityBlockChunker`, `BlockSealedCallback`, `is_zero_input_epoch` | 60s/90s hysteresis debouncer for cognitive activity blocks. |
| [`sre.py`](./sre.py) | `SREObservabilityRecorder`, `SREHealthReport`, `evaluate_sre_health` | SRE Golden Signals evaluator, structured JSON event logger, and Prometheus metrics. |
| [`__init__.py`](./__init__.py) | Re-exports all engine classes and helpers | Clean package facade. |
