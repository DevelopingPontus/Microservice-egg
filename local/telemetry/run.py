"""CLI entrypoint for the local fatigue telemetry daemon."""

from __future__ import annotations

import argparse
import logging

from telemetry import TelemetryDaemon


def main() -> None:
    parser = argparse.ArgumentParser(description="Local fatigue telemetry collector & evaluator")
    parser.add_argument("--db", default="data/telemetry.db", help="Path to SQLite WAL database")
    parser.add_argument("--flush-interval", type=float, default=5.0, help="SQLite batch flush interval (s)")
    parser.add_argument("--retention-days", type=int, default=14, help="Raw telemetry retention in days")
    parser.add_argument("--eval-interval", type=float, default=60.0, help="Fatigue evaluation interval (s)")
    parser.add_argument("--port", type=int, default=9105, help="Prometheus metrics port on 127.0.0.1")
    parser.add_argument("--collector-only", action="store_true", help="Disable Phase 6 evaluator/exporter")
    parser.add_argument("--enable-webcam", action="store_true", help="Opt-in local webcam oculometrics")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    daemon = TelemetryDaemon(
        db_path=args.db,
        flush_interval_s=args.flush_interval,
        retention_days=args.retention_days,
        eval_interval_s=args.eval_interval,
        prometheus_port=args.port,
        enable_evaluator=not args.collector_only,
        enable_webcam=args.enable_webcam,
    )
    daemon.run_forever()


if __name__ == "__main__":
    main()
