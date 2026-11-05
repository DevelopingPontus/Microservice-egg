# `local/agent` — Local Cognitive Telemetry & Loopback Gateway

A standalone, privacy-by-construction Python 3.12 daemon that passively samples hardware interaction timing and foreground application switches in 30-second micro-epochs, persists qualified telemetry to a local SQLite WAL database, evaluates 4 cognitive load dimensions (**Gauges**) alongside cumulative capacity reservoirs (**Fuel Tanks**), and exposes read-only JSON and Prometheus endpoints strictly on `127.0.0.1:8765`.

This module is completely decoupled from any downstream consumer: it has zero knowledge of what reads its loopback HTTP endpoints or scrapes its metrics.

---

## 1. Core Guarantees & Privacy Invariants

1. **Zero Content Capture**: The collector layer never inspects, buffers, logs, or persists key characters, key codes, scancodes, mouse coordinates, clipboard contents, window titles, file names, or URLs.
2. **Sanitized Process Basenames Only**: Active windows are resolved strictly to executable or bundle basenames (e.g., `Code.exe`, `Firefox.app`, `Terminal.app`). Window titles, paths, and query parameters are stripped in memory before accumulation.
3. **100% Local Persistence**: All SQLite WAL files (`epoch_metrics_30s` and `activity_blocks`) remain on the local filesystem. The daemon makes zero outbound network requests.
4. **Strict Loopback Binding (`127.0.0.1`)**: The embedded HTTP server validates its host binding at startup and rejects `0.0.0.0` or non-loopback network interfaces.
5. **Headless & Deterministic Simulation (`--simulate`)**: Runs deterministically without a physical display (`$DISPLAY`), OS accessibility hooks, or input hardware when invoked with `--simulate`.

---

## 2. Architecture: Hourglass Data Flow & LCA Crossroads

The package is structured around the **Hourglass + Lowest Common Ancestor (LCA) Crossroads** pattern:

- **Downward Control ("I'll say when")**: [`app/service.py`](./app/service.py) (`TelemetryService`) is the single root supervisor that controls runtime scheduling and wires intake, storage, and output branches together.
- **Upward Contracts ("What do you want?")**: [`app/common/`](./app/common/) holds shared immutable configuration (`config.py`), pure domain DTOs and pooling/qualification math (`models.py`), and structural `Protocol` definitions (`protocols.py`).
- **Zero Sibling Behavioral Imports**: Leaf packages under `intake/`, `storage/`, and `output/` never import from sibling leaf packages or from `service.py` (enforced via AST inspection in `tests/test_architecture_boundaries.py`).

```text
local/agent/
├── run_daemon.py                  # CLI entry point
├── pyproject.toml                 # Python 3.12 + uv project & strict tool gates
├── app/
│   ├── service.py                 # Root supervisor ("I'll say when")
│   ├── common/                    # LCA Crossroads ("What do you want?")
│   │   ├── config.py              # Operational & Well-Guard constants, DaemonConfig
│   │   ├── models.py              # Immutable DTOs, Well-Guard qualification & pooling math
│   │   └── protocols.py           # Structural interfaces across intake, storage, output
│   ├── intake/                    # Converges raw OS signals into debounced blocks
│   │   ├── collectors/            # Zero-text input listener & window process resolver
│   │   └── engine/                # 30s EpochBuffer, EpochScheduler, Chunker & SRE recorder
│   ├── storage/                   # Raw Material Store (SQLite WAL)
│   │   ├── database.py            # Async SQLite connection & WAL pragma initialization
│   │   └── repository.py          # CRUD & range queries for epochs and activity blocks
│   └── output/                    # Value Creation Branches
│       ├── dimensions/            # 4 pluggable scientific dimension evaluators
│       └── api/                   # Loopback FastAPI server & Pydantic v2 schemas
└── tests/                         # Unit, integration, math-equivalence & AST boundary tests
```

---

## 3. Data Qualification ("Well-Guard"), Gauges & Fuel Tanks

To prevent idle desktop hours, off-computer conversations, laptop sleep gaps, or OS key-repeat floods from contaminating insights, data is positively qualified before evaluation:

### Signal Hygiene at Intake

