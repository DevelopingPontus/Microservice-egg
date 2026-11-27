"""DevOps / SRE operational observability metrics for the telemetry daemon.

Why these metrics?
------------------
In DevOps/SRE, service health is commonly monitored with the **RED method**
(Rate, Errors, Duration) plus **saturation/capacity** signals:

1. **Counter vs. Gauge** (Prometheus fundamentals):
   - A `Counter` only ever goes up (e.g., total events flushed, total errors).
     In PromQL you wrap counters in `rate(...[5m])` or `increase(...[5m])`
     so restarts/resets are handled automatically.
   - A `Gauge` can go up or down (e.g., queue depth, DB size, latency of the
     last operation, uptime).

2. **What each metric diagnoses**:
   - `events_enqueued` / `events_flushed` (Rate): If `raw_keystrokes` is 0
     while you type, OS input permissions are broken. If `enqueued >> flushed`,
     the SQLite writer thread is stuck.
   - `queue_size` (Saturation / Backpressure): Buffers bursts in memory.
     If it climbs steadily instead of draining to 0 every 5s, disk I/O is
     falling behind.
   - `flush_duration_s` / `eval_duration_s` (Duration / Latency): Catches
     SQLite lock contention or slow queries as 14 days of data accumulate.
   - `db_size_bytes` (Capacity): Verifies 14-day pruning keeps disk usage
     bounded (includes `-wal` and `-shm` files).
   - `uptime_seconds` & `last_eval_ts` (Liveness / Heartbeat): Detects silent
     crash-loops (`uptime` resetting to 0) or a frozen evaluator thread
     (`time() - last_eval_ts > 120s`).
   - `errors_total` (Errors): Counts exceptions by component (`writer`,
     `evaluator`) so failures are visible in Grafana instead of hidden in logs.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from prometheus_client import CollectorRegistry, Counter, Gauge


class DaemonObservability:
    """Prometheus operational metrics: RED (Rate, Errors, Duration) + Saturation."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self._start_ts = time.time()

        # RATE (Counters): monotonically increasing; query with rate(...[5m]) in PromQL.
        self.events_enqueued = Counter(
            "telemetry_events_enqueued_total",
            "Total raw telemetry events enqueued by collectors",
            ["table"],
            registry=registry,
        )
        self.events_flushed = Counter(
            "telemetry_events_flushed_total",
            "Total raw telemetry events written to SQLite",
            ["table"],
            registry=registry,
        )

        # SATURATION (Gauge): in-memory backpressure; should drain to 0 every 5s.
        self.queue_size = Gauge(
            "telemetry_writer_queue_size",
            "Current number of buffered events waiting in BatchWriter queue",
            registry=registry,
        )

        # DURATION (Gauges): execution time of the two main I/O paths.
        self.flush_duration_s = Gauge(
            "telemetry_db_flush_duration_seconds",
            "Duration of the most recent SQLite batch flush in seconds",
            registry=registry,
        )
        self.eval_duration_s = Gauge(
            "telemetry_eval_duration_seconds",
            "Duration of the most recent rolling fatigue evaluation in seconds",
            registry=registry,
        )

        # CAPACITY & LIVENESS (Gauges): disk footprint, process uptime, and heartbeat.
        self.db_size_bytes = Gauge(
            "telemetry_db_size_bytes",
            "Current SQLite database size on disk in bytes (including WAL)",
            registry=registry,
        )
        self.uptime_seconds = Gauge(
            "telemetry_daemon_uptime_seconds",
            "Seconds since the telemetry daemon started",
            registry=registry,
        )
        self.last_eval_ts = Gauge(
            "telemetry_last_eval_timestamp_seconds",
            "Unix timestamp of the most recent successful evaluation",
            registry=registry,
        )

        # ERRORS (Counter): labeled by component so you know *where* a failure happened.
        self.errors_total = Counter(
            "telemetry_errors_total",
            "Total runtime errors by component",
            ["component"],
            registry=registry,
        )

    def refresh_system_gauges(self, db_path: Path) -> None:
        """Update uptime and SQLite (+WAL/-shm) file size gauges."""
        self.uptime_seconds.set(round(time.time() - self._start_ts, 1))
        total_bytes = 0
        # In WAL mode, SQLite splits data across .db, .db-wal, and .db-shm.
        for suffix in ("", "-wal", "-shm"):
            p = Path(f"{db_path}{suffix}")
            if p.exists():
                total_bytes += os.path.getsize(p)
        self.db_size_bytes.set(total_bytes)
