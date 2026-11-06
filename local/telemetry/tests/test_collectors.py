"""Unit tests for protocol-driven OS and synthetic telemetry collectors."""

from pathlib import Path
from unittest.mock import MagicMock, mock_open

import pytest

from app.intake.collectors import (
    InputListenerProtocol,
    NativeWindowResolver,
    PynputInputListener,
    SyntheticInputListener,
    SyntheticWindowResolver,
    WindowResolverProtocol,
    create_input_listener,
    create_window_resolver,
    is_correction_key,
    sanitize_process_name,
)
from app.intake.engine import SlidingWindowBuffer


class _FakeKey:
    """Stub key object with a .name attribute."""

    def __init__(self, name: str) -> None:
        self.name = name


class _FakeHandle:
    """Stub start/stop handle for verifying PynputInputListener lifecycle."""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


def test_sanitize_process_name_strips_paths_titles_and_urls() -> None:
    """Verify window titles, file paths, and URLs are stripped to executable names."""
    assert sanitize_process_name("") == "unknown"
    assert sanitize_process_name("   ") == "unknown"
    assert sanitize_process_name("/usr/bin/firefox - Private Browsing") == "firefox"
    assert (
        sanitize_process_name(r"C:\Program Files\Microsoft VS Code\Code.exe — secret_doc.md")
        == "Code.exe"
    )
    assert sanitize_process_name("Visual Studio Code.app: main.py") == "Visual Studio Code.app"
    assert sanitize_process_name("chrome://settings?search=password") == "chrome"
    assert sanitize_process_name("https://") == "unknown"


def test_window_resolvers_satisfy_protocol_and_handle_errors() -> None:
    """Verify NativeWindowResolver and SyntheticWindowResolver implement WindowResolverProtocol."""
    sim_resolver = create_window_resolver(simulate=True)
    assert isinstance(sim_resolver, WindowResolverProtocol)
    assert isinstance(sim_resolver, SyntheticWindowResolver)

    custom_sim = SyntheticWindowResolver(
        schedule=[("/Applications/Slack.app - #general", 2), ("Code.exe", 1)]
    )
    assert custom_sim.get_active_process_name() == "Slack.app"
    assert custom_sim.get_active_process_name() == "Slack.app"
    assert custom_sim.get_active_process_name() == "Code.exe"
    assert custom_sim.get_active_process_name() == "Slack.app"

    with pytest.raises(ValueError, match="schedule must not be empty"):
        SyntheticWindowResolver(schedule=[])

    # NativeWindowResolver with injected probe and failing probe fallback
    native_ok = NativeWindowResolver(raw_probe=lambda: ("/bin/zsh - project", 12345))
    assert isinstance(native_ok, WindowResolverProtocol)
    assert native_ok.get_active_process_name() == "zsh"
    assert native_ok.get_active_window_id() == 12345

    def _failing_probe() -> str:
        raise RuntimeError("No display server")

    native_fail = NativeWindowResolver(raw_probe=_failing_probe)
    assert native_fail.get_active_process_name() == "unknown"
    assert native_fail.get_active_window_id() is None

    default_native = create_window_resolver(simulate=False)
    assert isinstance(default_native, NativeWindowResolver)
    assert isinstance(default_native.get_active_process_name(), str)
    assert sim_resolver.get_active_window_id() is None


def test_is_correction_key_zero_content_inspection() -> None:
    """Verify only backspace and delete are flagged as corrections."""
    assert is_correction_key(_FakeKey("backspace")) is True
    assert is_correction_key(_FakeKey("DELETE")) is True
    assert is_correction_key(_FakeKey("enter")) is False
    assert is_correction_key("Key.backspace") is True
    assert is_correction_key("Key.delete") is True
    assert is_correction_key("a") is False


def test_synthetic_input_listener_and_factory() -> None:
    """Verify SyntheticInputListener lifecycle and deterministic burst emission."""
    buf = SlidingWindowBuffer()
    listener = create_input_listener(buf, simulate=True)
    assert isinstance(listener, InputListenerProtocol)
    assert isinstance(listener, SyntheticInputListener)
    assert listener.is_running is False

    # Emitting while stopped is a no-op
    listener.emit_synthetic_burst()
    assert buf.commit_slice().total_keystrokes == 0

    listener.start()
    assert listener.is_running is True
    listener.emit_synthetic_burst(keystrokes=12, corrections=2, iki_ms=150.0, clicks=2, scrolls=4)
    listener.stop()
    assert listener.is_running is False

    dto = buf.commit_slice()
    assert dto.total_keystrokes == 12
    assert dto.correction_keystrokes == 2
    assert dto.iki_count == 11
    assert dto.mouse_click_count == 2
    assert dto.scroll_count == 4


