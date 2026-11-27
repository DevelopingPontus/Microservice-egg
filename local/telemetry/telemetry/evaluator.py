"""Phase 6: Rolling-window peer-reviewed metric evaluator and Prometheus exporter."""

from __future__ import annotations

import math
import sqlite3
import statistics
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from prometheus_client import CollectorRegistry, Gauge, start_http_server

from telemetry.anchors import (
    APP_ANCHOR_SPECS,
    GLOBAL_ANCHOR_SPECS,
    refresh_app_anchors,
)
from telemetry.db import init_db

# Peer-reviewed data-quality gates (minimum samples & physiological bounds)
MIN_WINDOW_KEYSTROKES = 30
KEY_HOLD_MIN_MS = 10.0
KEY_HOLD_MAX_MS = 1000.0
KEY_FLIGHT_MAX_MS = 2000.0

MIN_WINDOW_MOUSE_MOVES = 20
MIN_WINDOW_CLICKS = 5
MOUSE_MAX_DT_MS = 1000.0
CLICK_LATENCY_MAX_MS = 5000.0

MIN_WINDOW_FOCUS_SEGMENTS = 3
MIN_FOCUS_SEGMENT_S = 1.0
MIN_RATE_ACTIVE_S = 180.0  # 3-minute minimum active span for per-minute rates (Section 5)

MIN_WINDOW_WEBCAM_SAMPLES = 30
MIN_WEBCAM_VALID_RATIO = 0.50  # Withhold webcam metrics if >50% of frames were dim/no-face/bad-yaw
MIN_WINDOW_BLINKS = 5
MICROSLEEP_THRESHOLD_MS = 500.0
MIN_WINDOW_RPPG_SAMPLES = 5
RPPG_MIN_BPM = 45.0
RPPG_MAX_BPM = 150.0
MIN_DOMINANT_APP_S = 60.0
MIN_EVAL_SPAN_S = 300.0  # Require >= 5 min active span in app before emitting evaluated/alert metrics


def _precise_median(
    values: list[float],
    min_n: int = 10,
    max_rel_se: float = 0.15,
) -> float | None:
    """Return median only when relative standard error (via MAD) is <= max_rel_se."""
    n = len(values)
    if n < min_n:
        return None
    med = statistics.median(values)
    if med <= 1e-9:
        return None
    mad = statistics.median(abs(x - med) for x in values)
    rel_se = (1.4826 * mad) / (math.sqrt(n) * med)
    return med if rel_se <= max_rel_se else None


@dataclass(frozen=True)
class FatigueEvaluation:
    ts: float
    # Peer-reviewed raw window metrics (None when data quality gate is not met)
    key_hold_ms: float | None = None
    key_flight_ms: float | None = None
    backspace_rate: float | None = None
    key_pause_rate: float | None = None
    mouse_velocity_px_per_sec: float | None = None
    mouse_acceleration_px_per_sec2: float | None = None
    mouse_clicks_per_min: float | None = None
    mouse_click_latency_ms: float | None = None
    window_focus_duration_s: float | None = None
    window_switches_per_min: float | None = None
    # Active-window context (dominant non-idle app_hash & strictly app-filtered metrics)
    dominant_app_hash: str | None = None
    app_key_flight_ms: float | None = None
    app_backspace_rate: float | None = None
    app_mouse_velocity_px_per_sec: float | None = None
    # Section 2: Opt-in webcam oculometrics, facial action & rPPG HR
    webcam_valid_frame_ratio: float | None = None
    webcam_perclos: float | None = None
    webcam_ear_variance: float | None = None
    webcam_blink_duration_ms: float | None = None
    webcam_blink_rate_per_min: float | None = None
    webcam_microsleeps: int | None = None
    webcam_mar: float | None = None
    webcam_lid_tightening: float | None = None
    webcam_head_pitch_variance: float | None = None
    webcam_rppg_hr_bpm: float | None = None


def _mouse_accelerations(rows: list[tuple[float, float]]) -> list[float]:
    """Compute magnitude of cursor acceleration (px/s^2) between consecutive moves."""
    accels: list[float] = []
    prev_vel: float | None = None
    for dist_px, dt_ms in rows:
        vel = (dist_px / dt_ms) * 1000.0
        if prev_vel is not None:
            accels.append(abs(vel - prev_vel) / (dt_ms / 1000.0))
        prev_vel = vel
    return accels


