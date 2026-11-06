# `local/telemetry/app/intake/collectors/` Context & Interface Contract

> **Hardware and OS window signal collection: Zero-content keyboard/mouse hooks and executable-only window resolution.**

---

## 1. Scope & Privacy Invariants

- **Zero Content Capture**: Never inspects, logs, or buffers key characters, key codes, scancodes, mouse coordinates, window titles, or URLs.
- **Executable Sanitization (`sanitize_process_name`)**: Strips paths, window titles, and URL schemes to resolve strictly the executable or bundle identifier (`Code.exe`, `Slack.app`, `firefox`).
- **Headless CI Readiness (`--simulate`)**: `create_input_listener` and `create_window_resolver` provide deterministic synthetic implementations (`SyntheticInputListener`, `SyntheticWindowResolver`) so tests and headless environments never require a physical display server.
- **LCA Contract Imports Only**: Imports structural contracts (`InputTickSinkProtocol`, `InputListenerProtocol`, `WindowResolverProtocol`) strictly from `app.common.protocols`.

---

## 2. File Inventory

| File | Primary Exports | Responsibility |
| :--- | :--- | :--- |
| [`input_listener.py`](./input_listener.py) | `PynputInputListener`, `SyntheticInputListener`, `create_input_listener`, `is_correction_key`, `is_macos_input_monitoring_trusted` | Anonymous keyboard/mouse event hooks and deterministic synthetic burst generator. |
| [`window_resolver.py`](./window_resolver.py) | `NativeWindowResolver`, `SyntheticWindowResolver`, `create_window_resolver`, `sanitize_process_name` | Foreground application process resolution and strict title/URL sanitization. |
| [`__init__.py`](./__init__.py) | Public collector classes and factories | Clean package facade. |
