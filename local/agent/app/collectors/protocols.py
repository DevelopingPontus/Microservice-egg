"""Protocol interfaces for hardware and window telemetry collectors."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class InputListenerProtocol(Protocol):
    """Contract for OS-native and synthetic keyboard/mouse listeners."""

    def start(self) -> None:
        """Start listening for input events and feeding the EpochBuffer."""

    def stop(self) -> None:
        """Stop listening for input events and release resources."""


@runtime_checkable
class WindowResolverProtocol(Protocol):
    """Contract for OS-native and synthetic foreground process resolvers."""

    def get_active_process_name(self) -> str:
        """Return the sanitized executable or bundle name of the active window."""
