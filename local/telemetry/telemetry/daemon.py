"""Daemon coordinator tying Phases 1-6 together with graceful shutdown."""

from __future__ import annotations

import logging
import signal
import threading
from pathlib import Path

from prometheus_client import CollectorRegistry

from telemetry.collectors import (
    ActivityTracker,
    KeystrokeCollector,
    MouseCollector,
    WindowFocusCollector,
)
from telemetry.db import BatchWriter
from telemetry.evaluator import FatigueEvaluator
from telemetry.observability import DaemonObservability
from telemetry.webcam import WebcamOculometricsCollector

log = logging.getLogger(__name__)


class TelemetryDaemon:
    """Runs the local collector + SQLite WAL writer + rolling Prometheus evaluator."""

    def __init__(
        self,
        db_path: str | Path = "data/telemetry.db",
        flush_interval_s: float = 5.0,
        retention_days: int = 14,
        eval_interval_s: float = 60.0,
        prometheus_port: int = 9105,
        enable_evaluator: bool = True,
        enable_webcam: bool = False,
    ) -> None:
        self.db_path = Path(db_path)
        self.registry = CollectorRegistry()
        self.obs = DaemonObservability(self.registry)
        self.writer = BatchWriter(
            db_path=self.db_path,
            flush_interval_s=flush_interval_s,
            retention_days=retention_days,
            observability=self.obs,
        )
        self.activity = ActivityTracker()
        self.keystrokes = KeystrokeCollector(self.writer, self.activity)
        self.mouse = MouseCollector(self.writer, self.activity)
        self.windows = WindowFocusCollector(self.writer, self.activity)
        self.webcam = WebcamOculometricsCollector(self.writer) if enable_webcam else None
        self.evaluator = (
            FatigueEvaluator(
                db_path=self.db_path,
                eval_interval_s=eval_interval_s,
                prometheus_port=prometheus_port,
                registry=self.registry,
                observability=self.obs,
                on_confirm_needed=(self.webcam.trigger_burst if self.webcam is not None else None),
            )
            if enable_evaluator
            else None
        )
        self._stop_event = threading.Event()

    def start(self) -> None:
        log.info("Starting telemetry daemon (db=%s)", self.db_path)
        self.writer.start()
        self.keystrokes.start()
        self.mouse.start()
        self.windows.start()
        if self.webcam is not None:
            log.info("Webcam enabled in on-demand confirmation mode (60s burst, 10m cooldown).")
        if self.evaluator is not None:
            self.evaluator.start(start_http=True)
            log.info(
                "Prometheus metrics exposed at http://%s:%d/metrics",
                self.evaluator.prometheus_host,
                self.evaluator.prometheus_port,
            )

    def stop(self) -> None:
        log.info("Stopping telemetry daemon...")
        self.keystrokes.stop()
        self.mouse.stop()
        self.windows.stop()
        if self.evaluator is not None:
            self.evaluator.stop()
        if self.webcam is not None:
            self.webcam.stop()
        self.writer.stop()
        log.info("Telemetry daemon stopped cleanly.")

    def run_forever(self) -> None:
        def _handle_signal(signum: int, _frame: object) -> None:
            log.info("Received signal %d, shutting down...", signum)
            self._stop_event.set()

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        self.start()
        try:
            while not self._stop_event.wait(1.0):
                pass
        finally:
            self.stop()