def evaluate_once(
    conn: sqlite3.Connection,
    now: float | None = None,
    window_s: float = 900.0,
) -> FatigueEvaluation:
    """Query the rolling window and emit quality-gated peer-reviewed raw metrics."""
    t = now if now is not None else time.time()
    win_start = t - window_s

    # 1. Keystroke dynamics (de Jong et al. 2020; Pimenta et al. 2013; Althoff et al. 2017)
    win_keys = conn.execute(
        "SELECT hold_ms, flight_ms, is_backspace FROM raw_keystrokes "
        "WHERE ts >= ? AND ts <= ? ORDER BY ts DESC LIMIT 150",
        (win_start, t),
    ).fetchall()

    key_hold_ms: float | None = None
    key_flight_ms: float | None = None
    backspace_rate: float | None = None
    key_pause_rate: float | None = None

    if len(win_keys) >= MIN_WINDOW_KEYSTROKES:
        win_holds = [r[0] for r in win_keys if KEY_HOLD_MIN_MS <= r[0] <= KEY_HOLD_MAX_MS]
        key_hold_ms = _precise_median(win_holds, min_n=10, max_rel_se=0.15)

        win_flights = [r[1] for r in win_keys if r[1] is not None and 0.0 < r[1] <= KEY_FLIGHT_MAX_MS]
        key_flight_ms = _precise_median(win_flights, min_n=10, max_rel_se=0.15)

        key_pause_rate = sum(1 for r in win_keys if r[1] is None) / len(win_keys)
        backspace_rate = sum(r[2] for r in win_keys) / len(win_keys)

    # 2. Mouse kinematics: velocity, acceleration, click rate, click latency
    win_mouse = conn.execute(
        "SELECT distance_px, dt_ms FROM raw_mouse "
        "WHERE ts >= ? AND ts <= ? AND is_click = 0 AND distance_px > 0 AND dt_ms > 0 AND dt_ms <= ? "
        "ORDER BY ts ASC",
        (win_start, t, MOUSE_MAX_DT_MS),
    ).fetchall()
    win_click_rows = conn.execute(
        "SELECT dt_ms FROM raw_mouse WHERE ts >= ? AND ts <= ? AND is_click = 1",
        (win_start, t),
    ).fetchall()

    mouse_vel_px_s: float | None = None
    mouse_accel_px_s2: float | None = None
    mouse_clicks_per_min: float | None = None
    mouse_click_latency_ms: float | None = None

    if len(win_mouse) >= MIN_WINDOW_MOUSE_MOVES:
        win_vels = [(d / dt) * 1000.0 for d, dt in win_mouse]
        mouse_vel_px_s = _precise_median(win_vels, min_n=10, max_rel_se=0.15)

        win_accels = _mouse_accelerations(win_mouse)
        if len(win_accels) >= MIN_WINDOW_MOUSE_MOVES - 1:
            mouse_accel_px_s2 = statistics.median(win_accels)

    win_mouse_span = conn.execute(
        "SELECT MIN(ts), MAX(ts) FROM raw_mouse WHERE ts >= ? AND ts <= ?",
        (win_start, t),
    ).fetchone()
    mouse_span_s = (
        (win_mouse_span[1] - win_mouse_span[0])
        if win_mouse_span and win_mouse_span[0] is not None and win_mouse_span[1] is not None
        else 0.0
    )
    if (len(win_click_rows) > 0 or len(win_mouse) >= MIN_WINDOW_MOUSE_MOVES) and mouse_span_s >= MIN_RATE_ACTIVE_S:
        mouse_clicks_per_min = len(win_click_rows) / (mouse_span_s / 60.0)

    win_click_lats = [r[0] for r in win_click_rows if 0.0 < r[0] <= CLICK_LATENCY_MAX_MS]
    if len(win_click_lats) >= MIN_WINDOW_CLICKS:
        mouse_click_latency_ms = statistics.median(win_click_lats)

    # 3. Window focus duration & app switch rate (Mark et al. CHI 2016)
    win_focus = conn.execute(
        "SELECT ts_end - ts_start FROM raw_windows "
        "WHERE ts_start >= ? AND ts_start <= ? AND is_idle = 0 AND (ts_end - ts_start) >= ?",
        (win_start, t, MIN_FOCUS_SEGMENT_S),
    ).fetchall()

    focus_duration_s: float | None = None
    window_switches_per_min: float | None = None

    if len(win_focus) >= MIN_WINDOW_FOCUS_SEGMENTS:
        focus_duration_s = statistics.median(r[0] for r in win_focus)
        active_focus_s = sum(r[0] for r in win_focus)
        if active_focus_s >= MIN_RATE_ACTIVE_S:
            window_switches_per_min = len(win_focus) / (active_focus_s / 60.0)

    # Dominant active app_hash in the 15-min window (for per-app context gauges)
    dom_row = conn.execute(
        "SELECT app_hash, SUM(ts_end - ts_start) AS total_s FROM raw_windows "
        "WHERE ts_start >= ? AND ts_start <= ? AND is_idle = 0 AND (ts_end - ts_start) >= ? "
        "GROUP BY app_hash ORDER BY total_s DESC LIMIT 1",
        (win_start, t, MIN_FOCUS_SEGMENT_S),
    ).fetchone()
    dominant_app_hash: str | None = (
        dom_row[0] if dom_row is not None and dom_row[1] >= MIN_DOMINANT_APP_S else None
    )
    if dominant_app_hash is None:
        # Fallback when staying in one app without switching (no completed raw_windows row yet)
        ks_app = conn.execute(
            "SELECT app_hash FROM raw_keystrokes "
            "WHERE ts >= ? AND ts <= ? AND app_hash != '' "
            "GROUP BY app_hash ORDER BY COUNT(*) DESC LIMIT 1",
            (win_start, t),
        ).fetchone()
        if ks_app is not None:
            dominant_app_hash = ks_app[0]

    # Strictly app-filtered metrics for the dominant active app (no cross-app mixing)
    app_key_flight_ms: float | None = None
    app_backspace_rate: float | None = None
    app_mouse_vel_px_s: float | None = None
    if dominant_app_hash is not None:
        app_keys = conn.execute(
            "SELECT ts, flight_ms, is_backspace FROM raw_keystrokes "
            "WHERE ts >= ? AND ts <= ? AND app_hash = ? ORDER BY ts DESC LIMIT 150",
            (win_start, t, dominant_app_hash),
        ).fetchall()
        app_key_span = (app_keys[0][0] - app_keys[-1][0]) if len(app_keys) >= 2 else 0.0
        if len(app_keys) >= MIN_WINDOW_KEYSTROKES and app_key_span >= MIN_EVAL_SPAN_S:
            app_flights = [r[1] for r in app_keys if r[1] is not None and 0.0 < r[1] <= KEY_FLIGHT_MAX_MS]
            app_key_flight_ms = _precise_median(app_flights, min_n=10, max_rel_se=0.15)
            app_backspace_rate = sum(r[2] for r in app_keys) / len(app_keys)

        app_mouse = conn.execute(
            "SELECT ts, distance_px, dt_ms FROM raw_mouse "
            "WHERE ts >= ? AND ts <= ? AND app_hash = ? AND is_click = 0 "
            "AND distance_px > 0 AND dt_ms > 0 AND dt_ms <= ? ORDER BY ts ASC",
            (win_start, t, dominant_app_hash, MOUSE_MAX_DT_MS),
        ).fetchall()
        app_mouse_span = (app_mouse[-1][0] - app_mouse[0][0]) if len(app_mouse) >= 2 else 0.0
        if len(app_mouse) >= MIN_WINDOW_MOUSE_MOVES and app_mouse_span >= MIN_EVAL_SPAN_S:
            app_mouse_vel_px_s = _precise_median(
                [(d / dt) * 1000.0 for _, d, dt in app_mouse], min_n=10, max_rel_se=0.15
            )

    # 4. Section 2: Opt-in webcam oculometrics, facial action & rPPG HR
    win_cam = conn.execute(
        "SELECT ear, mar, head_pitch, lid_tightening, is_closed, blink_duration_ms, rppg_hr_bpm, valid_ratio "
        "FROM raw_webcam WHERE ts >= ? AND ts <= ?",
        (win_start, t),
    ).fetchall()

    webcam_valid_ratio: float | None = None
    webcam_perclos: float | None = None
    webcam_ear_var: float | None = None
    webcam_blink_dur_ms: float | None = None
    webcam_blink_rate: float | None = None
    webcam_microsleeps: int | None = None
    webcam_mar: float | None = None
    webcam_lid_tight: float | None = None
    webcam_pitch_var: float | None = None
    webcam_rppg_hr: float | None = None

    if len(win_cam) >= MIN_WINDOW_WEBCAM_SAMPLES:
        webcam_valid_ratio = statistics.fmean(r[7] for r in win_cam)
        # Withhold all webcam oculometrics if >50% of frames were dim / no-face / bad-yaw
        if webcam_valid_ratio >= MIN_WEBCAM_VALID_RATIO:
            webcam_perclos = sum(r[4] for r in win_cam) / len(win_cam)
            webcam_ear_var = statistics.variance(r[0] for r in win_cam)
            webcam_mar = statistics.median(r[1] for r in win_cam)
            webcam_pitch_var = statistics.variance(r[2] for r in win_cam)
            webcam_lid_tight = statistics.median(r[3] for r in win_cam)

            win_blinks = [r[5] for r in win_cam if r[5] is not None]
            if len(win_blinks) >= MIN_WINDOW_BLINKS:
                webcam_blink_dur_ms = statistics.median(win_blinks)
                webcam_microsleeps = sum(1 for b in win_blinks if b > MICROSLEEP_THRESHOLD_MS)
                observed_min = len(win_cam) / 60.0
                if observed_min > 0:
                    webcam_blink_rate = len(win_blinks) / observed_min

            win_hrs = [r[6] for r in win_cam if r[6] is not None and RPPG_MIN_BPM <= r[6] <= RPPG_MAX_BPM]
            if len(win_hrs) >= MIN_WINDOW_RPPG_SAMPLES:
                webcam_rppg_hr = statistics.median(win_hrs)

    result = FatigueEvaluation(
        ts=t,
        key_hold_ms=round(key_hold_ms, 2) if key_hold_ms is not None else None,
        key_flight_ms=round(key_flight_ms, 2) if key_flight_ms is not None else None,
        backspace_rate=round(backspace_rate, 4) if backspace_rate is not None else None,
        key_pause_rate=round(key_pause_rate, 4) if key_pause_rate is not None else None,
        mouse_velocity_px_per_sec=round(mouse_vel_px_s, 2) if mouse_vel_px_s is not None else None,
        mouse_acceleration_px_per_sec2=(
            round(mouse_accel_px_s2, 2) if mouse_accel_px_s2 is not None else None
        ),
        mouse_clicks_per_min=round(mouse_clicks_per_min, 2) if mouse_clicks_per_min is not None else None,
        mouse_click_latency_ms=(
            round(mouse_click_latency_ms, 2) if mouse_click_latency_ms is not None else None
        ),
        window_focus_duration_s=round(focus_duration_s, 2) if focus_duration_s is not None else None,
        window_switches_per_min=(
            round(window_switches_per_min, 2) if window_switches_per_min is not None else None
        ),
        dominant_app_hash=dominant_app_hash,
        app_key_flight_ms=round(app_key_flight_ms, 2) if app_key_flight_ms is not None else None,
        app_backspace_rate=round(app_backspace_rate, 4) if app_backspace_rate is not None else None,
        app_mouse_velocity_px_per_sec=(
            round(app_mouse_vel_px_s, 2) if app_mouse_vel_px_s is not None else None
        ),
        webcam_valid_frame_ratio=round(webcam_valid_ratio, 4) if webcam_valid_ratio is not None else None,
        webcam_perclos=round(webcam_perclos, 4) if webcam_perclos is not None else None,
        webcam_ear_variance=round(webcam_ear_var, 6) if webcam_ear_var is not None else None,
        webcam_blink_duration_ms=round(webcam_blink_dur_ms, 2) if webcam_blink_dur_ms is not None else None,
        webcam_blink_rate_per_min=round(webcam_blink_rate, 2) if webcam_blink_rate is not None else None,
        webcam_microsleeps=webcam_microsleeps,
        webcam_mar=round(webcam_mar, 4) if webcam_mar is not None else None,
        webcam_lid_tightening=round(webcam_lid_tight, 4) if webcam_lid_tight is not None else None,
        webcam_head_pitch_variance=round(webcam_pitch_var, 6) if webcam_pitch_var is not None else None,
        webcam_rppg_hr_bpm=round(webcam_rppg_hr, 1) if webcam_rppg_hr is not None else None,
    )

    logged = (
        result.key_hold_ms,
        result.app_key_flight_ms if result.dominant_app_hash else result.key_flight_ms,
        result.app_backspace_rate if result.dominant_app_hash else result.backspace_rate,
        result.key_pause_rate,
        (
            result.app_mouse_velocity_px_per_sec
            if result.dominant_app_hash
            else result.mouse_velocity_px_per_sec
        ),
        result.mouse_acceleration_px_per_sec2,
        result.mouse_clicks_per_min,
        result.mouse_click_latency_ms,
        result.window_focus_duration_s,
        result.window_switches_per_min,
        result.webcam_valid_frame_ratio,
        result.webcam_perclos,
        result.webcam_ear_variance,
        result.webcam_blink_duration_ms,
        result.webcam_blink_rate_per_min,
        result.webcam_microsleeps,
        result.webcam_mar,
        result.webcam_lid_tightening,
        result.webcam_head_pitch_variance,
        result.webcam_rppg_hr_bpm,
    )
    if any(v is not None for v in logged):
        with conn:
            conn.execute(
                """
                INSERT INTO fatigue_log (
                    ts, app_hash, key_hold_ms, key_flight_ms, backspace_rate, key_pause_rate,
                    mouse_velocity_px_per_sec, mouse_acceleration_px_per_sec2,
                    mouse_clicks_per_min, mouse_click_latency_ms,
                    window_focus_duration_s, window_switches_per_min,
                    webcam_valid_frame_ratio, webcam_perclos, webcam_ear_variance,
                    webcam_blink_duration_ms, webcam_blink_rate_per_min, webcam_microsleeps,
                    webcam_mar, webcam_lid_tightening, webcam_head_pitch_variance, webcam_rppg_hr_bpm
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (result.ts, result.dominant_app_hash or "", *logged),
            )
    return result


class FatigueEvaluator:
    """Periodic rolling evaluator exporting each peer-reviewed raw metric to Prometheus."""

    def __init__(
        self,
        db_path: str | Path,
        eval_interval_s: float = 60.0,
        window_s: float = 900.0,
        prometheus_port: int = 9105,
        prometheus_host: str = "127.0.0.1",
        registry: CollectorRegistry | None = None,
        observability: object | None = None,
        on_confirm_needed: Callable[[], object] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.eval_interval_s = eval_interval_s
        self.window_s = window_s
        self.prometheus_port = prometheus_port
        self.prometheus_host = prometheus_host
        self.obs = observability
        self.on_confirm_needed = on_confirm_needed

        reg = registry if registry is not None else CollectorRegistry()
        self.registry = reg

        # Peer-reviewed raw window metrics (each as its own Prometheus entity)
        self.g_key_hold_ms = Gauge(
            "telemetry_key_hold_ms",
            "Median keystroke hold time in ms (de Jong et al. 2020; Pimenta et al. 2013)",
            registry=reg,
        )
        self.g_key_flight_ms = Gauge(
            "telemetry_key_flight_ms",
            "Median inter-key flight interval in ms (de Jong et al. 2020; Althoff et al. 2017)",
            registry=reg,
        )
        self.g_backspace_rate = Gauge(
            "telemetry_backspace_rate",
            "Error-correction backspace ratio 0-1 (de Jong et al. 2020)",
            registry=reg,
        )
        self.g_key_pause_rate = Gauge(
            "telemetry_key_pause_rate",
            "Fraction of keystrokes preceded by a >2s typing pause",
            registry=reg,
        )
        self.g_mouse_vel_raw = Gauge(
            "telemetry_mouse_velocity_px_per_sec",
            "Median cursor velocity in px/s (Pimenta et al. 2013; Thorpe et al. 2021)",
            registry=reg,
        )
        self.g_mouse_accel_raw = Gauge(
            "telemetry_mouse_acceleration_px_per_sec2",
            "Median cursor acceleration magnitude in px/s^2 (Pimenta et al. 2013)",
            registry=reg,
        )
        self.g_mouse_clicks = Gauge(
            "telemetry_mouse_clicks_per_min",
            "Mouse clicks per minute in the rolling window",
            registry=reg,
        )
        self.g_mouse_click_lat = Gauge(
            "telemetry_mouse_click_latency_ms",
            "Median pre-click dwell/latency in ms (Althoff et al. 2017)",
            registry=reg,
        )
        self.g_focus_duration = Gauge(
            "telemetry_window_focus_duration_seconds",
            "Median active window focus duration in seconds (Mark et al. CHI 2016)",
            registry=reg,
        )
        self.g_window_switches = Gauge(
            "telemetry_window_switches_per_min",
            "Application window switches per minute (Mark et al. CHI 2016)",
            registry=reg,
        )

        # Per-app context gauges (labeled by active app_hash — no hardcoded categories)
        self.g_app_flight = Gauge(
            "telemetry_app_key_flight_ms",
            "Median keystroke flight time (ms) in the dominant active app",
            ["app"],
            registry=reg,
        )
        self.g_app_backspace = Gauge(
            "telemetry_app_backspace_rate",
            "Backspace rate (0-1) in the dominant active app",
            ["app"],
            registry=reg,
        )
        self.g_app_mouse_vel = Gauge(
            "telemetry_app_mouse_velocity_px_per_sec",
            "Median mouse velocity (px/s) in the dominant active app",
            ["app"],
            registry=reg,
        )

        # Permanent personal-best anchor & IQR gauges (all 17 loaded from SQLite)
        self.g_app_anchors: dict[str, Gauge] = {
            col: Gauge(
                f"telemetry_anchor_{col}",
                f"Personal-best anchor for {col} per app",
                ["app"],
                registry=reg,
            )
            for col, *_ in APP_ANCHOR_SPECS
        }
        self.g_app_iqrs: dict[str, Gauge] = {
            col: Gauge(
                f"telemetry_iqr_{col}",
                f"Personal IQR (P75-P25) for {col} per app",
                ["app"],
                registry=reg,
            )
            for col, *_ in APP_ANCHOR_SPECS
        }
        self.g_global_anchors: dict[str, Gauge] = {}
        self.g_global_iqrs: dict[str, Gauge] = {}
        for col, metric_name, *_ in GLOBAL_ANCHOR_SPECS:
            g = Gauge(metric_name, f"Personal-best anchor for {col}", registry=reg)
            g.set(math.nan)
            self.g_global_anchors[col] = g
            iqr_name = metric_name.replace("telemetry_anchor_", "telemetry_iqr_")
            gi = Gauge(iqr_name, f"Personal IQR (P75-P25) for {col}", registry=reg)
            gi.set(math.nan)
            self.g_global_iqrs[col] = gi
        self._last_anchor_refresh_ts: float = 0.0
        self._known_anchor_apps: set[str] = set()
        self.anchor_refresh_interval_s: float = 86400.0
        self.anchor_warmup_check_s: float = 900.0

        # Section 2: Opt-in webcam oculometrics, facial action & rPPG HR
        self.g_cam_valid = Gauge(
            "telemetry_webcam_valid_frame_ratio",
            "Fraction of usable webcam frames (0-1; <0.5 withholds webcam metrics)",
            registry=reg,
        )
        self.g_warmup_progress = Gauge(
            "telemetry_anchor_warmup_progress",
            "Active app progress toward 60-sample anchor unlock (0-1)",
            registry=reg,
        )
        self.g_baseline_days = Gauge(
            "telemetry_baseline_days_collected",
            "Distinct calendar days in fatigue_log (alerts unlock at >= 7 days)",
            registry=reg,
        )
        self.g_perclos = Gauge("telemetry_webcam_perclos", "PERCLOS eyelid closure ratio 0-1", registry=reg)
        self.g_ear_var = Gauge("telemetry_webcam_ear_variance", "Eye Aspect Ratio variance", registry=reg)
        self.g_blink_dur = Gauge("telemetry_webcam_blink_duration_ms", "Median blink duration in ms", registry=reg)
        self.g_blink_rate = Gauge("telemetry_webcam_blink_rate_per_min", "Blink rate (blinks/min)", registry=reg)
        self.g_microsleeps = Gauge("telemetry_webcam_microsleeps", "Behavioral microsleeps (blinks >500ms)", registry=reg)
        self.g_mar = Gauge("telemetry_webcam_mar", "Median Mouth Aspect Ratio (yawning)", registry=reg)
        self.g_lid_tight = Gauge("telemetry_webcam_lid_tightening", "Normalized brow-to-lid ratio (Kong et al. 2020)", registry=reg)
        self.g_pitch_var = Gauge("telemetry_webcam_head_pitch_variance", "Head pitch variance (nodding)", registry=reg)
        self.g_rppg_hr = Gauge("telemetry_webcam_rppg_hr_bpm", "Webcam rPPG mean heart rate in bpm (30s window)", registry=reg)

        self._last_app_hash: str | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._conn: sqlite3.Connection | None = None

    def _update_gauges(self, ev: FatigueEvaluation) -> None:
        for gauge, val in (
            (self.g_key_hold_ms, ev.key_hold_ms),
            (self.g_key_flight_ms, ev.key_flight_ms),
            (self.g_backspace_rate, ev.backspace_rate),
            (self.g_key_pause_rate, ev.key_pause_rate),
            (self.g_mouse_vel_raw, ev.mouse_velocity_px_per_sec),
            (self.g_mouse_accel_raw, ev.mouse_acceleration_px_per_sec2),
            (self.g_mouse_clicks, ev.mouse_clicks_per_min),
            (self.g_mouse_click_lat, ev.mouse_click_latency_ms),
            (self.g_focus_duration, ev.window_focus_duration_s),
            (self.g_window_switches, ev.window_switches_per_min),
            (self.g_cam_valid, ev.webcam_valid_frame_ratio),
            (self.g_perclos, ev.webcam_perclos),
            (self.g_ear_var, ev.webcam_ear_variance),
            (self.g_blink_dur, ev.webcam_blink_duration_ms),
            (self.g_blink_rate, ev.webcam_blink_rate_per_min),
            (self.g_microsleeps, ev.webcam_microsleeps),
            (self.g_mar, ev.webcam_mar),
            (self.g_lid_tight, ev.webcam_lid_tightening),
            (self.g_pitch_var, ev.webcam_head_pitch_variance),
            (self.g_rppg_hr, ev.webcam_rppg_hr_bpm),
        ):
            gauge.set(val if val is not None else math.nan)

        if self._last_app_hash is not None and self._last_app_hash != ev.dominant_app_hash:
            for gauge in (self.g_app_flight, self.g_app_backspace, self.g_app_mouse_vel):
                gauge.labels(app=self._last_app_hash).set(math.nan)

        if ev.dominant_app_hash is not None:
            for gauge, val in (
                (self.g_app_flight, ev.app_key_flight_ms),
                (self.g_app_backspace, ev.app_backspace_rate),
                (self.g_app_mouse_vel, ev.app_mouse_velocity_px_per_sec),
            ):
                gauge.labels(app=ev.dominant_app_hash).set(val if val is not None else math.nan)
        self._last_app_hash = ev.dominant_app_hash

    def _needs_webcam_confirmation(self, conn: sqlite3.Connection, ev: FatigueEvaluation) -> bool:
        """Return True if passive data shows drift or is missing during active work."""
        if ev.dominant_app_hash is None:
            return False
        # 1. Silent/inconclusive active work (reading/watching without typing or mousing)
        if ev.key_flight_ms is None and ev.mouse_velocity_px_per_sec is None:
            return True
        # 2. Passive drift vs. stored per-app anchor
        row = conn.execute(
            "SELECT key_flight_ms, backspace_rate, mouse_velocity_px_per_sec "
            "FROM app_anchors WHERE app_hash = ?",
            (ev.dominant_app_hash,),
        ).fetchone()
        if row is None:
            return False
        a_flight, a_bs, a_mvel = row
        if a_flight and ev.app_key_flight_ms and ev.app_key_flight_ms > 1.20 * a_flight:
            return True
        if a_bs and ev.app_backspace_rate and ev.app_backspace_rate > 1.50 * a_bs:
            return True
        if a_mvel and ev.app_mouse_velocity_px_per_sec and ev.app_mouse_velocity_px_per_sec < 0.75 * a_mvel:
            return True
        return False

    def run_once(self, now: float | None = None) -> FatigueEvaluation:
        t0 = time.perf_counter()
        conn = self._conn or init_db(self.db_path)
        try:
            ev = evaluate_once(conn, now=now, window_s=self.window_s)
            self._update_gauges(ev)
            days = conn.execute(
                "SELECT COUNT(DISTINCT date(ts, 'unixepoch', 'localtime')) FROM fatigue_log"
            ).fetchone()[0]
            self.g_baseline_days.set(float(days))
            if ev.dominant_app_hash is not None:
                app_n = conn.execute(
                    "SELECT COUNT(*) FROM fatigue_log WHERE app_hash = ?",
                    (ev.dominant_app_hash,),
                ).fetchone()[0]
                self.g_warmup_progress.set(round(min(1.0, app_n / 60.0), 3))
            else:
                self.g_warmup_progress.set(math.nan)
            if self.on_confirm_needed is not None and self._needs_webcam_confirmation(conn, ev):
                self.on_confirm_needed()
            if self.obs is not None:
                self.obs.eval_duration_s.set(round(time.perf_counter() - t0, 6))
                self.obs.last_eval_ts.set(ev.ts)
                self.obs.refresh_system_gauges(self.db_path)
            return ev
        except Exception:
            if self.obs is not None:
                self.obs.errors_total.labels(component="evaluator").inc()
            raise
        finally:
            if self._conn is None:
                conn.close()

    def start(self, start_http: bool = True) -> None:
        self._conn = init_db(self.db_path)
        if start_http:
            start_http_server(
                self.prometheus_port,
                addr=self.prometheus_host,
                registry=self.registry,
            )
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="fatigue-evaluator", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def export_stored_anchors(self, conn: sqlite3.Connection) -> None:
        """Load all 17 permanent anchors from SQLite app_anchors into Prometheus gauges."""
        app_cols = [s[0] for s in APP_ANCHOR_SPECS]
        g_cols = [s[0] for s in GLOBAL_ANCHOR_SPECS]
        all_cols = app_cols + g_cols
        rows = conn.execute(
            f"SELECT app_hash, {', '.join(all_cols)} FROM app_anchors"
        ).fetchall()
        for row in rows:
            app_hash = row[0]
            self._known_anchor_apps.add(app_hash)
            values = dict(zip(all_cols, row[1:]))
            if app_hash == "_global":
                for col in g_cols:
                    if values[col] is not None:
                        self.g_global_anchors[col].set(values[col])
            else:
                for col in app_cols:
                    if values[col] is not None:
                        self.g_app_anchors[col].labels(app=app_hash).set(values[col])

        for app_hash, metric, iqr_val in conn.execute(
            "SELECT app_hash, metric, iqr FROM app_iqrs"
        ).fetchall():
            if app_hash == "_global" and metric in self.g_global_iqrs:
                self.g_global_iqrs[metric].set(iqr_val)
            elif metric in self.g_app_iqrs:
                self.g_app_iqrs[metric].labels(app=app_hash).set(iqr_val)

    def _run(self) -> None:
        if self._conn is not None:
            refresh_app_anchors(self._conn)
            self.export_stored_anchors(self._conn)
            self._last_anchor_refresh_ts = time.time()
        self.run_once()
        while not self._stop_event.wait(self.eval_interval_s):
            ev = self.run_once()
            now = time.time()
            needs_warmup = (
                "_global" not in self._known_anchor_apps
                or (
                    ev.dominant_app_hash is not None
                    and ev.dominant_app_hash not in self._known_anchor_apps
                )
            )
            interval = self.anchor_warmup_check_s if needs_warmup else self.anchor_refresh_interval_s
            if self._conn is not None and (now - self._last_anchor_refresh_ts) >= interval:
                refresh_app_anchors(self._conn, now=now)
                self.export_stored_anchors(self._conn)
                self._last_anchor_refresh_ts = now
