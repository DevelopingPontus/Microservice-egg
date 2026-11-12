"""Stateful focus sessionization, 30m attention residue, and comms interruption tracking."""

from __future__ import annotations

from collections import deque

from app.config import MetricValue


class FocusSessionTracker:
    """Tracks Flow (Dim 1), Attention Residue (Dim 2), and Interruptions (Dim 3)."""

    def __init__(
        self,
        *,
        idle_threshold_seconds: float = 300.0,
        session_close_switch_seconds: float = 60.0,
        deep_work_threshold_seconds: float = 1500.0,
        residue_window_seconds: float = 1800.0,
    ) -> None:
        self._idle_threshold = idle_threshold_seconds
        self._session_close_switch_sec = session_close_switch_seconds
        self._deep_work_threshold_sec = deep_work_threshold_seconds
        self._residue_window_sec = residue_window_seconds

        self._switch_history_5m: deque[tuple[float, int]] = deque()
        self.prev_process: str | None = None
        self._in_idle_state: bool = False

        # Dimension 1: Flow and sustained focus
        self.focus_app: str = "idle"
        self.focus_start_ts: float | None = None
        self._candidate_app: str | None = None
        self._candidate_since_ts: float | None = None
        self.deep_work_blocks_total: int = 0
        self._current_session_counted_deep: bool = False
        self._last_switch_ts: float | None = None
        self.last_switch_recovery_sec: float = 0.0
        self._awaiting_switch_recovery: bool = False

        # Dimension 2: Attention residue (task -> (departure_ts, cumulative_elsewhere_baseline))
        self._departed_tasks: dict[str, tuple[float, float]] = {}
        self._total_non_idle_seconds: float = 0.0
        self.last_residue_gap_sec: float = 0.0
        self.last_residue_elsewhere_sec: float = 0.0
        self.residue_return_count: int = 0

        # Dimension 3: Interruption and resumption lag
        self.in_interruption: bool = False
        self._interrupted_from_app: str | None = None
        self._return_from_interruption_ts: float | None = None
        self.last_resumption_lag_sec: float = 0.0
        self.interruptions_total: int = 0

    def update_5m_switches(self, now: float, observed_switches: int) -> int:
        """Record observed switches and return rolling 5-minute switch total."""
        if observed_switches > 0:
            self._switch_history_5m.append((now, observed_switches))
        cutoff_5m = now - 300.0
        while self._switch_history_5m and self._switch_history_5m[0][0] < cutoff_5m:
            self._switch_history_5m.popleft()
        return sum(count for _, count in self._switch_history_5m)

    def focus_session_length_seconds(self, now: float) -> float:
        """Return elapsed duration of the current debounced focus session."""
        return max(0.0, now - self.focus_start_ts) if self.focus_start_ts is not None else 0.0

    def update_flow_and_residue(
        self,
        *,
        now: float,
        dt_sec: float,
        primary_app: str,
        app_cat: str,
        kpm: float,
        spm: float,
        idle_seconds: float,
        events: list[dict[str, MetricValue]],
    ) -> None:
        """Advance focus sessionization and 30-minute attention residue tracking."""
        is_idle = idle_seconds >= self._idle_threshold or primary_app == "idle"
        if not is_idle:
            self._total_non_idle_seconds += dt_sec

        if is_idle and not self._in_idle_state:
            self._in_idle_state = True
            events.append({"event": "idle_start", "idle_seconds": round(idle_seconds, 1)})
        elif not is_idle:
            self._in_idle_state = False

        if self.prev_process is not None and primary_app != self.prev_process:
            events.append(
                {
                    "event": "switch",
                    "from_app": self.prev_process,
                    "to_app": primary_app,
                    "to_category": app_cat,
                }
            )
            self._last_switch_ts = now
            self._awaiting_switch_recovery = True

        if self._awaiting_switch_recovery and (kpm >= 10.0 or spm >= 1.0):
            if self._last_switch_ts is not None:
                self.last_switch_recovery_sec = max(0.0, now - self._last_switch_ts)
            self._awaiting_switch_recovery = False

        if self.focus_start_ts is None:
            self.focus_app = primary_app
            self.focus_start_ts = now
            events.append({"event": "focus_start", "app": primary_app, "app_category": app_cat})
            return

        if primary_app == self.focus_app:
            self._candidate_app = None
            self._candidate_since_ts = None
        else:
            if self._candidate_app != primary_app:
                self._candidate_app = primary_app
                self._candidate_since_ts = now
            elif (
                self._candidate_since_ts is not None
                and (now - self._candidate_since_ts) >= self._session_close_switch_sec
            ):
                prev_app = self.focus_app
                session_duration = max(0.0, self._candidate_since_ts - self.focus_start_ts)
                events.append(
                    {
                        "event": "focus_end",
                        "app": prev_app,
                        "duration_seconds": round(session_duration, 2),
                    }
                )
                if prev_app != "idle":
                    self._departed_tasks[prev_app] = (
                        self._candidate_since_ts,
                        self._total_non_idle_seconds,
                    )

                self._check_residue_return(primary_app, now)

                self.focus_app = primary_app
                self.focus_start_ts = self._candidate_since_ts
                self._current_session_counted_deep = False
                self._candidate_app = None
                self._candidate_since_ts = None
                events.append(
                    {
                        "event": "focus_start",
                        "app": primary_app,
                        "app_category": app_cat,
                    }
                )

        if (
            self.prev_process == self.focus_app
            and primary_app != self.focus_app
            and self.focus_app != "idle"
        ):
            self._departed_tasks[self.focus_app] = (now, self._total_non_idle_seconds)
        elif (
            self.prev_process is not None
            and self.prev_process != self.focus_app
            and primary_app == self.focus_app
        ):
            self._check_residue_return(primary_app, now)

        if (
            self.focus_start_ts is not None
            and not self._current_session_counted_deep
            and (now - self.focus_start_ts) >= self._deep_work_threshold_sec
        ):
            self.deep_work_blocks_total += 1
            self._current_session_counted_deep = True

    def _check_residue_return(self, primary_app: str, now: float) -> None:
        if primary_app in self._departed_tasks:
            dep_ts, dep_active_base = self._departed_tasks.pop(primary_app)
            gap = max(0.0, now - dep_ts)
            if 0.0 < gap <= self._residue_window_sec:
                self.last_residue_gap_sec = gap
                self.last_residue_elsewhere_sec = max(
                    0.0,
                    self._total_non_idle_seconds - dep_active_base,
                )
                self.residue_return_count += 1

    def update_interruption_and_resumption(
        self,
        *,
        now: float,
        primary_app: str,
        app_cat: str,
        kpm: float,
        spm: float,
        events: list[dict[str, MetricValue]],
    ) -> None:
        """Track comms app interruptions and resumption lag upon returning to work."""
        if app_cat == "comms" and not self.in_interruption:
            self.in_interruption = True
            self._interrupted_from_app = self.prev_process or self.focus_app
            self._return_from_interruption_ts = None
            self.interruptions_total += 1
            events.append(
                {
                    "event": "interruption",
                    "comms_app": primary_app,
                    "interrupted_from": self._interrupted_from_app or "unknown",
                }
            )
        elif self.in_interruption and app_cat != "comms" and primary_app != "idle":
            if self._return_from_interruption_ts is None:
                self._return_from_interruption_ts = now
            if kpm >= 15.0 or spm >= 1.5:
                lag = max(0.0, now - self._return_from_interruption_ts)
                self.last_resumption_lag_sec = lag
                self.in_interruption = False
                self._return_from_interruption_ts = None
                events.append(
                    {
                        "event": "resumed",
                        "resumed_app": primary_app,
                        "resumption_lag_seconds": round(lag, 2),
                    }
                )
