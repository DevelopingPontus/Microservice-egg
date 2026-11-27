#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PY_BIN=".venv/bin/python"
[[ -x "$PY_BIN" ]] || PY_BIN="$(command -v python3.12 || command -v python3)"
exec "$PY_BIN" cli.py "$@"
