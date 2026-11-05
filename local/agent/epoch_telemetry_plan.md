# Architecture & Implementation Plan: Epoch-Based Cognitive Telemetry Service

## 1. System Overview & Architectural Boundary

This document outlines the architectural specification and implementation plan for a local-first, privacy-by-construction **Cognitive Telemetry Ingestion Service**.

Instead of storing high-frequency physical event ticks (keystrokes, mouse moves) or pre-computing opinionated high-level session blocks, the system records **30-second micro-epochs** into an asynchronous, WAL-enabled SQLite database.

```text
┌────────────────────────────────────────────────────────┐
│  Hardware Listeners (pynput) & OS Window Poller        │
│  - Captures keydown intervals, correction flags, mouse │
│  - Polls sanitized foreground process name             │
└──────────────────────────┬─────────────────────────────┘
                           │ Ephemeral event ticks (RAM only)
                           ▼
┌────────────────────────────────────────────────────────┐
│  In-Memory 30-Second Epoch Ring Buffer                 │
│  - Accumulates delta timestamps, key counts, dwells    │
│  - Computes epoch primitives (active sec, sum, sum_sq) │
└──────────────────────────┬─────────────────────────────┘
                           │ Flush micro-rollup every 30s (~120 rows/hr)
                           ▼
┌────────────────────────────────────────────────────────┐
│  SQLite Datastore (`telemetry_epochs.db`, WAL Mode)     │
│  - Table: `epoch_metrics_30s`                          │
└──────────────────────────┬─────────────────────────────┘
                           │ Fast range queries (e.g. WHERE start >= ?)
                           ▼
┌────────────────────────────────────────────────────────┐
│  Downstream Consumers (Decoupled Services / APIs)       │
│  - Real-time /status: 5-minute rolling window           │
│  - Activity Block Chunker: 60s/90s debounce state machine│
│  - Daily Summary API: 24-hour circadian & entropy load │
└────────────────────────────────────────────────────────┘
```

---

## 2. Mathematical Preservability & Pooled Aggregation

To allow downstream consumers to compute the 4 scientific dimensions across arbitrary time windows (e.g., 5-minute status, 90-minute blocks, 24-hour daily summaries) without mathematical distortion, each epoch stores aggregate primitives rather than lossy pre-divided averages.

### 2.1. Temporal Dynamics

* **Primitives Stored:**
  * `active_seconds`: Total seconds in the 30-second window where user input occurred.
  * `micro_pause_count`: Number of inter-event gaps between $1.0\text{ s}$ and $5.0\text{ s}$.
  * `mouse_click_count`: Total mouse button clicks in the 30-second window.
  * `scroll_count`: Total scroll wheel / trackpad scroll events in the 30-second window (distinguishes active reading advancement from stalled re-reading or restless cursor fidgeting).
* **Downstream Aggregation ($N$ epochs):**
  $$\text{Duty Cycle} = \frac{\sum_{i=1}^N \text{active\_seconds}_i}{\sum_{i=1}^N \text{total\_epoch\_seconds}_i}$$

### 2.2. Attentional Fragmentation

* **Primitives Stored:**
  * `dwell_distribution_json`: JSON map of `{process_name: dwell_seconds}` for all foreground applications active in the 30-second window.
  * `context_switch_count`: Total foreground application switches during the epoch.
* **Downstream Aggregation ($N$ epochs):**
  1. Merge maps: $T_{proc} = \sum ext{dwell}_{proc}$ across all target epochs.
  2. Total dwell: $T_{total} = \sum T_{proc}$.
  3. Proportions: $p_k = rac{T_{proc_k}}{T_{total}}$.
  4. Shannon Entropy:
     $$H = -\sum_{k} p_k \ln(p_k)$$
  5. Switch Rate:
     $$ ext{Switches Per Minute} = rac{\sum_{i=1}^N ext{context\_switch\_count}_i}{ext{Total Minutes}}$$

### 2.3. Psychomotor Mechanics

* **Primitives Stored:**
  * `total_keystrokes`: Total keydown count ($K_{total}$).
  * `correction_keystrokes`: Count of `Backspace` and `Delete` keys ($K_{del}$).
  * `iki_count`: Number of inter-keystroke intervals observed ($N_{iki}$).
  * `iki_sum_ms`: Sum of all intervals ($\sum IKI$).
  * `iki_sum_sq_ms`: Sum of squared intervals ($\sum IKI^2$).
