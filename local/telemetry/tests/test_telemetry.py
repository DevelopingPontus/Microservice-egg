"""Unit & integration tests covering Phases 1-6."""

from __future__ import annotations

import math
from types import SimpleNamespace

from prometheus_client import CollectorRegistry

from telemetry import (
    ActivityTracker,
    BatchWriter,
    FatigueEvaluator,
    KeystrokeCollector,
    MouseCollector,
    WindowFocusCollector,
    evaluate_once,
    hash_app_name,
    init_db,
    prune_old_data,
)


def test_phase1_sqlite_wal_and_batch_writer(tmp_path) -> None:
    db_path = tmp_path / "telemetry.db"
    conn = init_db(db_path)
    mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    assert mode.lower() == "wal"
    conn.close()

    writer = BatchWriter(db_path, flush_interval_s=60.0)
    writer.start()
    writer.enqueue("raw_keystrokes", (1000.0, 80.0, 120.0, 0, "app1"))
    writer.enqueue("raw_mouse", (1000.0, 42.5, 75.0, 0, "app1"))
    writer.enqueue("raw_windows", (900.0, 1000.0, "abc123", 0))
    written = writer.flush()
    writer.stop()

    assert written == 3
    conn = init_db(db_path)
    assert conn.execute("SELECT COUNT(*) FROM raw_keystrokes").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM raw_mouse").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM raw_windows").fetchone()[0] == 1
    conn.close()


def test_phase2_keystroke_collector(tmp_path) -> None:
    db_path = tmp_path / "keys.db"
    writer = BatchWriter(db_path, flush_interval_s=60.0)
    writer.start()
    collector = KeystrokeCollector(writer, ActivityTracker())

    k_a = SimpleNamespace(vk=65, name=None)
    k_bs = SimpleNamespace(vk=8, name="backspace")

    # First key: 100ms hold, no prior flight
    collector.handle_press(k_a, perf_now=1.000, wall_now=100.0)
    collector.handle_release(k_a, perf_now=1.100, wall_now=100.1)

    # Second key: 150ms flight, 80ms hold, backspace=1
    collector.handle_press(k_bs, perf_now=1.200, wall_now=100.2)
    collector.handle_release(k_bs, perf_now=1.280, wall_now=100.28)

    # Third key after >2000ms pause: flight_ms must be NULL
    collector.handle_press(k_a, perf_now=5.000, wall_now=104.0)
    collector.handle_release(k_a, perf_now=5.090, wall_now=104.09)

    writer.flush()
    writer.stop()

    conn = init_db(db_path)
    rows = conn.execute(
        "SELECT hold_ms, flight_ms, is_backspace FROM raw_keystrokes ORDER BY ts"
    ).fetchall()
    conn.close()

    assert len(rows) == 3
    assert round(rows[0][0], 1) == 100.0 and rows[0][1] is None and rows[0][2] == 0
    assert round(rows[1][0], 1) == 80.0 and round(rows[1][1], 1) == 180.0 and rows[1][2] == 1
    assert round(rows[2][0], 1) == 90.0 and rows[2][1] is None and rows[2][2] == 0


def test_phase3_mouse_collector_throttling_and_clicks(tmp_path) -> None:
    db_path = tmp_path / "mouse.db"
    writer = BatchWriter(db_path, flush_interval_s=60.0)
    writer.start()
    collector = MouseCollector(writer, ActivityTracker(), sample_interval_ms=50.0)

    collector.handle_move(0, 0, perf_now=1.000, wall_now=100.0)
    # 20ms later -> throttled (ignored)
    collector.handle_move(10, 0, perf_now=1.020, wall_now=100.02)
    # 60ms after initial -> recorded (distance = 3-4-5 triangle = 5.0)
    collector.handle_move(3, 4, perf_now=1.060, wall_now=100.06)
    # Click recorded immediately
    collector.handle_click(3, 4, "left", True, perf_now=1.070, wall_now=100.07)
    # Release ignored
    collector.handle_click(3, 4, "left", False, perf_now=1.080, wall_now=100.08)

    writer.flush()
    writer.stop()

    conn = init_db(db_path)
    rows = conn.execute(
        "SELECT distance_px, dt_ms, is_click FROM raw_mouse ORDER BY ts"
    ).fetchall()
    conn.close()

    assert len(rows) == 2
    assert round(rows[0][0], 2) == 5.0 and round(rows[0][1], 1) == 60.0 and rows[0][2] == 0
    assert rows[1][2] == 1


