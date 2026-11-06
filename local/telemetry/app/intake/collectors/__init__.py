"""Zero-content hardware and foreground window collectors (`app/intake/collectors/`)."""

from app.common.protocols import (
    InputListenerProtocol,
    InputTickSinkProtocol,
    SyntheticBurstEmitterProtocol,
    WindowResolverProtocol,
)
from app.intake.collectors.input_listener import (
    PynputInputListener,
    SyntheticInputListener,
    create_input_listener,
    is_correction_key,
    is_macos_accessibility_trusted,
)
from app.intake.collectors.window_resolver import (
    NativeWindowResolver,
    SyntheticWindowResolver,
    create_window_resolver,
    sanitize_process_name,
)

__all__ = [
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
    "is_macos_accessibility_trusted",
    "sanitize_process_name",
]
