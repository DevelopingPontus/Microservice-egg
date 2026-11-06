"""Unified LCA Crossroads structural protocols ("What do you want?") for `app/common/`.

Defines all cross-package structural interfaces shared between `intake/` and `output/`
without requiring any sibling package imports.
"""

from typing import Any, Protocol, runtime_checkable

from app.common.models import (
    SchedulerDiagnostics,
)

__all__ = [
    "DimensionEvalProtocol",
    "InputLifecycleProtocol",
    "InputListenerProtocol",
    "InputTickSinkProtocol",
    "PooledMetricsProtocol",
    "SyntheticBurstEmitterProtocol",
    "SyntheticBurstSourceProtocol",
    "TelemetryGatewayBackendProtocol",
    "TelemetrySampleProtocol",
    "WindowResolverProtocol",
    "WindowSourceProtocol",
]


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


InputLifecycleProtocol = InputListenerProtocol


@runtime_checkable
class SyntheticBurstEmitterProtocol(InputListenerProtocol, Protocol):
    """Extended contract for deterministic synthetic listeners in --simulate mode."""

    @property
    def is_running(self) -> bool:
        """Whether synthetic input collection is marked active."""

    def emit_synthetic_burst(self) -> None:
        """Emit one deterministic sequence of synthetic input events into the sink."""


SyntheticBurstSourceProtocol = SyntheticBurstEmitterProtocol


@runtime_checkable
class WindowResolverProtocol(Protocol):
    """Contract for OS-native and synthetic foreground process resolvers."""

    def get_active_process_name(self) -> str:
        """Return the sanitized executable or bundle name of the active window."""

    def get_active_window_id(self) -> int | None:
        """Return the OS-native integer window ID, or None if unsupported or unknown."""


WindowSourceProtocol = WindowResolverProtocol


@runtime_checkable
class DimensionEvalProtocol(Protocol):
    """Structural contract for a single evaluated scientific dimension result."""

    @property
    def dimension_name(self) -> str: ...

    @property
    def strain_score(self) -> float: ...

    @property
    def state_label(self) -> str: ...

    @property
    def metrics(self) -> dict[str, Any]: ...

    @property
    def blameless_summary(self) -> str: ...


@runtime_checkable
class PooledMetricsProtocol(Protocol):
    """Structural contract for pooled telemetry metrics across a sample window."""

    @property
    def sample_count(self) -> int: ...

    @property
    def total_duration_seconds(self) -> float: ...

    @property
    def total_active_seconds(self) -> float: ...

    @property
    def duty_cycle(self) -> float: ...

    @property
    def total_micro_pauses(self) -> int: ...

    @property
    def total_mouse_clicks(self) -> int: ...

    @property
    def total_scroll_events(self) -> int: ...

    @property
    def total_context_switches(self) -> int: ...

    @property
    def switches_per_minute(self) -> float: ...

    @property
    def merged_dwell_seconds(self) -> dict[str, float]: ...

    @property
    def primary_process(self) -> str: ...

    @property
    def primary_process_ratio(self) -> float: ...

    @property
    def shannon_entropy(self) -> float: ...

    @property
    def total_keystrokes(self) -> int: ...

    @property
    def correction_keystrokes(self) -> int: ...

    @property
    def correction_ratio(self) -> float: ...

    @property
    def iki_count(self) -> int: ...

    @property
    def is_psychomotor_valid(self) -> bool: ...

    @property
    def iki_mean_ms(self) -> float: ...

    @property
    def iki_variance_ms2(self) -> float: ...

    @property
    def iki_std_dev_ms(self) -> float: ...

    @property
    def iki_cv(self) -> float: ...


@runtime_checkable
class TelemetrySampleProtocol(Protocol):
    """Structural contract for an in-memory telemetry sample slice."""

    @property
    def timestamp_start(self) -> float: ...

    @property
    def timestamp_end(self) -> float: ...

    @property
    def primary_process(self) -> str: ...

    @property
    def active_seconds(self) -> float: ...

    @property
    def micro_pause_count(self) -> int: ...

    @property
    def context_switch_count(self) -> int: ...

    @property
    def dwell_distribution(self) -> dict[str, float]: ...

    @property
    def total_keystrokes(self) -> int: ...

    @property
    def correction_keystrokes(self) -> int: ...

    @property
    def iki_count(self) -> int: ...

    @property
    def iki_sum_ms(self) -> float: ...

    @property
    def iki_sum_sq_ms(self) -> float: ...

    @property
    def mouse_click_count(self) -> int: ...

    @property
    def scroll_count(self) -> int: ...

    @property
    def duration_seconds(self) -> float: ...


@runtime_checkable
class TelemetryGatewayBackendProtocol(Protocol):
    """Structural contract for querying daemon diagnostics and Prometheus metrics."""

    def get_diagnostics(self) -> SchedulerDiagnostics:
        """Return operational scheduler diagnostics."""

    def render_prometheus_metrics(self) -> str:
        """Render Prometheus text exposition metrics."""
