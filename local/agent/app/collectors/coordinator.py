"""Folder orchestrator for hardware input and active window collectors."""

from app.collectors.input_listener import create_input_listener
from app.collectors.protocols import (
    InputListenerProtocol,
    InputTickSinkProtocol,
    SyntheticBurstEmitterProtocol,
    WindowResolverProtocol,
)
from app.collectors.window_resolver import create_window_resolver


class CollectorCoordinator:
    """Folder orchestrator coordinating input listeners and active window resolution."""

    def __init__(
        self,
        *,
        input_listener: InputListenerProtocol,
        window_resolver: WindowResolverProtocol,
    ) -> None:
        self._input_listener = input_listener
        self._window_resolver = window_resolver

    @classmethod
    def create(
        cls,
        sink: InputTickSinkProtocol,
        *,
        simulate: bool = False,
        input_listener: InputListenerProtocol | None = None,
        window_resolver: WindowResolverProtocol | None = None,
    ) -> "CollectorCoordinator":
        """Build a CollectorCoordinator with native or synthetic collectors."""
        resolved_input = (
            input_listener
            if input_listener is not None
            else create_input_listener(sink, simulate=simulate)
        )
        resolved_window = (
            window_resolver
            if window_resolver is not None
            else create_window_resolver(simulate=simulate)
        )
        return cls(
            input_listener=resolved_input,
            window_resolver=resolved_window,
        )

    @property
    def input_listener(self) -> InputListenerProtocol:
        """Underlying keyboard/mouse input listener."""
        return self._input_listener

    @property
    def window_resolver(self) -> WindowResolverProtocol:
        """Underlying foreground window process resolver."""
        return self._window_resolver

    def start(self) -> None:
        """Start hardware or synthetic input collection."""
        self._input_listener.start()

    def stop(self) -> None:
        """Stop hardware or synthetic input collection."""
        self._input_listener.stop()

    def get_active_process_name(self) -> str:
        """Sample the sanitized active foreground process name."""
        return self._window_resolver.get_active_process_name()

    def emit_synthetic_burst_if_active(self) -> bool:
        """Emit a deterministic synthetic input burst if running in synthetic mode."""
        if (
            isinstance(self._input_listener, SyntheticBurstEmitterProtocol)
            and self._input_listener.is_running
        ):
            self._input_listener.emit_synthetic_burst()
            return True
        return False
