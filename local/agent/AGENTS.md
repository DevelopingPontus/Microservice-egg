# Scoped Rules: `local/agent/` (Local Cognitive Telemetry, Chunker & Localhost API)

You are working inside `local/agent/`, the always-on Python 3.12 background service running on the user's device. It powers **Pillar 2 (Time & Flow Management)** and **Pillar 3 (Emotional & Energy Regulation)** of EGG, organized in the self-documenting **Hourglass + LCA Architecture**:

1. **LCA Crossroads Contracts (`app/common/`)**: Shared immutable configuration (`config.py`), domain DTOs and lossless pooling math (`models.py`), and structural interfaces (`protocols.py`).
2. **Intake Pillar (`app/intake/`)**:
   - **Hardware/Window Collectors (`app/intake/collectors/`)**: Zero-content keyboard/mouse hooks and sanitized foreground window process resolution.
   - **30s Buffer, Scheduler, 60s/90s Chunker & SRE (`app/intake/engine/`)**: Volatile 30s `EpochBuffer`, monotonic `EpochScheduler`, 60s/90s `ActivityBlockChunker`, and `SREObservabilityRecorder`.
3. **Raw Material Store (`app/storage/`)**: Local SQLite WAL persistence (`epoch_metrics_30s`, `activity_blocks`).
4. **Value Creation Output Pillar (`app/output/`)**:
   - **Pluggable 4-Dimension Scientific Engine (`app/output/dimensions/`)**: Temporal, Attentional, Psychomotor, and Circadian evaluators.
   - **Localhost FastAPI Gateway (`app/output/api/` — `127.0.0.1:8765`)**: Consumer-agnostic loopback HTTP and Prometheus metrics provider (`/health`, `/metrics`, `/api/v1/*`).
5. **Root Supervisor (`app/service.py`)**: Controls runtime timing ("I'll say when") and wires `intake/` $\rightarrow$ `storage/` $\rightarrow$ `output/`.

## 1. Python Toolchain & Mandatory Quality Gates (`uv`)

This service standardizes on **`uv`** (`/Users/pontus/.local/bin/uv` or `.venv/bin/`).

- **Dependency Management**: Always use `uv add`, `uv add --dev`, and `uv sync` inside `local/agent/`. Never use raw `pip install` or global Python packages.
- **Mandatory Verification Loop**: Before marking any code change or sprint task in `local/agent/` complete, you **MUST** run and pass all three gates from `local/agent/`:
  1. **Lint & Format (`ruff`)**:
     - `.venv/bin/ruff check .`
     - `.venv/bin/ruff format --check .`
  2. **Strict Static Typing (`mypy`)**:
     - `.venv/bin/mypy --strict app tests run_daemon.py`
  3. **Automated Tests & Coverage (`pytest`)**:
     - `.venv/bin/pytest --cov=app --cov-fail-under=90`

## 2. Strict Privacy, SQLite WAL & Lossless Pooling (`app/storage/`, `app/common/models.py`)

- **Telemetry Never Leaves the Machine**: All `epoch_metrics_30s` and `activity_blocks` rows remain strictly inside the local SQLite database.
- **No Raw Ticks in SQLite**: High-frequency keyboard/mouse timestamps and 4Hz window ticks exist **strictly in volatile RAM** (`EpochBuffer`) and are flushed every 30 seconds (`EPOCH_DURATION_SECONDS = 30.0`).
- **Lossless Algebraic Primitives**: Store only additive and poolable primitives in `epoch_metrics_30s`:
  - `iki_count` ($N$), `iki_sum_ms` ($\sum x$), and `iki_sum_sq_ms` ($\sum x^2$) so downstream queries compute exact pooled variance ($\sigma^2_{\text{pooled}} = \max(0.0, \frac{\sum x^2}{N} - \mu^2_{\text{pooled}})$), guarded by `is_psychomotor_valid` (`iki_count >= 10`).
  - Filter out OS auto-repeat intervals $< 25\text{ ms}$ (`IKI_MIN_OUTLIER_MS`) and pause intervals $> 5000\text{ ms}$ (`IKI_MAX_OUTLIER_MS`) before accumulating IKI sums.
  - Count inter-event gaps in $[1.0\text{ s}, 5.0\text{ s}]$ as `micro_pause_count`, plus `mouse_click_count` and `scroll_count` so downstream dimensions can distinguish active reading progression (scrolling) from stalled re-reading or restless cursor fidgeting.
  - Compute `primary_process_ratio` ($p_{\max} = T_{\text{primary}} / T_{\text{total}}$) alongside Shannon entropy ($H$) over merged `dwell_distribution_json`.
