"""Architectural boundary tests enforcing Zero-Upward and Zero-Sibling imports across app/."""

import ast
from pathlib import Path

from app.collectors import CollectorCoordinator, SyntheticInputListener
from app.config import DaemonConfig
from app.dimensions import DimensionContext, create_default_registry
from app.engine import EngineOrchestrator, EpochBuffer
from app.service import TelemetryService
from app.storage import StorageOrchestrator

APP_ROOT = Path(__file__).resolve().parent.parent / "app"
SUBFOLDER_NAMES = ("collectors", "engine", "storage", "dimensions", "api")


def _extract_app_imports(py_file: Path) -> list[tuple[int, str]]:
    """Parse a Python file's AST and return (lineno, top_subpackage) for all app.* imports."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app" or alias.name.startswith("app."):
                    parts = alias.name.split(".")
                    target = parts[1] if len(parts) > 1 else ""
                    found.append((node.lineno, target))
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.level > 0:
                found.append((node.lineno, "<relative>"))
            elif node.module == "app" or node.module.startswith("app."):
                parts = node.module.split(".")
                target = parts[1] if len(parts) > 1 else ""
                found.append((node.lineno, target))
    return found


def test_subfolders_have_zero_upward_or_sibling_imports() -> None:
    """Every subfolder in app/ must only import from itself (never upward or sideways)."""
    violations: list[str] = []

    for subfolder in SUBFOLDER_NAMES:
        folder_path = APP_ROOT / subfolder
        assert folder_path.is_dir(), f"Expected subfolder {folder_path} to exist"

        for py_file in sorted(folder_path.rglob("*.py")):
            rel_path = py_file.relative_to(APP_ROOT.parent)
            for lineno, target in _extract_app_imports(py_file):
                if target != subfolder:
                    violations.append(
                        f"{rel_path}:{lineno} imports 'app.{target}' inside 'app/{subfolder}/' "
                        f"(only 'app.{subfolder}.*' is allowed)"
                    )

    assert not violations, "Hierarchical folder isolation violated:\n" + "\n".join(violations)


async def test_folder_orchestrators_and_root_service_wiring(tmp_path: Path) -> None:
    """Verify folder orchestrators (Collectors, Engine, Storage, Dimensions) and root service."""
    db_path = tmp_path / "orchestrator_test.db"
    config = DaemonConfig(
        epoch_duration_seconds=5.0,
        window_poll_interval_seconds=0.05,
        database_path=db_path,
        simulate=True,
    )
    service = TelemetryService(config)

    assert isinstance(service.collectors, CollectorCoordinator)
    assert isinstance(service.engine, EngineOrchestrator)
    assert isinstance(service.storage, StorageOrchestrator)
    assert service.storage.db_path == db_path
    assert len(service.dimensions.dimensions) == 4

    await service.storage.initialize()
    service.collectors.start()
    assert service.collectors.emit_synthetic_burst_if_active() is True
    proc = service.collectors.get_active_process_name()
    assert proc == "Code.exe"
    service.engine.scheduler.poll_window_once(0.25)
    service.collectors.stop()
    assert service.collectors.emit_synthetic_burst_if_active() is False

    flushed = await service.engine.flush_now()
    assert flushed.id == 1
    assert await service.storage.count_epochs() == 1

    persisted_epochs = await service.storage.fetch_epochs_in_range(0.0, float("inf"))
    assert len(persisted_epochs) == 1
    pooled = service.storage.pool_epochs(persisted_epochs)
    assert pooled.epoch_count == 1
    assert pooled.total_keystrokes == 12

    dim_registry = create_default_registry()
    ctx = DimensionContext.from_epochs(persisted_epochs, pooled=pooled)
    evals = dim_registry.evaluate_all(ctx)
    assert set(evals.keys()) == {
        "temporal_dynamics",
        "attentional_fragmentation",
        "psychomotor_mechanics",
        "circadian_load",
    }

    # Verify CollectorCoordinator with non-synthetic listener returns False for synthetic burst
    buf = EpochBuffer()
    sim_listener = SyntheticInputListener(buf)
    coord = CollectorCoordinator(
        input_listener=sim_listener,
        window_resolver=service.collectors.window_resolver,
    )
    assert coord.emit_synthetic_burst_if_active() is False
