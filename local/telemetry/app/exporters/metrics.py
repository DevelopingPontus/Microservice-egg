"""Declarative OpenTelemetry & Prometheus recorder for independent raw metrics."""

from collections.abc import Callable, Iterable, Mapping

from opentelemetry.metrics import CallbackOptions, Meter, Observation
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from app.collector import (
    RawAttentionWindowMetrics,
    RawCorrectionPauseMetrics,
    RawKeystrokeTimingMetrics,
    RawMouseKinematicsMetrics,
    RawTemporalSessionMetrics,
)

_COUNTER_SPECS: tuple[tuple[str, str], ...] = (
    ("user_keystrokes_total", "Total keystrokes recorded."),
    ("user_corrections_total", "Total backspace and delete keystrokes recorded."),
    ("user_mouse_clicks_total", "Total mouse button presses recorded."),
    ("user_scroll_events_total", "Total scroll events recorded."),
    ("user_context_switches_total", "Total window context switches recorded."),
)

_SCALAR_GAUGE_SPECS: tuple[tuple[str, str, str], ...] = (
    # 1. Keystroke Timing (raw ms & counts)
    ("user_iki_mean_ms", "Mean inter-keystroke interval in milliseconds.", "ms"),
    ("user_iki_std_dev_ms", "Standard deviation of inter-keystroke intervals (ms).", "ms"),
    ("user_iki_mad_ms", "Median absolute deviation (MAD) of inter-keystroke intervals (ms).", "ms"),
    ("user_iki_sample_count", "Number of valid IKI pairs in current sliding window.", "1"),
    ("user_hold_time_ms", "Median key hold/dwell time (KeyUp minus KeyDown) in ms.", "ms"),
    ("user_flight_time_ms", "Median key flight time (next KeyDown minus prev KeyUp) in ms.", "ms"),
    ("user_window_keystrokes", "Keystrokes inside current sliding window.", "1"),
    # 2. Corrections & Pauses (raw ms & counts)
    (
        "user_pre_correction_pause_ms",
        "Median IKI immediately before correction keystrokes (ms).",
        "ms",
    ),
    (
        "user_post_correction_pause_ms",
        "Median IKI immediately after correction keystrokes (ms).",
        "ms",
    ),
    ("user_window_corrections", "Correction keystrokes inside current sliding window.", "1"),
    ("user_micro_pauses_window", "Count of 1-5s micro-pauses in current sliding window.", "1"),
    ("user_pauses_gt_2s_window", "Typing pauses longer than 2s in current sliding window.", "1"),
    ("user_bursts_window", "Typing bursts between >2s pauses in current sliding window.", "1"),
    # 3. Mouse Kinematics (raw unnormalized values & counts)
    ("user_mouse_sample_entropy", "Mouse velocity Sample Entropy (raw).", "1"),
    ("user_mouse_submovements_window", "Acceleration zero-crossings in sliding window.", "1"),
    ("user_mouse_curvature_auc", "Mouse trajectory curvature ratio in sliding window.", "1"),
    ("user_mouse_x_flips_window", "Horizontal directional reversals in sliding window.", "1"),
    ("user_window_mouse_clicks", "Mouse clicks inside current sliding window.", "1"),
    ("user_window_scroll_events", "Scroll events inside current sliding window.", "1"),
    # 4. Attention & Window Dwell (raw bits, seconds & counts)
    (
        "user_shannon_entropy_bits",
        "Shannon attentional entropy (bits, log2) across active apps.",
        "bits",
    ),
    (
        "user_primary_process_dwell_seconds",
        "Dwell seconds of primary process in sliding window.",
        "s",
    ),
    ("user_active_processes_count", "Distinct active processes in sliding window.", "1"),
    ("user_window_context_switches", "Context switches inside current sliding window.", "1"),
    # 5. Temporal & Session Durations (raw seconds)
    ("user_window_active_seconds", "Active interaction seconds in current sliding window.", "s"),
    ("user_window_duration_seconds", "Total elapsed duration of current sliding window.", "s"),
    ("user_session_uptime_seconds", "Continuous session uptime in seconds.", "s"),
    ("user_active_work_seconds", "Total active working time in seconds with thought grace.", "s"),
    ("user_away_idle_seconds", "Total away/idle seconds beyond thought grace.", "s"),
)

