# Sprint 1.0 Report: Domain-Scoped Monorepo, Privacy-by-Construction & DevOps Guardrails

- **Date**: 2026-10-28
- **Sprint**: `Sprint 1.0 — Architecture & DevOps Foundation`
- **Services Touched**: Root Monorepo (`Microservice-egg`), `telemetry/daemon`, `telemetry/api` (rules)
- **Verification Status**:
  - `ruff check` & `ruff format --check`: **PASS (0 warnings/errors)**
  - `mypy --strict`: **PASS (7 source files, 0 issues)**
  - `pytest --cov=app --cov-fail-under=90`: **PASS (3/3 tests, 100.00% line & branch coverage)**
  - Environment: **Python 3.12 (`uv.lock` deterministic build, 23 packages)**

---

## 1. Executive Summary (Company-Style Sprint Review)

In Sprint 1.0, we established the architectural blueprint and automated DevOps quality gates for the **Cognitive Telemetry & Activity Block Platform**—a local-first system that helps knowledge workers gain empirical self-insight into focus, attentional fragmentation, and psychomotor fatigue without compromising privacy.

Before writing core ingestion or API logic, we solved three foundational systems engineering challenges:
1. **How do you test OS-level hardware hooks (`pynput`, macOS `NSWorkspace`, Linux `Xlib`) inside headless Docker containers and CI runners?**
2. **How do you structure a multi-service repository so both human reviewers and AI coding agents have strict context isolation?**
3. **How do you enforce privacy and mathematical invariants automatically on every commit?**

---

## 2. Key Architectural & DevOps Decisions (ADRs)

### ADR-01: Domain-Scoped Multi-Service Monorepo over Polyrepo
- **Context**: The platform separates high-frequency 30-second epoch collection (`telemetry/daemon`) from downstream scientific dimension aggregation, 60s/90s activity block debouncing, and FastAPI delivery (`telemetry/api`).
- **Decision**: Organize services inside a single monorepo (`Microservice-egg/telemetry/daemon` and `Microservice-egg/telemetry/api`), each with its own isolated `uv` environment (`pyproject.toml` + `uv.lock`).
- **Impact**: Enables path-filtered CI/CD pipelines, atomic end-to-end integration tests over shared SQLite WAL volumes, and scoped AI context boundaries.

### ADR-02: Hardware Decoupling via Python Protocols & Synthetic Mode
- **Context**: Native keyboard/mouse listeners and window resolvers fail in headless Linux CI containers without physical displays (`$DISPLAY`) or OS accessibility permissions.
- **Decision**: Decouple all collectors behind strict `typing.Protocol` interfaces (`InputListenerProtocol`, `WindowResolverProtocol`) and ship deterministic synthetic implementations (`--simulate`).
- **Impact**: 100% of the pipeline can be unit-tested and run inside `docker compose` in CI/CD without hardware dependencies.

### ADR-03: Hierarchical AI Guardrails (`AGENTS.md`) & Mandatory Verification Gates
- **Context**: AI-assisted engineering requires strict guardrails so architectural invariants (zero keystroke logging, lossless algebraic primitives $\sum x$ and $\sum x^2$, `127.0.0.1` binding) never drift across sessions.
- **Decision**: Implement hierarchical `AGENTS.md` files at the root, `telemetry/daemon/`, and `telemetry/api/` levels, paired with a mandatory 3-step verification loop (`ruff`, `mypy --strict`, `pytest --cov-fail-under=90`).

---

## 3. Deliverables Shipped in Sprint 1.0

| Component | Path | Description |
| :--- | :--- | :--- |
| **Master Plan** | `DEVOPS_PORTFOLIO_PLAN.md` | Unified system architecture, data flow diagrams, and 3-phase DevOps roadmap. |
| **Root Rules** | `AGENTS.md` | Global privacy invariants, localhost binding rules, and mandatory `uv` verification loop. |
| **Service Rules** | `telemetry/daemon/AGENTS.md` & `telemetry/api/AGENTS.md` | Context-scoped mathematical and architectural boundaries per microservice. |
| **Daemon Toolchain** | `telemetry/daemon/pyproject.toml` & `uv.lock` | Reproducible Python 3.12 environment with `aiosqlite`, `pynput`, `ruff`, `mypy`, `pytest`. |
| **12-Factor Config** | `telemetry/daemon/app/config.py` | Immutable `DaemonConfig` dataclass (`frozen=True, slots=True`) with env-var overrides (`TELEMETRY_DB_PATH`, `TELEMETRY_EPOCH_SECONDS`). |
| **Unit Tests** | `telemetry/daemon/tests/test_config.py` | 100% branch-covered unit tests validating config defaults, env overrides, and error handling. |

---

## 4. LinkedIn Carousel Slide Deck Blueprint (7 Slides)

> **Tip**: Copy these slides directly into **Gamma.app**, **Marp**, **Canva**, or **Figma** to generate a clean dark-mode technical carousel.

### Slide 1 — Cover Slide
- **Headline**: Building a Privacy-First Cognitive Telemetry Platform: Day 1 Architecture & DevOps Guardrails
- **Subheadline**: How I set up a production-grade Python monorepo before writing a single line of business logic.
- **Visual Prompt**: High-level diagram showing `telemetry/daemon` $\rightarrow$ `SQLite WAL (30s Epochs)` $\rightarrow$ `telemetry/api (FastAPI & Scientific Dimensions)`.
- **Footer**: Engineering Sprint 1.0 • DevOps & Systems Architecture

---

