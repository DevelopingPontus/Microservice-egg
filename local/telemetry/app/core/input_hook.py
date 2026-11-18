"""Zero-text keyboard and mouse collectors with headless synthetic simulation support."""

import contextlib
import ctypes
import sys
import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

_CORRECTION_KEY_NAMES: frozenset[str] = frozenset({"backspace", "delete"})
_CORRECTION_KEY_STRINGS: frozenset[str] = frozenset({"Key.backspace", "Key.delete"})
_NAVIGATION_KEY_NAMES: frozenset[str] = frozenset(
    {"up", "down", "left", "right", "home", "end", "page_up", "page_down", "tab", "esc", "enter"}
)
_MODIFIER_KEY_NAMES: frozenset[str] = frozenset(
    {
        "shift",
        "shift_l",
        "shift_r",
        "ctrl",
        "ctrl_l",
        "ctrl_r",
        "alt",
        "alt_l",
        "alt_r",
        "cmd",
        "cmd_l",
        "cmd_r",
        "caps_lock",
    }
)


@runtime_checkable
class InputTickSinkProtocol(Protocol):
    """Structural contract for any accumulator receiving anonymous hardware input ticks."""

    def record_key(
        self,
        *,
        is_correction: bool,
        key_category: str = "alphanumeric",
        key_slot: int | None = None,
        delta_ms: float | None = None,
        event_time: float | None = None,
    ) -> None: ...

    def record_key_release(
        self,
        *,
        key_slot: int | None = None,
        hold_time_ms: float | None = None,
        event_time: float | None = None,
    ) -> None: ...

    def record_mouse_click(self, *, event_time: float | None = None) -> None: ...

    def record_mouse_scroll(self, *, event_time: float | None = None) -> None: ...

    def record_mouse_move(
        self,
        *,
        x: float | None = None,
        y: float | None = None,
        event_time: float | None = None,
    ) -> None: ...


@runtime_checkable
class InputListenerProtocol(Protocol):
    """Contract for OS-native and synthetic keyboard/mouse listeners."""

    def start(self) -> None: ...

    def stop(self) -> None: ...


@runtime_checkable
class SyntheticBurstEmitterProtocol(InputListenerProtocol, Protocol):
    """Extended contract for deterministic synthetic listeners in --simulate mode."""

    @property
    def is_running(self) -> bool: ...

    def emit_synthetic_burst(self) -> None: ...


def is_macos_input_monitoring_trusted() -> bool:
    """Return True if macOS process has Input Monitoring or Accessibility permission."""
    if sys.platform != "darwin":
        return True
    try:
        cg = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
        if hasattr(cg, "CGPreflightListenEventAccess") and bool(cg.CGPreflightListenEventAccess()):
            return True
        app_services = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        return bool(app_services.AXIsProcessTrusted())
    except Exception:
        return True


is_macos_accessibility_trusted = is_macos_input_monitoring_trusted


class _StoppableHandle(Protocol):
    """Minimal protocol for background listener handles managed by PynputInputListener."""

    def start(self) -> None: ...

    def stop(self) -> None: ...


def is_correction_key(key: object) -> bool:
    """Return True strictly for Backspace or Delete keys without reading character content."""
    key_name = getattr(key, "name", None)
    if isinstance(key_name, str):
        return key_name.lower() in _CORRECTION_KEY_NAMES
    return str(key) in _CORRECTION_KEY_STRINGS


def classify_key_category(key: object) -> str:
    """Classify a key into a zero-PII broad category without storing character content."""
    if is_correction_key(key):
        return "correction"
    key_name = getattr(key, "name", None)
    if isinstance(key_name, str):
        normalized = key_name.lower()
        if normalized in _NAVIGATION_KEY_NAMES:
            return "navigation"
        if normalized in _MODIFIER_KEY_NAMES:
            return "modifier"
    return "alphanumeric"


def key_slot_id(key: object) -> int:
    """Return an ephemeral per-process hash to pair KeyDown/KeyUp without storing PII."""
    vk = getattr(key, "vk", None)
    if isinstance(vk, int):
        return vk
    try:
        return hash(key)
    except TypeError:
        return id(key)


