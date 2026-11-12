"""6-Dimension Workflow & Overview Module (`app/analysis/workflow/`).

Combines `classifier.py` (6 work categories), `sessions.py` (focus, residue,
interruption tracking), and `rhythms.py` (ultradian, chronotype, typing bursts)
into `StatefulOverviewEngine`.
"""

from __future__ import annotations

import datetime
import platform
from dataclasses import dataclass

from app.analysis.workflow.classifier import (
    ALL_WORK_CATEGORIES,
    WorkCategoryClassification,
    classify_app_category,
    classify_work_category,
    resolve_keystroke_bucket,
    resolve_session_length_bucket,
    resolve_time_block,
)
from app.analysis.workflow.rhythms import RhythmTracker
from app.analysis.workflow.sessions import FocusSessionTracker
from app.collector import PooledTelemetryMetrics
from app.config import MetricValue

__all__ = [
    "ALL_WORK_CATEGORIES",
    "FocusSessionTracker",
    "OverviewDimensionsSnapshot",
    "RhythmTracker",
    "StatefulOverviewEngine",
    "WorkCategoryClassification",
    "WorkflowEngine",
    "classify_app_category",
    "classify_work_category",
    "resolve_keystroke_bucket",
    "resolve_session_length_bucket",
    "resolve_time_block",
]


@dataclass(frozen=True, slots=True)
class OverviewDimensionsSnapshot:
    """Snapshot of the 6 stateful dimensions and work categories from the Overview plan."""

    classification: WorkCategoryClassification
    # 1. Flow and sustained focus
    current_focus_app: str
    focus_session_length_seconds: float
    deep_work_blocks_total: int
    switch_recovery_seconds: float
    # 2. Attention residue
    last_residue_gap_seconds: float
    last_residue_elsewhere_seconds: float
    residue_return_count: int
    # 3. Interruption and resumption lag
    in_interruption: bool
    last_resumption_lag_seconds: float
    interruptions_total: int
    # 4. Ultradian rhythms
    minute_input_intensity: float
    dominant_ultradian_period_minutes: float
    # 5. Chronotype
    deep_work_minutes_by_hour: dict[str, float]
    chronotype_center_of_mass_hour: float
    # 6. Typing rhythm and pauses
    typing_mode: str
    pauses_gt_2s_window: int
    composing_pauses_total: int
    mean_burst_length_keys: float
    edit_ratio: float
    # Cumulative work category seconds & discrete Loki events emitted on this tick
    category_seconds_total: dict[str, float]
    discrete_events: tuple[dict[str, MetricValue], ...]


