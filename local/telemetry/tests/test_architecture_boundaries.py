"""Architectural fitness tests enforcing the 6 Global Rules in root `AGENTS.md`."""

import ast
from pathlib import Path

from app.__main__ import main as app_main
from app.collector import SlidingWindowBuffer, SyntheticInputListener
from app.config import DaemonConfig
from app.service import TelemetryService

TELEMETRY_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = TELEMETRY_ROOT.parent.parent
APP_ROOT = TELEMETRY_ROOT / "app"
FEATURE_MODULES: tuple[str, ...] = ("collector", "analysis", "exporters", "api")


def _extract_app_imports(py_file: Path) -> list[tuple[int, tuple[str, ...]]]:
    """Parse a Python file's AST and return (lineno, module_parts) for all app.* imports."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    found: list[tuple[int, tuple[str, ...]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app" or alias.name.startswith("app."):
                    parts = tuple(alias.name.split(".")[1:])
                    found.append((node.lineno, parts))
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.level > 0:
                found.append((node.lineno, ("<relative>",)))
            elif node.module == "app" or node.module.startswith("app."):
                parts = tuple(node.module.split(".")[1:])
                found.append((node.lineno, parts))
    return found


def test_single_root_agents_md_and_standalone_readme_convention() -> None:
    """Enforce Rule 1 (Single root AGENTS.md) and Rule 2 (README.md marks standalone roots)."""
    # Rule 1: Only root AGENTS.md may exist across the entire repository
    agents_files = [
        p.relative_to(REPO_ROOT)
        for p in REPO_ROOT.rglob("*")
        if p.is_file() and p.name.lower() == "agents.md" and ".git" not in p.parts
    ]
    assert agents_files == [Path("AGENTS.md")], (
        f"Rule 1 violation: Expected only root AGENTS.md, found: {agents_files}"
    )

    # Rule 2: Standalone roots have README.md; internal packages inside app/ do not
    standalone_roots = (
        REPO_ROOT,
        TELEMETRY_ROOT,
        APP_ROOT,
        REPO_ROOT / "local" / "ui",
        REPO_ROOT / "server",
    )
    for root_dir in standalone_roots:
        readme = root_dir / "README.md"
        assert readme.is_file(), f"Rule 2 violation: Standalone root {root_dir} missing README.md"

    assert (APP_ROOT / "__main__.py").is_file(), "Standalone app/ must have __main__.py"
    assert app_main(["--simulate", "--duration", "0.05", "--no-api", "--no-otlp"]) == 0

    internal_packages = (
        APP_ROOT / "collector",
        APP_ROOT / "analysis",
        APP_ROOT / "analysis" / "strain",
        APP_ROOT / "analysis" / "workflow",
        APP_ROOT / "exporters",
        APP_ROOT / "api",
    )
    for pkg_dir in internal_packages:
        assert not (pkg_dir / "README.md").exists(), (
            f"Rule 2 violation: Internal package {pkg_dir} must not contain a README.md"
        )


def test_one_way_pipeline_and_facade_encapsulation() -> None:
    """Enforce Rule 3 (One-Way Pipeline) and Rule 4 (Public Facade Encapsulation)."""
    violations: list[str] = []

    # Allowed upstream top-level facades for each stage in the one-way pipeline:
    # config -> collector -> analysis -> (exporters, api) -> service
    allowed_upstream_facades: dict[str, frozenset[str]] = {
        "collector": frozenset({"config"}),
        "analysis": frozenset({"config", "collector"}),
        "exporters": frozenset({"config", "collector", "analysis"}),
        "api": frozenset({"config", "analysis"}),
    }

    # 1. Verify all 4 top-level feature folders exist and have non-empty __init__.py facades
    for mod_name in FEATURE_MODULES:
        mod_dir = APP_ROOT / mod_name
        init_file = mod_dir / "__init__.py"
        assert mod_dir.is_dir(), f"Expected feature module {mod_dir} to exist"
        assert init_file.is_file() and len(init_file.read_text(encoding="utf-8").strip()) > 50

    # 2. service.py must only import top-level facades (1 level deep)
    service_file = APP_ROOT / "service.py"
    for lineno, parts in _extract_app_imports(service_file):
        if len(parts) != 1 or parts[0] not in (*FEATURE_MODULES, "config"):
            target = ".".join(("app", *parts))
            violations.append(
                f"service.py:{lineno} reaches into '{target}' instead of a top-level facade"
            )

    # 3. Check every package in the one-way pipeline for:
    #    (a) one-way dependency order, and
    #    (b) facade-only cross-package imports (never reaching into another package's submodules)
    for pkg_name, allowed_external in allowed_upstream_facades.items():
        for py_file in sorted((APP_ROOT / pkg_name).rglob("*.py")):
            rel = py_file.relative_to(TELEMETRY_ROOT)
            for lineno, parts in _extract_app_imports(py_file):
                if not parts:
                    continue
                target_pkg = parts[0]
                if target_pkg == pkg_name:
                    # Internal import within the same top-level package is allowed
                    continue
                if target_pkg not in allowed_external:
                    violations.append(
                        f"{rel}:{lineno} imports 'app.{'.'.join(parts)}' "
                        f"(violates one-way pipeline for '{pkg_name}/')"
                    )
                elif len(parts) > 1:
                    violations.append(
                        f"{rel}:{lineno} reaches into 'app.{'.'.join(parts)}' "
                        f"instead of importing top-level facade 'app.{target_pkg}'"
                    )

    # 4. Sibling subpackages inside analysis/ (strain/ vs workflow/) must never import each other
    for submod, sibling in (("strain", "workflow"), ("workflow", "strain")):
        for py_file in sorted((APP_ROOT / "analysis" / submod).rglob("*.py")):
            rel = py_file.relative_to(TELEMETRY_ROOT)
            for lineno, parts in _extract_app_imports(py_file):
                if len(parts) >= 2 and parts[:2] == ("analysis", sibling):
                    violations.append(
                        f"{rel}:{lineno} imports sibling 'app.analysis.{sibling}' "
                        f"inside 'analysis/{submod}/'"
                    )

    assert not violations, "Architecture boundary violations:\n" + "\n".join(violations)


async def test_root_service_combines_feature_modules() -> None:
    """Verify TelemetryService wires collector, analysis, exporters, and api cleanly."""
    config = DaemonConfig(
        sliding_window_seconds=10.0,
        emit_interval_seconds=0.1,
        window_poll_interval_seconds=0.05,
        simulate=True,
        enable_otlp=False,
    )
    service = TelemetryService(config)

    assert isinstance(service.buffer, SlidingWindowBuffer)
    assert isinstance(service.input_listener, SyntheticInputListener)
    assert service.config.api_host == "127.0.0.1"
    assert service.config.api_port == 8765

    service.collector.start()
    service.collector.poll_window(0.25)
    service.collector.stop()

    metrics, report = service.evaluate_and_emit_once()
    assert metrics.sample_count >= 1
    assert metrics.total_keystrokes == 12
    assert report.sre_status in ("nominal", "flow_optimal", "warning", "critical")
    assert service.last_state is not None
