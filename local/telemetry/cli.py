"""Cross-platform interactive CLI menu for Local Fatigue Telemetry (macOS, Linux, Windows)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def venv_python() -> Path:
    if sys.platform == "win32":
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def venv_pip() -> Path:
    if sys.platform == "win32":
        return ROOT / ".venv" / "Scripts" / "pip.exe"
    return ROOT / ".venv" / "bin" / "pip"


def has_venv() -> bool:
    return venv_python().exists()


def has_webcam_deps() -> bool:
    if not has_venv():
        return False
    res = subprocess.run(
        [str(venv_python()), "-c", "import cv2, mediapipe"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return res.returncode == 0


def has_docker() -> bool:
    if shutil.which("docker") is None:
        return False
    res = subprocess.run(
        ["docker", "info"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return res.returncode == 0


def setup_env(with_webcam: bool = False) -> None:
    if not has_venv():
        print(f"Creating virtual environment with {sys.executable}...")
        subprocess.check_call([sys.executable, "-m", "venv", str(ROOT / ".venv")])
    extras = ".[webcam,dev]" if with_webcam else ".[dev]"
    print(f"Installing dependencies ({extras})...")
    subprocess.check_call(
        [str(venv_pip()), "install", "--disable-pip-version-check", "-e", extras],
        cwd=ROOT,
    )
    print("Setup complete.")


def fix_macos_permissions() -> None:
    if sys.platform != "darwin":
        print("Permission helper is only needed on macOS.")
        return
    print("\n=== macOS Permissions Helper ===")
    print("Why these permissions are needed:")
    print("  - Accessibility & Input Monitoring: lets pynput measure key/mouse timing (ms).")
    print("    No typed characters or screen (x, y) coordinates are ever stored.")
    print("  - Camera (optional): lets MediaPipe measure 60s eye-closure bursts in memory.")
    print("    No photos or video frames are ever saved to disk.\n")
    print("Opening Accessibility & Input Monitoring settings...")
    for pane in ("Privacy_Accessibility", "Privacy_ListenEvent"):
        subprocess.run(
            ["open", f"x-apple.systempreferences:com.apple.preference.security?{pane}"],
            check=False,
        )
    if has_webcam_deps():
        print("Requesting Camera permission on the main thread...")
        subprocess.run(
            [
                str(venv_python()),
                "-c",
                "import cv2; cap = cv2.VideoCapture(0); print('   Camera opened:', cap.isOpened()); cap.release()",
            ],
            check=False,
        )
        subprocess.run(
            ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera"],
            check=False,
        )
    print("Toggle ON your terminal app (or toggle OFF anytime to revoke), then restart it if prompted.")


def configure_autostart(enable_webcam: bool = False) -> None:
    """Install OS-native auto-start on login (launchd / systemd --user / Task Scheduler)."""
    print("\nWhy auto-start is useful:")
    print("  Runs the lightweight local collector (run.py) on login so your personal")
    print("  baseline stays continuous without needing Docker/Grafana open all day.\n")
    if not has_venv():
        setup_env(with_webcam=enable_webcam)
    py = str(venv_python())
    script = str(ROOT / "run.py")
    extra_flag = " --enable-webcam" if enable_webcam else ""

    if sys.platform == "darwin":
        dst = Path.home() / "Library" / "LaunchAgents" / "com.telemetry.fatigue.plist"
        dst.parent.mkdir(parents=True, exist_ok=True)
        args_xml = f"        <string>{py}</string>\n        <string>{script}</string>"
        if enable_webcam:
            args_xml += "\n        <string>--enable-webcam</string>"
        log_dir = Path.home() / "Library" / "Logs"
        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.telemetry.fatigue</string>
    <key>ProgramArguments</key><array>
{args_xml}
    </array>
    <key>WorkingDirectory</key><string>{ROOT}</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>{log_dir / "telemetry-fatigue.out.log"}</string>
    <key>StandardErrorPath</key><string>{log_dir / "telemetry-fatigue.err.log"}</string>
</dict>
</plist>
"""
        dst.write_text(plist, encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(dst)], stderr=subprocess.DEVNULL)
        subprocess.check_call(["launchctl", "load", str(dst)])
        print(f"Auto-start enabled via launchd ({dst}).")

    elif sys.platform.startswith("linux"):
        unit_dir = Path.home() / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        unit_file = unit_dir / "telemetry-fatigue.service"
        unit = (
            "[Unit]\nDescription=Local Fatigue Telemetry Daemon\n\n"
            f"[Service]\nWorkingDirectory={ROOT}\n"
            f"ExecStart=\"{py}\" \"{script}\"{extra_flag}\nRestart=on-failure\n\n"
            "[Install]\nWantedBy=default.target\n"
        )
        unit_file.write_text(unit, encoding="utf-8")
        subprocess.check_call(["systemctl", "--user", "daemon-reload"])
        subprocess.check_call(["systemctl", "--user", "enable", "--now", "telemetry-fatigue.service"])
        print(f"Auto-start enabled via systemd --user ({unit_file}).")

    elif sys.platform == "win32":
        cmd = f'"{py}" "{script}"{extra_flag}'
        subprocess.check_call(
            ["schtasks", "/Create", "/F", "/SC", "ONLOGON", "/TN", "LocalFatigueTelemetry", "/TR", cmd]
        )
        print("Auto-start enabled via Windows Task Scheduler (LocalFatigueTelemetry).")
    else:
        print(f"Unsupported OS for auto-start: {sys.platform}")


