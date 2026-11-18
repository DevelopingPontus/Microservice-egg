"""Prometheus and OpenTelemetry recorder for correction and pause metrics."""

from collections.abc import Callable, Iterable

from opentelemetry.metrics import CallbackOptions, Meter, Observation
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from app.features.correction_pauses.models import RawCorrectionPauseMetrics

_SCALAR_SPECS: tuple[tuple[str, str, str], ...] = (
    ("user_pre_correction_pause_ms", "Median IKI before correction keystrokes.", "ms"),
    ("user_post_correction_pause_ms", "Median IKI after correction keystrokes.", "ms"),
    ("user_window_corrections", "Correction keystrokes recorded.", "1"),
    ("user_micro_pauses_window", "Count of 1-5s micro-pauses recorded.", "1"),
    ("user_pauses_gt_2s_window", "Typing pauses longer than 2s recorded.", "1"),
    ("user_bursts_window", "Typing bursts between >2s pauses recorded.", "1"),
)


class CorrectionPauseRecorder:
    """Records correction and pause metrics into Prometheus and OpenTelemetry."""

    def __init__(self, meter: Meter, registry: CollectorRegistry) -> None:
        self._meter = meter
        self._registry = registry

        self._otel_counter = meter.create_counter(
            "user_corrections_total",
            description="Total backspace and delete keystrokes recorded.",
            unit="1",
        )
        self._prom_counter = Counter(
            "egg_user_corrections_total",
            "Total backspace and delete keystrokes recorded.",
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

        self._otel_pre_hist = meter.create_histogram(
            "user_pre_correction_pause_hist_ms",
            description="Raw pre-correction pause durations.",
            unit="ms",
        )
        self._prom_pre_hist = Histogram(
            "egg_user_pre_correction_pause_hist_ms",
            "Raw pre-correction pause durations.",
            buckets=(50.0, 100.0, 200.0, 350.0, 500.0, 750.0, 1000.0, 2000.0),
            registry=self._registry,
        )

        self._otel_post_hist = meter.create_histogram(
            "user_post_correction_pause_hist_ms",
            description="Raw post-correction pause durations.",
            unit="ms",
        )
        self._prom_post_hist = Histogram(
            "egg_user_post_correction_pause_hist_ms",
            "Raw post-correction pause durations.",
            buckets=(50.0, 100.0, 200.0, 350.0, 500.0, 750.0, 1000.0, 2000.0),
            registry=self._registry,
        )

    def _make_callback(self, key: str) -> Callable[[CallbackOptions], Iterable[Observation]]:
        def _cb(_opts: CallbackOptions) -> Iterable[Observation]:
            yield Observation(self._current_values.get(key, 0.0))

        return _cb

    def record(self, metrics: RawCorrectionPauseMetrics, *, correction_delta: int = 0) -> None:
        """Record correction and pause metrics."""
        if correction_delta > 0:
            self._otel_counter.add(correction_delta)
            self._prom_counter.inc(correction_delta)

        for v in metrics.pre_correction_pauses_ms:
            self._otel_pre_hist.record(v)
            self._prom_pre_hist.observe(v)

        for v in metrics.post_correction_pauses_ms:
            self._otel_post_hist.record(v)
            self._prom_post_hist.observe(v)

        updates = {
            "user_pre_correction_pause_ms": metrics.pre_correction_pause_median_ms,
            "user_post_correction_pause_ms": metrics.post_correction_pause_median_ms,
            "user_window_corrections": float(metrics.correction_keystrokes),
            "user_micro_pauses_window": float(metrics.micro_pauses_count),
            "user_pauses_gt_2s_window": float(metrics.pauses_gt_2s_count),
            "user_bursts_window": float(metrics.burst_count),
        }
        for k, val in updates.items():
            self._current_values[k] = val
            self._prom_gauges[k].set(val)
