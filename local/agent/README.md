# `telemetry/daemon` — Cognitive Telemetry Epoch Ingestion Service

Local-first, privacy-by-construction 30-second micro-epoch telemetry ingestion daemon.

## Quality Gates & Verification Commands

All commands are executed inside `telemetry/daemon/` using `uv`:

```bash
# 1. Sync dependencies
uv sync

# 2. Lint & Format Check
uv run ruff check .
uv run ruff format --check .

# 3. Strict Static Type Checking
uv run mypy --strict app tests

# 4. Run Automated Tests with Coverage Gate (>=90%)
uv run pytest --cov=app --cov-fail-under=90
```
