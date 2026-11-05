"""Architectural boundary tests enforcing the Hourglass + LCA (`common/`) rule."""

import ast
from pathlib import Path

from app.common import DaemonConfig
from app.intake.collectors import SyntheticInputListener
from app.intake.engine import EpochBuffer
from app.output.dimensions import DimensionContext, create_default_registry
from app.service import TelemetryService
from app.storage import EpochRepository

APP_ROOT = Path(__file__).resolve().parent.parent / "app"
LEAF_PACKAGES: tuple[tuple[str, ...], ...] = (
    ("intake", "collectors"),
    ("intake", "engine"),
    ("storage",),
    ("output", "dimensions"),
    ("output", "api"),
)


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


def test_hourglass_and_lca_common_architecture_boundaries() -> None:
    """Enforce 'Downward = I'll say when (service.py)' and 'Upward = What do you want (common/)'."""
    violations: list[str] = []

    # 1. Every behavioral leaf package may ONLY import from itself or from app.common.*
    for leaf_parts in LEAF_PACKAGES:
        folder_path = APP_ROOT.joinpath(*leaf_parts)
        assert folder_path.is_dir(), f"Expected leaf package {folder_path} to exist"
        leaf_prefix = ".".join(("app", *leaf_parts))

        for py_file in sorted(folder_path.rglob("*.py")):
            rel_path = py_file.relative_to(APP_ROOT.parent)
            for lineno, target_parts in _extract_app_imports(py_file):
                is_self = (
                    len(target_parts) >= len(leaf_parts)
                    and target_parts[: len(leaf_parts)] == leaf_parts
                )
                is_common = len(target_parts) >= 1 and target_parts[0] == "common"
                if not (is_self or is_common):
                    target_str = ".".join(("app", *target_parts))
                    violations.append(
                        f"{rel_path}:{lineno} imports '{target_str}' inside '{leaf_prefix}' "
                        f"(only '{leaf_prefix}.*' and LCA contract 'app.common.*' are allowed)"
                    )

    # 2. LCA contract folder (app/common/) must NEVER import from intake, storage, output, service
    common_dir = APP_ROOT / "common"
    assert common_dir.is_dir(), f"Expected LCA contract folder {common_dir} to exist"
    for py_file in sorted(common_dir.rglob("*.py")):
        rel_path = py_file.relative_to(APP_ROOT.parent)
        for lineno, target_parts in _extract_app_imports(py_file):
            if not (len(target_parts) >= 1 and target_parts[0] == "common"):
                target_str = ".".join(("app", *target_parts))
                violations.append(
                    f"{rel_path}:{lineno} imports '{target_str}' inside LCA contract 'app/common/'"
                )

    assert not violations, "Hourglass + LCA architectural boundary violated:\n" + "\n".join(
        violations
    )


async def test_root_service_wires_intake_storage_and_output(tmp_path: Path) -> None:
    """Verify TelemetryService ('I'll say when') wires intake, storage, and output directly."""
    db_path = tmp_path / "hourglass_test.db"
    config = DaemonConfig(
        epoch_duration_seconds=5.0,
        window_poll_interval_seconds=0.05,
        database_path=db_path,
        simulate=True,
    )
    service = TelemetryService(config)

    assert isinstance(service.buffer, EpochBuffer)
    assert isinstance(service.input_listener, SyntheticInputListener)
    assert isinstance(service.repository, EpochRepository)
    assert service.storage is service.repository
    assert service.repository.db_path == db_path
    assert len(service.dimensions.dimensions) == 4
    assert service.api_host == "127.0.0.1"
    assert service.api_port == 8765

    await service.repository.initialize()
    service.input_listener.start()
    service.input_listener.emit_synthetic_burst()
    proc = service.window_resolver.get_active_process_name()
    assert proc == "Code.exe"
    service.scheduler.poll_window_once(0.25)
    service.input_listener.stop()

    flushed = await service.scheduler.flush_now()
    assert flushed.id == 1
    assert await service.repository.count_epochs() == 1

    persisted_epochs = await service.repository.fetch_epochs_in_range(0.0, float("inf"))
    assert len(persisted_epochs) == 1
    pooled = service.repository.pool_epochs(persisted_epochs)
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
