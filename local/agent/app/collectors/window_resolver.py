"""Cross-platform active window process resolver with strict title/URL sanitization."""

import re
from collections.abc import Callable, Sequence

from app.collectors.protocols import WindowResolverProtocol

_TITLE_SEPARATORS = re.compile(r"(?:\s+[-—|]\s+|:\s+).*$")


def sanitize_process_name(raw_name: str) -> str:
    """Strip file paths, window titles, URLs, and query strings from a raw process string."""
    cleaned = raw_name.strip()
    if not cleaned:
        return "unknown"

    # Strip any window title suffix (e.g. "Code.exe - main.py — project" -> "Code.exe")
    cleaned = _TITLE_SEPARATORS.sub("", cleaned).strip()

    # Strip URL schemes or query parameters if a raw string ever contained one
    if cleaned.lower().startswith(("http://", "https://", "://")):
        return "unknown"
    if "://" in cleaned:
        cleaned = cleaned.split("://", maxsplit=1)[0].strip()
    cleaned = cleaned.split("?", maxsplit=1)[0].strip()

    # Extract basename across both POSIX ('/') and Windows ('\\') paths
    normalized = cleaned.replace("\\", "/")
    basename = normalized.rsplit("/", maxsplit=1)[-1].strip()

    # Take first token unless it ends with .app (e.g. "Visual Studio Code.app" -> keep bundle name)
    if basename and not basename.endswith(".app"):
        basename = basename.split()[0]

    return basename if basename else "unknown"


def _default_os_process_probe() -> str:
    """Best-effort OS probe for the active foreground application name."""
    try:
        # macOS AppKit NSWorkspace probe (lazy import for headless safety)
        from AppKit import NSWorkspace

        active_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if active_app is not None:
            name = active_app.localizedName()
            if name:
                return f"{name}.app"
    except Exception:
        pass
    return "unknown"


class NativeWindowResolver:
    """OS-native foreground process resolver that strictly sanitizes output."""

    def __init__(
        self,
        raw_probe: Callable[[], str] | None = None,
    ) -> None:
        self._raw_probe = raw_probe if raw_probe is not None else _default_os_process_probe

    def get_active_process_name(self) -> str:
        """Query the OS probe and return only a sanitized executable/bundle name."""
        try:
            raw = self._raw_probe()
        except Exception:
            return "unknown"
        return sanitize_process_name(raw)


class SyntheticWindowResolver:
    """Deterministic foreground process resolver for headless CI and --simulate mode."""

    DEFAULT_SCHEDULE: tuple[tuple[str, int], ...] = (
        ("Code.exe", 80),  # 20s in IDE (80 ticks @ 0.25s)
        ("Firefox.app", 24),  # 6s in documentation browser
        ("Preview.app", 12),  # 3s in PDF reader
        ("Slack.app", 4),  # 1s brief chat check
    )

    def __init__(
        self,
        schedule: Sequence[tuple[str, int]] | None = None,
    ) -> None:
        active_schedule = schedule if schedule is not None else self.DEFAULT_SCHEDULE
        if not active_schedule:
            raise ValueError("SyntheticWindowResolver schedule must not be empty")
        self._expanded: list[str] = []
        for proc_name, tick_count in active_schedule:
            clean = sanitize_process_name(proc_name)
            self._expanded.extend([clean] * max(1, tick_count))
        self._index: int = 0

    def get_active_process_name(self) -> str:
        """Return the next sanitized process name in the deterministic cycle."""
        proc = self._expanded[self._index % len(self._expanded)]
        self._index += 1
        return proc


def create_window_resolver(*, simulate: bool = False) -> WindowResolverProtocol:
    """Factory returning a SyntheticWindowResolver in simulate mode or NativeWindowResolver."""
    if simulate:
        return SyntheticWindowResolver()
    return NativeWindowResolver()
