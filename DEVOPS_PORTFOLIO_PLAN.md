# Master Architecture & DevOps Portfolio Plan: `Microservice-egg`

## 1. Portfolio Vision & System Overview

`Microservice-egg` is a production-grade, privacy-by-construction **Cognitive Telemetry & Activity Block Platform** built to demonstrate senior-level **DevOps, Software Architecture, and Systems Engineering** practices.

Designed to give knowledge workers (specifically individuals with ADHD) empirical, non-judgmental self-insight into their work patterns, the platform bridges **OS-level hardware telemetry** with **containerized microservices, mathematically lossless aggregation, and automated CI/CD**.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                     Service 1: telemetry/daemon (Host / Edge)                │
│  ┌──────────────────────────────┐      ┌──────────────────────────────────┐  │
│  │ Protocol Collectors          │      │ 30s Epoch Ring Buffer (RAM)      │  │
│  │ - Native (pynput/NSWorkspace)├─────►│ - Ephemeral ticks only           │  │
│  │ - Synthetic (--simulate)     │      │ - Algebraic primitives (Σx, Σx²) │  │
│  └──────────────────────────────┘      └─────────────────┬────────────────┘  │
└──────────────────────────────────────────────────────────┼───────────────────┘
                                                           │ Every 30s (~120 rows/hr)
                                                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                Shared Local Persistence (SQLite WAL Mode)                    │
│  - `epoch_metrics_30s`: Lossless 30s primitives written by Daemon            │
│  - `activity_blocks`: Finalized debounced sessions & scientific insights     │
└──────────────────────────────────────────────────────────┬───────────────────┘
                                                           │ Async time-range queries
                                                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                 Service 2: telemetry/api (FastAPI & Chunker Engine)          │
│  ┌────────────────────────────────────┐  ┌────────────────────────────────┐  │
│  │ Pluggable Dimension Registry       │  │ Activity Block Chunker         │  │
│  │ 1. Temporal Dynamics (Duty cycle)  │  │ - 60s transient excursion buf  │  │
│  │ 2. Attentional (Shannon entropy H) │  │ - 90s definitive seal boundary │  │
│  │ 3. Psychomotor (Pooled IKI CV)     │  ├────────────────────────────────┤  │
│  │ 4. Circadian (Diurnal & load)      │  │ FastAPI REST API (127.0.0.1)   │  │
│  └────────────────────────────────────┘  └────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Monorepo Directory Structure

This repository uses **Domain-Scoped Monorepo Grouping** so each microservice maintains an isolated dependency tree, test suite, and AI context boundary (`AGENTS.md`), while sharing unified CI/CD orchestration at the root.

```text
Microservice-egg/
├── .github/
│   └── workflows/
│       ├── ci-telemetry-daemon.yml     # Path-filtered CI (Ubuntu + macOS matrix)
│       ├── ci-telemetry-api.yml        # Path-filtered CI + Docker build test
│       └── integration-e2e.yml         # Daemon (--simulate) + API end-to-end test
├── AGENTS.md                           # Global monorepo & DevOps rules for AI agents
├── DEVOPS_PORTFOLIO_PLAN.md            # Master system & DevOps roadmap (this file)
├── reports/                            # Chronological sprint reports & LinkedIn slide scripts
│   ├── README.md                       # Report & carousel slide template specification
│   └── 01-sprint-1.0-monorepo-and-devops-guardrails.md
├── docker-compose.yml                  # Spins up synthetic Daemon + API + observability
├── Makefile                            # Developer UX shortcuts (make lint, test, sim)
├── telemetry/                          # Domain: Cognitive Telemetry Engine
│   ├── daemon/                         # Service 1: 30s Epoch Ingestion Daemon
│   │   ├── AGENTS.md                   # Daemon-specific privacy & math invariants
│   │   ├── epoch_telemetry_plan.md     # Detailed daemon specification
│   │   ├── app/                        # Collectors, Protocols, EpochBuffer, Storage
│   │   ├── tests/                      # Unit & SQLite WAL tests (≥90% coverage)
│   │   ├── Dockerfile                  # Headless test & synthetic workload image
│   │   ├── run_daemon.py               # CLI entry point (--simulate supported)
│   │   └── pyproject.toml              # Isolated uv environment
│   └── api/                            # Service 2: Pluggable Dimensions, Chunker & FastAPI
│       ├── AGENTS.md                   # API, Chunker & BaseDimension rules
│       ├── app/
│       │   ├── dimensions/             # BaseDimension, Registry, 4 scientific dims
│       │   ├── engine/                 # 60s/90s Debounce Activity Block Chunker
│       │   ├── storage/                # Epoch reader & activity_blocks repository
│       │   └── api/                    # FastAPI routes (/status, /blocks, /summary)
│       ├── tests/                      # Dimension math, chunker hysteresis, API tests
│       ├── Dockerfile                  # Production multi-stage uv container
│       └── pyproject.toml              # Isolated uv environment
└── infra/                              # Observability & local deployment configs
    └── README.md                       # launchd / systemd templates & Prometheus setup
```

