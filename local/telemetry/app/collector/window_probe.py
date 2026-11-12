"""Cross-platform active window process resolver with strict title/URL sanitization."""

import contextlib
import ctypes
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from typing import Protocol, runtime_checkable

_TITLE_SEPARATORS = re.compile(r"(?:\s+[-—|]\s+|:\s+).*$")


@runtime_checkable
class WindowResolverProtocol(Protocol):
    """Contract for OS-native and synthetic foreground process resolvers."""

    def get_active_process_name(self) -> str:
        """Return the sanitized executable or bundle name of the active window."""

    def get_active_window_id(self) -> int | None:
        """Return the OS-native integer window ID, or None if unsupported or unknown."""


def sanitize_process_name(raw_name: str) -> str:
    """Strip file paths, window titles, URLs, and query strings from a raw process string."""
    cleaned = raw_name.strip()
    if not cleaned:
        return "unknown"

    cleaned = _TITLE_SEPARATORS.sub("", cleaned).strip()

    if cleaned.lower().startswith(("http://", "https://", "://")):
        return "unknown"
    if "://" in cleaned:
        cleaned = cleaned.split("://", maxsplit=1)[0].strip()
    cleaned = cleaned.split("?", maxsplit=1)[0].strip()

    normalized = cleaned.replace("\\", "/")
    basename = normalized.rsplit("/", maxsplit=1)[-1].strip()

    if basename and not basename.endswith(".app"):
        basename = basename.split()[0]

    return basename if basename else "unknown"


def _probe_macos_active_window() -> tuple[str, int | None]:
    """Resolve active application and window ID on macOS via Quartz or AppKit."""
    with contextlib.suppress(Exception):
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListExcludeDesktopElements,
            kCGWindowListOptionOnScreenOnly,
        )

        windows = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
            kCGNullWindowID,
        )
        if windows:
            for w in windows:
                if w.get("kCGWindowLayer", -1) == 0:
                    owner = str(w.get("kCGWindowOwnerName", "unknown"))
                    wid = int(w.get("kCGWindowNumber", 0))
                    app_name = owner if owner.endswith(".app") else f"{owner}.app"
                    return app_name, wid

    with contextlib.suppress(Exception):
        from AppKit import NSWorkspace

        active_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if active_app is not None:
            name = active_app.localizedName()
            if name:
                app_name = name if name.endswith(".app") else f"{name}.app"
                return app_name, None

    return "unknown", None


def _probe_macos_active_process() -> str:
    """Resolve active application name on macOS via AppKit NSWorkspace."""
    proc, _ = _probe_macos_active_window()
    return proc


def _probe_windows_active_window() -> tuple[str, int | None]:
    """Resolve active application and window ID on Windows using Win32 API via ctypes."""
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return "unknown", None

    user32 = windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "unknown", None

    wid = int(hwnd)
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return "unknown", wid

    kernel32 = windll.kernel32
    h_proc = kernel32.OpenProcess(0x1000, False, pid.value)
    if not h_proc:
        return "unknown", wid

    try:
        buf = ctypes.create_unicode_buffer(512)
        size = ctypes.c_ulong(512)
        if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
            return str(buf.value), wid
    finally:
        kernel32.CloseHandle(h_proc)

    return "unknown", wid


def _probe_windows_active_process() -> str:
    """Resolve active application on Windows using Win32 API via ctypes."""
    proc, _ = _probe_windows_active_window()
    return proc


def _probe_linux_active_window() -> tuple[str, int | None]:
    """Resolve active application and window ID on Linux via xdotool or X11 /proc lookup."""
    if shutil.which("xdotool") is not None:
        try:
            win_out = subprocess.check_output(
                ["xdotool", "getactivewindow"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=0.2,
            ).strip()
            wid = int(win_out) if win_out.isdigit() else None
            pid_out = subprocess.check_output(
                ["xdotool", "getactivewindow", "getwindowpid"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=0.2,
            ).strip()
            if pid_out.isdigit():
                with open(f"/proc/{pid_out}/comm", encoding="utf-8") as f:
                    return f.read().strip(), wid
        except Exception:
            pass

    with contextlib.suppress(Exception):
        from Xlib import X, display

        d = display.Display()
        root = d.screen().root
        atom_net_active = d.intern_atom("_NET_ACTIVE_WINDOW")
        prop = root.get_full_property(atom_net_active, X.AnyPropertyType)
        if prop and prop.value:
            win_id = int(prop.value[0])
            win = d.create_resource_object("window", win_id)
            wm_class = win.get_wm_class()
            if wm_class and len(wm_class) >= 2:
                return str(wm_class[1]), win_id
            if wm_class:
                return str(wm_class[0]), win_id

    return "unknown", None


def _probe_linux_active_process() -> str:
    """Resolve active application on Linux via xdotool or X11 /proc lookup."""
    proc, _ = _probe_linux_active_window()
    return proc


def _default_os_window_probe() -> tuple[str, int | None]:
    """Best-effort cross-platform OS probe for active foreground application and window ID."""
    try:
        if sys.platform == "darwin":
            return _probe_macos_active_window()
        if sys.platform == "win32":
            return _probe_windows_active_window()
        if sys.platform.startswith("linux"):
            return _probe_linux_active_window()
    except Exception:
        pass
    return "unknown", None


def _default_os_process_probe() -> str:
    """Best-effort cross-platform OS probe for active foreground application name."""
    proc, _ = _default_os_window_probe()
    return proc


class NativeWindowResolver:
    """OS-native foreground process resolver that strictly sanitizes output."""

    def __init__(
        self,
        raw_probe: Callable[[], str | tuple[str, int | None]] | None = None,
    ) -> None:
        self._raw_probe = raw_probe if raw_probe is not None else _default_os_window_probe
        self._cached_proc: str = "unknown"
        self._cached_window_id: int | None = None

    def _poll(self) -> None:
        try:
            raw = self._raw_probe()
            if isinstance(raw, tuple):
                proc_str, wid = raw
                self._cached_proc = sanitize_process_name(proc_str)
                self._cached_window_id = wid
            else:
                self._cached_proc = sanitize_process_name(raw)
                self._cached_window_id = None
        except Exception:
            self._cached_proc = "unknown"
            self._cached_window_id = None

    def get_active_process_name(self) -> str:
        """Query the OS probe and return only a sanitized executable/bundle name."""
        self._poll()
        return self._cached_proc

    def get_active_window_id(self) -> int | None:
        """Return the OS-native integer window ID, or None if unsupported or unknown."""
        return self._cached_window_id


class SyntheticWindowResolver:
    """Deterministic foreground process resolver for headless CI and --simulate mode."""

    DEFAULT_SCHEDULE: tuple[tuple[str, int], ...] = (
        ("Code.exe", 80),
        ("Slack.app", 16),
        ("Code.exe", 60),
        ("Firefox.app", 100),
        ("Preview.app", 12),
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

    def get_active_window_id(self) -> int | None:
        """Synthetic resolver does not produce OS window IDs."""
        return None


def create_window_resolver(*, simulate: bool = False) -> WindowResolverProtocol:
    """Create a WindowResolverProtocol instance based on the simulate flag."""
    if simulate:
        return SyntheticWindowResolver()
    return NativeWindowResolver()
