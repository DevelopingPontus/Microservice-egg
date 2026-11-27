"""Permanent per-app and global personal-best anchors & personal IQRs in SQLite."""

from __future__ import annotations

import math
import sqlite3
import statistics
import time

MIN_ANCHOR_SAMPLES = 60  # ~1 hour of valid 1-min evaluations before setting an anchor
BACKSPACE_ANCHOR_FLOOR = 0.02

# (column_name, quantile, floor, round_digits, require_clean_typing)
APP_ANCHOR_SPECS: tuple[tuple[str, float, float, int, bool], ...] = (
    ("key_flight_ms", 0.20, 0.0, 2, True),
    ("key_hold_ms", 0.20, 0.0, 2, True),
    ("backspace_rate", 0.20, BACKSPACE_ANCHOR_FLOOR, 4, False),
    ("key_pause_rate", 0.20, 0.01, 4, False),
    ("mouse_velocity_px_per_sec", 0.80, 0.0, 2, False),
    ("mouse_acceleration_px_per_sec2", 0.80, 0.0, 2, False),
    ("mouse_clicks_per_min", 0.80, 0.0, 2, False),
    ("mouse_click_latency_ms", 0.20, 0.0, 2, False),
)

GLOBAL_ANCHOR_SPECS: tuple[tuple[str, str, float, float, int], ...] = (
    ("window_focus_duration_s", "telemetry_anchor_window_focus_duration_seconds", 0.80, 0.0, 2),
    ("window_switches_per_min", "telemetry_anchor_window_switches_per_min", 0.20, 0.0, 2),
    ("webcam_ear_variance", "telemetry_anchor_webcam_ear_variance", 0.20, 0.0005, 6),
    ("webcam_blink_duration_ms", "telemetry_anchor_webcam_blink_duration_ms", 0.20, 0.0, 2),
    ("webcam_blink_rate_per_min", "telemetry_anchor_webcam_blink_rate_per_min", 0.50, 1.0, 2),
    ("webcam_mar", "telemetry_anchor_webcam_mar", 0.20, 0.02, 4),
    ("webcam_lid_tightening", "telemetry_anchor_webcam_lid_tightening", 0.80, 0.0, 4),
    ("webcam_head_pitch_variance", "telemetry_anchor_webcam_head_pitch_variance", 0.20, 0.0005, 6),
    ("webcam_rppg_hr_bpm", "telemetry_anchor_webcam_rppg_hr_bpm", 0.50, 0.0, 1),
)