---

## 3. Core Architectural Pillars

### 3.1. Privacy by Construction
* **Zero Keystroke Content**: Key characters, key codes, clipboard contents, window titles, and URL parameters are **never** inspected, buffered, or persisted.
* **Executable Sanitization**: Active window polling resolves strictly to the executable or bundle identifier (e.g., `Code.exe`, `Slack.app`, `firefox`).
* **Local-Only Binding**: All HTTP endpoints bind strictly to `127.0.0.1` (`port 8765`).

### 3.2. Lossless Algebraic Epoch Storage
Instead of storing raw hardware ticks (which bloat storage and risk privacy) or pre-averaged percentages (which cannot be accurately re-combined across variable time windows), `telemetry/daemon` writes **30-second algebraic primitives** into `epoch_metrics_30s`:
* **Temporal**: `active_seconds`, `micro_pause_count` ($1.0\text{--}5.0\text{ s}$ gaps).
* **Attentional**: `context_switch_count`, `dwell_distribution_json` (`{process: seconds}`).
* **Psychomotor**: `total_keystrokes`, `correction_keystrokes`, `iki_count`, `iki_sum_ms` ($\sum x$), `iki_sum_sq_ms` ($\sum x^2$).
* **Circadian**: `timestamp_start`, `timestamp_end`.

### 3.3. Open-Closed Scientific Dimensions (`telemetry/api`)
Downstream analysis in `telemetry/api` implements the **Pluggable Dimension Pattern** (`BaseDimension` + `DimensionRegistry`):
1. **Temporal Dynamics**: Duty cycle ($T_{\text{active}} / T_{\text{total}}$), continuous block duration, micro-pause rate.
2. **Attentional Fragmentation**: Application Shannon entropy ($H = -\sum p_k \ln p_k$), context switches per minute.
3. **Psychomotor Mechanics**: Exact pooled Inter-Keystroke Interval Coefficient of Variation ($CV = \sigma_{\text{pooled}} / \mu_{\text{pooled}}$) and correction ratio ($R_{\text{corr}} = K_{\text{del}} / K_{\text{total}}$).
4. **Circadian & Cumulative Load**: Diurnal slotting, post-prandial dip window ($13:00\text{--}15:00$), cumulative screen time without a $>30\text{ min}$ reset.

### 3.4. Stateful Activity Block Debouncing
To prevent brief interruptions (e.g., changing a track in Spotify for 10 seconds) from fragmenting deep-work sessions:
* **Transient Interruption Buffer ($<60\text{ s}$)**: Absorbed into the active block and counted only as internal context switches.
* **Definitive Block Boundary ($\ge 90\text{ s}$)**: Seals the current `ActivityBlock`, runs `evaluate_scientific_insights()` across all registered dimensions, and persists the block to `activity_blocks`.

---

## 4. DevOps Portfolio Engineering Pillars