class PynputInputListener:
    """OS-level keyboard/mouse listener forwarding anonymous ticks to an InputTickSinkProtocol."""

    def __init__(
        self,
        buffer: InputTickSinkProtocol,
        *,
        listener_starter: Callable[
            ["PynputInputListener"], tuple[_StoppableHandle, _StoppableHandle]
        ]
        | None = None,
    ) -> None:
        self._buffer = buffer
        self._listener_starter = listener_starter
        self._kb_handle: _StoppableHandle | None = None
        self._mouse_handle: _StoppableHandle | None = None
        self._running: bool = False

    @property
    def is_running(self) -> bool:
        """Whether the listener is currently active."""
        return self._running

    def on_key_press(self, key: object) -> None:
        """Handle a keydown event using only broad key category and ephemeral slot hash."""
        self._buffer.record_key(
            is_correction=is_correction_key(key),
            key_category=classify_key_category(key),
            key_slot=key_slot_id(key),
        )

    def on_key_release(self, key: object) -> None:
        """Handle a keyup event to compute dwell/hold time without storing character content."""
        self._buffer.record_key_release(key_slot=key_slot_id(key))

    def on_mouse_click(self, _x: float, _y: float, _button: object, pressed: bool) -> None:
        """Record mouse button press ticks while ignoring coordinates and release events."""
        if pressed:
            self._buffer.record_mouse_click()

    def on_mouse_scroll(self, _x: float, _y: float, _dx: float, _dy: float) -> None:
        """Record scroll ticks (reading progression) while ignoring coordinates."""
        self._buffer.record_mouse_scroll()

    def on_mouse_move(self, x: float, y: float) -> None:
        """Record ephemeral mouse trajectory coordinates for kinematic entropy/submovements."""
        self._buffer.record_mouse_move(x=float(x), y=float(y))

    def _default_start_handles(self) -> tuple[_StoppableHandle, _StoppableHandle]:
        """Lazy-import pynput and create keyboard/mouse listener handles."""
        from pynput import keyboard, mouse

        kb: _StoppableHandle = keyboard.Listener(
            on_press=self.on_key_press,
            on_release=self.on_key_release,
        )
        ms: _StoppableHandle = mouse.Listener(
            on_click=self.on_mouse_click,
            on_scroll=self.on_mouse_scroll,
            on_move=self.on_mouse_move,
        )
        return kb, ms

    def start(self) -> None:
        """Start OS keyboard and mouse listeners if not already running."""
        if self._running:
            return

        starter = (
            self._listener_starter
            if self._listener_starter is not None
            else lambda _self: self._default_start_handles()
        )
        kb, ms = starter(self)
        try:
            kb.start()
            ms.start()
            self._kb_handle = kb
            self._mouse_handle = ms
            self._running = True
        except Exception as exc:
            with contextlib.suppress(Exception):
                kb.stop()
            with contextlib.suppress(Exception):
                ms.stop()
            self._kb_handle = None
            self._mouse_handle = None
            self._running = False
            if sys.platform == "darwin":
                sys.stderr.write(
                    "[WARN] Failed to attach macOS input listener (Check System Settings -> "
                    "Privacy & Security -> Input Monitoring / Accessibility). "
                    f"Detail: {exc}\n"
                )
            elif sys.platform.startswith("linux"):
                sys.stderr.write(f"[WARN] Failed to attach Linux input listener: {exc}\n")
            else:
                sys.stderr.write(f"[WARN] Failed to attach input listener: {exc}\n")

    def stop(self) -> None:
        """Stop OS keyboard and mouse listeners and release handles."""
        if not self._running:
            return
        if self._kb_handle is not None:
            self._kb_handle.stop()
            self._kb_handle = None
        if self._mouse_handle is not None:
            self._mouse_handle.stop()
            self._mouse_handle = None
        self._running = False


class SyntheticInputListener:
    """Deterministic headless input generator for --simulate mode and CI verification."""

    def __init__(self, buffer: InputTickSinkProtocol) -> None:
        self._buffer = buffer
        self._running: bool = False
        self._sim_clock: float = time.monotonic()

    @property
    def is_running(self) -> bool:
        """Whether synthetic input collection is marked active."""
        return self._running

    def start(self) -> None:
        """Mark the synthetic listener as active."""
        self._running = True

    def stop(self) -> None:
        """Mark the synthetic listener as stopped."""
        self._running = False

    def emit_synthetic_burst(
        self,
        *,
        keystrokes: int = 12,
        corrections: int = 1,
        iki_ms: float = 160.0,
        clicks: int = 1,
        scrolls: int = 3,
    ) -> None:
        """Emit a deterministic sequence of typing, clicking, and scrolling into the sink."""
        if not self._running:
            return
        step_sec = iki_ms / 1000.0
        for idx in range(keystrokes):
            self._sim_clock += step_sec
            is_corr = idx < corrections
            self._buffer.record_key(
                is_correction=is_corr,
                key_category="correction" if is_corr else "alphanumeric",
                key_slot=idx % 4,
                delta_ms=iki_ms if idx > 0 else None,
                event_time=self._sim_clock,
            )
            self._buffer.record_key_release(
                key_slot=idx % 4,
                hold_time_ms=85.0 + float((idx % 3) * 10),
                event_time=self._sim_clock + 0.085,
            )
        for _ in range(clicks):
            self._sim_clock += 0.20
            self._buffer.record_mouse_click(event_time=self._sim_clock)
        for _ in range(scrolls):
            self._sim_clock += 0.30
            self._buffer.record_mouse_scroll(event_time=self._sim_clock)
        for step_idx in range(8):
            self._sim_clock += 0.04
            self._buffer.record_mouse_move(
                x=100.0 + float(step_idx * 18),
                y=200.0 + float((step_idx % 3) * 12),
                event_time=self._sim_clock,
            )


def create_input_listener(
    buffer: InputTickSinkProtocol,
    *,
    simulate: bool = False,
) -> InputListenerProtocol:
    """Factory returning a SyntheticInputListener in simulate mode or PynputInputListener."""
    if simulate:
        return SyntheticInputListener(buffer)
    return PynputInputListener(buffer)