def test_phase4_window_focus_and_idle(tmp_path) -> None:
    db_path = tmp_path / "windows.db"
    writer = BatchWriter(db_path, flush_interval_s=60.0)
    writer.start()

    activity = ActivityTracker()
    activity.touch(1000.0)
    apps = iter(["VSCode", "VSCode", "Safari", "Safari"])
    collector = WindowFocusCollector(
        writer,
        activity,
        idle_threshold_s=60.0,
        app_provider=lambda: next(apps),
    )

    collector.poll_once(now=1000.0)  # starts VSCode
    collector.poll_once(now=1010.0)  # still VSCode (no row written)
    collector.poll_once(now=1020.0)  # switches to Safari -> writes VSCode [1000, 1020]
    collector.poll_once(now=1065.0)  # idle (>60s since 1000) -> writes Safari [1020, 1065]
    collector.flush_current(now=1100.0)  # writes idle [1065, 1100]

    writer.flush()
    writer.stop()

    conn = init_db(db_path)
    rows = conn.execute(
        "SELECT ts_start, ts_end, app_hash, is_idle FROM raw_windows ORDER BY ts_start"
    ).fetchall()
    conn.close()

    assert len(rows) == 3
    assert rows[0] == (1000.0, 1020.0, hash_app_name("VSCode"), 0)
    assert rows[1] == (1020.0, 1065.0, hash_app_name("Safari"), 0)
    assert rows[2] == (1065.0, 1100.0, "idle", 1)


def test_phase5_retention_pruning(tmp_path) -> None:
    db_path = tmp_path / "prune.db"
    conn = init_db(db_path)
    now = 2_000_000.0
    old_ts = now - (15 * 86400)
    fresh_ts = now - (2 * 86400)

    with conn:
        conn.execute("INSERT INTO raw_keystrokes VALUES (?, 80, 120, 0, 'a')", (old_ts,))
        conn.execute("INSERT INTO raw_keystrokes VALUES (?, 80, 120, 0, 'a')", (fresh_ts,))
        conn.execute("INSERT INTO raw_mouse VALUES (?, 10, 50, 0, 'a')", (old_ts,))
        conn.execute("INSERT INTO raw_windows VALUES (?, ?, 'a', 0)", (old_ts, old_ts + 10))

    deleted = prune_old_data(conn, retention_days=14, now=now)
    assert deleted == {
        "raw_keystrokes": 1,
        "raw_mouse": 1,
        "raw_windows": 1,
        "raw_webcam": 0,
    }
    assert conn.execute("SELECT COUNT(*) FROM raw_keystrokes").fetchone()[0] == 1
    conn.close()


