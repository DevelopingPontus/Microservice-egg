# Project Architecture & Development Rules (`Microservice-egg`)

This root `AGENTS.md` is the **single source of truth** for architectural rules across `Microservice-egg`.

## Core Architecture Patterns

- **Package-by-Component / Modulith with Standalone Subsystems**: Code is grouped by feature with strict public facades (`__init__.py`), and meaningful subsystems can be booted standalone (`README.md` + `__main__.py` / `run.py`).
- **Functional Core, Imperative Shell (One-Way Pipeline)**: Domain analysis (`analysis/`) is 100% pure (zero I/O) inside a one-way pipeline (`config` $\rightarrow$ `collector` $\rightarrow$ `analysis` $\rightarrow$ `exporters`/`api` $\rightarrow$ `service`).
- **Architectural Fitness Functions**: Module boundaries, one-way dependencies, and standalone conventions are enforced automatically in CI via AST unit tests (`test_architecture_boundaries.py`).

```text
Microservice-egg/                           # [README.md] Combines local/ + server/
├── local/                                  # Combines telemetry/ + ui/ (100% private client tier)
│   ├── telemetry/                          # [README.md] Combines app/ + observability/ (`uv run run.py`)
│   │   ├── observability/                  # Concrete tools: OTel Collector, Prometheus, Loki, Tempo, Grafana
│   │   └── app/                            # [README.md] Standalone daemon (`uv run python -m app`)
│   │       ├── collector/                  # 1. Sensor package -> ActivitySnapshot
│   │       ├── analysis/                   # 2. Pure math package (strain/ + workflow/) -> CognitiveState
│   │       ├── exporters/                  # 3. Universal OTLP & Prometheus emitters -> .publish()
│   │       └── api/                        # 4. Loopback FastAPI gateway (127.0.0.1:8765)
│   └── ui/                                 # [README.md] Standalone ADHD frontend (energy_bar + focus_timeline + task_tree)
└── server/                                 # [README.md] Standalone Topic-Tree service (graph_cache + unzipper + api)
```

## The 6 Global Rules

1. **Rule 1 — Single Source of Truth (`AGENTS.md`)**:
   - This root `AGENTS.md` is the **only** `AGENTS.md` in the repository. Never create nested `AGENTS.md` files in subdirectories.
2. **Rule 2 — Standalone Subsystems Marked by `README.md`**:
   - Folders that form a useful runnable application or subsystem can be booted standalone (`Microservice-egg/`, `local/telemetry/`, `local/telemetry/app/`, `local/ui/`, `server/`).
   - A folder contains a `README.md` (with standalone run instructions and ports/endpoints) **if and only if** it is a standalone runnable unit. Internal code packages (`collector/`, `analysis/`, `exporters/`, `api/`, `strain/`, `workflow/`) never contain a `README.md`.
3. **Rule 3 — One-Way Pipeline Order (Functional Core, Imperative Shell)**:
   - Internal packages inside a service follow a strict **one-way dependency graph (DAG)**:
     `config` $\rightarrow$ `collector` $\rightarrow$ `analysis` $\rightarrow$ (`exporters`, `api`) $\rightarrow$ `service`
   - Downstream stages may import data types from upstream stages, never the reverse. Sibling subpackages (`strain/` vs. `workflow/`, `exporters/` vs. `api/`) never import each other.
4. **Rule 4 — Public Facade Encapsulation ("The Hammer Rule")**:
   - Each package folder exposes its public API through its `__init__.py` facade ("the hammer").
   - Cross-package imports must target **only the top-level package facade** (`from app.collector import ActivitySnapshot`, `from app.analysis import CognitiveState`)—never reaching 2+ levels deep into internal files (`app.collector.sliding_window` or `app.analysis.strain`).
5. **Rule 5 — Universal Emitters (`exporters/`) vs. Concrete Tool Stack (`observability/`)**:
   - Application code (`app/exporters/`) emits vendor-neutral standards (OpenTelemetry OTLP + Prometheus `/metrics`) so `local/telemetry/app/` runs standalone without Docker.
   - Concrete tool configurations (`observability/` + `docker-compose.yml` for OTel Collector, Prometheus, Loki, Tempo, and Grafana) live one level above `app/` in `local/telemetry/` and consume those universal signals.
6. **Rule 6 — DRY Data Contracts & Automated Fitness Functions**:
   - Define immutable data structures (`@dataclass(frozen=True)`) once in the upstream module that produces them and re-export them via its `__init__.py` facade.
   - All architectural rules above are verified automatically on every test run via `local/telemetry/tests/test_architecture_boundaries.py`.
