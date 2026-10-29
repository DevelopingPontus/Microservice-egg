# Scoped Rules: `local/agent` (Local Cognitive Telemetry, Chunker & Localhost API)

You are working inside `local/agent/`, the always-on Python background service that runs on the user's computer. It handles:
1. **30s Micro-Epoch Hardware/Window Ingestion** (`app/collectors/`, `app/engine/buffer.py`)
2. **Pluggable Scientific Dimension Engine** (`app/dimensions/`)
3. **60s/90s Hysteresis Activity Block Chunker** (`app/engine/chunker.py`)
4. **Local SQLite WAL Persistence** (`app/storage/` — private telemetry + cached active topic trees from `server/`)
5. **Localhost FastAPI Service (`127.0.0.1:8765`)** (`app/api/` — consumed by `local/ui/`)

## 1. Strict Privacy & Data Locality Invariants

- **Telemetry Never Leaves the Machine**: All `epoch_metrics_30s` and `activity_blocks` rows stay strictly inside the local SQLite database. Never transmit user telemetry to `server/` or any external endpoint.
- **No Raw Ticks in SQLite**: High-frequency keyboard/mouse timestamps and 1Hz window ticks exist **strictly in volatile RAM** (`EpochBuffer`) and are reset every 30 seconds (`EPOCH_DURATION_SEC = 30`).
- **Lossless Algebraic Primitives**: Store only additive and poolable primitives in `epoch_metrics_30s`:
  - `iki_count` ($N$), `iki_sum_ms` ($\sum x$), and `iki_sum_sq_ms` ($\sum x^2$) so downstream queries compute exact pooled variance ($\sigma^2_{\text{pooled}} = \frac{\sum x^2}{N} - \mu^2_{\text{pooled}}$).
  - Filter out pause intervals $> 5000\text{ ms}$ (`MAX_VALID_IKI_MS`) before accumulating IKI sums.
  - Count inter-event gaps in $[1.0\text{ s}, 5.0\text{ s}]$ as `micro_pause_count`.
- **SQLite Concurrency**: Always configure SQLite with `PRAGMA journal_mode = WAL;` and `PRAGMA synchronous = NORMAL;`.

## 2. Protocol-Driven Hardware Decoupling

- All hardware and OS window collectors in `app/collectors/` **must** implement `InputListenerProtocol` and `WindowResolverProtocol`.
- Never import `pynput`, `AppKit`, `Quartz`, `win32gui`, or `Xlib` at module top-level without a fallback; always support `--simulate` mode (`SyntheticInputListener`, `SyntheticWindowResolver`) so tests and Docker containers run headlessly in CI.

## 3. Open-Closed Scientific Dimension Engine (`app/dimensions/`)

- Every scientific dimension must inherit from `BaseDimension` and register with `DimensionRegistry`:
  1. `TemporalDynamicsDimension`: Duty cycle ($T_{\text{active}} / T_{\text{total}}$), continuous focus duration, micro-pause frequency.
  2. `AttentionalFragmentationDimension`: Shannon entropy ($H = -\sum (t_k / T) \ln(t_k / T)$) over merged `dwell_distribution_json`, and context-switch rate per minute.
  3. `PsychomotorMechanicsDimension`: Exact pooled IKI Coefficient of Variation ($CV = \sigma_{\text{pooled}} / \mu_{\text{pooled}}$) and correction ratio ($R_{\text{corr}} = K_{\text{del}} / K_{\text{total}}$).
  4. `CircadianLoadDimension`: Diurnal slotting, post-prandial dip detection ($13:00\text{--}15:00$), and cumulative screen load without a $>30\text{ min}$ reset.

## 4. Activity Block Hysteresis & Localhost API (`app/engine/chunker.py`, `app/api/`)

- **60s / 90s Hysteresis State Machine**:
  - **Transient Excursion ($< 60\text{ s}$)**: Do not split the active `ActivityBlock`; absorb the excursion and increment internal context switches.
  - **Definitive Block Seal ($\ge 90\text{ s}$)**: Seal the current `ActivityBlock`, evaluate all registered dimensions, and write to `activity_blocks`.
- **Localhost Binding**: FastAPI must bind strictly to `127.0.0.1` (`port 8765` by default).
- **Topic Tree Local Cache**: When fetching topic trees from the central `server/` (Spring Boot + Neo4j), cache the user's selected topic tree and personal step completion status locally in SQLite for offline availability and focus-block correlation.