def test_phase6_evaluator_and_prometheus_gauges(tmp_path) -> None:
    db_path = tmp_path / "eval.db"
    conn = init_db(db_path)
    now = 2_000_000.0

    # Seed 14-day baseline: fast typing (80ms hold, 120ms flight, 2% backspace),
    # fast mouse (500 px/s), long focus (120s).
    with conn:
        for i in range(300):
            ts = now - 86400 + i
            bs = 1 if (i % 50 == 0) else 0
            conn.execute(
                "INSERT INTO raw_keystrokes VALUES (?, ?, ?, ?, 'app')",
                (ts, 80.0 + (i % 5), 120.0 + (i % 10), bs),
            )
        for i in range(50):
            conn.execute(
                "INSERT INTO raw_mouse VALUES (?, ?, ?, 0, 'app')",
                (now - 86400 + i, 50.0 + (i % 5) * 4.0, 100.0),
            )
        for i in range(25):
            conn.execute(
                "INSERT INTO raw_mouse VALUES (?, 0.0, ?, 1, 'app')",
                (now - 86400 + i * 10, 150.0 + (i % 5) * 10.0),
            )
        for i in range(20):
            # Vary baseline switch density (1 or 2 switches per 15-min bucket)
            t0 = now - 86400 + i * 1000
            conn.execute(
                "INSERT INTO raw_windows VALUES (?, ?, 'app', 0)",
                (t0, t0 + 120.0 + (i % 10)),
            )
            if i % 2 == 0:
                conn.execute(
                    "INSERT INTO raw_windows VALUES (?, ?, 'app2', 0)",
                    (t0 + 200.0, t0 + 320.0),
                )

        # Seed current 15-min window (>= 5m span = 360s so evaluated per-app metrics qualify)
        for i in range(40):
            ts = now - 400 + i * 10
            bs = 1 if (i % 4 == 0) else 0
            conn.execute(
                "INSERT INTO raw_keystrokes VALUES (?, ?, ?, ?, 'app')",
                (ts, 120.0, 220.0, bs),
            )
        for i in range(25):
            conn.execute(
                "INSERT INTO raw_mouse VALUES (?, ?, ?, 0, 'app')",
                (now - 400 + i * 15, 15.0 + (i % 2), 100.0),
            )
        for i in range(6):
            conn.execute(
                "INSERT INTO raw_mouse VALUES (?, 0.0, ?, 1, 'app')",
                (now - 400 + i * 60, 320.0),
            )
        for i in range(5):
            t0 = now - 300 + i * 45
            conn.execute(
                "INSERT INTO raw_windows VALUES (?, ?, 'app', 0)",
                (t0, t0 + 40.0),
            )

    ev = evaluate_once(conn, now=now)
    assert ev.key_hold_ms == 120.0
    assert ev.key_flight_ms == 220.0
    assert ev.backspace_rate == 0.25
    assert ev.mouse_velocity_px_per_sec == 150.0
    assert ev.mouse_acceleration_px_per_sec2 == 100.0
    assert ev.mouse_click_latency_ms == 320.0
    assert ev.window_focus_duration_s == 40.0
    # 5 segments * 40s = 200s active => 5 / (200/60) = 1.5 switches/min
    assert ev.window_switches_per_min == 1.5
    assert conn.execute("SELECT COUNT(*) FROM fatigue_log").fetchone()[0] == 1
    conn.close()

    # Verify Prometheus gauge export via custom registry (no z-scores or fatigue_score)
    reg = CollectorRegistry()
    evaluator = FatigueEvaluator(db_path, registry=reg)
    evaluator.run_once(now=now)
    assert reg.get_sample_value("fatigue_score") is None
    assert reg.get_sample_value("fatigue_key_flight_zscore") is None
    assert reg.get_sample_value("telemetry_key_hold_ms") == 120.0
    assert reg.get_sample_value("telemetry_key_flight_ms") == 220.0
    assert reg.get_sample_value("telemetry_backspace_rate") == 0.25
    assert reg.get_sample_value("telemetry_key_pause_rate") == 0.0
    assert reg.get_sample_value("telemetry_mouse_velocity_px_per_sec") == 150.0
    assert reg.get_sample_value("telemetry_mouse_acceleration_px_per_sec2") == 100.0
    # 6 clicks over 360s span => 1.0 clicks/min
    assert reg.get_sample_value("telemetry_mouse_clicks_per_min") == 1.0
    assert reg.get_sample_value("telemetry_mouse_click_latency_ms") == 320.0
    assert reg.get_sample_value("telemetry_window_focus_duration_seconds") == 40.0
    assert reg.get_sample_value("telemetry_window_switches_per_min") == 1.5
    # Per-app context gauges (dominant active app = 'app')
    assert reg.get_sample_value("telemetry_app_key_flight_ms", {"app": "app"}) == 220.0
    assert reg.get_sample_value("telemetry_app_backspace_rate", {"app": "app"}) == 0.25
    assert reg.get_sample_value("telemetry_app_mouse_velocity_px_per_sec", {"app": "app"}) == 150.0


