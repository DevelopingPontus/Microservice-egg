"""OpenTelemetry Focus Session & App Dwell Tracing (Tempo integration)."""

import time
from typing import Any

from opentelemetry.trace import Span, StatusCode, Tracer


class FocusSessionTracer:
    """Tracks continuous application focus sessions as OpenTelemetry Spans."""

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer
        self._current_span: Span | None = None
        self._current_app: str | None = None
        self._span_start_time: float | None = None

    def start_or_switch_focus(
        self,
        app_name: str,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Start or transition focus to a new active application span."""
        sanitized = app_name.strip() or "unknown"
        if self._current_app == sanitized and self._current_span is not None:
            return  # Still in the same application span

        # End existing span if switching apps
        self.end_current_focus(attributes=attributes)

        # Start new focus span
        self._current_app = sanitized
        self._span_start_time = time.monotonic()
        span = self._tracer.start_span(
            f"focus_session:{sanitized}",
            attributes={
                "app.name": sanitized,
                "session.type": "active_window",
            },
        )
        self._current_span = span

    def record_excursion(
        self,
        excursion_app: str,
        duration_seconds: float,
        *,
        excursion_type: str = "app_switch",
    ) -> None:
        """Record an absorbed transient excursion as a child span/event in Tempo."""
        if self._current_span is not None:
            self._current_span.add_event(
                "excursion_absorbed",
                attributes={
                    "excursion.app": excursion_app,
                    "excursion.duration_seconds": round(duration_seconds, 2),
                    "excursion.type": excursion_type,
                },
            )

    def end_current_focus(self, *, attributes: dict[str, Any] | None = None) -> None:
        """End the currently active focus span."""
        if self._current_span is not None:
            if attributes:
                for k, v in attributes.items():
                    self._current_span.set_attribute(k, v)
            if self._span_start_time is not None:
                duration = time.monotonic() - self._span_start_time
                self._current_span.set_attribute("focus.duration_seconds", round(duration, 2))
            self._current_span.set_status(StatusCode.OK)
            self._current_span.end()
            self._current_span = None
            self._current_app = None
            self._span_start_time = None
