"""Active window probes re-exported from app.core."""

from app.core import (
    NativeWindowResolver,
    SyntheticWindowResolver,
    WindowResolverProtocol,
    create_window_resolver,
    sanitize_process_name,
)

__all__ = [
    "NativeWindowResolver",
    "SyntheticWindowResolver",
    "WindowResolverProtocol",
    "create_window_resolver",
    "sanitize_process_name",
]
