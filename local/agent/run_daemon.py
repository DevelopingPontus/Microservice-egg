"""CLI entry point for the EGG 30-second cognitive telemetry daemon."""

import asyncio
import sys
from collections.abc import Sequence

from app.service import run_from_cli


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local cognitive telemetry daemon from the command line."""
    diagnostics = asyncio.run(run_from_cli(argv))
    sys.stdout.write(
        "EGG telemetry daemon exited cleanly "
        f"(epochs_flushed={diagnostics.epochs_flushed_total}, "
        f"window_ticks={diagnostics.window_ticks_total}, "
        f"last_flush_ms={diagnostics.last_flush_duration_ms:.2f})\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
