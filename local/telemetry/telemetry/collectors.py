"""Phases 2, 3, 4: Anonymized keystroke, mouse, and window-focus collectors."""

from __future__ import annotations

import hashlib
import math
import sys
import threading
import time
from typing import Any, Callable

from telemetry.db import BatchWriter

MAX_FLIGHT_MS = 2000.0


class ActivityTracker:
    """Thread-safe tracker for the latest user input timestamp and active app_hash."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_input_ts = time.time()
        self._app_hash = ""

    def touch(self, now: float | None = None) -> None:
        with self._lock:
            self._last_input_ts = now if now is not None else time.time()

    def set_app_hash(self, app_hash: str) -> None:
        with self._lock:
            self._app_hash = app_hash

    def get_app_hash(self) -> str:
        with self._lock:
            return self._app_hash

    def idle_seconds(self, now: float | None = None) -> float:
        current = now if now is not None else time.time()
        with self._lock:
            return max(0.0, current - self._last_input_ts)


class KeystrokeCollector:
    """Phase 2: Logs (ts, hold_ms, flight_ms, is_backspace) without storing characters."""

    def __init__(
        self,
        writer: BatchWriter,
        activity: ActivityTracker,
        max_flight_ms: float = MAX_FLIGHT_MS,
    ) -> None:
        self.writer = writer
        self.activity = activity
        self.max_flight_ms = max_flight_ms
        self._key_down: dict[str, float] = {}
        self._last_key_up: float | None = None
        self._listener: Any = None

    @staticmethod
    def _key_id(key: Any) -> tuple[str, bool]:
        """Return an ephemeral in-memory key identifier and whether it is Backspace."""
        name = getattr(key, "name", None)
        is_backspace = name in ("backspace", "delete")
        # Use object/vk identity only in memory to match press->release; never persisted.
        vk = getattr(key, "vk", None)
        ident = f"vk:{vk}" if vk is not None else f"key:{name or hash(key)}"
        return ident, is_backspace

    def handle_press(
        self,
        key: Any,
        *_args: Any,
        perf_now: float | None = None,
        wall_now: float | None = None,
    ) -> None:
        t_perf = perf_now if perf_now is not None else time.perf_counter()
        self.activity.touch(wall_now)
        key_id, _ = self._key_id(key)
        # Ignore OS key-repeat press events while key is already held down.
        self._key_down.setdefault(key_id, t_perf)

    def handle_release(
        self,
        key: Any,
        *_args: Any,
        perf_now: float | None = None,
        wall_now: float | None = None,
    ) -> None:
        t_perf = perf_now if perf_now is not None else time.perf_counter()
        t_wall = wall_now if wall_now is not None else time.time()
        self.activity.touch(t_wall)

        key_id, is_backspace = self._key_id(key)
        down_ts = self._key_down.pop(key_id, None)
        if down_ts is None:
            return

        hold_ms = max(0.0, (t_perf - down_ts) * 1000.0)
        flight_ms: float | None = None
        if self._last_key_up is not None:
            gap_ms = (t_perf - self._last_key_up) * 1000.0
            if 0.0 <= gap_ms <= self.max_flight_ms:
                flight_ms = gap_ms

        self._last_key_up = t_perf
        self.writer.enqueue(
            "raw_keystrokes",
            (t_wall, hold_ms, flight_ms, int(is_backspace), self.activity.get_app_hash()),
        )

    def start(self) -> None:
        from pynput import keyboard

        self._listener = keyboard.Listener(
            on_press=lambda key: self.handle_press(key),
            on_release=lambda key: self.handle_release(key),
        )
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


class MouseCollector:
    """Phase 3: Throttled mouse movement (10-20 Hz) and immediate click logging."""

    def __init__(
        self,
        writer: BatchWriter,
        activity: ActivityTracker,
        sample_interval_ms: float = 75.0,
    ) -> None:
        self.writer = writer
        self.activity = activity
        self.sample_interval_ms = sample_interval_ms
        self._last_pos: tuple[float, float] | None = None
        self._last_move_perf: float | None = None
        self._listener: Any = None

    def handle_move(
        self,
        x: float,
        y: float,
        *_args: Any,
        perf_now: float | None = None,
        wall_now: float | None = None,
    ) -> None:
        t_perf = perf_now if perf_now is not None else time.perf_counter()
        t_wall = wall_now if wall_now is not None else time.time()
        self.activity.touch(t_wall)

        if self._last_pos is None or self._last_move_perf is None:
            self._last_pos = (x, y)
            self._last_move_perf = t_perf
            return

        dt_ms = (t_perf - self._last_move_perf) * 1000.0
        if dt_ms < self.sample_interval_ms:
            return

        dx = x - self._last_pos[0]
        dy = y - self._last_pos[1]
        dist_px = math.hypot(dx, dy)
        self._last_pos = (x, y)
        self._last_move_perf = t_perf
        self.writer.enqueue("raw_mouse", (t_wall, dist_px, dt_ms, 0, self.activity.get_app_hash()))

    def handle_click(
        self,
        x: float,
        y: float,
        _button: Any,
        pressed: bool,
        *_args: Any,
        perf_now: float | None = None,
        wall_now: float | None = None,
    ) -> None:
        if not pressed:
            return
        t_perf = perf_now if perf_now is not None else time.perf_counter()
        t_wall = wall_now if wall_now is not None else time.time()
        self.activity.touch(t_wall)

        dist_px = 0.0
        dt_ms = 0.0
        if self._last_pos is not None and self._last_move_perf is not None:
            dist_px = math.hypot(x - self._last_pos[0], y - self._last_pos[1])
            dt_ms = max(0.0, (t_perf - self._last_move_perf) * 1000.0)
        self._last_pos = (x, y)
        self._last_move_perf = t_perf
        self.writer.enqueue("raw_mouse", (t_wall, dist_px, dt_ms, 1, self.activity.get_app_hash()))

    def start(self) -> None:
        from pynput import mouse

        self._listener = mouse.Listener(
            on_move=lambda x, y: self.handle_move(x, y),
            on_click=lambda x, y, btn, pressed: self.handle_click(x, y, btn, pressed),
        )
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


def hash_app_name(app_name: str) -> str:
    """Privacy-safe short SHA-256 hash of the active application name."""
    return hashlib.sha256(app_name.encode("utf-8")).hexdigest()[:16]


def get_active_app_name() -> str:
    """Return the frontmost application name on macOS, Windows, or Linux X11."""
    if sys.platform == "darwin":
        try:
            from AppKit import NSWorkspace

            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is not None and app.localizedName():
                return str(app.localizedName())
        except Exception:
            pass
    elif sys.platform == "win32":
        try:
            import win32gui

            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            if title:
                # Use the trailing app segment (e.g. "file.py - Visual Studio Code" -> "Visual Studio Code")
                return title.split(" - ")[-1].strip()
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        try:
            import subprocess

            out = subprocess.check_output(
                ["xdotool", "getactivewindow", "getwindowclassname"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=1.0,
            ).strip()
            if out:
                return out
        except Exception:
            pass
    return "unknown"


class WindowFocusCollector:
    """Phase 4: 1-second poller logging active app & idle (>60s) transitions."""

    def __init__(
        self,
        writer: BatchWriter,
        activity: ActivityTracker,
        poll_interval_s: float = 1.0,
        idle_threshold_s: float = 60.0,
        app_provider: Callable[[], str] = get_active_app_name,
    ) -> None:
        self.writer = writer
        self.activity = activity
        self.poll_interval_s = poll_interval_s
        self.idle_threshold_s = idle_threshold_s
        self.app_provider = app_provider

        self._current_app_hash: str | None = None
        self._current_is_idle: bool | None = None
        self._segment_start: float | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def poll_once(self, now: float | None = None) -> None:
        t = now if now is not None else time.time()
        is_idle = self.activity.idle_seconds(t) >= self.idle_threshold_s
        app_hash = "idle" if is_idle else hash_app_name(self.app_provider())
        self.activity.set_app_hash("" if is_idle else app_hash)

        if self._segment_start is None:
            self._current_app_hash = app_hash
            self._current_is_idle = is_idle
            self._segment_start = t
            return

        if app_hash != self._current_app_hash or is_idle != self._current_is_idle:
            self.writer.enqueue(
                "raw_windows",
                (self._segment_start, t, self._current_app_hash, int(bool(self._current_is_idle))),
            )
            self._current_app_hash = app_hash
            self._current_is_idle = is_idle
            self._segment_start = t

    def flush_current(self, now: float | None = None) -> None:
        """Emit the in-progress window segment on clean shutdown."""
        if self._segment_start is not None and self._current_app_hash is not None:
            t = now if now is not None else time.time()
            self.writer.enqueue(
                "raw_windows",
                (self._segment_start, t, self._current_app_hash, int(bool(self._current_is_idle))),
            )
            self._segment_start = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="window-focus-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self.flush_current()

    def _run(self) -> None:
        self.poll_once()
        while not self._stop_event.wait(self.poll_interval_s):
            self.poll_once()