def _percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile (q in 0..1) on a non-empty list."""
    s = sorted(values)
    idx = q * (len(s) - 1)
    lo = int(math.floor(idx))
    hi = min(lo + 1, len(s) - 1)
    frac = idx - lo
    return s[lo] + frac * (s[hi] - s[lo])


def refresh_app_anchors(
    conn: sqlite3.Connection,
    min_samples: int = MIN_ANCHOR_SAMPLES,
    now: float | None = None,
) -> dict[str, dict[str, float | None]]:
    """Compute/update all 17 permanent personal-best anchors and IQRs from fatigue_log."""
    t = now if now is not None else time.time()
    anchors: dict[str, dict[str, float | None]] = {}

    app_cols = [s[0] for s in APP_ANCHOR_SPECS]
    app_hashes = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT app_hash FROM fatigue_log WHERE app_hash != ''"
        ).fetchall()
    ]
    with conn:
        for app in app_hashes:
            rows = conn.execute(
                f"SELECT {', '.join(app_cols)} FROM fatigue_log WHERE app_hash = ? "
                "AND (webcam_perclos IS NULL OR webcam_perclos <= 0.15) "
                "AND (webcam_microsleeps IS NULL OR webcam_microsleeps = 0)",
                (app,),
            ).fetchall()
            bs_idx = app_cols.index("backspace_rate")
            bspaces = [r[bs_idx] for r in rows if r[bs_idx] is not None]
            med_bs = statistics.median(bspaces) if bspaces else None

            computed: dict[str, float | None] = {}
            computed_iqrs: dict[str, float] = {}
            for idx, (col, q, floor, digits, clean_only) in enumerate(APP_ANCHOR_SPECS):
                vals = [
                    r[idx]
                    for r in rows
                    if r[idx] is not None
                    and (not clean_only or med_bs is None or r[bs_idx] is None or r[bs_idx] <= med_bs)
                ]
                if len(vals) >= min_samples:
                    anc = round(max(_percentile(vals, q), floor), digits)
                    iqr = _percentile(vals, 0.75) - _percentile(vals, 0.25)
                    iqr_floor = max(floor, abs(anc) * 0.05, 1e-4)
                    computed[col] = anc
                    computed_iqrs[col] = round(max(iqr, iqr_floor), max(digits, 4))
                else:
                    computed[col] = None

            if any(v is not None for v in computed.values()):
                placeholders = ", ".join("?" for _ in app_cols)
                updates = ", ".join(
                    f"{c}=COALESCE(excluded.{c}, app_anchors.{c})" for c in app_cols
                )
                conn.execute(
                    f"INSERT INTO app_anchors (app_hash, updated_ts, sample_count, {', '.join(app_cols)}) "
                    f"VALUES (?, ?, ?, {placeholders}) "
                    f"ON CONFLICT(app_hash) DO UPDATE SET "
                    f"updated_ts=excluded.updated_ts, sample_count=excluded.sample_count, {updates}",
                    (app, t, len(rows), *(computed[c] for c in app_cols)),
                )
                for col, iqr_val in computed_iqrs.items():
                    conn.execute(
                        "INSERT INTO app_iqrs (app_hash, metric, iqr) VALUES (?, ?, ?) "
                        "ON CONFLICT(app_hash, metric) DO UPDATE SET iqr=excluded.iqr",
                        (app, col, iqr_val),
                    )
                anchors[app] = computed

        # Global anchors (window focus/switches + webcam metrics)
        g_cols = [s[0] for s in GLOBAL_ANCHOR_SPECS]
        g_rows = conn.execute(
            f"SELECT {', '.join(g_cols)} FROM fatigue_log "
            "WHERE (webcam_perclos IS NULL OR webcam_perclos <= 0.15) "
            "AND (webcam_microsleeps IS NULL OR webcam_microsleeps = 0)"
        ).fetchall()
        g_computed: dict[str, float | None] = {}
        g_iqrs: dict[str, float] = {}
        for idx, (col, _, q, floor, digits) in enumerate(GLOBAL_ANCHOR_SPECS):
            vals = [r[idx] for r in g_rows if r[idx] is not None]
            if len(vals) >= min_samples:
                anc = round(max(_percentile(vals, q), floor), digits)
                iqr = _percentile(vals, 0.75) - _percentile(vals, 0.25)
                iqr_floor = max(floor, abs(anc) * 0.05, 1e-4)
                g_computed[col] = anc
                g_iqrs[col] = round(max(iqr, iqr_floor), max(digits, 4))
            else:
                g_computed[col] = None
        if any(v is not None for v in g_computed.values()):
            placeholders = ", ".join("?" for _ in g_cols)
            updates = ", ".join(
                f"{c}=COALESCE(excluded.{c}, app_anchors.{c})" for c in g_cols
            )
            conn.execute(
                f"INSERT INTO app_anchors (app_hash, updated_ts, sample_count, {', '.join(g_cols)}) "
                f"VALUES ('_global', ?, ?, {placeholders}) "
                f"ON CONFLICT(app_hash) DO UPDATE SET "
                f"updated_ts=excluded.updated_ts, sample_count=excluded.sample_count, {updates}",
                (t, len(g_rows), *(g_computed[c] for c in g_cols)),
            )
            for col, iqr_val in g_iqrs.items():
                conn.execute(
                    "INSERT INTO app_iqrs (app_hash, metric, iqr) VALUES ('_global', ?, ?) "
                    "ON CONFLICT(app_hash, metric) DO UPDATE SET iqr=excluded.iqr",
                    (col, iqr_val),
                )
            anchors["_global"] = g_computed
    return anchors