class StatefulOverviewEngine:
    """Combines `classifier`, `FocusSessionTracker`, and `RhythmTracker`."""

    def __init__(
        self,
        *,
        idle_threshold_seconds: float = 300.0,
        session_close_switch_seconds: float = 60.0,
        deep_work_threshold_seconds: float = 1500.0,
        residue_window_seconds: float = 1800.0,
        navigating_switch_override_5m: int = 6,
        producing_min_kpm: float = 25.0,
        consuming_min_spm: float = 1.0,
        device_label: str | None = None,
    ) -> None:
        self._idle_threshold = idle_threshold_seconds
        self._navigating_switch_override = navigating_switch_override_5m
        self._producing_min_kpm = producing_min_kpm
        self._consuming_min_spm = consuming_min_spm
        self._device = device_label or (platform.system().lower() or "local-host")

        self.sessions = FocusSessionTracker(
            idle_threshold_seconds=idle_threshold_seconds,
            session_close_switch_seconds=session_close_switch_seconds,
            deep_work_threshold_seconds=deep_work_threshold_seconds,
            residue_window_seconds=residue_window_seconds,
        )
        self.rhythms = RhythmTracker()

        self._category_seconds_total: dict[str, float] = {cat: 0.0 for cat in ALL_WORK_CATEGORIES}
        self._last_eval_ts: float | None = None

    def evaluate_tick(
        self,
        metrics: PooledTelemetryMetrics,
        *,
        idle_seconds: float = 0.0,
        now_timestamp: float | None = None,
        switch_delta: int | None = None,
        pauses_gt_2s_delta: int | None = None,
    ) -> OverviewDimensionsSnapshot:
        """Advance all 6 stateful dimensions and classify the active work segment."""
        now = (
            now_timestamp
            if now_timestamp is not None
            else datetime.datetime.now(datetime.UTC).timestamp()
        )
        dt_sec = (
            max(0.0, min(60.0, now - self._last_eval_ts))
            if self._last_eval_ts is not None
            else max(0.5, min(10.0, metrics.total_duration_seconds))
        )
        self._last_eval_ts = now

        events: list[dict[str, MetricValue]] = []
        primary_app = metrics.primary_process or "idle"
        app_cat = classify_app_category(primary_app)

        obs_switches = switch_delta if switch_delta is not None else metrics.total_context_switches
        switches_5m = self.sessions.update_5m_switches(now, obs_switches)

        eff_minutes = (
            max(metrics.total_duration_seconds / 60.0, 0.25)
            if metrics.total_duration_seconds > 0.0
            else 0.0
        )
        kpm = (metrics.total_keystrokes / eff_minutes) if eff_minutes > 0.0 else 0.0
        spm = (metrics.total_scroll_events / eff_minutes) if eff_minutes > 0.0 else 0.0
        scroll_to_input_ratio = round(
            metrics.total_scroll_events / max(1, metrics.total_keystrokes),
            4,
        )

        self.sessions.update_flow_and_residue(
            now=now,
            dt_sec=dt_sec,
            primary_app=primary_app,
            app_cat=app_cat,
            kpm=kpm,
            spm=spm,
            idle_seconds=idle_seconds,
            events=events,
        )
        self.sessions.update_interruption_and_resumption(
            now=now,
            primary_app=primary_app,
            app_cat=app_cat,
            kpm=kpm,
            spm=spm,
            events=events,
        )

        focus_len_sec = self.sessions.focus_session_length_seconds(now)
        classification = classify_work_category(
            now=now,
            app_cat=app_cat,
            kpm=kpm,
            spm=spm,
            scroll_to_input_ratio=scroll_to_input_ratio,
            switches_5m=switches_5m,
            idle_seconds=idle_seconds,
            focus_len_sec=focus_len_sec,
            metrics=metrics,
            idle_threshold_seconds=self._idle_threshold,
            navigating_switch_override_5m=self._navigating_switch_override,
            producing_min_kpm=self._producing_min_kpm,
            consuming_min_spm=self._consuming_min_spm,
            device_label=self._device,
        )
        self._category_seconds_total[classification.activity] = round(
            self._category_seconds_total.get(classification.activity, 0.0) + dt_sec,
            2,
        )

        if classification.activity == "unclassified":
            events.append(
                {
                    "event": "unclassified_segment",
                    "app_category": classification.app_category,
                    "duration_seconds": round(metrics.total_duration_seconds, 2),
                    "keystroke_bucket": classification.keystroke_bucket,
                    "failed_rule": classification.failed_rule,
                    "is_borderline": classification.is_borderline,
                }
            )

        minute_intensity = round(
            kpm + (spm * 2.0) + (metrics.total_mouse_clicks / max(eff_minutes, 0.25)),
            2,
        )
        self.rhythms.update_ultradian(now=now, minute_intensity=minute_intensity)
        center_hour = self.rhythms.update_chronotype(
            now=now,
            dt_sec=dt_sec,
            activity=classification.activity,
            focus_len_sec=focus_len_sec,
        )
        typing_mode, window_pauses_2s, mean_burst_keys = self.rhythms.update_typing_rhythm(
            metrics,
            pauses_gt_2s_delta=pauses_gt_2s_delta,
        )

        self.sessions.prev_process = primary_app

        return OverviewDimensionsSnapshot(
            classification=classification,
            current_focus_app=self.sessions.focus_app,
            focus_session_length_seconds=round(focus_len_sec, 2),
            deep_work_blocks_total=self.sessions.deep_work_blocks_total,
            switch_recovery_seconds=round(self.sessions.last_switch_recovery_sec, 2),
            last_residue_gap_seconds=round(self.sessions.last_residue_gap_sec, 2),
            last_residue_elsewhere_seconds=round(self.sessions.last_residue_elsewhere_sec, 2),
            residue_return_count=self.sessions.residue_return_count,
            in_interruption=self.sessions.in_interruption,
            last_resumption_lag_seconds=round(self.sessions.last_resumption_lag_sec, 2),
            interruptions_total=self.sessions.interruptions_total,
            minute_input_intensity=minute_intensity,
            dominant_ultradian_period_minutes=round(
                self.rhythms.dominant_ultradian_period_min,
                1,
            ),
            deep_work_minutes_by_hour=dict(self.rhythms.deep_work_minutes_by_hour),
            chronotype_center_of_mass_hour=round(center_hour, 2),
            typing_mode=typing_mode,
            pauses_gt_2s_window=window_pauses_2s,
            composing_pauses_total=self.rhythms.composing_pauses_total,
            mean_burst_length_keys=mean_burst_keys,
            edit_ratio=round(metrics.correction_ratio, 4),
            category_seconds_total=dict(self._category_seconds_total),
            discrete_events=tuple(events),
        )


WorkflowEngine = StatefulOverviewEngine