* **Downstream Aggregation ($N$ epochs):**
  * Correction Ratio:
    $$R_{corr} = rac{\sum K_{del}}{\sum K_{total}}$$
  * Exact Pooled Rhythm Stability ($CV = rac{\sigma}{\mu}$):
    $$\mu_{pooled} = rac{\sum ext{iki\_sum\_ms}}{\sum N_{iki}}$$
    $$\sigma_{pooled}^2 = rac{\sum ext{iki\_sum\_sq\_ms}}{\sum N_{iki}} - (\mu_{pooled})^2$$
    $$CV = rac{\sqrt{\sigma_{pooled}^2}}{\mu_{pooled}}$$

### 2.4. Circadian & Cumulative Load

* **Primitives Stored:**
  * `timestamp_start` & `timestamp_end`: Monotonic / Epoch timestamps.
* **Downstream Evaluation:**
  * Post-Prandial Alertness Dip: Flagged if epoch local hour $\in [13, 15)$.
  * Continuous Load: Sum of contiguous epoch durations where idle gaps between epochs $< 1800 ext{ s}$ (30 minutes).

---

## 3. Database Schema (`telemetry_epochs.db`)

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS epoch_metrics_30s (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_start REAL NOT NULL,           -- Unix epoch timestamp (seconds)
    timestamp_end REAL NOT NULL,             -- Unix epoch timestamp (seconds)
    primary_process TEXT NOT NULL,           -- Process with dominant dwell time in this epoch
    
    -- Temporal Dynamics & Interaction Modality
    active_seconds REAL NOT NULL,            -- Active input seconds in the epoch (0.0 - 30.0)
    micro_pause_count INTEGER NOT NULL,      -- Gaps between 1.0s and 5.0s
    mouse_click_count INTEGER NOT NULL DEFAULT 0, -- Mouse click events in the epoch
    scroll_count INTEGER NOT NULL DEFAULT 0,      -- Scroll events in the epoch (reading progression)
    
    -- Attentional Fragmentation
    context_switch_count INTEGER NOT NULL,   -- Number of process switches
    dwell_distribution_json TEXT NOT NULL,   -- JSON: {"Code.exe": 24.5, "Slack.exe": 5.5}
    
    -- Psychomotor Mechanics (Algebraic Aggregates)
    total_keystrokes INTEGER NOT NULL,       -- Total key presses
    correction_keystrokes INTEGER NOT NULL,  -- Backspace/Delete presses
    iki_count INTEGER NOT NULL,              -- Number of registered IKI samples
    iki_sum_ms REAL NOT NULL,                -- Sum(IKI) for pooled mean
    iki_sum_sq_ms REAL NOT NULL,             -- Sum(IKI^2) for pooled standard deviation
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_epochs_time_range 
ON epoch_metrics_30s(timestamp_start, timestamp_end);
```

---

## 4. Project Directory Layout (`local/agent/`)

```text
local/agent/
├── AGENTS.md                     # Automated AGY agent guardrails & verification rules
├── epoch_telemetry_plan.md       # Service architectural specification (this file)
├── app/
│   ├── __init__.py
│   ├── service.py                # Root supervisor ("I'll say when") & CLI runner
│   ├── common/                   # LCA Crossroads Contracts ("What do you want?")
│   │   ├── __init__.py
│   │   ├── config.py             # Operational constants & DaemonConfig
│   │   ├── models.py             # Shared immutable DTOs & lossless pooling math
│   │   └── protocols.py          # Unified cross-package Protocol interfaces
│   ├── intake/                   # Intake Pillar (Converges raw signals)
│   │   ├── collectors/
│   │   │   ├── __init__.py
│   │   │   ├── input_listener.py # pynput keyboard/mouse hooks + SyntheticInputListener
│   │   │   └── window_resolver.py # Cross-platform active window poller + SyntheticWindowResolver
│   │   └── engine/
│   │       ├── __init__.py
│   │       ├── buffer.py         # In-memory accumulator for current 30s epoch
│   │       ├── scheduler.py      # Periodic 30s timer & database flush coordinator
│   │       ├── chunker.py        # 60s/90s Hysteresis Activity Block Chunker
│   │       └── sre.py            # SRE Golden Signal evaluator & Prometheus metrics recorder
│   ├── storage/                  # Raw Material Store (SQLite WAL)
│   │   ├── __init__.py
│   │   ├── database.py           # SQLite WAL connection & schema (epoch_metrics_30s, activity_blocks)
│   │   └── repository.py         # Async CRUD repository (EpochRepository)
│   └── output/                   # Value Creation Pillar (Branches out from stored data)
│       ├── dimensions/
│       │   ├── __init__.py
│       │   ├── base.py           # BaseDimension & DimensionRegistry
│       │   ├── temporal.py       # Dimension 1: Duty cycle & active reading detection
│       │   ├── attentional.py    # Dimension 2: Shannon entropy & context switch rate
│       │   ├── psychomotor.py    # Dimension 3: Pooled IKI CV & correction ratio
│       │   └── circadian.py      # Dimension 4: Post-prandial dip & cumulative load
│       └── api/
│           ├── __init__.py
│           ├── schemas.py        # Pydantic v2 response models
│           ├── routes.py         # FastAPI routes (/health, /metrics, /api/v1/*)
│           └── server.py         # FastAPI factory & loopback host enforcement (127.0.0.1:8765)
├── tests/
│   ├── test_architecture_boundaries.py # Two-way AST folder isolation verification
│   ├── test_math_pooling.py      # Unit tests for CV & pooled variance correctness
│   ├── test_buffer.py            # Unit tests for epoch aggregation logic
│   ├── test_collectors.py        # Protocol & synthetic collector verification
│   ├── test_storage.py           # SQLite read/write validation
│   ├── test_scheduler_and_service.py # Scheduler & daemon lifecycle tests
│   ├── test_dimensions.py        # 4-Dimension Scientific Engine tests
│   ├── test_chunker_and_sre.py   # 60s/90s hysteresis & SRE Golden Signal tests
│   └── test_api.py               # FastAPI loopback gateway & route tests
├── run_daemon.py                 # Native host OS daemon launcher (--simulate flag supported)
├── pyproject.toml                # Managed by uv (ruff, mypy --strict, pytest, coverage)
├── uv.lock                       # Deterministic dependency lockfile
└── README.md
```

---

## 5. Detailed Component Specifications

### 5.1. `app/common/config.py`

Defines operational constants:

* `EPOCH_DURATION_SECONDS`: `30.0`
* `IDLE_EVENT_THRESHOLD_SECONDS`: `1.5` (Threshold to treat time gap as idle)
* `MICRO_PAUSE_MIN_SECONDS`: `1.0`
* `MICRO_PAUSE_MAX_SECONDS`: `5.0`
* `WINDOW_POLL_INTERVAL_SECONDS`: `0.25`
* `DATABASE_PATH`: `"telemetry_epochs.db"`

### 5.2. `app/common/protocols.py` (LCA Dependency Injection Contracts)

To enable headless execution in Docker containers and Linux CI runners without physical hardware or display servers, all OS-specific collectors adhere to strict Python `typing.Protocol` interfaces:

* `InputListenerProtocol`:
  * `start() -> None`
  * `stop() -> None`
* `WindowResolverProtocol`:
  * `get_active_process_name() -> str`
* Concrete implementations include **Native OS Collectors** (`PynputInputListener`, `NativeWindowResolver`) and **Deterministic/Synthetic Collectors** (`SyntheticInputListener`, `SyntheticWindowResolver`) for automated testing and containerized portfolio demos.

### 5.3. `app/intake/collectors/input_listener.py`

Uses `pynput` with strict privacy invariants:

* **Zero Character Storage:** Does not inspect key characters, codes, or strings.
* **Key Handling:**
  * Checks identity for `keyboard.Key.backspace` and `keyboard.Key.delete`.
  * Computes $\Delta t = \text{now} - \text{last\_press}$. Drops IKI outliers $> 5000\text{ ms}$ (treated as pauses rather than psychomotor intervals).
* **Mouse Handling:**
  * Clicks: Trigger active tick.
  * Movement: Throttled to $4\text{ Hz}$ ($250\text{ ms}$) ticks to avoid filling memory while maintaining continuous active input status.

### 5.4. `app/intake/collectors/window_resolver.py`

Polls active window every $250\text{ ms}$:

* **Sanitization:** Resolves executable file name only (`Code.exe`, `Slack.app`, `chrome`). Strips all window titles, document names, and browser URLs.
* **Platform Implementations:**
  * macOS: `NSWorkspace.sharedWorkspace().frontmostApplication().localizedName()`
  * Windows: `win32gui.GetForegroundWindow()` + `win32process.GetWindowThreadProcessId()` + `psutil.Process(pid).name()`
  * Linux: `Xlib.display` active window property.
  * Headless / Container Fallback: `SyntheticWindowResolver` injected via `WindowResolverProtocol`.

### 5.5. `app/intake/engine/buffer.py` (`EpochBuffer`)

Thread-safe accumulator holding raw ticks for the active 30-second window:

* Methods:
  * `record_key(is_correction: bool, delta_ms: Optional[float])`
  * `record_mouse_activity()`
  * `record_window_tick(process_name: str, duration_sec: float)`
  * `harvest_and_reset(timestamp_start, timestamp_end) -> EpochMetricsDTO`
* Computations on harvest:
  * Calculates `active_seconds` by summing non-idle intervals.
  * Identifies `primary_process` (argmax of dwell times).
  * Serializes `dwell_distribution_json`.
  * Computes `iki_sum_ms` and `iki_sum_sq_ms`.

### 5.6. `app/intake/engine/scheduler.py`

Asynchronous runner:

* Ticks every 30 seconds using monotonic time clocks.
* Calls `harvest_and_reset()` on `EpochBuffer`.
* Dispatches async write to `app/storage/repository.py`.
* Resets state clean for the next epoch window.

---

## 6. DevOps Toolchain & Quality Gates

To ensure production-grade reliability and reproducibility across local development and containerized CI:

* **Package & Environment Management:** Standardized on **`uv`** (`pyproject.toml` + `uv.lock`).
* **Deployment Architecture (Native Host OS Daemon):**
  * **Native Host Execution:** Because hardware keyboard/mouse hooks and OS window servers (`NSWorkspace`/`Quartz`, `win32gui`, `Xlib`) exist on the user's host OS, `local/agent` runs natively as a host background daemon (`uv run python run_daemon.py`) serving `http://127.0.0.1:8765`—not inside a container.
  * **Headless CI & Local Observability:** `--simulate` mode enables deterministic headless CI execution, while the root `docker-compose.yml` runs `prometheus` and `grafana` scraping `host.docker.internal:8765/metrics`.
* **Automated Verification Loop (Required before completing any task):**
  1. **Lint & Format (`ruff`):** `uv run ruff check .` and `uv run ruff format --check .`
  2. **Static Type Checking (`mypy`):** `uv run mypy --strict app tests`
  3. **Test Suite & Coverage (`pytest`):** `uv run pytest --cov=app --cov-fail-under=90`

---

## 7. Phased Implementation Roadmap

### Sprint 0: Repository Foundation & DevOps Guardrails

1. Initialize Git repository, `.gitignore`, and `.agents/rules/project-invariants.md`.
2. Initialize `uv` project (`pyproject.toml`, `uv.lock`) with `ruff`, `mypy`, `pytest`, `pytest-asyncio`, `pytest-cov`, `aiosqlite`, and `pynput`.
3. Verify the empty test/lint/typecheck pipeline runs cleanly.

### Sprint 1: Data Contracts & Storage Foundation (Days 1–2)

1. Set up SQLite schema with WAL mode and time-range indexing (`app/storage/database.py`).
2. Implement `aiosqlite` repository with batch insert functions, DTOs, and range queries (`app/storage/repository.py`).
3. Write unit tests for exact pooled variance, Shannon entropy, and mean math aggregation (`tests/test_math_pooling.py`, `tests/test_storage.py`).

### Sprint 2: Collectors, Protocols & In-Memory Accumulator (Days 3–5)

1. Define `InputListenerProtocol` and `WindowResolverProtocol` in `app/collectors/protocols.py`.
2. Implement `EpochBuffer` with thread-safe accumulator methods and statistical summarization (`app/engine/buffer.py`).
3. Implement zero-text `pynput` listener, cross-platform window resolver, and synthetic/mock collectors (`app/collectors/`).

### Sprint 3: Scheduler, Daemon Supervisor & Containerization (Days 6–7)

1. Wire 30-second async periodic scheduler (`app/engine/scheduler.py`).
2. Implement graceful shutdown handlers (`SIGINT`, `SIGTERM`) ensuring in-flight buffer flush (`app/service.py`, `run_daemon.py`).
3. Add `Dockerfile` for headless verification and synthetic telemetry generation.

---

## 8. Instructions for Agents / Developers

When implementing code for this system:

1. **Never alter the privacy invariant:** Do not introduce logging or fields for key codes, key characters, URL query strings, or document titles.
2. **Never store raw event ticks in SQLite:** All keystroke deltas and mouse coordinates must stay in ephemeral memory within `EpochBuffer` and be aggregated on harvest.
3. **Preserve exact aggregation formulas:** Do not store only standard deviation or mean. Keep `iki_sum_ms`, `iki_sum_sq_ms`, and `iki_count` so downstream queries can calculate pooled variance without loss of precision.
4. **Enforce Protocol DI & Verification Gates:** Always program against `InputListenerProtocol` and `WindowResolverProtocol` so unit tests never require a physical display server, and always run `ruff`, `mypy --strict`, and `pytest` before marking any sprint task complete.
