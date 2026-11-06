# `local/telemetry` — EGG Cognitive Host Telemetry & SRE Observability

A self-contained, privacy-by-construction Python 3.12 daemon and containerized observability stack (**"User-as-a-Server"**). Passively samples hardware interaction timing and foreground application switches across rolling sliding windows, evaluates 4 physical SRE dimensions, exports open telemetry over OTLP gRPC/HTTP, and serves Prometheus, Loki, Tempo, and Grafana dashboards strictly on `127.0.0.1`.

This package can run as a **standalone product** or as a **git submodule** within the broader EGG monorepo.

---

## 1. Prerequisites

Before running the suite, ensure your machine satisfies the following prerequisites:

### 1.1 Core Tooling

- **Python 3.12+**: Modern Python runtime.
- **`uv` Package Manager**: Fast, deterministic package manager:

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- **Docker Desktop / Docker Engine (v2) with Compose**:
  - Required to run the local containerized stack (Grafana, Prometheus, Loki, Tempo, OTel Collector).
  - *Note*: If Docker is not installed or running, the telemetry daemon can still run in standalone host mode (`--no-stack`) serving its embedded REST API on `127.0.0.1:8765`.

### 1.2 Operating System Input Permissions

To passively monitor interaction timing without text capture, your OS requires appropriate input event privileges:

#### macOS (Accessibility & Input Monitoring)

1. Open **System Settings** $\rightarrow$ **Privacy & Security** $\rightarrow$ **Accessibility**.
2. Enable your terminal emulator (e.g., **Terminal.app**, **iTerm2**, **Alacritty**, or **VS Code**).
3. Check **Input Monitoring** if prompted.
4. Restart your terminal application so macOS updates its process security tokens.

#### Linux (X11 vs. Wayland)

- **X11 / Xorg (Recommended)**: Works out of the box with `xdotool` and `pynput`.
- **Wayland**: Security policies isolate input across windows. To grant input device access, ensure your user belongs to the `input` group:

  ```bash
  sudo usermod -aG input $USER
  ```

  Then log out and log back in.

#### Windows

- Native Windows APIs (`user32.dll` and `kernel32.dll`) are supported out of the box with standard user privileges.

#### Zero-Permission Mode (Synthetic Telemetry)

To run in CI or test without granting OS permissions:

```bash
uv run run.py --synthetic
```

---

## 2. Quickstart: One-Command Execution

### Default: Start Everything (Docker Stack + Python Daemon)

```bash
cd local/telemetry
uv run run.py
```

This single command:

1. Automatically boots the Docker Compose observability stack in the `egg-telemetry` project namespace.
2. Displays the interactive dashboard discovery banner with clickable URLs.
3. Launches the local Python telemetry daemon collecting real-time host metrics.
4. On `Ctrl+C`, cleanly stops the daemon and stops the containers.

---

## 3. UI Endpoints & Dashboards

When the stack starts, access the following pre-configured services:

| Service | URL | Description | Default Credentials |
| :--- | :--- | :--- | :--- |
| **Grafana Dashboard** | `http://127.0.0.1:3000/d/user-as-a-server` | Single pane of glass for physical SRE dimensions (Duty Cycle, Thrashing, Jitter, Errors, Uptime). | `admin` / `eggadmin` |
| **Prometheus TSDB** | `http://127.0.0.1:9090` | Raw time-series database and PromQL query explorer. | *None (open loopback)* |
| **Loki Logs** | `http://127.0.0.1:3000/explore` *(Loki)* | Structured JSON log stream of state ticks and SRE alert events. | `admin` / `eggadmin` |
| **Tempo Traces** | `http://127.0.0.1:3000/explore` *(Tempo)* | Active application focus span traces capturing context switches. | `admin` / `eggadmin` |
| **Host Daemon API** | `http://127.0.0.1:8765` | Localhost REST API for UI task breakdown clients. | *None (loopback only)* |
| **Interactive API Docs** | `http://127.0.0.1:8765/docs` | Swagger OpenAPI specification and live query explorer. | *None (loopback only)* |
| **Health Check** | `http://127.0.0.1:8765/health` | Daemon heartbeat and overall SRE system status. | *None (loopback only)* |

---

## 4. CLI Commands & Options

```bash
# Health check all Docker containers and daemon HTTP endpoints
uv run run.py --status

# Run daemon only without Docker (for CI or external observability)
uv run run.py --no-stack

# Start Docker containers only and leave them running
uv run run.py --stack-only

# Stop Docker containers (preserves container state)
uv run run.py --stop

# Teardown Docker containers and network
uv run run.py --down

# Teardown Docker containers and purge persistent data volumes
uv run run.py --clean

# Run with synthetic test probes for a fixed 10-second duration
uv run run.py --synthetic --duration 10
```

---

## 5. Architectural Guarantees & Privacy

1. **Zero Content Capture**: Never records key characters, scancodes, clipboard text, window titles, or URLs.
2. **Sanitized Process Basenames Only**: Only process binaries are identified (e.g., `Code.exe`, `terminal`).
3. **Strict Loopback Binding (`127.0.0.1`)**: All services bind exclusively to localhost.
4. **4 Physical Dimensions (Zero Speculation)**:
   - **Temporal**: Duty Cycle (% active time) & Idle time.
   - **Attentional**: Context-switching velocity & Shannon entropy thrashing.
   - **Psychomotor**: Inter-keystroke interval CV (jitter) & Backspace/Delete correction ratio (friction).
   - **Session Uptime**: Uninterrupted load duration.

---

## 6. Verification & Quality Gates

Run the automated test and quality gate pipeline:

```bash
# 1. Format check
uv run ruff format --check .

# 2. Linting
uv run ruff check .

# 3. Strict static type analysis
uv run mypy --strict app tests run.py

# 4. Unit tests and coverage floor (>= 90%)
uv run pytest --cov=app --cov-fail-under=90
```
