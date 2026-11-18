"""Accumulator for mouse movement trajectories, clicks, and scrolls."""

import threading

from app.core import MOUSE_MOVE_THROTTLE_SECONDS
from app.features.mouse_kinematics.math import compute_mouse_kinematics
from app.features.mouse_kinematics.models import RawMouseKinematicsMetrics


class MouseKinematicsAccumulator:
    """Thread-safe accumulator for mouse points, clicks, and scrolls."""

    def __init__(self, *, mouse_move_throttle_seconds: float = MOUSE_MOVE_THROTTLE_SECONDS) -> None:
        self._throttle = mouse_move_throttle_seconds
        self._lock = threading.Lock()

        self._points: list[tuple[float, float, float]] = []
        self._clicks: int = 0
        self._scrolls: int = 0
        self._click_delta: int = 0
        self._scroll_delta: int = 0

        self._last_sample_time: float | None = None
        self._last_move_time: float | None = None

    def record_mouse_move(
        self,
        *,
        x: float | None = None,
        y: float | None = None,
        event_time: float | None = None,
    ) -> None:
        """Record a throttled 50Hz mouse point."""
        import time

        now = event_time if event_time is not None else time.monotonic()
        with self._lock:
            if (
                x is not None
                and y is not None
                and len(self._points) < 250
                and (self._last_sample_time is None or (now - self._last_sample_time) >= 0.02)
            ):
                self._points.append((x, y, now))
                self._last_sample_time = now

            if self._last_move_time is not None and (now - self._last_move_time) < self._throttle:
                return
            self._last_move_time = now

    def record_mouse_click(self) -> None:
        """Record an anonymous mouse click."""
        with self._lock:
            self._clicks += 1
            self._click_delta += 1

    def record_mouse_scroll(self) -> None:
        """Record an anonymous mouse scroll."""
        with self._lock:
            self._scrolls += 1
            self._scroll_delta += 1

    def has_good_sample(self, min_points: int = 25) -> bool:
        """Return True if sufficient trajectory points or clicks/scrolls have accumulated."""
        with self._lock:
            return len(self._points) >= min_points or self._clicks >= 5 or self._scrolls >= 5

    def consume(self) -> tuple[RawMouseKinematicsMetrics, int, int]:
        """Consume and reset accumulated mouse kinematics metrics."""
        with self._lock:
            pts = list(self._points)
            clicks = self._clicks
            scrolls = self._scrolls
            c_delta = self._click_delta
            s_delta = self._scroll_delta

            self._points.clear()
            self._clicks = 0
            self._scrolls = 0
            self._click_delta = 0
            self._scroll_delta = 0

        sampen, submov, auc, xflips = compute_mouse_kinematics(pts)
        metrics = RawMouseKinematicsMetrics(
            sample_entropy=sampen,
            submovements=submov,
            curvature_auc=auc,
            x_flips=xflips,
            mouse_clicks=clicks,
            scroll_events=scrolls,
        )
        return metrics, c_delta, s_delta
