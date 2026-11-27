# Local Fatigue Telemetry (`local/telemetry`)

100% local, privacy-preserving fatigue telemetry collector, permanent per-app IQR baseline engine, and Prometheus + Grafana observability stack.

## Quick Start

```bash
./start.sh
```

The interactive menu lets you:
1. **Start Full Stack** (Passive: Keyboard, Mouse, Window Focus + Prometheus + Grafana)
2. **Start Full Stack + Webcam** (On-demand 60s confirmation bursts, 10m cooldown)
3. **Start Local Daemon Only** (no Docker — SQLite + `:9105/metrics`)
4. **Setup / Install Dependencies** (core or core + webcam)
5. **Fix macOS Permissions** (opens Accessibility, Input Monitoring & Camera settings)
6. **Run Tests** (`pytest`)

## Endpoints & Storage
- **Grafana**: `http://127.0.0.1:3000` (*Local Fatigue Telemetry* & *DevOps & System Health*)
- **Prometheus**: `http://127.0.0.1:9090` (35-day persistent volume, IQR drift clusters & 5 alerts)
- **Daemon `/metrics`**: `http://127.0.0.1:9105/metrics`
- **SQLite WAL DB**: `data/telemetry.db` (`0o600` owner-only; 14-day raw retention; permanent `fatigue_log`, `app_anchors`, `app_iqrs`)

## Architecture Diagrams
Open [FLOWCHART.md](FLOWCHART.md) in VS Code (`Cmd+Shift+V`) for auto-generated Mermaid diagrams (runtime flow, AST module graph, SQLite ER diagram, Prometheus catalog, cluster alert tree, webcam state machine, and timing sequence). Refresh anytime with:

```bash
.venv/bin/python generate_flowchart.py
```

## Tests

```bash
.venv/bin/pytest -v
```
