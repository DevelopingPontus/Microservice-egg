# Master Architecture & DevOps Portfolio Plan: `Microservice-egg`

## 1. Portfolio Vision & Two-Tier System Overview

`Microservice-egg` is a production-grade, privacy-by-construction **Cognitive Telemetry & Executive-Function Platform** built to demonstrate senior-level **DevOps, Polyglot Software Architecture (`Python` + `Java/Spring Boot`), and Graph Systems Engineering (`Neo4j` + `SQLite WAL`)**.

The platform is architected around a strict **privacy and compute boundary** that splits execution between **`local/`** (running on the user's computer) and **`server/`** (running as a centralized multi-user service):

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                     LOCAL TIER (`local/` — User's Computer)                  │
│                                                                              │
│  ┌────────────────────────────────────┐  ┌────────────────────────────────┐  │
│  │ `local/agent` (Python 3.12 + uv)   │  │ `local/ui` (Component App)     │  │
│  │ • Protocol Collectors (Native/Sim) │  │ • Interactive Topic Tree UI    │  │
│  │ • 30s Epoch Ring Buffer (RAM)      │◄─┤ • Focus & Activity Dashboards  │  │
│  │ • Pluggable Scientific Dimensions  │  │ • Connects to 127.0.0.1:8765   │  │
│  │ • 60s/90s Activity Block Chunker   │  │ • Can open/close freely        │  │
│  │ • Localhost FastAPI (127.0.0.1)    │  └────────────────────────────────┘  │
│  └───────────┬────────────────────────┘                                      │
│              │ Local SQLite WAL (`epoch_metrics_30s`, `activity_blocks`,     │
│              │                   `cached_topic_trees` — NEVER leaves device) │
└──────────────┼───────────────────────────────────────────────────────────────┘
               │ HTTPS REST (Topic Breakdown Request / Cache Sync)
               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                  SERVER TIER (`server/` — Central Cloud/Container)              │
│                                                                                 │
│  ┌───────────────────────────────────────┐  ┌────────────────────────────────┐  │
│  │ `server` (Java 27 + Spring Boot 4.1.2)│  │ Shared Neo4j 5+ Graph DB       │  │
│  │ • Topic Tree REST Controllers         ├─►│ • `(:Topic)-[:HAS_SUBTOPIC]->` │  │
│  │ • Semantic Vector Matcher             │  │ • Built-in Vector Index        │  │
│  │ • Recursive LLM Tree Builder          │  │   (matches equivalent phrasing)│  │
│  │   (invoked ONLY on cache misses)      │  │ • Sub-node graph reuse         │  │
│  └───────────────────────────────────────┘  └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Why This Architecture Follows Industry Best Practice

1. **Strict Telemetry Locality (`local/agent/`)**: Hardware and window telemetry is deeply personal. By processing 30s epochs, 60s/90s activity blocks, and scientific dimensions locally in SQLite WAL on the user's machine, private behavioral data **never leaves the device**.
2. **Always-On Background Agent + On-Demand UI (`local/agent/` $\leftrightarrow$ `local/ui/`)**: Just like ActivityWatch, Docker Desktop, or Tailscale, `local/agent/` runs continuously in the background and exposes a localhost API (`127.0.0.1:8765`). Users can close `local/ui/` at any time without interrupting background telemetry collection, and `local/agent/` caches active topic trees in local SQLite for full offline support.
3. **Cache-First Graph & Vector Topic Server (`server/` — Spring Boot + Neo4j)**:
   - Breaking down a topic into a tree of sub-topics and actionable steps produces **universal, non-private knowledge** that can be shared across all users.
   - Using **Neo4j Vector Indexes**, if a user asks for a topic that is phrased slightly differently from an existing topic in the graph, the Spring Boot server matches the existing `:Topic` node semantically and returns its subgraph immediately—avoiding redundant, slow, and expensive LLM calls.

---

## 2. Monorepo Directory Structure

```text
Microservice-egg/
├── .github/
│   └── workflows/
│       ├── ci-local-agent.yml          # Path-filtered Python CI (uv, ruff, mypy, pytest)
│       ├── ci-server.yml               # Path-filtered Java/Spring Boot + Neo4j CI
│       └── integration-e2e.yml         # Docker Compose E2E verification
├── AGENTS.md                           # Global monorepo & DevOps rules for AI agents
├── DEVOPS_PORTFOLIO_PLAN.md            # Master system & DevOps roadmap (this file)
├── reports/                            # Chronological sprint reports & LinkedIn slide scripts
│   ├── README.md                       # Report & carousel slide template specification
│   └── 01-sprint-1.0-monorepo-and-devops-guardrails.md
├── docker-compose.yml                  # Local Observability (Prometheus + Grafana) & Server Tier
├── observability/                      # Prometheus scrape config & pre-provisioned Grafana dashboards
├── local/                              # Tier 1: Runs Natively on the User's Computer (Host OS)
│   ├── agent/                          # Always-on Native Host Python 3.12 Background Daemon
│   │   ├── AGENTS.md                   # Local agent privacy, math & dimension rules
│   │   ├── epoch_telemetry_plan.md     # Detailed 30s epoch & architecture specification
│   │   ├── app/
│   │   │   ├── service.py              # Root Supervisor ("I'll say when": wires intake -> storage -> output)
│   │   │   ├── common/                 # LCA Crossroads Contracts ("What do you want?": config, models, protocols)
│   │   │   ├── intake/                 # Intake Pillar (collectors/ + engine/: 30s buffer, scheduler, chunker, SRE)
│   │   │   ├── storage/                # Raw Material Store (Async SQLite WAL: epochs & activity blocks)
│   │   │   └── output/                 # Value Creation Pillar (dimensions/ + api/ on 127.0.0.1:8765)
│   │   ├── tests/                      # Unit, AST boundary, math pooling & API tests (≥90% coverage)
│   │   ├── run_daemon.py               # Native host daemon entry point (serves 127.0.0.1:8765 live)
│   │   └── pyproject.toml              # Isolated uv environment
│   └── ui/                             # Component-Based Local Client Frontend
│       └── AGENTS.md                   # UI component & localhost gateway rules
└── server/                             # Tier 2: Central Shared Topic-Tree Server (Containerized)
    └── AGENTS.md                       # Java 27, Spring Boot 4.1.2 & Neo4j Hourglass + LCA rules
```

---

## 3. Core Engineering Pillars

### 3.1. Privacy by Construction & Lossless Algebraic Storage (`local/agent/`)

- **Zero Keystroke Content**: Key characters, key codes, clipboard contents, window titles, and URL parameters are **never** inspected, buffered, or persisted.
- **Executable Sanitization**: Active window polling resolves strictly to the executable or bundle identifier (e.g., `Code.exe`, `Slack.app`, `firefox`).
- **Lossless 30s Algebraic Primitives (`epoch_metrics_30s`)**:
  - **Temporal**: `active_seconds`, `micro_pause_count` ($1.0\text{--}5.0\text{ s}$ gaps).
  - **Attentional**: `context_switch_count`, `dwell_distribution_json` (`{process: seconds}`).
  - **Psychomotor**: `total_keystrokes`, `correction_keystrokes`, `iki_count` ($N$), `iki_sum_ms` ($\sum x$), `iki_sum_sq_ms` ($\sum x^2$).
  - **Circadian**: `timestamp_start`, `timestamp_end`.

### 3.2. Open-Closed Scientific Dimensions & 60s/90s Chunker (`local/agent/`)

Downstream analysis in `local/agent/app/output/dimensions/` implements the **Pluggable Dimension Pattern** (`BaseDimension` + `DimensionRegistry`):

1. **Temporal Dynamics**: Duty cycle ($T_{\text{active}} / T_{\text{total}}$), continuous block duration, micro-pause rate.
2. **Attentional Fragmentation**: Application Shannon entropy ($H = -\sum p_k \ln p_k$), context switches per minute.
3. **Psychomotor Mechanics**: Exact pooled Inter-Keystroke Interval Coefficient of Variation ($CV = \sigma_{\text{pooled}} / \mu_{\text{pooled}}$) and correction ratio ($R_{\text{corr}} = K_{\text{del}} / K_{\text{total}}$).
4. **Circadian & Cumulative Load**: Diurnal slotting, post-prandial dip window ($13:00\text{--}15:00$), cumulative screen time without a $>30\text{ min}$ reset.

**Stateful Activity Block Debouncing (`app/intake/engine/chunker.py`)**:

- **Transient Interruption Buffer ($<60\text{ s}$)**: Absorbed into the active block and counted only as internal context switches.
- **Definitive Block Boundary ($\ge 90\text{ s}$)**: Seals the current `ActivityBlock`, runs `evaluate_scientific_insights()` across all registered dimensions, and persists the block to `activity_blocks`.

### 3.3. Semantic Topic Graph & Subtree Reuse (`server/`)

- **Spring Boot 4.1.2 + Spring Data Neo4j**: Models topics as a directed graph (`(:Topic)-[:HAS_SUBTOPIC]->(:Topic)`).
- **Vector Similarity Matching**: Uses Neo4j vector indexes to resolve slightly different phrasings of the same topic to existing `:Topic` nodes in the database instead of generating duplicate LLM topic trees.
- **Sub-Node Graph Reuse**: When decomposing a novel topic, any sub-topic that matches an existing node in Neo4j links directly to that existing subtree.

---

## 4. Phased Execution Roadmap

### Phase 1: `local/agent` — 30s Epoch Ingestion & Storage Foundation (**COMPLETED**)

- **Sprint 1.0 (Foundation)**: Initialize monorepo, hierarchical `AGENTS.md` guardrails, and `local/agent` `uv` environment (`pyproject.toml`, `ruff`, `mypy --strict`, `pytest`) — **Completed**.
- **Sprint 1.1 (Storage & Pooled Math)**: Implement `app/storage/database.py` (SQLite WAL mode) and `app/storage/repository.py`, plus mathematical pooling verification tests (`tests/test_math_pooling.py`, `tests/test_storage.py`) — **Completed**.
- **Sprint 1.2 (Protocols, Collectors & Buffer)**: Implement `app/collectors/protocols.py`, `EpochBuffer` (`app/engine/buffer.py`), native OS collectors, and deterministic synthetic collectors (`tests/test_buffer.py`, `tests/test_collectors.py`) — **Completed**.
- **Sprint 1.3 (Scheduler & CLI Supervisor)**: Implement 30s monotonic scheduler, graceful signal handling (`SIGINT`/`SIGTERM` flush), and CLI `--simulate` mode — **Completed**.

### Phase 2: `local/agent` — Scientific Dimensions, 60s/90s Chunker, Localhost API & Live Observability (**COMPLETED**)

- **Sprint 2.1 (Dimension Engine)**: Implement `BaseDimension`, `DimensionRegistry`, and the 4 scientific dimension classes (`app/dimensions/`) with unit tests for Shannon entropy, pooled IKI CV, duty cycle, and circadian load — **Completed**.
- **Sprint 2.2 (Activity Block Chunker & SRE Signals)**: Implement the 60s/90s hysteresis state machine (`app/engine/chunker.py`), SRE health evaluator (`app/engine/sre.py`), Prometheus gauges/counters, and Folder Orchestrator isolation (`tests/test_architecture_boundaries.py`) — **Completed**.
- **Sprint 2.3 (FastAPI Localhost Gateway, Hourglass + LCA Architecture & Live Grafana)**: Refactor `app/` into the self-documenting Hourglass + LCA layout (`common/`, `intake/`, `storage/`, `output/`, `service.py`), implement `/health`, `/metrics`, `/api/v1/status`, `/api/v1/blocks`, and `/api/v1/summary/today` on `127.0.0.1:8765` running concurrently inside the native host daemon (`run_daemon.py`), and wire `docker-compose.yml` (`prometheus` + `grafana` scraping `host.docker.internal:8765/metrics`) — **Completed**.

### Phase 3: `server` — Java 27 / Spring Boot 4.1.2 / Neo4j Shared Topic-Tree Service (**NEXT**)

- **Sprint 3.1 (Spring Boot & Neo4j Graph Domain)**: Initialize Spring Boot 4.1.2 project (`server/`), configure `:Topic` Neo4j entities, repositories, and Testcontainers setup.
- **Sprint 3.2 (Semantic Vector Matching & Cache-First Lookup)**: Implement Neo4j vector index lookup so semantically equivalent topic queries resolve to existing `:Topic` subtrees.
- **Sprint 3.3 (Recursive LLM Decomposition, Subtree Reuse & Local Offline Cache)**: Implement LLM fallback for cache misses that links existing sub-topics and expands only missing nodes, and connect `local/` offline topic-tree caching against the verified server contract.

### Phase 4: `local/ui`, Observability (`Prometheus` + `Grafana`) & Root DevOps CI/CD Orchestration

- **Sprint 4.1 (Component UI & Blameless User Insights)**: Scaffold component-based `local/ui` consuming `127.0.0.1:8765` for interactive Topic Trees and SRE-inspired Activity Block insights ("USE Method / Golden Signals for Focus").
- **Sprint 4.2 (Docker Compose, Prometheus/Grafana & GitHub Actions CI/CD)**: Wire `docker-compose.yml` (`local-agent --simulate`, `server`, `neo4j`, `prometheus`, `grafana`) exposing operational metrics (Neo4j vector cache hit ratio, LLM decomposition latency, and local 30s epoch flush health) alongside path-filtered GitHub Actions workflows (`.github/workflows/`).
