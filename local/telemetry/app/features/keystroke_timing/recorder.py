"""Prometheus and OpenTelemetry recorder for keystroke timing metrics."""

from collections.abc import Callable, Iterable

from opentelemetry.metrics import CallbackOptions, Meter, Observation
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from app.features.keystroke_timing.models import RawKeystrokeTimingMetrics

_SCALAR_SPECS: tuple[tuple[str, str, str], ...] = (
    ("user_iki_mean_ms", "Mean inter-keystroke interval in milliseconds.", "ms"),
    ("user_iki_std_dev_ms", "Standard deviation of inter-keystroke intervals (ms).", "ms"),
    ("user_iki_mad_ms", "Median absolute deviation (MAD) of inter-keystroke intervals (ms).", "ms"),
    ("user_iki_sample_count", "Number of valid IKI pairs in current sample.", "1"),
    ("user_hold_time_ms", "Median key hold/dwell time in ms.", "ms"),
    ("user_flight_time_ms", "Median key flight time in ms.", "ms"),
    ("user_window_keystrokes", "Keystrokes recorded.", "1"),
)


class KeystrokeTimingRecorder:
    """Records keystroke timing metrics into Prometheus and OpenTelemetry."""

    def __init__(self, meter: Meter, registry: CollectorRegistry) -> None:
        self._meter = meter
        self._registry = registry

        self._otel_counter = meter.create_counter(
            "user_keystrokes_total", description="Total keystrokes recorded.", unit="1"
        )
        self._prom_counter = Counter(
            "egg_user_keystrokes_total", "Total keystrokes recorded.", registry=self._registry
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

        self._otel_iki_hist = meter.create_histogram(
            "user_iki_ms", description="Raw inter-keystroke intervals.", unit="ms"
        )
        self._prom_iki_hist = Histogram(
            "egg_user_iki_ms",
            "Raw inter-keystroke intervals.",
            buckets=(20.0, 40.0, 60.0, 80.0, 100.0, 150.0, 200.0, 300.0, 500.0, 1000.0, 2000.0),
            registry=self._registry,
        )

        self._otel_hold_hist = meter.create_histogram(
            "user_hold_time_hist_ms", description="Raw key hold durations.", unit="ms"
        )
        self._prom_hold_hist = Histogram(
            "egg_user_hold_time_hist_ms",
            "Raw key hold durations.",
            buckets=(20.0, 40.0, 60.0, 80.0, 100.0, 120.0, 150.0, 200.0, 300.0),
            registry=self._registry,
        )

        self._otel_flight_hist = meter.create_histogram(
            "user_flight_time_hist_ms", description="Raw key flight durations.", unit="ms"
        )
        self._prom_flight_hist = Histogram(
            "egg_user_flight_time_hist_ms",
            "Raw key flight durations.",
            buckets=(20.0, 40.0, 60.0, 80.0, 100.0, 150.0, 250.0, 500.0, 1000.0),
            registry=self._registry,
        )

    def _make_callback(self, key: str) -> Callable[[CallbackOptions], Iterable[Observation]]:
        def _cb(_opts: CallbackOptions) -> Iterable[Observation]:
            yield Observation(self._current_values.get(key, 0.0))

        return _cb

    def record(self, metrics: RawKeystrokeTimingMetrics, *, keystroke_delta: int = 0) -> None:
        """Record keystroke timing metrics."""
        if keystroke_delta > 0:
            self._otel_counter.add(keystroke_delta)
            self._prom_counter.inc(keystroke_delta)

        for v in metrics.iki_values_ms:
            self._otel_iki_hist.record(v)
            self._prom_iki_hist.observe(v)

        for v in metrics.hold_times_ms:
            self._otel_hold_hist.record(v)
            self._prom_hold_hist.observe(v)

        for v in metrics.flight_times_ms:
            self._otel_flight_hist.record(v)
            self._prom_flight_hist.observe(v)

        updates = {
            "user_iki_mean_ms": metrics.iki_mean_ms,
            "user_iki_std_dev_ms": metrics.iki_std_dev_ms,
            "user_iki_mad_ms": metrics.iki_mad_ms,
            "user_iki_sample_count": float(metrics.iki_count),
            "user_hold_time_ms": metrics.hold_time_median_ms,
            "user_flight_time_ms": metrics.flight_time_median_ms,
            "user_window_keystrokes": float(metrics.total_keystrokes),
        }
        for k, val in updates.items():
            self._current_values[k] = val
            self._prom_gauges[k].set(val)
