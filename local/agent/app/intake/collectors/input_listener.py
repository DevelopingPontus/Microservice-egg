"""Zero-text keyboard and mouse collectors with headless synthetic simulation support."""

from collections.abc import Callable
from typing import Protocol

from app.common.protocols import InputListenerProtocol, InputTickSinkProtocol

_CORRECTION_KEY_NAMES: frozenset[str] = frozenset({"backspace", "delete"})
_CORRECTION_KEY_STRINGS: frozenset[str] = frozenset({"Key.backspace", "Key.delete"})


class _StoppableHandle(Protocol):
    """Minimal protocol for background listener handles managed by PynputInputListener."""

    def start(self) -> None:
        """Start the underlying OS hook thread."""

    def stop(self) -> None:
        """Stop the underlying OS hook thread."""


def is_correction_key(key: object) -> bool:
    """Return True strictly for Backspace or Delete keys without reading character content."""
    key_name = getattr(key, "name", None)
    if isinstance(key_name, str):
        return key_name.lower() in _CORRECTION_KEY_NAMES
    return str(key) in _CORRECTION_KEY_STRINGS


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
        """Handle a keydown event by checking only the correction flag."""
        self._buffer.record_key(is_correction=is_correction_key(key))

    def on_mouse_click(self, _x: float, _y: float, _button: object, pressed: bool) -> None:
        """Record mouse button press ticks while ignoring coordinates and release events."""
        if pressed:
            self._buffer.record_mouse_click()

    def on_mouse_scroll(self, _x: float, _y: float, _dx: float, _dy: float) -> None:
        """Record scroll ticks (reading progression) while ignoring coordinates."""
        self._buffer.record_mouse_scroll()

    def on_mouse_move(self, _x: float, _y: float) -> None:
        """Record throttled mouse movement presence while ignoring coordinates."""
        self._buffer.record_mouse_move()

    def _default_start_handles(self) -> tuple[_StoppableHandle, _StoppableHandle]:
        """Lazy-import pynput and create keyboard/mouse listener handles."""
        from pynput import keyboard, mouse

        kb: _StoppableHandle = keyboard.Listener(on_press=self.on_key_press)
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
        kb.start()
        ms.start()
        self._kb_handle = kb
        self._mouse_handle = ms
        self._running = True

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
        self._sim_clock: float = 1000.0

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
        """Emit a deterministic sequence of typing, clicking, and scrolling into EpochBuffer."""
        if not self._running:
            return
        step_sec = iki_ms / 1000.0
        for idx in range(keystrokes):
            self._sim_clock += step_sec
            self._buffer.record_key(
                is_correction=(idx < corrections),
                delta_ms=iki_ms if idx > 0 else None,
                event_time=self._sim_clock,
            )
        for _ in range(clicks):
            self._sim_clock += 0.20
            self._buffer.record_mouse_click(event_time=self._sim_clock)
        for _ in range(scrolls):
            self._sim_clock += 0.30
            self._buffer.record_mouse_scroll(event_time=self._sim_clock)
        self._sim_clock += 0.30
        self._buffer.record_mouse_move(event_time=self._sim_clock)


def create_input_listener(
    buffer: InputTickSinkProtocol,
    *,
    simulate: bool = False,
) -> InputListenerProtocol:
    """Factory returning a SyntheticInputListener in simulate mode or PynputInputListener."""
    if simulate:
        return SyntheticInputListener(buffer)
    return PynputInputListener(buffer)