def revert_settings() -> None:
    """Transparently revert auto-start, reset anchors, or open OS permission revocation."""
    print("\n=== Revert / Reset Settings ===")
    print("  1) Disable & remove Auto-Start on Login")
    print("  2) Reset Personal-Best Anchors & IQRs (keeps raw data & fatigue_log)")
    print("  3) Open macOS Privacy Settings to revoke permissions")
    print("  4) Back\n")
    sub = input("Choose [1-4]: ").strip()

    if sub == "1":
        if sys.platform == "darwin":
            dst = Path.home() / "Library" / "LaunchAgents" / "com.telemetry.fatigue.plist"
            if dst.exists():
                subprocess.run(["launchctl", "unload", str(dst)], stderr=subprocess.DEVNULL)
                dst.unlink()
                print(f"Removed launchd auto-start ({dst}).")
            else:
                print("Auto-start is not currently installed.")
        elif sys.platform.startswith("linux"):
            unit = Path.home() / ".config" / "systemd" / "user" / "telemetry-fatigue.service"
            subprocess.run(["systemctl", "--user", "disable", "--now", "telemetry-fatigue.service"], check=False)
            if unit.exists():
                unit.unlink()
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
            print("Removed systemd --user auto-start.")
        elif sys.platform == "win32":
            subprocess.run(["schtasks", "/Delete", "/F", "/TN", "LocalFatigueTelemetry"], check=False)
            print("Removed Windows Task Scheduler auto-start.")
    elif sub == "2":
        db_file = ROOT / "data" / "telemetry.db"
        if not db_file.exists():
            print("No database found yet.")
            return
        ans = input("Reset app_anchors & app_iqrs (e.g. after changing keyboard)? [y/N]: ").strip()
        if ans.lower() == "y":
            import sqlite3

            conn = sqlite3.connect(str(db_file))
            with conn:
                for table in ("app_anchors", "app_iqrs"):
                    try:
                        conn.execute(f"DELETE FROM {table}")
                    except sqlite3.OperationalError:
                        pass
            conn.close()
            print("Anchors & IQRs cleared; they will rebuild from fatigue_log on next start.")
    elif sub == "3" and sys.platform == "darwin":
        for pane in ("Privacy_Accessibility", "Privacy_ListenEvent", "Privacy_Camera"):
            subprocess.run(
                ["open", f"x-apple.systempreferences:com.apple.preference.security?{pane}"],
                check=False,
            )
        print("Opened macOS Privacy panes—toggle OFF your terminal app to revoke.")


