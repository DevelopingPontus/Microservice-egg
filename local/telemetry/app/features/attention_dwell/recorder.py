"""Prometheus and OpenTelemetry recorder for attention and window dwell metrics."""

from collections.abc import Callable, Iterable

from opentelemetry.metrics import CallbackOptions, Meter, Observation
from prometheus_client import CollectorRegistry, Counter, Gauge

from app.features.attention_dwell.models import RawAttentionWindowMetrics

_SCALAR_SPECS: tuple[tuple[str, str, str], ...] = (
    ("user_shannon_entropy_bits", "Shannon attentional entropy across active apps.", "bits"),
    ("user_primary_process_dwell_seconds", "Dwell seconds of primary process.", "s"),
    ("user_active_processes_count", "Distinct active processes recorded.", "1"),
    ("user_window_context_switches", "Context switches recorded.", "1"),
)


class AttentionDwellRecorder:
    """Records attentional entropy and process dwell metrics into Prometheus and OpenTelemetry."""

    def __init__(self, meter: Meter, registry: CollectorRegistry) -> None:
        self._meter = meter
        self._registry = registry

        self._otel_counter = meter.create_counter(
            "user_context_switches_total",
            description="Total window context switches recorded.",
            unit="1",
        )
        self._prom_counter = Counter(
            "egg_user_context_switches_total",
            "Total window context switches recorded.",
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

        self._process_dwells: dict[str, float] = {}
        self._prom_process_dwell = Gauge(
            "egg_user_process_dwell_seconds",
            "Per-process dwell seconds.",
            labelnames=("process",),
            registry=self._registry,
        )
        meter.create_observable_gauge(
            "user_process_dwell_seconds",
            callbacks=[self._observe_process_dwell],
            description="Per-process dwell seconds.",
            unit="s",
        )

    def _make_callback(self, key: str) -> Callable[[CallbackOptions], Iterable[Observation]]:
        def _cb(_opts: CallbackOptions) -> Iterable[Observation]:
            yield Observation(self._current_values.get(key, 0.0))

        return _cb

    def _observe_process_dwell(self, _options: CallbackOptions) -> Iterable[Observation]:
        for proc_name, secs in self._process_dwells.items():
            yield Observation(secs, {"process": proc_name})

    def record(self, metrics: RawAttentionWindowMetrics, *, context_switch_delta: int = 0) -> None:
        """Record attention window and process dwell metrics."""
        if context_switch_delta > 0:
            self._otel_counter.add(context_switch_delta)
            self._prom_counter.inc(context_switch_delta)

        updates = {
            "user_shannon_entropy_bits": metrics.shannon_entropy_bits,
            "user_primary_process_dwell_seconds": metrics.primary_process_dwell_seconds,
            "user_active_processes_count": float(metrics.distinct_processes_count),
            "user_window_context_switches": float(metrics.context_switches),
        }
        for k, val in updates.items():
            self._current_values[k] = val
            self._prom_gauges[k].set(val)

        for old_proc in list(self._process_dwells):
            if old_proc not in metrics.merged_dwell_seconds:
                self._process_dwells[old_proc] = 0.0
                self._prom_process_dwell.labels(process=old_proc).set(0.0)
        for proc_name, dwell_sec in metrics.merged_dwell_seconds.items():
            rounded_dwell = round(dwell_sec, 2)
            self._process_dwells[proc_name] = rounded_dwell
            self._prom_process_dwell.labels(process=proc_name).set(rounded_dwell)
