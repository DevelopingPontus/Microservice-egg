# Master Architecture & DevOps Portfolio Plan: `Microservice-egg`

## 1. Portfolio Vision & Recursive Feature-Module Overview

`Microservice-egg` is a production-grade, privacy-by-construction **Cognitive Telemetry & Executive-Function Platform** built to demonstrate senior-level **DevOps, SRE Observability (`OpenTelemetry` + `Prometheus` + `Loki` + `Tempo` + `Grafana`), Polyglot Software Architecture (`Python` + `Java/Spring Boot`), and Graph Systems Engineering (`Neo4j`)**.

The platform is organized around a simple recursive rule: **every folder is a standalone feature module that combines its direct children to create new functionality**, split at the root between **`local/`** (100% private on the user's computer) and **`server/`** (centralized shared topic cache):

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                     LOCAL TIER (`local/` — User's Computer)                  │
│  Combines `telemetry/` + `ui/` into an offline-capable personal workspace    │
│                                                                              │
│  ┌────────────────────────────────────┐  ┌────────────────────────────────┐  │
│  │ `local/telemetry` (Python 3.12+uv) │  │ `local/ui` (Mobile-First App)  │  │
│  │ • `collector/` (60s Snapshot)      │  │ • `energy_bar/` (Strain State) │  │
│  │ • `analysis/` (`strain`+`workflow`)│◄─┤ • `focus_timeline/` (Flow)     │  │
│  │ • `exporters/` (OTel/Prom/Loki)    │  │ • `task_tree/` (Step Cards)    │  │
│  │ • `api/` (127.0.0.1:8765)          │  │ • Connects to 127.0.0.1:8765   │  │
│  └───────────┬────────────────────────┘  └────────────────────────────────┘  │
│              │ OTLP gRPC/HTTP Loopback (NEVER leaves device)                 │
│              ▼                                                               │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ Local Observability Suite (`local/telemetry/docker-compose.yml`)       │  │
│  │ • OTel Collector (`count` & `spanmetrics` connectors)                  │  │
│  │ • Prometheus TSDB (`alert_rules.yml` 60s/90s hysteresis)               │  │
│  │ • Loki Logs (JSON discrete events) • Tempo Traces • Grafana (3000)     │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────┬───────────────────────────────────────────────────────────────┘
               │ HTTPS REST (Generic Topic Breakdown Request / Cache Sync)
               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                  SERVER TIER (`server/` — Central Cloud/Container)              │
│  Combines `graph_cache/` + `unzipper/` + `api/` for shared topic decomposition  │
│                                                                                 │
│  ┌───────────────────────────────────────┐  ┌────────────────────────────────┐  │
│  │ `server` (Java 27 + Spring Boot 4.1.2)│  │ Shared Neo4j 5+ Graph DB       │  │
│  │ • `graph_cache/` (Vector Similarity)  ├─►│ • `(:Topic)-[:HAS_SUBTOPIC]->` │  │
│  │ • `unzipper/` (LLM on Cache Miss)     │  │ • Built-in Vector Index        │  │
│  │ • `api/` (REST Controllers & Metrics) │  │   (matches equivalent phrasing)│  │
│  └───────────────────────────────────────┘  └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Monorepo Directory Structure

Every standalone runnable subsystem is marked by a `README.md` at its root, while internal packages follow a one-way pipeline enforced by [`AGENTS.md`](./AGENTS.md) and `test_architecture_boundaries.py`:

```text
Microservice-egg/                       # [README.md] Combines local/ + server/
├── .github/
│   └── workflows/
│       ├── ci-local-telemetry.yml      # Path-filtered Python CI (uv, ruff, mypy, pytest)
│       ├── ci-server.yml               # Path-filtered Java/Spring Boot + Neo4j CI
│       └── integration-e2e.yml         # Docker Compose E2E verification
├── AGENTS.md                           # Single source of truth for architectural rules
├── DEVOPS_PORTFOLIO_PLAN.md            # Master system & DevOps roadmap (this file)
├── reports/                            # Local-only sprint reports & slide generator
├── local/                              # Combines telemetry/ + ui/ (100% private client tier)
│   ├── telemetry/                      # [README.md] Combines app/ + observability/ (`uv run run.py`)
│   │   ├── README.md                   # Quickstart & DevOps Observability Learning Guide
│   │   ├── docker-compose.yml          # Local OTel Collector, Prometheus, Loki, Tempo & Grafana
│   │   ├── observability/              # Concrete tool configs: OTel, Prometheus (+ alert_rules.yml), Loki, Tempo, Grafana
│   │   ├── app/                        # [README.md] Standalone daemon (`uv run python -m app`)
│   │   │   ├── README.md               # Standalone lightweight daemon guide
│   │   │   ├── __main__.py             # Standalone CLI entry point
│   │   │   ├── config.py               # DaemonConfig operational constants
│   │   │   ├── service.py              # Thin root coordinator
│   │   │   ├── collector/              # 1. Sensor package: input_hook + window_probe + sliding_window -> ActivitySnapshot
│   │   │   ├── analysis/               # 2. Pure math package: strain/ + workflow/ -> Unified CognitiveState (zero I/O)
│   │   │   │   ├── strain/             #    Combines temporal + attentional + psychomotor + uptime -> StrainReport
│   │   │   │   └── workflow/           #    Combines classifier + sessions + rhythms -> WorkflowSnapshot
│   │   │   ├── exporters/              # 3. Universal OTLP & Prometheus emitters -> Single .publish() sink
│   │   │   └── api/                    # 4. Loopback 127.0.0.1:8765 HTTP & Prometheus gateway
│   │   ├── tests/                      # Unit, boundary, math pooling & API tests (≥90% coverage)
│   │   ├── run.py                      # Unified stack + daemon orchestrator CLI
│   │   └── pyproject.toml              # Isolated uv environment
│   └── ui/                             # [README.md] Combines energy_bar/ + focus_timeline/ + task_tree/
│       └── README.md                   # Standalone ADHD frontend guide
└── server/                             # [README.md] Combines graph_cache/ + unzipper/ + api/
    └── README.md                       # Standalone Java 27, Spring Boot 4.1.2 & Neo4j service guide
```

---

## 3. Core Engineering Modules

### 3.1. `local/telemetry/app/collector/` — Privacy-Safe 60s Activity Sensor

- **Combines**: `input_hook.py` + `window_probe.py` + `sliding_window.py` + `models.py`.
- **Zero Content Capture**: Key characters, key codes, clipboard contents, window titles, and URL parameters are never inspected, buffered, or persisted. Active windows resolve strictly to sanitized executable/bundle names (`Code.exe`, `Slack.app`, `Firefox.app`).
- **Complete `ActivitySnapshot`**: Commits 60s sliding-window slices, computes exact pooled statistics (`duty_cycle`, `shannon_entropy`, `iki_cv`, `correction_ratio`), tracks 3-minute reading/thought grace periods, and computes per-tick monotonic counter deltas internally.

### 3.2. `local/telemetry/app/analysis/` — Pure Cognitive State Engine

`analysis/` combines two pure feature modules with **zero I/O and zero external framework dependencies**:

1. **`analysis/strain/` — 4-Dimension SRE Health (`egg_user_*`)**:
   - Combines `temporal.py` (Duty Cycle & reading vs. stalled modality), `attentional.py` (Shannon entropy & switch rate), `psychomotor.py` (pooled IKI CV & correction ratio), and `uptime.py` (continuous session load) with weighted baseline exclusion into a single `CognitiveStrainReport` (`nominal`, `flow_optimal`, `warning`, `critical`).
2. **`analysis/workflow/` — 6-Dimension Overview & Work Categories (`egg_overview_*`)**:
   - **`classifier.py`**: Evaluates the 6 work categories in strict priority order (`idle` $\rightarrow$ `communicating` $\rightarrow$ `consuming` $\rightarrow$ `producing` $\rightarrow$ `navigating` $\rightarrow$ `unclassified`).
   - **`sessions.py`**: Tracks 60s-debounced focus sessions, $>25\text{m}$ deep-work blocks, 30m attention residue, and `comms` interruption resumption lag.
   - **`rhythms.py`**: Computes per-minute input intensity, lag-autocorrelation ultradian cycle period, 24h circular chronotype center-of-mass, and typing burst mode (`composing` vs. `transcribing`).

### 3.3. `local/telemetry/app/exporters/` & `api/` — Observability & Localhost Gateway

- **`exporters/`**: Combines `otel.py`, declarative table-driven `metrics.py`, stateful alert/heartbeat `logs.py`, and Tempo `traces.py` behind a single `exporters.publish(snapshot, state)` call.
- **`api/`**: Serves `/health`, `/metrics`, `/api/v1/status`, and `/api/v1/state` strictly on `127.0.0.1:8765`.

### 3.4. `server/` — Semantic Topic Graph & Subtree Reuse

- **Combines**: `graph_cache/` (Neo4j `:Topic` graph + vector similarity index), `unzipper/` (embeddings + LLM decomposition on cache misses), and `api/` (REST controller).
- **Sub-Node Graph Reuse**: Semantically equivalent topics resolve to existing `:Topic` subtrees with `0` LLM calls; novel topics reuse any sub-steps that already exist in Neo4j.

---

## 4. Phased Execution Roadmap

### Phase 1: `local/telemetry` — `collector/` Sensor & Lossless Pooling (**COMPLETED**)

- Initialize monorepo, `uv` environment (`ruff`, `mypy --strict`, `pytest`), lossless algebraic pooling math, OS/synthetic input and window probes, and the 60s sliding window buffer.

### Phase 2: `local/telemetry` — `analysis/`, `exporters/`, `api/` & Observability Stack (**COMPLETED**)

- Implement `analysis/strain/` (4 SRE dimensions) and `analysis/workflow/` (6 Overview dimensions & work categories), `exporters/` (OTel, Prometheus, Loki, Tempo), `api/` (`127.0.0.1:8765`), `run.py`, and the 28-panel Grafana dashboard (`user-as-a-server.json`).

### Phase 3: `server` — Java 27 / Spring Boot 4.1.2 / Neo4j Shared Topic-Tree Service (**NEXT**)

- Implement `graph_cache/` (Neo4j entities + vector similarity lookup), `unzipper/` (LLM fallback on cache miss with sub-node reuse), and `api/` with Testcontainers verification.

### Phase 4: `local/ui` & Root DevOps CI/CD Orchestration

- Implement `local/ui/` (`energy_bar/` + `focus_timeline/` + `task_tree/`) consuming `http://127.0.0.1:8765/api/v1/`, and wire E2E Docker Compose + path-filtered GitHub Actions workflows.