- **SQLite Concurrency**: Always configure connections with `PRAGMA journal_mode = WAL;`, `PRAGMA synchronous = NORMAL;`, `PRAGMA foreign_keys = ON;`, and `PRAGMA busy_timeout = 5000;`.

## 3. Protocol-Driven Hardware Decoupling (`app/intake/collectors/`)

- All hardware and OS window collectors must implement `InputListenerProtocol` and `WindowResolverProtocol` from `app.common.protocols`.
- Resolve active windows strictly to sanitized executable or bundle names (e.g., `Code.exe`, `Slack.app`, `firefox`)—never window titles or URLs.
- Never import `pynput`, `AppKit`, `Quartz`, `win32gui`, or `Xlib` at module top-level without a fallback; always support `--simulate` mode (`SyntheticInputListener`, `SyntheticWindowResolver`) for headless CI.

## 4. Pluggable Scientific Dimension Engine (`app/output/dimensions/`)

Every scientific dimension inherits from `BaseDimension` and registers with `DimensionRegistry`:

1. `TemporalDynamicsDimension`: Duty cycle ($T_{\text{active}} / T_{\text{total}}$), continuous focus duration, micro-pause frequency.
2. `AttentionalFragmentationDimension`: Shannon entropy ($H = -\sum p_k \ln p_k$) over merged `dwell_distribution_json`, and context-switch rate per minute.
3. `PsychomotorMechanicsDimension`: Exact pooled IKI Coefficient of Variation ($CV = \sigma_{\text{pooled}} / \mu_{\text{pooled}}$) and correction ratio ($R_{\text{corr}} = K_{\text{del}} / K_{\text{total}}$).
4. `CircadianLoadDimension`: Diurnal slotting, post-prandial dip detection ($13:00\text{--}15:00$), and cumulative screen load without a $>30\text{ min}$ reset.

## 5. Activity Block Hysteresis, No-Input Tail Cut-Off & Localhost API (`app/intake/engine/chunker.py`, `app/output/api/`)

- **App-Switch Hysteresis & Extended Reading Bridge with No-Input Cut-Off**:
  - **Active App-Switch Excursion ($< 90\text{ s}$ / $\le 2$ epochs)**: Absorb brief app checks without splitting the active `ActivityBlock`; seal on the 3rd epoch ($\ge 90\text{ s}$).
  - **Silent Reading/Thinking Bridge ($\le 120\text{ s}$ / $\le 4$ zero-input epochs)**: Hold up to 4 zero-input epochs in the pending buffer; if input resumes before $150\text{ s}$, absorb them as bridged reading/thinking time.
  - **Definitive No-Input Cut-Off ($\ge 150\text{ s}$ / 5 zero-input epochs)**: Seal the current `ActivityBlock` at the last real input timestamp and retroactively cut off all trailing zero-input epochs from both the sealed block and the daily evaluation collection (`qualify_collected_epochs`).
- **Localhost Gateway**: Bind FastAPI strictly to `127.0.0.1:8765` without assuming or coupling to any specific downstream consumer.

## 6. Hourglass + LCA Folder Isolation & Routing

Every behavioral leaf package under `app/` (`intake/collectors`, `intake/engine`, `storage`, `output/dimensions`, `output/api`) has **zero sibling imports and zero upward service imports**, enforced in CI by [`tests/test_architecture_boundaries.py`](./tests/test_architecture_boundaries.py). Behavioral leaf packages may only import from themselves or upward from [`app/common/`](./app/common/AGENTS.md), and are wired together strictly by [`app/service.py`](./app/service.py):

- **[`app/`](./app/AGENTS.md)**: Root supervisor ([`service.py`](./app/service.py)).
  - [`app/common/`](./app/common/AGENTS.md): LCA Crossroads contracts (`config.py`, `models.py`, `protocols.py`).
  - [`app/intake/`](./app/intake/AGENTS.md): [`collectors/`](./app/intake/collectors/AGENTS.md) and [`engine/`](./app/intake/engine/AGENTS.md).
  - [`app/storage/`](./app/storage/AGENTS.md): SQLite WAL persistence (`database.py`, `repository.py`).
  - [`app/output/`](./app/output/AGENTS.md): [`dimensions/`](./app/output/dimensions/AGENTS.md) and [`api/`](./app/output/api/AGENTS.md).
- **[`tests/`](./tests/AGENTS.md)**: Test suites, AST boundary verification, mathematical pooling proof, and $\ge 90\%$ coverage gate.
