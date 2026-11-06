"""Unified CLI entry point and stack orchestrator for EGG Telemetry & SRE Observability.

By default, running `python run.py` (or `egg-telemetry`) brings up the Docker Compose
observability stack (Prometheus, Loki, Tempo, Grafana, OTel Collector), displays clickable
endpoint URLs with explanations, and starts the local host telemetry daemon.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import httpx

from app.service import run_from_cli

PROJECT_DIR = Path(__file__).resolve().parent
COMPOSE_FILE = PROJECT_DIR / "docker-compose.yml"
PROJECT_NAME = "egg-telemetry"

STARTUP_BANNER = """
================================================================================
  EGG: Cognitive SRE Observability Platform ("User-as-a-Server")
================================================================================
  Observability Endpoints & Dashboards:

  [1] Grafana Dashboard (Single Pane of Glass):
      http://127.0.0.1:3000/d/user-as-a-server
      All metrics, focus context traces, and structured logs (admin / eggadmin)

  [2] Telemetry REST API & Docs (Swagger UI):
      http://127.0.0.1:8765/docs
      Interactive API explorer, live energy levels, and /health status

  [3] Prometheus Metrics TSDB:
      http://127.0.0.1:9090
      Raw time-series database and PromQL query console
================================================================================
  [Press Ctrl+C to cleanly stop the daemon and Docker containers]
================================================================================
"""


def _is_docker_available() -> bool:
    """Check if docker CLI is available on PATH and daemon is responsive."""
    if shutil.which("docker") is None:
        return False
    try:
        res = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False


def _docker_compose_cmd(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a docker compose command with deterministic project name and compose file."""
    cmd = [
        "docker",
        "compose",
        "-p",
        PROJECT_NAME,
        "-f",
        str(COMPOSE_FILE),
        *args,
    ]
    return subprocess.run(
        cmd,
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        check=False,
    )


def start_docker_stack() -> bool:
    """Start or verify the Docker Compose observability stack."""
    if not _is_docker_available():
        sys.stderr.write(
            "[WARN] Docker daemon is not running or docker CLI is not installed.\n"
            "       Proceeding in standalone daemon mode without containerized dashboards.\n"
            "       (Tip: Start Docker Desktop to enable Grafana, Prometheus, Loki, and Tempo.)\n\n"
        )
        return False

    sys.stdout.write("[INFO] Starting EGG observability stack (docker compose up -d)...\n")
    proc = _docker_compose_cmd("up", "-d")
    if proc.returncode != 0:
        sys.stderr.write(f"[WARN] Failed to start Docker Compose stack:\n{proc.stderr}\n")
        return False

    sys.stdout.write("[OK] Observability containers are running.\n")
    return True


def stop_docker_stack() -> None:
    """Stop the Docker Compose observability stack without deleting containers."""
    if not _is_docker_available():
        return
    sys.stdout.write("\n[STOP] Stopping EGG observability containers...\n")
    _docker_compose_cmd("stop")
    sys.stdout.write("[OK] Containers stopped cleanly.\n")


def teardown_docker_stack(prune_volumes: bool = False) -> None:
    """Tear down containers and networks completely."""
    if not _is_docker_available():
        return
    sys.stdout.write("\n[CLEAN] Tearing down EGG observability stack (docker compose down)...\n")
    args = ["down"]
    if prune_volumes:
        args.append("-v")
    _docker_compose_cmd(*args)
    sys.stdout.write("[OK] Stack torn down cleanly.\n")


def check_status() -> int:
    """Probe and print the health status of all stack endpoints and the local daemon."""
    sys.stdout.write(
        "================================================================================\n"
        "  EGG Platform Health & Status Check\n"
        "================================================================================\n"
    )

    # 1. Docker containers check
    if _is_docker_available():
        res = _docker_compose_cmd("ps", "--format", "json")
        if res.returncode == 0 and res.stdout.strip():
            sys.stdout.write("Docker Containers:\n")
            lines = res.stdout.strip().splitlines()
            for line in lines:
                try:
                    data = json.loads(line)
                    name = data.get("Name", "container")
                    state = data.get("State", "unknown")
                    status = data.get("Status", "")
                    sys.stdout.write(f"  * {name:<22}: {state.upper()} ({status})\n")
                except Exception:
                    sys.stdout.write(f"  * {line}\n")
        else:
            sys.stdout.write("Docker Containers: None running for project 'egg-telemetry'.\n")
    else:
        sys.stdout.write("Docker: Not running or not available.\n")

    sys.stdout.write("\nHTTP Endpoints Health Probes:\n")
    endpoints = [
        ("Grafana UI", "http://127.0.0.1:3000/api/health"),
        ("Prometheus TSDB", "http://127.0.0.1:9090/-/healthy"),
        ("Loki Logs", "http://127.0.0.1:3100/ready"),
        ("Tempo Traces", "http://127.0.0.1:3200/ready"),
        ("Telemetry Daemon API", "http://127.0.0.1:8765/health"),
    ]

    with httpx.Client(timeout=1.5) as client:
        for name, url in endpoints:
            try:
                resp = client.get(url)
                if resp.status_code == 200:
                    sys.stdout.write(f"  [OK]   {name:<22} ({url})\n")
                else:
                    sys.stdout.write(
                        f"  [WARN] {name:<22} ({url}) responded with HTTP {resp.status_code}\n"
                    )
            except Exception:
                sys.stdout.write(f"  [FAIL] {name:<22} ({url}) is UNREACHABLE\n")

    sys.stdout.write(
        "================================================================================\n"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI orchestrator for EGG telemetry and observability stack."""
    raw_args = list(sys.argv[1:] if argv is None else argv)

    # Top-level standalone orchestration commands
    if "--status" in raw_args:
        return check_status()

    if "--down" in raw_args:
        teardown_docker_stack(prune_volumes=False)
        return 0

    if "--clean" in raw_args:
        teardown_docker_stack(prune_volumes=True)
        return 0

    if "--stop" in raw_args:
        stop_docker_stack()
        return 0

    if "--stack-only" in raw_args:
        started = start_docker_stack()
        if started:
            sys.stdout.write(STARTUP_BANNER)
        return 0 if started else 1

    # Default execution: starts stack + daemon
    no_stack = "--no-stack" in raw_args or "--daemon-only" in raw_args
    down_on_exit = "--down-on-exit" in raw_args

    daemon_args = [
        arg for arg in raw_args if arg not in ("--no-stack", "--daemon-only", "--down-on-exit")
    ]

    stack_started = False
    if not no_stack:
        stack_started = start_docker_stack()

    # Always output the discovery banner
    sys.stdout.write(STARTUP_BANNER)

    try:
        diagnostics = asyncio.run(run_from_cli(daemon_args))
        sys.stdout.write(
            "EGG telemetry daemon exited cleanly "
            f"(samples_emitted={diagnostics.samples_emitted_total}, "
            f"window_ticks={diagnostics.window_ticks_total})\n"
        )
    except KeyboardInterrupt:
        sys.stdout.write("\nInterrupted by user (SIGINT).\n")
    finally:
        if stack_started:
            if down_on_exit:
                teardown_docker_stack()
            else:
                stop_docker_stack()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