_HISTOGRAM_SPECS: tuple[tuple[str, str, str, tuple[float, ...]], ...] = (
    (
        "user_iki_ms",
        "Raw individual inter-keystroke interval observations (ms).",
        "ms",
        (20.0, 40.0, 60.0, 80.0, 100.0, 150.0, 200.0, 300.0, 500.0, 1000.0, 2000.0),
    ),
    (
        "user_hold_time_hist_ms",
        "Raw individual key hold/dwell durations (ms).",
        "ms",
        (20.0, 40.0, 60.0, 80.0, 100.0, 120.0, 150.0, 200.0, 300.0),
    ),
    (
        "user_flight_time_hist_ms",
        "Raw individual key flight durations (ms).",
        "ms",
        (20.0, 40.0, 60.0, 80.0, 100.0, 150.0, 250.0, 500.0, 1000.0),
    ),
    (
        "user_pre_correction_pause_hist_ms",
        "Raw individual pre-correction pause durations (ms).",
        "ms",
        (50.0, 100.0, 200.0, 350.0, 500.0, 750.0, 1000.0, 2000.0),
    ),
    (
        "user_post_correction_pause_hist_ms",
        "Raw individual post-correction pause durations (ms).",
        "ms",
        (50.0, 100.0, 200.0, 350.0, 500.0, 750.0, 1000.0, 2000.0),
    ),
)