### Slide 2 — The Problem: Hardware Hooks Meet Headless CI/CD
- **Headline**: The DevOps Challenge: Testing OS Hardware Listeners in Headless Containers
- **Body**:
  - Our ingestion daemon tracks typing rhythm mechanics (inter-keystroke intervals) and window switches using `pynput` and OS APIs (`NSWorkspace`, `win32gui`, `Xlib`).
  - **The Catch**: Headless Linux Docker containers and GitHub Actions runners don't have keyboards, mice, or display servers (`$DISPLAY`).
  - **The Solution**: Strict Dependency Injection using Python `typing.Protocol` interfaces + a deterministic `--simulate` workload mode for end-to-end container testing.

---

### Slide 3 — Architecture: Domain-Scoped Monorepo
- **Headline**: Why We Chose a Domain-Scoped Monorepo (`telemetry/daemon` + `telemetry/api`)
- **Body**:
  - **Service 1 (`telemetry/daemon`)**: Lightweight 30s micro-epoch collector writing lossless algebraic primitives ($\sum x, \sum x^2$) to SQLite in WAL mode.
  - **Service 2 (`telemetry/api`)**: Pluggable Scientific Dimension Engine, 60s/90s hysteresis Activity Block Chunker, and FastAPI server.
  - **Isolated Environments**: Each service has its own `pyproject.toml` and `uv.lock`—enabling path-filtered CI pipelines and zero cross-service coupling.

---

### Slide 4 — Privacy by Construction & Lossless Math
- **Headline**: Privacy by Construction + Zero-Loss Statistical Pooling
- **Body**:
  - **Zero Keystroke Content**: Key codes, characters, window titles, and URLs are never captured or buffered—even in RAM.
  - **Why Pre-Averaged Metrics Fail**: Averaging averages across 30s windows distorts standard deviation.
  - **Algebraic Primitives**: Every 30s epoch stores `iki_count` ($N$), `iki_sum_ms` ($\sum x$), and `iki_sum_sq_ms` ($\sum x^2$) so downstream services compute exact pooled variance ($\sigma^2_{\text{pooled}}$) across 5-minute, 90-minute, or 24-hour windows.

---

### Slide 5 — Context Engineering: Hierarchical `AGENTS.md`
- **Headline**: Treating AI Context Like System Architecture
- **Body**:
  - Instead of dumping the whole repo into an AI prompt, we built hierarchical `AGENTS.md` guardrails:
    - `/AGENTS.md` $\rightarrow$ Global DevOps, privacy, and verification gates.
    - `/telemetry/daemon/AGENTS.md` $\rightarrow$ Ephemeral RAM buffer & SQLite WAL rules.
    - `/telemetry/api/AGENTS.md` $\rightarrow$ Open-closed `BaseDimension` & chunker hysteresis rules.
  - Working inside a service directory loads *only* that service's context + global standards.

---

### Slide 6 — The Automated Verification Loop
- **Headline**: Zero Broken Commits: Our 3-Gate Verification Loop
- **Body**:
  - Every sprint task must pass three automated gates via **`uv`** before completion:
    1. **Lint & Format**: `uv run ruff check .` & `ruff format --check .`
    2. **Strict Static Typing**: `uv run mypy --strict app tests`
    3. **Automated Tests & Coverage**: `uv run pytest --cov=app --cov-fail-under=90`
  - **Sprint 1.0 Result**: 23 packages locked in `471ms`, `0` mypy issues, `100.0%` test coverage on our 12-Factor `DaemonConfig` module.

---

### Slide 7 — What's Next in Sprint 1.1
- **Headline**: Next Up: Sprint 1.1 — Async SQLite WAL & Pooled Variance Verification
- **Body**:
  - Implementing `app/storage/database.py` (SQLite WAL mode + time-range indexing).
  - Building `app/storage/repository.py` with async batch inserts & DTOs.
  - Proving mathematically that pooled variance across $N$ 30-second epochs matches raw unchunked variance to $10^{-9}$ precision.
- **Call to Action**: Follow along as I build and containerize this platform sprint by sprint!

---

## 5. Ready-to-Post LinkedIn Caption

```text
How do you run CI/CD and Docker integration tests for a service that relies on physical keyboard, mouse, and OS window hooks? 🛠️

Today I kicked off Sprint 1.0 of my new DevOps & Systems Engineering project: a Privacy-by-Construction Cognitive Telemetry & Activity Block Platform built in Python.

Before writing feature code, I treated Day 1 like a production engineering team:

1️⃣ Hardware Decoupling via Protocols:
OS listeners (pynput, NSWorkspace, Xlib) fail in headless Linux CI containers. By isolating hardware collectors behind Python typing.Protocol interfaces with a deterministic --simulate mode, the entire stack can run end-to-end inside Docker Compose and GitHub Actions.

2️⃣ Domain-Scoped Monorepo + uv:
Split the ingestion daemon (telemetry/daemon) and downstream FastAPI/Chunker engine (telemetry/api) into isolated uv environments within a single monorepo—setting up clean boundaries for path-filtered CI workflows.

3️⃣ Hierarchical AI Guardrails & Quality Gates:
Scoped AGENTS.md rules per service and wired a strict 3-step verification gate (ruff + mypy --strict + pytest >=90% branch coverage) that must pass before any task is marked complete.

Swipe through the slides for a breakdown of the architecture, lossless statistical pooling (Σx and Σx²), and our Day 1 verification pipeline 👉

Next up in Sprint 1.1: Async SQLite WAL storage and mathematical proof tests for pooled variance and Shannon entropy.

#DevOps #Python #SoftwareArchitecture #PlatformEngineering #BuildInPublic #FastAPI #CICD
```
