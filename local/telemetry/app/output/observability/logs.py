"""Structured JSON SRE logger for Loki and console observability."""

import json
import logging
from typing import Any

from app.common.models import CognitiveStrainReport, PooledTelemetryMetrics


class SREEventLogger:
    """Emits structured JSON logs tailored for Grafana Loki ingestion."""

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        service_name: str = "egg-telemetry",
    ) -> None:
        self._logger = logger if logger is not None else logging.getLogger("egg.sre")
        self._service = service_name

    def _emit(self, level: int, payload: dict[str, Any]) -> None:
        """Format event dictionary with standard SRE labels and output as JSON."""
        enriched = {
            "service": self._service,
            **payload,
        }
        self._logger.log(level, json.dumps(enriched, sort_keys=True))

    def log_session_heartbeat(
        self,
        metrics: PooledTelemetryMetrics,
        report: CognitiveStrainReport,
        session_uptime_seconds: float,
        active_work_seconds: float,
    ) -> None:
        """Log calm periodic session heartbeat for Loki observability."""
        self._emit(
            logging.INFO,
            {
                "event": "session_heartbeat",
                "primary_process": metrics.primary_process,
                "active_work_minutes": round(active_work_seconds / 60.0, 1),
                "continuous_uptime_minutes": round(session_uptime_seconds / 60.0, 1),
                "duty_cycle": metrics.duty_cycle,
                "shannon_entropy": metrics.shannon_entropy,
                "workflow_state": report.dominant_state_label,
                "sre_status": report.sre_status,
                "message": (
                    f"Active in {metrics.primary_process} "
                    f"({round(active_work_seconds / 60.0, 1)}m active work today, "
                    f"{report.dominant_state_label})."
                ),
            },
        )

    def log_focus_switch(
        self,
        from_app: str,
        to_app: str,
    ) -> None:
        """Log active foreground application switch."""
        self._emit(
            logging.INFO,
            {
                "event": "focus_switch",
                "from_process": from_app,
                "to_process": to_app,
                "message": f"Focus shifted from {from_app} to {to_app}.",
            },
        )

    def log_state_tick(
        self,
        metrics: PooledTelemetryMetrics,
        report: CognitiveStrainReport,
        session_uptime_seconds: float,
    ) -> None:
        """Log regular periodic state evaluation."""
        self._emit(
            logging.INFO,
            {
                "event": "cognitive_state_tick",
                "primary_process": metrics.primary_process,
                "duty_cycle": metrics.duty_cycle,
                "shannon_entropy": metrics.shannon_entropy,
                "correction_ratio": metrics.correction_ratio,
                "iki_cv": metrics.iki_cv,
                "overall_strain": report.overall_strain_score,
                "sre_status": report.sre_status,
                "session_uptime_seconds": round(session_uptime_seconds, 1),
            },
        )

    def log_excursion_absorbed(
        self,
        primary_app: str,
        excursion_app: str,
        duration_seconds: float,
    ) -> None:
        """Log transient excursion absorbed by the hysteresis debouncer."""
        self._emit(
            logging.INFO,
            {
                "event": "excursion_absorbed",
                "primary_process": primary_app,
                "excursion_process": excursion_app,
                "duration_seconds": round(duration_seconds, 2),
                "message": (
                    f"Transient excursion ({duration_seconds:.1f}s) in {excursion_app} "
                    f"absorbed into {primary_app} focus."
                ),
            },
        )

    def log_sre_alert(
        self,
        severity: str,
        report: CognitiveStrainReport,
        primary_app: str,
    ) -> None:
        """Log objective SRE alert on high cognitive strain."""
        level = logging.WARNING if severity == "warning" else logging.ERROR
        self._emit(
            level,
            {
                "event": "sre_alert",
                "severity": severity,
                "primary_process": primary_app,
                "overall_strain": report.overall_strain_score,
                "dominant_state": report.dominant_state_label,
                "triggered_dimensions": list(report.triggered_dimensions),
                "alert_reason": report.sre_alert_reason,
                "message": report.sre_alert_reason,
            },
        )