class CognitiveMetricsRecorder:
    """Declarative bridge recording independent raw metrics into OpenTelemetry and Prometheus."""

    def __init__(
        self,
        meter: Meter,
        *,
        registry: CollectorRegistry | None = None,
    ) -> None:
        self._meter = meter
        self._prom_registry = registry if registry is not None else CollectorRegistry()

        # 1. Monotonic Counters
        self._otel_counters = {
            name: meter.create_counter(name, description=desc, unit="1")
            for name, desc in _COUNTER_SPECS
        }
        self._prom_counters = {
            name: Counter(f"egg_{name}", desc, registry=self._prom_registry)
            for name, desc in _COUNTER_SPECS
        }

        # 2. Scalar Gauges (raw units only)
        self._current_metrics: dict[str, float] = {name: 0.0 for name, _, _ in _SCALAR_GAUGE_SPECS}
        self._prom_scalar_gauges: dict[str, Gauge] = {}
        for otel_name, desc, unit in _SCALAR_GAUGE_SPECS:
            self._prom_scalar_gauges[otel_name] = Gauge(
                f"egg_{otel_name}",
                desc,
                registry=self._prom_registry,
            )
            meter.create_observable_gauge(
                otel_name,
                callbacks=[self._make_scalar_callback(otel_name)],
                description=desc,
                unit=unit,
            )

        # 3. Labeled Per-Process Dwell Gauge
        self._process_dwells: dict[str, float] = {}
        self._prom_process_dwell = Gauge(
            "egg_user_process_dwell_seconds",
            "Per-process dwell seconds in the active sliding window.",
            labelnames=("process",),
            registry=self._prom_registry,
        )
        meter.create_observable_gauge(
            "user_process_dwell_seconds",
            callbacks=[self._observe_process_dwell],
            description="Per-process dwell seconds in the active sliding window.",
            unit="s",
        )

        # 4. Raw Observation Histograms
        self._otel_histograms = {
            name: meter.create_histogram(name, description=desc, unit=unit)
            for name, desc, unit, _ in _HISTOGRAM_SPECS
        }
        self._prom_histograms = {
            name: Histogram(
                f"egg_{name}",
                desc,
                buckets=buckets,
                registry=self._prom_registry,
            )
            for name, desc, _, buckets in _HISTOGRAM_SPECS
        }

    def _make_scalar_callback(self, key: str) -> Callable[[CallbackOptions], Iterable[Observation]]:
        def _callback(_options: CallbackOptions) -> Iterable[Observation]:
            yield Observation(self._current_metrics.get(key, 0.0))

        return _callback

    def _observe_process_dwell(self, _options: CallbackOptions) -> Iterable[Observation]:
        for proc_name, secs in self._process_dwells.items():
            yield Observation(secs, {"process": proc_name})

    def _update_scalars(self, values: Mapping[str, float]) -> None:
        for key, val in values.items():
            self._current_metrics[key] = val
            self._prom_scalar_gauges[key].set(val)

    def _inc_counter(self, name: str, delta: int) -> None:
        if delta > 0:
            self._otel_counters[name].add(delta)
            self._prom_counters[name].inc(delta)

    def _observe_histogram(self, name: str, values: Iterable[float]) -> None:
        otel_hist = self._otel_histograms[name]
        prom_hist = self._prom_histograms[name]
        for val in values:
            otel_hist.record(val)
            prom_hist.observe(val)

    @property
    def registry(self) -> CollectorRegistry:
        """Prometheus CollectorRegistry."""
        return self._prom_registry

    def record_keystroke_timing(
        self,
        metrics: RawKeystrokeTimingMetrics,
        *,
        keystroke_delta: int = 0,
    ) -> None:
        """Independently record raw keystroke timing observations and window stats."""
        self._inc_counter("user_keystrokes_total", keystroke_delta)
        self._observe_histogram("user_iki_ms", metrics.iki_values_ms)
        self._observe_histogram("user_hold_time_hist_ms", metrics.hold_times_ms)
        self._observe_histogram("user_flight_time_hist_ms", metrics.flight_times_ms)
        self._update_scalars(
            {
                "user_iki_mean_ms": metrics.iki_mean_ms,
                "user_iki_std_dev_ms": metrics.iki_std_dev_ms,
                "user_iki_mad_ms": metrics.iki_mad_ms,
                "user_iki_sample_count": float(metrics.iki_count),
                "user_hold_time_ms": metrics.hold_time_median_ms,
                "user_flight_time_ms": metrics.flight_time_median_ms,
                "user_window_keystrokes": float(metrics.total_keystrokes),
            }
        )

    def record_correction_pauses(
        self,
        metrics: RawCorrectionPauseMetrics,
        *,
        correction_delta: int = 0,
    ) -> None:
        """Independently record raw correction pauses and typing pause counts."""
        self._inc_counter("user_corrections_total", correction_delta)
        self._observe_histogram(
            "user_pre_correction_pause_hist_ms", metrics.pre_correction_pauses_ms
        )
        self._observe_histogram(
            "user_post_correction_pause_hist_ms", metrics.post_correction_pauses_ms
        )
        self._update_scalars(
            {
                "user_pre_correction_pause_ms": metrics.pre_correction_pause_median_ms,
                "user_post_correction_pause_ms": metrics.post_correction_pause_median_ms,
                "user_window_corrections": float(metrics.correction_keystrokes),
                "user_micro_pauses_window": float(metrics.micro_pauses_count),
                "user_pauses_gt_2s_window": float(metrics.pauses_gt_2s_count),
                "user_bursts_window": float(metrics.burst_count),
            }
        )

    def record_mouse_kinematics(
        self,
        metrics: RawMouseKinematicsMetrics,
        *,
        mouse_click_delta: int = 0,
        scroll_delta: int = 0,
    ) -> None:
        """Independently record raw mouse kinematics and click/scroll counts."""
        self._inc_counter("user_mouse_clicks_total", mouse_click_delta)
        self._inc_counter("user_scroll_events_total", scroll_delta)
        self._update_scalars(
            {
                "user_mouse_sample_entropy": metrics.sample_entropy,
                "user_mouse_submovements_window": float(metrics.submovements),
                "user_mouse_curvature_auc": metrics.curvature_auc,
                "user_mouse_x_flips_window": float(metrics.x_flips),
                "user_window_mouse_clicks": float(metrics.mouse_clicks),
                "user_window_scroll_events": float(metrics.scroll_events),
            }
        )

    def record_attention_window(
        self,
        metrics: RawAttentionWindowMetrics,
        *,
        context_switch_delta: int = 0,
    ) -> None:
        """Independently record raw attentional entropy (bits) and per-process dwell seconds."""
        self._inc_counter("user_context_switches_total", context_switch_delta)
        self._update_scalars(
            {
                "user_shannon_entropy_bits": metrics.shannon_entropy_bits,
                "user_primary_process_dwell_seconds": metrics.primary_process_dwell_seconds,
                "user_active_processes_count": float(metrics.distinct_processes_count),
                "user_window_context_switches": float(metrics.context_switches),
            }
        )
        for old_proc in list(self._process_dwells):
            if old_proc not in metrics.merged_dwell_seconds:
                self._process_dwells[old_proc] = 0.0
                self._prom_process_dwell.labels(process=old_proc).set(0.0)
        for proc_name, dwell_sec in metrics.merged_dwell_seconds.items():
            rounded_dwell = round(dwell_sec, 2)
            self._process_dwells[proc_name] = rounded_dwell
            self._prom_process_dwell.labels(process=proc_name).set(rounded_dwell)

    def record_temporal_session(self, metrics: RawTemporalSessionMetrics) -> None:
        """Independently record raw active/idle/session duration seconds."""
        self._update_scalars(
            {
                "user_window_active_seconds": metrics.window_active_seconds,
                "user_window_duration_seconds": metrics.window_duration_seconds,
                "user_session_uptime_seconds": metrics.session_uptime_seconds,
                "user_active_work_seconds": metrics.active_work_seconds,
                "user_away_idle_seconds": metrics.away_idle_seconds,
            }
        )

    def render_prometheus_metrics(self) -> str:
        """Render Prometheus metrics in plain text exposition format."""
        return generate_latest(self._prom_registry).decode("utf-8")