- **Human Psychomotor IKI Band (`25.0 ms <= IKI <= 5000.0 ms`)**: Key-press intervals under `25 ms` (OS auto-repeat floods from holding a key) and over `5000 ms` (long thinking pauses) are excluded from Inter-Keystroke Interval (`IKI`) variance accumulation.
- **OS Sleep / Lid-Close Clamp (`1.5x` Epoch Span)**: If the OS sleeps mid-epoch, `EpochScheduler.flush_now()` clamps the epoch start timestamp so a multi-hour sleep remains a true chronological recovery gap rather than a multi-hour epoch.
- **Non-Work Process Filtering**: System and lock-screen identifiers (`idle`, `unknown`, `loginwindow.app`, `screensaverengine.app`, `lockapp.exe`) are stripped when merging process dwell distributions so they never inflate Shannon entropy ($H$).
- **Minimum Rate Denominator (`15.0 s`)**: Short partial epochs (such as shutdown flushes) use a minimum `15.0 s` rate denominator so a single event in a 1-second flush is never extrapolated into a 60/minute rate spike.

### The 3-Zone Progression Anchor Rule (Keep vs. Cut Off)

1. **Zone 1 — Verified Engaged Epochs (Keep)**: Any 30-second epoch with at least one physical progression signal (`active_seconds > 0`, `total_keystrokes > 0`, `scroll_count > 0`, `mouse_click_count > 0`, or `context_switch_count > 0` in a work process) is kept as a hard fact.
2. **Zone 2 — Bounded Reading/Thinking Bridge (`<= 120s` / 4 Epochs, Keep if Anchored)**: Up to 4 consecutive zero-input epochs (`120 s`) inside an active work block are held in a pending buffer. If the user resumes Zone 1 input before `150 s`, the silent pause is absorbed into the block as bridged reading/thinking time.
3. **Zone 3 — Unanchored Silence (`>= 150s` / 5 Epochs, Cut Off)**: When 5 consecutive zero-input epochs (`150 s`) occur, the chunker seals the active block at the timestamp of the **last real input** and **retroactively cuts off all 5 silent epochs** from both the sealed block and the daily evaluation collection.

### Instantaneous Gauges vs. Cumulative Fuel Tanks

- **The 4 Gauges (Evaluated strictly over qualified Zone 1 + Zone 2 epochs)**:
  1. `temporal_dynamics` (**Utilization**): Duty cycle ($T_{\text{active}} / T_{\text{total}}$), micro-pauses/min, and active reading detection (steady scrolling with low keystrokes).
  2. `attentional_fragmentation` (**Saturation / Thrashing**): Shannon entropy ($H = -\sum p_k \ln p_k$), primary process dwell ratio ($p_{\max}$), and context switches per minute.
  3. `psychomotor_mechanics` (**Error Rate / Jitter**): Exact pooled IKI Coefficient of Variation ($CV = \sigma / \mu$) and backspace/delete correction ratio. Automatically excluded from composite strain when `iki_count < 10`.
  4. `circadian_load` (**Uptime & Diurnal Phase**): Continuous active load since the last $\ge 30\text{ min}$ recovery gap, post-prandial trough ($13:00\text{--}15:00$), and late-night window ($22:00\text{--}06:00$).
- **The Fuel Tanks & Factual Floor (`FuelTankStatus`)**:
  - `verified_work_seconds`: Hard factual floor summed strictly across Zone 1 physical-input epochs.
  - `bridged_reading_seconds`: Bounded silent reading/thinking bridges ($\le 120\text{ s}$) anchored between Zone 1 inputs.
  - `estimated_work_seconds`: `verified_work_seconds + bridged_reading_seconds`.
  - `discarded_idle_seconds`: Unanchored zero-input time cut off from gauges.
  - `executive_fuel_remaining` (`[0.0, 1.0]`): Starts at `1.0` (`100%`), drains during engaged epochs scaled by interaction strain, partially refills on breaks $\ge 5\text{ min}$, and resets to `1.0` after $\ge 30\text{ min}$ off-screen recovery.

---

## 4. Installation & Running the Daemon

