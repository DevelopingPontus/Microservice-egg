"""Hardware and window telemetry collectors implementing strict Protocol interfaces."""

from app.collectors.coordinator import CollectorCoordinator
from app.collectors.input_listener import (
    PynputInputListener,
    SyntheticInputListener,
    create_input_listener,
    is_correction_key,
)
from app.collectors.protocols import (
    InputListenerProtocol,
    InputTickSinkProtocol,
    SyntheticBurstEmitterProtocol,
    WindowResolverProtocol,
)
from app.collectors.window_resolver import (
    NativeWindowResolver,
    SyntheticWindowResolver,
    create_window_resolver,
    sanitize_process_name,
)

__all__ = [
    "CollectorCoordinator",
    "InputListenerProtocol",
    "InputTickSinkProtocol",
    "NativeWindowResolver",
    "PynputInputListener",
    "SyntheticBurstEmitterProtocol",
    "SyntheticInputListener",
    "SyntheticWindowResolver",
    "WindowResolverProtocol",
    "create_input_listener",
    "create_window_resolver",
    "is_correction_key",
    "sanitize_process_name",
]
