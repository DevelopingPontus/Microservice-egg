# Scoped Rules: `local/agent/` (Local Cognitive Telemetry, Chunker & Localhost API)

You are working inside `local/agent/`, the always-on Python 3.12 background service running on the user's device. It powers **Pillar 2 (Time & Flow Management)** and **Pillar 3 (Emotional & Energy Regulation)** of EGG:
1. **30s Micro-Epoch Hardware/Window Ingestion** (`app/collectors/`, `app/engine/buffer.py`)
2. **Local SQLite WAL Persistence & Lossless Pooled Math** (`app/storage/`)
3. **Pluggable 4-Dimension Scientific Engine** (`app/dimensions/`)
4. **60s/90s Hysteresis Activity Block Chunker** (`app/engine/chunker.py`)
5. **Localhost FastAPI Gateway (`127.0.0.1:8765`)** (`app/api/` — consumed by `local/ui/` and caching topic trees from `server/`)

## 1. Python Toolchain & Mandatory Quality Gates (`uv`)

This service standardizes on **`uv`** (`/Users/pontus/.local/bin/uv`).

- **Dependency Management**: Always use `uv add`, `uv add --dev`, and `uv sync` inside `local/agent/`. Never use raw `pip install` or global Python packages.
- **Mandatory Verification Loop**: Before marking any code change or sprint task in `local/agent/` complete, you **MUST** run and pass all three gates from `local/agent/`:
  1. **Lint & Format (`ruff`)**:
     - `uv run ruff check .`
     - `uv run ruff format --check .`
  2. **Strict Static Typing (`mypy`)**:
     - `uv run mypy --strict app tests`
  3. **Automated Tests & Coverage (`pytest`)**:
     - `uv run pytest --cov=app --cov-fail-under=90`

## 2. Strict Privacy, SQLite WAL & Lossless Pooling (`app/storage/`)

- **Telemetry Never Leaves the Machine**: All `epoch_metrics_30s` and `activity_blocks` rows remain strictly inside the local SQLite database.
- **No Raw Ticks in SQLite**: High-frequency keyboard/mouse timestamps and 1Hz window ticks exist **strictly in volatile RAM** (`EpochBuffer`) and are flushed every 30 seconds (`EPOCH_DURATION_SEC = 30`).
- **Lossless Algebraic Primitives**: Store only additive and poolable primitives in `epoch_metrics_30s`:
  - `iki_count` ($N$), `iki_sum_ms` ($\sum x$), and `iki_sum_sq_ms` ($\sum x^2$) so downstream queries compute exact pooled variance ($\sigma^2_{\text{pooled}} = \max(0.0, \frac{\sum x^2}{N} - \mu^2_{\text{pooled}})$).
  - Filter out pause intervals $> 5000\text{ ms}$ (`MAX_VALID_IKI_MS`) before accumulating IKI sums.
  - Count inter-event gaps in $[1.0\text{ s}, 5.0\text{ s}]$ as `micro_pause_count`.
- **SQLite Concurrency**: Always configure connections with `PRAGMA journal_mode = WAL;`, `PRAGMA synchronous = NORMAL;`, `PRAGMA foreign_keys = ON;`, and `PRAGMA busy_timeout = 5000;`.

## 3. Protocol-Driven Hardware Decoupling (`app/collectors/`)

- All hardware and OS window collectors must implement `InputListenerProtocol` and `WindowResolverProtocol`.
- Resolve active windows strictly to sanitized executable or bundle names (e.g., `Code.exe`, `Slack.app`, `firefox`)—never window titles or URLs.
- Never import `pynput`, `AppKit`, `Quartz`, `win32gui`, or `Xlib` at module top-level without a fallback; always support `--simulate` mode (`SyntheticInputListener`, `SyntheticWindowResolver`) for headless CI and Docker execution.

## 4. Pluggable Scientific Dimension Engine (`app/dimensions/`)

Every scientific dimension inherits from `BaseDimension` and registers with `DimensionRegistry`:
1. `TemporalDynamicsDimension`: Duty cycle ($T_{\text{active}} / T_{\text{total}}$), continuous focus duration, micro-pause frequency.
2. `AttentionalFragmentationDimension`: Shannon entropy ($H = -\sum p_k \ln p_k$) over merged `dwell_distribution_json`, and context-switch rate per minute.
3. `PsychomotorMechanicsDimension`: Exact pooled IKI Coefficient of Variation ($CV = \sigma_{\text{pooled}} / \mu_{\text{pooled}}$) and correction ratio ($R_{\text{corr}} = K_{\text{del}} / K_{\text{total}}$).
4. `CircadianLoadDimension`: Diurnal slotting, post-prandial dip detection ($13:00\text{--}15:00$), and cumulative screen load without a $>30\text{ min}$ reset.

## 5. Activity Block Hysteresis & Localhost API (`app/engine/chunker.py`, `app/api/`)

- **60s / 90s Hysteresis State Machine**:
  - **Transient Excursion ($< 60\text{ s}$)**: Absorb brief app checks without splitting the active `ActivityBlock`; increment internal context switches.
  - **Definitive Block Seal ($\ge 90\text{ s}$)**: Seal the current `ActivityBlock`, evaluate all registered dimensions, and write to `activity_blocks`.
- **Localhost Gateway**: Bind FastAPI strictly to `127.0.0.1:8765`. Cache topic trees fetched from `server/` locally in SQLite so the user's active breakdown and step progress work offline.