def test_phase6_withholds_metrics_without_good_data(tmp_path) -> None:
    db_path = tmp_path / "sparse.db"
    conn = init_db(db_path)
    now = 2_000_000.0

    # Seed sparse / noisy data below peer-reviewed gates:
    # - Only 5 keystrokes (needs >= 30) and a stuck-key 5000ms hold outlier
    # - Only 3 mouse moves (needs >= 20)
    # - Only sub-second window flicker (needs >= 3 segments of >= 1s)
    with conn:
        for i in range(5):
            conn.execute("INSERT INTO raw_keystrokes VALUES (?, 5000.0, 120.0, 0, 'app')", (now - 60 + i,))
        for i in range(3):
            conn.execute("INSERT INTO raw_mouse VALUES (?, 10.0, 50.0, 0, 'app')", (now - 60 + i,))
        for i in range(5):
            t0 = now - 60 + i
            conn.execute("INSERT INTO raw_windows VALUES (?, ?, 'app', 0)", (t0, t0 + 0.2))

    ev = evaluate_once(conn, now=now)
    assert ev.key_hold_ms is None
    assert ev.key_flight_ms is None
    assert ev.mouse_velocity_px_per_sec is None
    assert ev.mouse_acceleration_px_per_sec2 is None
    assert ev.mouse_clicks_per_min is None
    assert ev.mouse_click_latency_ms is None
    assert ev.window_focus_duration_s is None
    assert ev.window_switches_per_min is None
    # No fake evaluation row written to fatigue_log
    assert conn.execute("SELECT COUNT(*) FROM fatigue_log").fetchone()[0] == 0
    conn.close()

    reg = CollectorRegistry()
    evaluator = FatigueEvaluator(db_path, registry=reg)
    evaluator.run_once(now=now)
    assert math.isnan(reg.get_sample_value("telemetry_key_hold_ms"))
    assert math.isnan(reg.get_sample_value("telemetry_mouse_velocity_px_per_sec"))
    assert math.isnan(reg.get_sample_value("telemetry_mouse_acceleration_px_per_sec2"))
    assert math.isnan(reg.get_sample_value("telemetry_mouse_click_latency_ms"))
    assert math.isnan(reg.get_sample_value("telemetry_window_focus_duration_seconds"))


def test_webcam_oculometrics_export(tmp_path) -> None:
    from telemetry import estimate_rppg_hr_bpm

    # Verify rPPG HR estimator recovers a synthetic 72 bpm (1.2 Hz) sine wave over 30s at 20 Hz
    sample_hz = 20.0
    green = [math.sin(2.0 * math.pi * (72.0 / 60.0) * (k / sample_hz)) for k in range(600)]
    assert estimate_rppg_hr_bpm(green, sample_hz=sample_hz) == 72.0

    db_path = tmp_path / "laptop_sensors.db"
    conn = init_db(db_path)
    now = 2_000_000.0

    # Seed 35 webcam samples: 10 closed (PERCLOS = 10/35), 6 blinks (2 microsleeps >500ms),
    # lid_tightening = 0.08, rPPG HR = 72.0 bpm
    blink_durs = [180.0, 200.0, 220.0, 240.0, 550.0, 620.0]
    with conn:
        for i in range(35):
            is_closed = 1 if i < 10 else 0
            ear = 0.15 if is_closed else 0.30
            b_dur = blink_durs[i] if i < len(blink_durs) else None
            hr = 72.0 if i < 10 else None
            conn.execute(
                "INSERT INTO raw_webcam VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now - 60 + i, ear, 0.25, 0.45 + (i % 3) * 0.02, 0.08, is_closed, b_dur, hr, 0.9),
            )
    conn.close()

    reg = CollectorRegistry()
    evaluator = FatigueEvaluator(db_path, registry=reg)
    ev = evaluator.run_once(now=now)

    assert ev.webcam_perclos == round(10 / 35, 4)
    assert ev.webcam_blink_duration_ms == 230.0
    assert ev.webcam_microsleeps == 2
    assert ev.webcam_blink_rate_per_min == round(6 / (35 / 60.0), 2)
    assert ev.webcam_lid_tightening == 0.08
    assert ev.webcam_rppg_hr_bpm == 72.0
    assert reg.get_sample_value("telemetry_webcam_perclos") == ev.webcam_perclos
    assert reg.get_sample_value("telemetry_webcam_blink_duration_ms") == 230.0
    assert reg.get_sample_value("telemetry_webcam_microsleeps") == 2.0
    assert reg.get_sample_value("telemetry_webcam_lid_tightening") == 0.08
    assert reg.get_sample_value("telemetry_webcam_rppg_hr_bpm") == 72.0
    assert reg.get_sample_value("telemetry_webcam_mar") == 0.25

    conn = init_db(db_path)
    row = conn.execute("SELECT webcam_perclos, webcam_rppg_hr_bpm FROM fatigue_log").fetchone()
    conn.close()
    assert row == (ev.webcam_perclos, 72.0)

    # Bad lighting / looking away (valid_ratio < 0.50) must withhold webcam oculometrics
    bad_db = tmp_path / "bad_cam.db"
    c2 = init_db(bad_db)
    with c2:
        for i in range(35):
            c2.execute(
                "INSERT INTO raw_webcam VALUES (?, 0.12, 0.25, 0.45, 0.08, 1.0, 200.0, 72.0, 0.2)",
                (now - 60 + i,),
            )
    c2.close()
    reg2 = CollectorRegistry()
    ev_bad = FatigueEvaluator(bad_db, registry=reg2).run_once(now=now)
    assert ev_bad.webcam_valid_frame_ratio == 0.2
    assert ev_bad.webcam_perclos is None
    assert math.isnan(reg2.get_sample_value("telemetry_webcam_perclos"))
    assert reg2.get_sample_value("telemetry_webcam_valid_frame_ratio") == 0.2