def test_pynput_input_listener_callbacks_and_lifecycle() -> None:
    """Verify PynputInputListener callbacks, idempotent start/stop, and factory creation."""
    buf = SlidingWindowBuffer()
    kb_handle = _FakeHandle()
    ms_handle = _FakeHandle()

    listener = PynputInputListener(
        buf,
        listener_starter=lambda _self: (kb_handle, ms_handle),
    )
    assert isinstance(listener, InputListenerProtocol)
    assert listener.is_running is False

    # Stop when not running is a safe no-op
    listener.stop()

    listener.start()
    assert listener.is_running is True
    assert kb_handle.started is True
    assert ms_handle.started is True

    # Calling start() again is idempotent
    listener.start()

    # Trigger callbacks
    listener.on_key_press(_FakeKey("a"))
    listener.on_key_press(_FakeKey("backspace"))
    listener.on_mouse_click(100.0, 200.0, "left", pressed=True)
    listener.on_mouse_click(100.0, 200.0, "left", pressed=False)  # Release ignored
    listener.on_mouse_scroll(100.0, 200.0, 0.0, -1.0)
    listener.on_mouse_move(105.0, 205.0)

    listener.stop()
    assert listener.is_running is False
    assert kb_handle.stopped is True
    assert ms_handle.stopped is True

    dto = buf.commit_slice()
    assert dto.total_keystrokes == 2
    assert dto.correction_keystrokes == 1
    assert dto.mouse_click_count == 1
    assert dto.scroll_count == 1

    # Verify factory creates PynputInputListener when simulate=False
    real_listener = create_input_listener(buf, simulate=False)
    assert isinstance(real_listener, PynputInputListener)


def test_pynput_input_listener_start_failure_cleans_up() -> None:
    """Verify failed listener start stops partial handles and sets is_running to False."""
    buf = SlidingWindowBuffer()
    kb_handle = _FakeHandle()

    class _FailingHandle:
        def __init__(self) -> None:
            self.stopped = False

        def start(self) -> None:
            raise RuntimeError("OS permission denied")

        def stop(self) -> None:
            self.stopped = True

    ms_handle = _FailingHandle()

    listener = PynputInputListener(
        buf,
        listener_starter=lambda _self: (kb_handle, ms_handle),
    )
    listener.start()

    assert listener.is_running is False
    assert kb_handle.stopped is True
    assert ms_handle.stopped is True

    # Subsequent stop() is a safe no-op
    listener.stop()
    assert listener.is_running is False


def test_is_macos_accessibility_trusted_function() -> None:
    """Verify is_macos_accessibility_trusted executes and returns a boolean."""
    from app.intake.collectors import is_macos_accessibility_trusted

    result = is_macos_accessibility_trusted()
    assert isinstance(result, bool)


def test_cross_platform_window_probes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test Linux and Windows fallback and probe paths."""

    from app.intake.collectors.window_resolver import (
        _default_os_process_probe,
        _probe_linux_active_process,
        _probe_windows_active_process,
    )

    # Windows fallback when windll is None
    assert _probe_windows_active_process() == "unknown"

    # Windows mock probe success
    mock_windll = MagicMock()
    mock_user32 = MagicMock()
    mock_kernel32 = MagicMock()
    mock_user32.GetForegroundWindow.return_value = 1234

    def mock_get_pid(_hwnd: object, byref_pid: object) -> int:
        byref_pid._obj.value = 9999  # type: ignore[attr-defined]
        return 1

    mock_user32.GetWindowThreadProcessId.side_effect = mock_get_pid
    mock_kernel32.OpenProcess.return_value = 5678

    def mock_query(_h: object, _f: object, buf: object, _s: object) -> int:
        buf.value = "notepad.exe"  # type: ignore[attr-defined]
        return 1

    mock_kernel32.QueryFullProcessImageNameW.side_effect = mock_query
    mock_windll.user32 = mock_user32
    mock_windll.kernel32 = mock_kernel32

    import ctypes

    monkeypatch.setattr(ctypes, "windll", mock_windll, raising=False)
    assert _probe_windows_active_process() == "notepad.exe"

    # Linux probe with mocked xdotool and /proc
    proc_dir = tmp_path / "proc" / "4321"
    proc_dir.mkdir(parents=True)
    (proc_dir / "comm").write_text("gnome-terminal\n", encoding="utf-8")

    monkeypatch.setattr(
        "shutil.which",
        lambda cmd: "/usr/bin/xdotool" if cmd == "xdotool" else None,
    )
    monkeypatch.setattr("subprocess.check_output", lambda *args, **kwargs: "4321\n")
    monkeypatch.setattr(
        "builtins.open",
        mock_open(read_data="gnome-terminal\n"),
    )
    assert _probe_linux_active_process() == "gnome-terminal"

    # Default OS probe with mocked platforms
    monkeypatch.setattr("sys.platform", "win32")
    assert _default_os_process_probe() == "notepad.exe"

    monkeypatch.setattr("sys.platform", "linux")
    assert _default_os_process_probe() == "gnome-terminal"

    monkeypatch.setattr("sys.platform", "unknown_os")
    assert _default_os_process_probe() == "unknown"