def start_full_stack(extra_args: list[str]) -> None:
    if not has_venv():
        setup_env(with_webcam=False)
    if not has_docker():
        print("Error: Docker is not running. Start Docker Desktop or choose Local Daemon Only.")
        sys.exit(1)

    print("Starting Prometheus (:9090) & Grafana (:3000)...")
    subprocess.check_call(["docker", "compose", "up", "-d"], cwd=ROOT)
    print("\nGrafana:    http://127.0.0.1:3000")
    print("Prometheus: http://127.0.0.1:9090")
    print("Metrics:    http://127.0.0.1:9105/metrics")
    print("Starting local telemetry daemon (Ctrl+C to stop everything)...")
    try:
        subprocess.call([str(venv_python()), str(ROOT / "run.py"), *extra_args], cwd=ROOT)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nStopping Prometheus & Grafana...")
        subprocess.run(["docker", "compose", "down"], cwd=ROOT, check=False)


def main() -> None:
    os.chdir(ROOT)
    if len(sys.argv) > 1:
        start_full_stack(sys.argv[1:])
        return

    venv_s = "OK" if has_venv() else "missing"
    cam_s = "OK" if has_webcam_deps() else "missing"
    dock_s = "OK" if has_docker() else "stopped"

    print("\n=== Local Fatigue Telemetry ===")
    print(f"OS: {sys.platform} | venv [{venv_s}] | webcam deps [{cam_s}] | docker [{dock_s}]\n")
    print("  1) Start Full Stack (Passive: Keyboard, Mouse, Window + Prometheus/Grafana)")
    print("  2) Start Full Stack + Webcam (On-demand 60s confirmation bursts)")
    print("  3) Start Local Daemon Only (No Docker — SQLite + :9105/metrics)")
    print("  4) Setup / Install Dependencies")
    print("  5) Enable Auto-Start on Computer Login")
    if sys.platform == "darwin":
        print("  6) Fix macOS Permissions (Accessibility, Input Monitoring & Camera)")
    print("  7) Revert / Reset Settings (disable auto-start, reset anchors, revoke permissions)")
    print("  8) Run Tests (pytest)")
    print("  9) Quit\n")

    choice = input("Choose [1-9]: ").strip()
    if choice == "1":
        start_full_stack([])
    elif choice == "2":
        if not has_webcam_deps():
            ans = input("Webcam deps (opencv, mediapipe) not installed. Install now? [y/N]: ").strip()
            if ans.lower() == "y":
                setup_env(with_webcam=True)
            else:
                return
        start_full_stack(["--enable-webcam"])
    elif choice == "3":
        if not has_venv():
            setup_env(with_webcam=False)
        print("Metrics: http://127.0.0.1:9105/metrics (Ctrl+C to stop)")
        subprocess.call([str(venv_python()), str(ROOT / "run.py")], cwd=ROOT)
    elif choice == "4":
        ans = input("Include optional webcam dependencies (opencv, mediapipe)? [y/N]: ").strip()
        setup_env(with_webcam=(ans.lower() == "y"))
    elif choice == "5":
        ans = input("Enable on-demand webcam in auto-start daemon? [y/N]: ").strip()
        configure_autostart(enable_webcam=(ans.lower() == "y"))
    elif choice == "6":
        fix_macos_permissions()
    elif choice == "7":
        revert_settings()
    elif choice == "8":
        if not has_venv():
            setup_env(with_webcam=False)
        subprocess.call([str(venv_python()), "-m", "pytest", "-v"], cwd=ROOT)
    elif choice == "9":
        return
    else:
        print("Invalid choice.")


if __name__ == "__main__":
    main()