def test_devops_observability_metrics(tmp_path) -> None:
    from telemetry import DaemonObservability

    db_path = tmp_path / "obs.db"
    reg = CollectorRegistry()
    obs = DaemonObservability(reg)

    writer = BatchWriter(db_path, flush_interval_s=60.0, observability=obs)
    writer.start()
    writer.enqueue("raw_keystrokes", (1000.0, 80.0, 120.0, 0, "app1"))
    writer.enqueue("raw_mouse", (1000.0, 15.0, 75.0, 0, "app1"))
    assert reg.get_sample_value("telemetry_writer_queue_size") == 2.0
    writer.flush()
    writer.stop()

    assert reg.get_sample_value("telemetry_events_flushed_total", {"table": "raw_keystrokes"}) == 1.0
    assert reg.get_sample_value("telemetry_events_flushed_total", {"table": "raw_mouse"}) == 1.0
    assert reg.get_sample_value("telemetry_writer_queue_size") == 0.0

    evaluator = FatigueEvaluator(db_path, registry=reg, observability=obs)
    evaluator.run_once(now=1000.0)
    assert reg.get_sample_value("telemetry_db_size_bytes") > 0
    assert reg.get_sample_value("telemetry_eval_duration_seconds") >= 0
    assert reg.get_sample_value("telemetry_last_eval_timestamp_seconds") == 1000.0


def test_permanent_sqlite_app_anchors(tmp_path) -> None:
    from telemetry import refresh_app_anchors

    db_path = tmp_path / "anchors.db"
    conn = init_db(db_path)

    # Seed 20 fatigue_log rows for 'vscode' (10 clean + 10 high-error) + 1 drowsy outlier
    with conn:
        for i in range(20):
            conn.execute(
                "INSERT INTO fatigue_log "
                "(ts, app_hash, key_flight_ms, backspace_rate, mouse_velocity_px_per_sec, "
                "window_focus_duration_s, window_switches_per_min) "
                "VALUES (?, 'vscode', ?, ?, ?, ?, ?)",
                (1000.0 + i * 60, 100.0 + i * 10.0, 0.01 * (i + 1), 200.0 + i * 10.0, 60.0 + i * 5.0, 1.0 + i * 0.2),
            )
        # Drowsy row with artificially fast typing must be excluded from anchor pool
        conn.execute(
            "INSERT INTO fatigue_log "
            "(ts, app_hash, key_flight_ms, backspace_rate, mouse_velocity_px_per_sec, webcam_perclos) "
            "VALUES (5000.0, 'vscode', 50.0, 0.01, 500.0, 0.30)"
        )

    # Below min_samples=60 -> nothing written yet
    assert refresh_app_anchors(conn, min_samples=60, now=2000.0) == {}

    # With min_samples=10 -> 2-pass filter keeps only the 10 clean rows (100..190) for flight
    anchors = refresh_app_anchors(conn, min_samples=10, now=2000.0)
    assert "vscode" in anchors and "_global" in anchors
    assert anchors["vscode"]["key_flight_ms"] == 118.0
    assert anchors["vscode"]["backspace_rate"] == 0.048
    assert anchors["vscode"]["mouse_velocity_px_per_sec"] == 352.0

    reg = CollectorRegistry()
    ev = FatigueEvaluator(db_path, registry=reg)
    ev.export_stored_anchors(conn)
    conn.close()

    assert reg.get_sample_value("telemetry_anchor_key_flight_ms", {"app": "vscode"}) == 118.0
    assert reg.get_sample_value("telemetry_anchor_backspace_rate", {"app": "vscode"}) == 0.048
    assert reg.get_sample_value("telemetry_anchor_mouse_velocity_px_per_sec", {"app": "vscode"}) == 352.0
    assert reg.get_sample_value("telemetry_anchor_window_focus_duration_seconds") == 136.0
