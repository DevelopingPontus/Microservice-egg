# Scoped Rules: `local/telemetry/` (Host Telemetry & SRE Observability Suite)

You are working inside `local/telemetry/`, the self-contained, always-on Python 3.12 background service and containerized observability stack running on the user's device. It powers **Pillar 2 (Time & Flow Management)** and **Pillar 3 (Emotional & Energy Regulation)** of EGG ("User-as-a-Server"), organized in the self-documenting **Hourglass + LCA Architecture**:

1. **LCA Crossroads Contracts (`app/common/`)**: Shared immutable configuration (`config.py`), domain DTOs and lossless pooling math (`models.py`), and structural interfaces (`protocols.py`).
2. **Intake Pillar (`app/intake/`)**:
   - **Hardware/Window Collectors (`app/intake/collectors/`)**: Zero-content keyboard/mouse hooks and cross-platform native foreground window process resolution (macOS, Windows, Linux).
   - **Sliding Window Engine (`app/intake/engine/window.py`)**: Stateless in-memory sliding window buffer (`SlidingWindowBuffer`).
3. **Observability & Output Pillar (`app/output/`)**:
   - **Pluggable 4-Dimension Physical SRE Engine (`app/output/dimensions/`)**: Temporal (Duty Cycle), Attentional (Context-switching velocity & Shannon entropy), Psychomotor (Keystroke CV & Correction Ratio), and Session Uptime evaluators.
   - **OpenTelemetry & SRE Observability (`app/output/observability/`)**: OTLP metric gauges, Loki structured logging, and Tempo distributed focus traces.
   - **Localhost FastAPI Gateway (`app/output/api/` — `127.0.0.1:8765`)**: Consumer-agnostic loopback HTTP and Prometheus metrics provider (`/health`, `/metrics`, `/api/v1/*`).
4. **Root Supervisor (`app/service.py`)**: Controls runtime timing ("I'll say when") and wires `intake/` $\rightarrow$ `output/`.
5. **CLI & Stack Orchestrator (`run.py`)**: Unified entrypoint managing Docker Compose (`docker compose -p egg-telemetry`) and the local Python service.

## 1. Python Toolchain & Mandatory Quality Gates (`uv`)

This service standardizes on **`uv`** (`/Users/pontus/.local/bin/uv` or `.venv/bin/`).

- **Dependency Management**: Always use `uv add`, `uv add --dev`, and `uv sync` inside `local/telemetry/`. Never use raw `pip install` or global Python packages.
- **Mandatory Verification Loop**: Before marking any code change or sprint task in `local/telemetry/` complete, you **MUST** run and pass all three gates from `local/telemetry/`:
  1. **Lint & Format (`ruff`)**:
     - `uv run ruff check .`
     - `uv run ruff format --check .`
  2. **Strict Static Typing (`mypy`)**:
     - `uv run mypy --strict app tests run.py`
  3. **Automated Tests & Coverage (`pytest`)**:
     - `uv run pytest --cov=app --cov-fail-under=90`

## 2. Strict Privacy & Zero Content Capture

- **Zero Text or Coordinate Inspection**: Never inspect, buffer, log, or persist key characters, key codes, scancodes, mouse coordinates, clipboard contents, window titles, file names, or URLs.
- **Sanitized Process Basenames Only**: Active windows are resolved strictly to executable or bundle basenames (e.g., `Code.exe`, `Firefox.app`, `Terminal.app`).
- **Strict Loopback Binding (`127.0.0.1`)**: All services bind exclusively to localhost.
