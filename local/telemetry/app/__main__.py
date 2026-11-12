"""Standalone entry point for `local/telemetry/app` (`uv run python -m app`)."""

import asyncio
import contextlib
from collections.abc import Sequence

from app.service import run_from_cli


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the standalone telemetry daemon from the CLI."""
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run_from_cli(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
