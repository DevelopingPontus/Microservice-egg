"""Prometheus and OpenTelemetry recorder for mouse kinematics metrics."""

from collections.abc import Callable, Iterable

from opentelemetry.metrics import CallbackOptions, Meter, Observation
from prometheus_client import CollectorRegistry, Counter, Gauge

from app.features.mouse_kinematics.models import RawMouseKinematicsMetrics

_SCALAR_SPECS: tuple[tuple[str, str, str], ...] = (
    ("user_mouse_sample_entropy", "Mouse velocity Sample Entropy (raw).", "1"),
    ("user_mouse_submovements_window", "Acceleration zero-crossings recorded.", "1"),
    ("user_mouse_curvature_auc", "Mouse trajectory curvature ratio.", "1"),
    ("user_mouse_x_flips_window", "Horizontal directional reversals recorded.", "1"),
    ("user_window_mouse_clicks", "Mouse clicks recorded.", "1"),
    ("user_window_scroll_events", "Scroll events recorded.", "1"),
)


class MouseKinematicsRecorder:
    """Records mouse kinematics metrics into Prometheus and OpenTelemetry."""

    def __init__(self, meter: Meter, registry: CollectorRegistry) -> None:
        self._meter = meter
        self._registry = registry

        self._otel_click_counter = meter.create_counter(
            "user_mouse_clicks_total", description="Total mouse button presses recorded.", unit="1"
        )
        self._prom_click_counter = Counter(
            "egg_user_mouse_clicks_total",
            "Total mouse button presses recorded.",
            registry=self._registry,
        )

        self._otel_scroll_counter = meter.create_counter(
            "user_scroll_events_total", description="Total scroll events recorded.", unit="1"
        )
        self._prom_scroll_counter = Counter(
            "egg_user_scroll_events_total",
            "Total scroll events recorded.",
            registry=self._registry,
        )

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

    def record(
        self,
        metrics: RawMouseKinematicsMetrics,
        *,
        mouse_click_delta: int = 0,
        scroll_delta: int = 0,
    ) -> None:
        """Record mouse kinematics metrics."""
        if mouse_click_delta > 0:
            self._otel_click_counter.add(mouse_click_delta)
            self._prom_click_counter.inc(mouse_click_delta)

        if scroll_delta > 0:
            self._otel_scroll_counter.add(scroll_delta)
            self._prom_scroll_counter.inc(scroll_delta)

        updates = {
            "user_mouse_sample_entropy": metrics.sample_entropy,
            "user_mouse_submovements_window": float(metrics.submovements),
            "user_mouse_curvature_auc": metrics.curvature_auc,
            "user_mouse_x_flips_window": float(metrics.x_flips),
            "user_window_mouse_clicks": float(metrics.mouse_clicks),
            "user_window_scroll_events": float(metrics.scroll_events),
        }
        for k, val in updates.items():
            self._current_values[k] = val
            self._prom_gauges[k].set(val)
