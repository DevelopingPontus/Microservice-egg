"""Prometheus and OpenTelemetry recorder for temporal and session duration metrics."""

from collections.abc import Callable, Iterable

from opentelemetry.metrics import CallbackOptions, Meter, Observation
from prometheus_client import CollectorRegistry, Gauge

from app.features.session_duration.models import RawTemporalSessionMetrics

_SCALAR_SPECS: tuple[tuple[str, str, str], ...] = (
    ("user_window_active_seconds", "Active interaction seconds in current sample.", "s"),
    ("user_window_duration_seconds", "Total elapsed duration of current sample.", "s"),
    ("user_session_uptime_seconds", "Continuous session uptime in seconds.", "s"),
    ("user_active_work_seconds", "Total active working time in seconds with thought grace.", "s"),
    ("user_away_idle_seconds", "Total away/idle seconds beyond thought grace.", "s"),
)


class SessionDurationRecorder:
    """Records session duration and active/idle metrics into Prometheus and OpenTelemetry."""

    def __init__(self, meter: Meter, registry: CollectorRegistry) -> None:
        self._meter = meter
        self._registry = registry

        self._current_values: dict[str, float] = {name: 0.0 for name, _, _ in _SCALAR_SPECS}
        self._prom_gauges: dict[str, Gauge] = {}
        for name, desc, unit in _SCALAR_SPECS:
            self._prom_gauges[name] = Gauge(f"egg_{name}", desc, registry=self._registry)
            meter.create_observable_gauge(
                name,
                callbacks=[self._make_callback(name)],
                description=desc,
                unit=unit,
            )

    def _make_callback(self, key: str) -> Callable[[CallbackOptions], Iterable[Observation]]:
        def _cb(_opts: CallbackOptions) -> Iterable[Observation]:
            yield Observation(self._current_values.get(key, 0.0))

        return _cb

    def record(self, metrics: RawTemporalSessionMetrics) -> None:
        """Record session duration metrics."""
        updates = {
            "user_window_active_seconds": metrics.window_active_seconds,
            "user_window_duration_seconds": metrics.window_duration_seconds,
            "user_session_uptime_seconds": metrics.session_uptime_seconds,
            "user_active_work_seconds": metrics.active_work_seconds,
            "user_away_idle_seconds": metrics.away_idle_seconds,
        }
        for k, val in updates.items():
            self._current_values[k] = val
            self._prom_gauges[k].set(val)
