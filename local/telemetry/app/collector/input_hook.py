"""Zero-text keyboard and mouse collectors re-exported from app.core."""

from app.core import (
    InputListenerProtocol,
    InputTickSinkProtocol,
    PynputInputListener,
    SyntheticBurstEmitterProtocol,
    SyntheticInputListener,
    classify_key_category,
    create_input_listener,
    is_correction_key,
    is_macos_accessibility_trusted,
    is_macos_input_monitoring_trusted,
    key_slot_id,
)

__all__ = [
    "InputListenerProtocol",
    "InputTickSinkProtocol",
    "PynputInputListener",
    "SyntheticBurstEmitterProtocol",
    "SyntheticInputListener",
    "classify_key_category",
    "create_input_listener",
    "is_correction_key",
    "is_macos_accessibility_trusted",
    "is_macos_input_monitoring_trusted",
    "key_slot_id",
]