All dependencies and virtual environments are managed with [`uv`](https://docs.astral.sh/uv/).

### Setup

```bash
cd local/agent
uv sync
```

### Run Modes

```bash
# 1. Standard Native Mode (OS keyboard/mouse hooks + foreground window polling + HTTP API on 127.0.0.1:8765)
uv run python run_daemon.py

# 2. Deterministic Simulation Mode (headless synthetic input/window schedule for testing or demos)
uv run python run_daemon.py --simulate --epoch-seconds 5

# 3. Bounded Headless Run Without HTTP Server
uv run python run_daemon.py --simulate --no-api --duration-seconds 30 --db-path /tmp/telemetry.db
```

### CLI Arguments & Environment Variables

| CLI Flag | Environment Variable | Default | Description |
| :--- | :--- | :--- | :--- |
| `--simulate` | *N/A* | `False` | Use deterministic synthetic input and window collectors. |
| `--epoch-seconds` | `TELEMETRY_EPOCH_SECONDS` | `30.0` | Duration of each micro-epoch before flushing to SQLite WAL. |
| `--db-path` | `TELEMETRY_DB_PATH` | `telemetry_epochs.db` | File path for the local SQLite WAL database. |
| `--api-port` | `TELEMETRY_API_PORT` | `8765` | TCP port for the loopback HTTP server on `127.0.0.1`. |
| `--no-api` | `TELEMETRY_ENABLE_API=0` | Enabled (`1`) | Disable the embedded FastAPI/Uvicorn HTTP server. |
| `--duration-seconds` | *N/A* | Unbounded | Stop gracefully after $N$ seconds (flushing in-flight data). |

---

## 5. Loopback HTTP & Prometheus Interface (`127.0.0.1:8765`)

When the HTTP server is enabled (default), the following read-only endpoints are served on `http://127.0.0.1:8765`:

| Method & Path | Query Parameters | Description |
| :--- | :--- | :--- |
| `GET /health` | None | Minimal liveness probe (`status`, `scheduler_running`, `epochs_flushed_total`). |
| `GET /api/v1/status` | None | Detailed scheduler diagnostics and live hysteresis chunker state counters. |
| `GET /api/v1/blocks` | `limit` (`1..500`, default `20`), or `start` & `end` (unix seconds) | Sealed activity blocks with pooled metrics, 4-dimension evaluations, and SRE status (`flow_optimal`, `nominal`, `warning`, `critical`). |
| `GET /api/v1/summary/today` | Optional `reference_timestamp` (unix seconds) | Daily summary evaluated over qualified work epochs, including `verified_work_seconds`, `bridged_reading_seconds`, `discarded_idle_seconds`, `executive_fuel_remaining`, and 4-dimension strain scores. |
| `GET /metrics` | None | Prometheus text exposition format (`text/plain; version=0.0.4`). |

### Exported Prometheus Metrics (`GET /metrics`)

- `egg_epochs_flushed_total` (`counter`): Total 30-second micro-epochs flushed.
- `egg_excursions_absorbed_total{excursion_type}` (`counter`): Transient app switches (`<90s`) and reading pauses (`<=120s`) absorbed into active blocks.
- `egg_activity_blocks_sealed_total{sre_status}` (`counter`): Sealed activity blocks by SRE status.
- `egg_sre_alerts_total{severity,dimension}` (`counter`): Cognitive load alerts emitted by severity (`warning`, `critical`) and dimension.
- `egg_epoch_duty_cycle_ratio` (`gauge`): Duty cycle ratio `[0.0, 1.0]` of the most recent epoch.
- `egg_epoch_shannon_entropy_nats` (`gauge`): Attentional Shannon entropy (nats) of the most recent epoch.
- `egg_dimension_strain_score{dimension}` (`gauge`): Normalized strain score `[0.0, 1.0]` per dimension on the latest sealed block.
- `egg_block_overall_strain_score` (`gauge`): Composite cognitive strain score `[0.0, 1.0]` of the latest sealed block.
- `egg_executive_fuel_tank_ratio` (`gauge`): Remaining executive capacity reservoir `[0.0, 1.0]`.

---

## 6. Development & Mandatory Quality Gates

Run all three verification gates from `local/agent/` before committing changes:

```bash
# 1. Lint & Format Check (Ruff)
uv run ruff check .
uv run ruff format --check .

# 2. Strict Static Type Checking (Mypy)
uv run mypy --strict app tests run_daemon.py

# 3. Automated Test Suite & Coverage Gate (>= 90%)
uv run pytest --cov=app --cov-fail-under=90
```
