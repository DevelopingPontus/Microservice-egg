# Global Monorepo & DevOps Rules (`Microservice-egg`)

You are working inside `Microservice-egg`, a domain-scoped multi-service monorepo for the **Cognitive Telemetry & Activity Block Platform**. Always adhere to these global engineering, privacy, and DevOps standards across all directories.

## 1. Monorepo Architecture & Context Boundaries

- **`telemetry/daemon/`**: Local-first 30-second micro-epoch ingestion daemon. Collects hardware/window activity via protocol interfaces and writes lossless algebraic primitives to SQLite (`epoch_metrics_30s` in WAL mode).
- **`telemetry/api/`**: Downstream FastAPI consumer, Pluggable Scientific Dimension Engine (`BaseDimension` / `DimensionRegistry`), and 60s/90s Activity Block Chunker (`activity_blocks`).
- **Service Isolation**: Each service folder (`telemetry/daemon/`, `telemetry/api/`) manages its own isolated Python environment via `uv` (`pyproject.toml` and `uv.lock`). Never mix or import internal application packages directly across service boundaries; services communicate strictly through the shared SQLite WAL datastore and documented schemas.

## 2. Uncompromised Privacy & Security Invariants

1. **Zero Keystroke Content**: Never capture, log, buffer, or store key characters, key codes, scancodes, or clipboard text anywhere in any service.
2. **Strict Process Sanitization**: Never capture or store window titles, file names, or URLs. Resolve active windows strictly to sanitized executable or bundle names (e.g., `Code.exe`, `Slack.app`, `firefox`).
3. **Localhost Binding Only**: Any HTTP server, metrics exporter, or API endpoint must bind strictly to `127.0.0.1` by default—never `0.0.0.0` on host interfaces unless explicitly inside an isolated container bridge.

## 3. DevOps Toolchain & Mandatory Verification Loop

All Python services in this repository standardize on **`uv`** (`/Users/pontus/.local/bin/uv`).

- **Dependency Management**: Always use `uv init`, `uv add`, `uv add --dev`, and `uv sync` within the target service directory. Never use raw `pip install` or global Python packages.
- **Mandatory Quality Gates**: Before marking any code implementation or sprint task complete, you **MUST** run and pass all three verification steps inside the modified service directory:
  1. **Lint & Format (`ruff`)**:
     - `uv run ruff check .`
     - `uv run ruff format --check .`
  2. **Strict Static Typing (`mypy`)**:
     - `uv run mypy --strict app tests`
  3. **Automated Tests & Coverage (`pytest`)**:
     - `uv run pytest --cov=app --cov-fail-under=90`

## 4. CI/CD, Container Readiness & Sprint Reporting

- **Headless Testability**: Every component must run deterministically in headless Linux Docker containers and CI runners without requiring a physical display server (`$DISPLAY`), accessibility permissions, or physical keyboard/mouse hardware.
- **Git Hygiene**: Keep commits atomic and scoped to a single service or infrastructure concern. Never commit `.venv/`, `__pycache__/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, or `*.db` / `*.db-wal` / `*.db-shm` SQLite files.
- **Sprint Progress Reports (`reports/`)**: At the conclusion of every sprint, create a new numbered report in `/Users/pontus/projects/Microservice-egg/reports/` following the template in `reports/README.md` (including verification metrics, architectural decisions, a 6–8 slide LinkedIn carousel script, and post copy).
