"""Protocol interfaces for hardware and window telemetry collectors."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class InputTickSinkProtocol(Protocol):
    """Structural contract for any accumulator receiving anonymous hardware input ticks."""

    def record_key(
        self,
        *,
        is_correction: bool,
        delta_ms: float | None = None,
        event_time: float | None = None,
    ) -> None:
        """Record an anonymous keystroke event without character or keycode content."""

    def record_mouse_click(self, *, event_time: float | None = None) -> None:
        """Record an anonymous mouse button press event."""

    def record_mouse_scroll(self, *, event_time: float | None = None) -> None:
        """Record an anonymous scroll progression event."""

    def record_mouse_move(self, *, event_time: float | None = None) -> None:
        """Record an anonymous throttled mouse movement tick."""


@runtime_checkable
class InputListenerProtocol(Protocol):
    """Contract for OS-native and synthetic keyboard/mouse listeners."""

    def start(self) -> None:
        """Start listening for input events and feeding the InputTickSinkProtocol."""

    def stop(self) -> None:
        """Stop listening for input events and release resources."""


@runtime_checkable
class SyntheticBurstEmitterProtocol(InputListenerProtocol, Protocol):
    """Extended contract for deterministic synthetic listeners in --simulate mode."""

    @property
    def is_running(self) -> bool:
        """Whether synthetic input collection is marked active."""

    def emit_synthetic_burst(self) -> None:
        """Emit one deterministic sequence of synthetic input events into the sink."""


@runtime_checkable
class WindowResolverProtocol(Protocol):
    """Contract for OS-native and synthetic foreground process resolvers."""

    def get_active_process_name(self) -> str:
        """Return the sanitized executable or bundle name of the active window."""