What makes this repository stand out in a DevOps engineering review:
1. **Hardware Decoupling via Python Protocols & Synthetic Mode**:
   * OS listeners (`pynput`, `NSWorkspace`, `win32gui`, `Xlib`) cannot run in headless Linux containers without display servers.
   * By programming against `InputListenerProtocol` and `WindowResolverProtocol` and providing a deterministic `--simulate` mode (`SyntheticInputListener`, `SyntheticWindowResolver`), the entire stack runs end-to-end inside Docker and GitHub Actions CI.
2. **Modern Reproducible Python Toolchain (`uv`)**:
   * Each service uses `uv` with locked `uv.lock` files and multi-stage Docker builds with bytecode compilation and layer caching.
3. **Strict Automated Quality Gates**:
   * **Linting & Formatting**: `ruff check` and `ruff format --check`
   * **Static Typing**: `mypy --strict`
   * **Automated Testing**: `pytest` + `pytest-asyncio` with $\ge 90\%$ branch/line coverage (`--cov-fail-under=90`).
4. **Path-Filtered Multi-OS CI/CD & E2E Compose Validation**:
   * Service workflows trigger only when their respective folders change (`telemetry/daemon/**` vs `telemetry/api/**`).
   * End-to-end integration workflow boots `docker compose up` with the daemon in `--simulate` mode and asserts live `/api/v1/status` and `/api/v1/blocks` responses from FastAPI.

---

## 5. Phased Execution Roadmap

### Phase 1: `telemetry/daemon` — Epoch Ingestion Service
* **Sprint 1.0 (Foundation)**: Initialize root Git repo, `AGENTS.md` hierarchy, and `telemetry/daemon` `uv` environment (`pyproject.toml`, `ruff`, `mypy`, `pytest`).
* **Sprint 1.1 (Storage & Pooled Math)**: Implement `app/storage/database.py` (SQLite WAL mode) and `app/storage/repository.py`, plus mathematical pooling verification tests (`tests/test_math_pooling.py`, `tests/test_storage.py`).
* **Sprint 1.2 (Protocols, Collectors & Buffer)**: Implement `app/collectors/protocols.py`, `EpochBuffer` (`app/engine/buffer.py`), native OS collectors, and deterministic synthetic collectors (`tests/test_buffer.py`, `tests/test_collectors.py`).
* **Sprint 1.3 (Scheduler, Supervisor & Container)**: Implement 30s monotonic scheduler, graceful signal handling (`SIGINT`/`SIGTERM` flush), `run_daemon.py --simulate`, and `telemetry/daemon/Dockerfile`.

### Phase 2: `telemetry/api` — Pluggable Dimensions, Chunker & FastAPI
* **Sprint 2.1 (Dimension Engine)**: Implement `BaseDimension`, `DimensionRegistry`, and the 4 scientific dimension classes with unit tests for Shannon entropy, pooled IKI CV, duty cycle, and circadian load.
* **Sprint 2.2 (Activity Block Chunker)**: Implement the 60s/90s hysteresis state machine reading from `epoch_metrics_30s` and writing sealed blocks to `activity_blocks`.
* **Sprint 2.3 (FastAPI Service & Container)**: Implement `/api/v1/status`, `/api/v1/blocks`, `/api/v1/blocks/{id}`, `/api/v1/summary/today`, and `/api/v1/insights/active` on `127.0.0.1:8765`, plus `telemetry/api/Dockerfile`.

### Phase 3: Root DevOps Orchestration & CI/CD
* **Sprint 3.1 (Docker Compose & Makefile)**: Wire `docker-compose.yml` connecting `telemetry-daemon --simulate` and `telemetry-api` over a shared SQLite WAL volume.
* **Sprint 3.2 (GitHub Actions Pipelines)**: Add path-filtered CI workflows (`.github/workflows/`) and end-to-end container smoke tests.
* **Sprint 3.3 (Portfolio Documentation)**: Polish root `README.md` with architecture diagrams, scientific citations, and 1-command quickstart instructions.
