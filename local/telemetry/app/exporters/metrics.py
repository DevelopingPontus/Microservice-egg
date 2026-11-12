"""Declarative OpenTelemetry & Prometheus metrics recorder for `strain/` and `workflow/`."""

from collections.abc import Callable, Iterable, Mapping

from opentelemetry.metrics import CallbackOptions, Meter, Observation
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from app.analysis import (
    CognitiveStrainReport,
    DimensionEvaluation,
    OverviewDimensionsSnapshot,
)
from app.collector import PooledTelemetryMetrics

_COUNTER_SPECS: tuple[tuple[str, str], ...] = (
    ("user_keystrokes_total", "Total keystrokes recorded."),
    ("user_corrections_total", "Total backspace and delete keystrokes recorded."),
    ("user_mouse_clicks_total", "Total mouse button presses recorded."),
    ("user_scroll_events_total", "Total scroll events recorded."),
    ("user_context_switches_total", "Total window context switches recorded."),
)

_SCALAR_GAUGE_SPECS: tuple[tuple[str, str, str], ...] = (
    # Pipeline A (`strain/` + raw 60s window)
    ("user_duty_cycle_ratio", "Active duty cycle ratio [0.0, 1.0] across active window.", "1"),
    ("user_window_active_seconds", "Active interaction seconds in current sliding window.", "s"),
    ("user_window_duration_seconds", "Total elapsed duration of current sliding window.", "s"),
    ("user_micro_pauses_window", "Count of 1-5s micro-pauses in current sliding window.", "1"),
    ("user_shannon_entropy_nats", "Shannon attentional entropy (nats) across active apps.", "nats"),
    ("user_primary_process_ratio", "Dwell share of primary process in sliding window.", "1"),
    ("user_active_processes_count", "Distinct active processes in sliding window.", "1"),
    ("user_context_switches_per_min", "Context switches per minute across active window.", "1/min"),
    ("user_correction_ratio", "Backspace/delete ratio to total keystrokes.", "1"),
    ("user_iki_mean_ms", "Mean inter-keystroke interval in milliseconds.", "ms"),
    ("user_iki_std_dev_ms", "Standard deviation of inter-keystroke intervals (ms).", "ms"),
    ("user_iki_jitter_cv", "Inter-keystroke interval coefficient of variation.", "1"),
    ("user_iki_sample_count", "Number of valid IKI pairs in current sliding window.", "1"),
    ("user_window_keystrokes", "Keystrokes inside current sliding window.", "1"),
    ("user_window_mouse_clicks", "Mouse clicks inside current sliding window.", "1"),
    ("user_window_scroll_events", "Scroll events inside current sliding window.", "1"),
    ("user_session_uptime_seconds", "Continuous session uptime in seconds.", "s"),
    ("user_active_work_seconds", "Total active working time in seconds with thought grace.", "s"),
    ("user_away_idle_seconds", "Total away/idle seconds beyond thought grace.", "s"),
    ("user_overall_strain_score", "Composite SRE cognitive strain score [0.0, 1.0].", "1"),
    # Pipeline B (`workflow/`)
    ("overview_focus_session_seconds", "Length of uninterrupted work on current focus app.", "s"),
    ("overview_deep_work_blocks_total", "Completed deep-work blocks longer than 25 minutes.", "1"),
    ("overview_switch_recovery_seconds", "Recovery time after most recent context switch.", "s"),
    ("overview_switches_in_5m", "Rolling context switch count in the last 5 minutes.", "1"),
    (
        "overview_attention_residue_gap_seconds",
        "Time away from a task before returning (<30m).",
        "s",
    ),
    (
        "overview_attention_residue_elsewhere_seconds",
        "Active time spent elsewhere before returning.",
        "s",
    ),
    (
        "overview_attention_residue_returns_total",
        "Total task returns within 30m residue window.",
        "1",
    ),
    ("overview_in_interruption", "Whether currently inside a comms interruption (1 or 0).", "1"),
    (
        "overview_resumption_lag_seconds",
        "Seconds to resume sustained work after interruption.",
        "s",
    ),
    ("overview_interruptions_total", "Total comms interruptions detected.", "1"),
    ("overview_minute_input_intensity", "Per-minute composite input intensity.", "1/min"),
    (
        "overview_ultradian_period_minutes",
        "Estimated dominant ultradian cycle period (min).",
        "min",
    ),
    ("overview_chronotype_center_hour", "Daily centre-of-mass hour [0-24) for deep work.", "h"),
    ("overview_pauses_gt_2s_window", "Typing pauses longer than 2s in current window.", "1"),
    ("overview_composing_pauses_total", "Cumulative typing pauses longer than 2s.", "1"),
    ("overview_burst_length_keys", "Mean keystrokes per burst between >2s pauses.", "1"),
    ("overview_scroll_to_input_ratio", "Scroll events to keystrokes ratio in window.", "1"),
)


