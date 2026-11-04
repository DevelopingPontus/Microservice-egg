# `.github/` Context & Interface Contract

> **Repository automation, CI/CD quality gates, and automated dependency management.**

---

## 1. What, Why, When & How

### What (Scope)

This folder manages the repository's continuous integration (CI), quality gate enforcement, and automated dependency scanning through GitHub Actions and Dependabot.

### Why (Rationale)

1. **Automated Quality Gate Enforcement**: To guarantee that no pull request can merge unless it passes formatting (`ruff`), strict type checking (`mypy --strict`), and unit test coverage floors ($\ge 90\%$).
2. **Path-Filtered CI Efficiency**: In a polyglot monorepo (`Python` + `Java`), running Java builds when only Python code changed wastes runner minutes and slows developer feedback. CI workflows are path-filtered to trigger only on relevant folder changes.

### When (Lifecycle)

- Triggers on pull requests targeting `main` and on direct pushes to `main`.
- Triggers on weekly schedules for automated dependency updates via Dependabot.

### How (Mechanics)

- **Path Filtering**: Workflows define `paths: ['local/agent/**', '.github/workflows/ci-local-agent.yml']` to isolate trigger conditions.
- **Headless Execution**: Uses `uv` and headless synthetic test simulation so workflows never require display servers (`$DISPLAY`), hardware devices, or physical GUI hooks.

---

## 2. File Inventory

| File | Purpose | Trigger Scope |
| :--- | :--- | :--- |
| [`dependabot.yml`](./dependabot.yml) | Weekly automated dependency version bumps for `uv` (Python), Maven/Gradle (Java), and GitHub Actions. | Scheduled weekly. |

---

## 3. Subfolder Routing

- [`workflows/`](./workflows/): Contains all GitHub Actions workflow YAML declarations:
  - [`ci-local-agent.yml`](./workflows/ci-local-agent.yml): Python 3.12 CI gate (`uv sync`, `ruff check`, `ruff format`, `mypy --strict`, `pytest --cov --cov-fail-under=90`).
  - *(Phase 3 planned)* `ci-server.yml`: Java 27 / Spring Boot 4.1.2 CI gate.
  - *(Phase 4 planned)* `integration-e2e.yml`: Docker Compose multi-tier end-to-end integration test.
