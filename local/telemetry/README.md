# Local Fatigue Telemetry (`local/telemetry`)

100% local, privacy-preserving fatigue telemetry collector, permanent per-app IQR baseline engine, and Prometheus + Grafana observability stack.

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** (recommended — manages Python 3.12 automatically via `.python-version` and locks dependencies via `uv.lock`):
  ```bash
  brew install uv   # macOS
  # or: curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Python 3.12** (pinned in `.python-version`; required for `mediapipe<0.10.20` webcam wheels; `uv` downloads it automatically if not installed).
- **Docker** (optional — required only for the Prometheus + Grafana observability stack; the local daemon runs standalone without Docker).
- **OS Permissions**:
  - **macOS**: Grant your terminal **Accessibility** and **Input Monitoring** (and **Camera** if using webcam mode). Use menu option **5** in `./start.sh` to open the settings panes directly.
  - **Linux (X11)**: `xdotool` for active window detection.

## Setup

```bash
cd local/telemetry

# Core + dev tools (pytest, ruff)
uv sync --extra dev

# Core + dev + opt-in webcam oculometrics (OpenCV + MediaPipe)
uv sync --extra dev --extra webcam
```

## Quick Start

### Interactive Menu (Recommended)

```bash
./start.sh
```

The interactive menu lets you:
1. **Start Full Stack** (Passive: Keyboard, Mouse, Window Focus + Prometheus + Grafana)
2. **Start Full Stack + Webcam** (On-demand 60s confirmation bursts, 10m cooldown)
3. **Start Local Daemon Only** (no Docker — SQLite + `:9105/metrics`)
4. **Setup / Install Dependencies** (core or core + webcam via `uv`)
5. **Fix macOS Permissions** (opens Accessibility, Input Monitoring & Camera settings)
6. **Run Tests** (`pytest`)

### Direct CLI Commands

```bash
# Run the daemon directly (no Docker)
uv run python run.py

# Run with opt-in webcam confirmation bursts
uv run python run.py --enable-webcam

# Start Prometheus + Grafana manually
docker compose up -d
```

## Endpoints & Storage

- **Grafana**: `http://127.0.0.1:3000` (*Local Fatigue Telemetry* & *DevOps & System Health*)
- **Prometheus**: `http://127.0.0.1:9090` (35-day persistent volume, IQR drift clusters & 5 alerts)
- **Daemon `/metrics`**: `http://127.0.0.1:9105/metrics`
- **SQLite WAL DB**: `data/telemetry.db` (`0o600` owner-only; 14-day raw retention; permanent `fatigue_log`, `app_anchors`, `app_iqrs`)

## Documentation & Architecture Diagrams

- **[METRICS.md](METRICS.md)**: Peer-reviewed metric definitions, quality gates, and alert thresholds.
- **[FLOWCHART.md](FLOWCHART.md)**: Auto-generated Mermaid diagrams (runtime flow, AST module graph, SQLite ER diagram, Prometheus catalog, cluster alert tree, webcam state machine, and timing sequence). Open in VS Code (`Cmd+Shift+V`) or refresh anytime with:
  ```bash
  uv run python generate_flowchart.py
  ```

## Lint & Tests

```bash
uv run ruff check telemetry tests run.py cli.py
uv run pytest -v --cov=telemetry
```