class CognitiveMetricsRecorder:
    """Declarative bridge recording telemetry into OpenTelemetry and Prometheus."""

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

        # 2. Scalar Gauges
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

        # 3. Labeled Gauges & Histograms
        self._dimension_scores: dict[str, float] = {}
        self._process_dwells: dict[str, float] = {}
        self._category_seconds: dict[str, float] = {}
        self._hourly_deep_work: dict[str, float] = {}
        self._activity_states: dict[tuple[str, str, str, str, str], float] = {}
        self._typing_modes: dict[str, float] = {
            "composing": 0.0,
            "transcribing": 0.0,
            "inactive": 1.0,
        }

        self._prom_dimension_strain = Gauge(
            "egg_user_dimension_strain_score",
            "Cognitive strain score [0.0, 1.0] by scientific dimension.",
            labelnames=("dimension",),
            registry=self._prom_registry,
        )
        self._prom_process_dwell = Gauge(
            "egg_user_process_dwell_seconds",
            "Per-process dwell seconds in the active sliding window.",
            labelnames=("process",),
            registry=self._prom_registry,
        )
        self._prom_overview_category_seconds = Gauge(
            "egg_overview_category_seconds_total",
            "Cumulative seconds spent in each Overview work category.",
            labelnames=("activity",),
            registry=self._prom_registry,
        )
        self._prom_overview_activity_state = Gauge(
            "egg_overview_activity_state",
            "Active Overview work category state (1 = active, 0 = inactive).",
            labelnames=(
                "activity",
                "app_category",
                "time_block",
                "session_length_bucket",
                "device",
            ),
            registry=self._prom_registry,
        )
        self._prom_overview_hourly_deep_work = Gauge(
            "egg_overview_deep_work_minutes_by_hour",
            "Cumulative deep-work minutes by hour of day (00..23).",
            labelnames=("hour",),
            registry=self._prom_registry,
        )
        self._prom_overview_typing_mode = Gauge(
            "egg_overview_typing_mode_state",
            "Current typing rhythm mode (composing, transcribing, inactive).",
            labelnames=("typing_mode",),
            registry=self._prom_registry,
        )

        self._otel_residue_hist = meter.create_histogram(
            "overview_attention_residue_gap_hist_seconds",
            description="Distribution of attention residue return gaps in seconds.",
            unit="s",
        )
        self._otel_resumption_hist = meter.create_histogram(
            "overview_resumption_lag_hist_seconds",
            description="Distribution of post-interruption resumption lag in seconds.",
            unit="s",
        )
        self._otel_iki_hist = meter.create_histogram(
            "overview_iki_window_mean_hist_ms",
            description="Distribution of sliding-window mean inter-keystroke intervals (ms).",
            unit="ms",
        )
        self._prom_residue_hist = Histogram(
            "egg_overview_attention_residue_gap_hist_seconds",
            "Distribution of attention residue return gaps in seconds.",
            buckets=(5.0, 15.0, 30.0, 60.0, 180.0, 300.0, 600.0, 1200.0, 1800.0),
            registry=self._prom_registry,
        )
        self._prom_resumption_hist = Histogram(
            "egg_overview_resumption_lag_hist_seconds",
            "Distribution of post-interruption resumption lag in seconds.",
            buckets=(2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
            registry=self._prom_registry,
        )
        self._prom_iki_hist = Histogram(
            "egg_overview_iki_window_mean_hist_ms",
            "Distribution of sliding-window mean inter-keystroke intervals (ms).",
            buckets=(50.0, 100.0, 150.0, 200.0, 300.0, 500.0, 1000.0, 2000.0),
            registry=self._prom_registry,
        )

        labeled_callbacks: tuple[
            tuple[str, str, str, Callable[[CallbackOptions], Iterable[Observation]]], ...
        ] = (
            (
                "user_dimension_strain_score",
                "Cognitive strain score [0.0, 1.0] by scientific dimension.",
                "1",
                self._observe_dimension_strain,
            ),
            (
                "user_process_dwell_seconds",
                "Per-process dwell seconds in the active sliding window.",
                "s",
                self._observe_process_dwell,
            ),
            (
                "overview_category_seconds_total",
                "Cumulative seconds spent in each Overview work category.",
                "s",
                self._observe_category_seconds,
            ),
            (
                "overview_activity_state",
                "Active Overview work category state (1 = active, 0 = inactive).",
                "1",
                self._observe_activity_state,
            ),
            (
                "overview_deep_work_minutes_by_hour",
                "Cumulative deep-work minutes by hour of day (00..23).",
                "min",
                self._observe_hourly_deep_work,
            ),
            (
                "overview_typing_mode_state",
                "Current typing rhythm mode (composing, transcribing, inactive).",
                "1",
                self._observe_typing_mode,
            ),
        )
        for name, desc, unit, cb in labeled_callbacks:
            meter.create_observable_gauge(name, callbacks=[cb], description=desc, unit=unit)

    def _make_scalar_callback(self, key: str) -> Callable[[CallbackOptions], Iterable[Observation]]:
        def _callback(_options: CallbackOptions) -> Iterable[Observation]:
            yield Observation(self._current_metrics.get(key, 0.0))

        return _callback

    def _observe_dimension_strain(self, _options: CallbackOptions) -> Iterable[Observation]:
        for dim_name, score in self._dimension_scores.items():
            yield Observation(score, {"dimension": dim_name})

    def _observe_process_dwell(self, _options: CallbackOptions) -> Iterable[Observation]:
        for proc_name, secs in self._process_dwells.items():
            yield Observation(secs, {"process": proc_name})

    def _observe_category_seconds(self, _options: CallbackOptions) -> Iterable[Observation]:
        for activity, secs in self._category_seconds.items():
            yield Observation(secs, {"activity": activity})

    def _observe_activity_state(self, _options: CallbackOptions) -> Iterable[Observation]:
        for (act, app_cat, t_block, s_bucket, dev), val in self._activity_states.items():
            yield Observation(
                val,
                {
                    "activity": act,
                    "app_category": app_cat,
                    "time_block": t_block,
                    "session_length_bucket": s_bucket,
                    "device": dev,
                },
            )

    def _observe_hourly_deep_work(self, _options: CallbackOptions) -> Iterable[Observation]:
        for hour_str, mins in self._hourly_deep_work.items():
            yield Observation(mins, {"hour": hour_str})

    def _observe_typing_mode(self, _options: CallbackOptions) -> Iterable[Observation]:
        for mode, val in self._typing_modes.items():
            yield Observation(val, {"typing_mode": mode})

    def _update_scalars(self, values: Mapping[str, float]) -> None:
        for key, val in values.items():
            self._current_metrics[key] = val
            self._prom_scalar_gauges[key].set(val)

    def _inc_counter(self, name: str, delta: int) -> None:
        if delta > 0:
            self._otel_counters[name].add(delta)
            self._prom_counters[name].inc(delta)

    @property
    def registry(self) -> CollectorRegistry:
        """Prometheus CollectorRegistry."""
        return self._prom_registry

    def record_tick(
        self,
        *,
        metrics: PooledTelemetryMetrics,
        session_uptime_seconds: float,
        evaluations: Mapping[str, DimensionEvaluation],
        report: CognitiveStrainReport,
        overview: OverviewDimensionsSnapshot | None = None,
        active_work_seconds: float = 0.0,
        away_idle_seconds: float = 0.0,
        keystroke_delta: int = 0,
        correction_delta: int = 0,
        context_switch_delta: int = 0,
        mouse_click_delta: int = 0,
        scroll_delta: int = 0,
    ) -> None:
        """Update OpenTelemetry and Prometheus gauges, histograms, and counters."""
        self._inc_counter("user_keystrokes_total", keystroke_delta)
        self._inc_counter("user_corrections_total", correction_delta)
        self._inc_counter("user_context_switches_total", context_switch_delta)
        self._inc_counter("user_mouse_clicks_total", mouse_click_delta)
        self._inc_counter("user_scroll_events_total", scroll_delta)

        self._update_scalars(
            {
                "user_duty_cycle_ratio": metrics.duty_cycle,
                "user_window_active_seconds": metrics.total_active_seconds,
                "user_window_duration_seconds": metrics.total_duration_seconds,
                "user_micro_pauses_window": float(metrics.total_micro_pauses),
                "user_shannon_entropy_nats": metrics.shannon_entropy,
                "user_primary_process_ratio": metrics.primary_process_ratio,
                "user_active_processes_count": float(len(metrics.merged_dwell_seconds)),
                "user_context_switches_per_min": metrics.switches_per_minute,
                "user_correction_ratio": metrics.correction_ratio,
                "user_iki_mean_ms": metrics.iki_mean_ms,
                "user_iki_std_dev_ms": metrics.iki_std_dev_ms,
                "user_iki_jitter_cv": metrics.iki_cv,
                "user_iki_sample_count": float(metrics.iki_count),
                "user_window_keystrokes": float(metrics.total_keystrokes),
                "user_window_mouse_clicks": float(metrics.total_mouse_clicks),
                "user_window_scroll_events": float(metrics.total_scroll_events),
                "user_session_uptime_seconds": session_uptime_seconds,
                "user_active_work_seconds": active_work_seconds,
                "user_away_idle_seconds": away_idle_seconds,
                "user_overall_strain_score": report.overall_strain_score,
            }
        )

        for dim_name, eval_res in evaluations.items():
            self._dimension_scores[dim_name] = eval_res.strain_score
            self._prom_dimension_strain.labels(dimension=dim_name).set(eval_res.strain_score)

        for old_proc in list(self._process_dwells):
            if old_proc not in metrics.merged_dwell_seconds:
                self._process_dwells[old_proc] = 0.0
                self._prom_process_dwell.labels(process=old_proc).set(0.0)
        for proc_name, dwell_sec in metrics.merged_dwell_seconds.items():
            rounded_dwell = round(dwell_sec, 2)
            self._process_dwells[proc_name] = rounded_dwell
            self._prom_process_dwell.labels(process=proc_name).set(rounded_dwell)

        if metrics.iki_mean_ms > 0.0:
            self._otel_iki_hist.record(metrics.iki_mean_ms)
            self._prom_iki_hist.observe(metrics.iki_mean_ms)

        if overview is not None:
            self._update_scalars(
                {
                    "overview_focus_session_seconds": overview.focus_session_length_seconds,
                    "overview_deep_work_blocks_total": float(overview.deep_work_blocks_total),
                    "overview_switch_recovery_seconds": overview.switch_recovery_seconds,
                    "overview_switches_in_5m": float(overview.classification.switches_in_5m),
                    "overview_attention_residue_gap_seconds": overview.last_residue_gap_seconds,
                    "overview_attention_residue_elsewhere_seconds": (
                        overview.last_residue_elsewhere_seconds
                    ),
                    "overview_attention_residue_returns_total": float(
                        overview.residue_return_count
                    ),
                    "overview_in_interruption": 1.0 if overview.in_interruption else 0.0,
                    "overview_resumption_lag_seconds": overview.last_resumption_lag_seconds,
                    "overview_interruptions_total": float(overview.interruptions_total),
                    "overview_minute_input_intensity": overview.minute_input_intensity,
                    "overview_ultradian_period_minutes": (
                        overview.dominant_ultradian_period_minutes
                    ),
                    "overview_chronotype_center_hour": overview.chronotype_center_of_mass_hour,
                    "overview_pauses_gt_2s_window": float(overview.pauses_gt_2s_window),
                    "overview_composing_pauses_total": float(overview.composing_pauses_total),
                    "overview_burst_length_keys": overview.mean_burst_length_keys,
                    "overview_scroll_to_input_ratio": (
                        overview.classification.scroll_to_input_ratio
                    ),
                }
            )

            if overview.last_residue_gap_seconds > 0.0:
                self._otel_residue_hist.record(overview.last_residue_gap_seconds)
                self._prom_residue_hist.observe(overview.last_residue_gap_seconds)
            if overview.last_resumption_lag_seconds > 0.0:
                self._otel_resumption_hist.record(overview.last_resumption_lag_seconds)
                self._prom_resumption_hist.observe(overview.last_resumption_lag_seconds)

            for cat_name, cat_secs in overview.category_seconds_total.items():
                self._category_seconds[cat_name] = cat_secs
                self._prom_overview_category_seconds.labels(activity=cat_name).set(cat_secs)

            for hour_str, mins in overview.deep_work_minutes_by_hour.items():
                self._hourly_deep_work[hour_str] = mins
                self._prom_overview_hourly_deep_work.labels(hour=hour_str).set(mins)

            for mode in ("composing", "transcribing", "inactive"):
                val = 1.0 if overview.typing_mode == mode else 0.0
                self._typing_modes[mode] = val
                self._prom_overview_typing_mode.labels(typing_mode=mode).set(val)

            for prev_key in list(self._activity_states):
                self._activity_states[prev_key] = 0.0
                self._prom_overview_activity_state.labels(*prev_key).set(0.0)
            cls = overview.classification
            active_key = (
                cls.activity,
                cls.app_category,
                cls.time_block,
                cls.session_length_bucket,
                cls.device,
            )
            self._activity_states[active_key] = 1.0
            self._prom_overview_activity_state.labels(*active_key).set(1.0)

    def render_prometheus_metrics(self) -> str:
        """Render Prometheus metrics in plain text exposition format."""
        return generate_latest(self._prom_registry).decode("utf-8")
