"""Self-contained protocols, constants, and epoch snapshot model for app/engine/."""

import json
from dataclasses import dataclass, replace
from typing import Any, Protocol, runtime_checkable

DEFAULT_EPOCH_DURATION_SECONDS: float = 30.0
DEFAULT_IDLE_EVENT_THRESHOLD_SECONDS: float = 1.5
DEFAULT_MICRO_PAUSE_MIN_SECONDS: float = 1.0
DEFAULT_MICRO_PAUSE_MAX_SECONDS: float = 5.0
DEFAULT_IKI_MAX_OUTLIER_MS: float = 5000.0
DEFAULT_MOUSE_MOVE_THROTTLE_SECONDS: float = 0.25
DEFAULT_WINDOW_POLL_INTERVAL_SECONDS: float = 0.25


@dataclass(frozen=True, slots=True)
class EpochSnapshot:
    """Immutable 30-second telemetry snapshot harvested by EpochBuffer."""

    timestamp_start: float
    timestamp_end: float
    primary_process: str
    active_seconds: float
    micro_pause_count: int
    context_switch_count: int
    dwell_distribution_json: str
    total_keystrokes: int
    correction_keystrokes: int
    iki_count: int
    iki_sum_ms: float
    iki_sum_sq_ms: float
    mouse_click_count: int = 0
    scroll_count: int = 0
    id: int | None = None

    @property
    def duration_seconds(self) -> float:
        """Total elapsed wall-clock seconds covered by this epoch."""
        return max(0.0, self.timestamp_end - self.timestamp_start)

    def parsed_dwell_distribution(self) -> dict[str, float]:
        """Deserialize dwell_distribution_json into a mapping of process -> seconds."""
        raw = json.loads(self.dwell_distribution_json)
        if not isinstance(raw, dict):
            raise ValueError("dwell_distribution_json must encode a JSON object")
        return {str(proc): float(seconds) for proc, seconds in raw.items()}

    def with_id(self, row_id: int) -> "EpochSnapshot":
        """Return a copy of this snapshot stamped with its persisted database id."""
        return replace(self, id=row_id)


@runtime_checkable
class EpochPersistenceProtocol(Protocol):
    """Structural contract for persisting a harvested 30s epoch snapshot."""

    async def insert_epoch(self, epoch: Any) -> int:
        """Persist a 30-second epoch snapshot and return its row id."""


@runtime_checkable
class WindowSourceProtocol(Protocol):
    """Structural contract for sampling the sanitized active foreground process name."""

    def get_active_process_name(self) -> str:
        """Return the sanitized executable or bundle name of the active window."""


@runtime_checkable
class InputLifecycleProtocol(Protocol):
    """Structural contract for starting and stopping an input listener."""

    def start(self) -> None:
        """Start input collection."""

    def stop(self) -> None:
        """Stop input collection."""


@runtime_checkable
class SyntheticBurstSourceProtocol(InputLifecycleProtocol, Protocol):
    """Structural contract for synthetic input listeners supporting deterministic bursts."""

    @property
    def is_running(self) -> bool:
        """Whether synthetic input collection is marked active."""

    def emit_synthetic_burst(self) -> None:
        """Emit one deterministic sequence of synthetic input events."""
