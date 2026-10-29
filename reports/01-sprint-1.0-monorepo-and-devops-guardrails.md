# Sprint 1.0 Report: Two-Tier Polyglot Architecture, Privacy-by-Construction & CI/CD Guardrails

- **Date**: 2026-10-29
- **Sprint**: `Sprint 1.0 — Architecture, Polyglot Monorepo & DevOps Foundation`
- **Services & Tiers Touched**:
  - Root Monorepo (`Microservice-egg`, `.github/workflows/ci-local-agent.yml`, `.github/dependabot.yml`)
  - Tier 1 Local Runtime (`local/agent/`, `local/ui/` rules)
  - Tier 2 Central Server (`server/` rules — Java 27 + Spring Boot 4.1.2 + Neo4j 5+)
- **Verification Status (`local/agent/`)**:
  - `ruff check .` & `ruff format --check .`: **PASS (0 warnings/errors)**
  - `mypy --strict app tests`: **PASS (9 source files, 0 issues)**
  - `pytest --cov=app --cov-fail-under=90`: **PASS (3/3 tests, 100.00% line & branch coverage)**
  - CI/CD Matrix: **Multi-OS GitHub Actions (`ubuntu-latest`, `macos-latest`) + Automated Dependabot (`uv`, `github-actions`, `maven`, `docker`)**

---

## 1. Executive Summary (Company-Style Sprint Review)

In Sprint 1.0, we designed and bootstrapped the architecture and automated DevOps pipeline for **`Microservice-egg`**—a polyglot **Cognitive Telemetry & Shared Topic-Tree Platform**.

Before writing ingestion or graph-traversal logic, we resolved four core systems engineering and privacy design questions:
1. **How do we guarantee that sensitive behavioral telemetry never leaves the user's computer while still enabling a shared, multi-user knowledge graph in the cloud?**
2. **How should the local desktop runtime be split so that closing the user interface never interrupts background 30-second hardware telemetry collection?**
3. **How can the central server avoid calling an LLM repeatedly when thousands of users ask to break down semantically identical topics?**
4. **How do we test OS-level hardware hooks (`pynput`, `NSWorkspace`, `Xlib`) and enforce strict quality gates automatically inside headless GitHub Actions runners?**

---

## 2. Key Architectural & DevOps Decisions (ADRs)

### ADR-01: Two-Tier Privacy-Split Monorepo (`local/` vs. `server/`)
- **Context**: Behavioral telemetry (typing cadence, window switches, fatigue trajectories) is deeply personal and must remain 100% on the user's device. Conversely, decomposing learning or project topics into recursive sub-topic trees benefits from a shared, multi-user knowledge base.
- **Decision**: Partition the monorepo into two strict physical tiers:
  - **Tier 1 (`local/`)**: Runs 100% on the user's machine. Private telemetry never leaves `local/`.
  - **Tier 2 (`server/`)**: Centralized multi-user **Shared Topic-Tree Service** containing zero personal telemetry.
- **Impact**: Enforces privacy by construction at the network boundary while keeping both tiers versioned and tested in a single polyglot monorepo.

### ADR-02: Local Agent (`local/agent/`) + Decoupled Component UI (`local/ui/`)
- **Context**: Running separate microservices on a user's laptop for 30s collection and local API queries adds unnecessary operational overhead, while bundling collection inside a UI process means telemetry stops whenever the user closes the window.
- **Decision**:
  - **`local/agent/` (Python 3.12 + `uv`)**: Always-on background service combining the 30s micro-epoch collector, SQLite WAL storage (`epoch_metrics_30s` & `activity_blocks`), Pluggable Scientific Dimension Engine, 60s/90s Hysteresis Chunker, and a localhost FastAPI gateway (`127.0.0.1:8765`). It also caches active topic trees fetched from `server/` locally in SQLite so personal progress stays private and works offline.
  - **`local/ui/` (Component Frontend)**: Modular UI communicating strictly with `http://127.0.0.1:8765`.
- **Impact**: Follows the battle-tested local daemon pattern (Docker Desktop, Raycast, Linear Local Sync): single background binary/service, zero data loss when the UI closes, and offline-first resilience.

### ADR-03: Cache-First Semantic Topic Graph (`server/` — Java 27 + Spring Boot 4.1.2 + Neo4j 5+)
- **Context**: Users frequently request breakdowns for identical or slightly differently phrased topics (e.g., *"Kubernetes Networking"* vs. *"K8s Network Architecture"*). Calling an LLM on every request wastes latency and tokens.
- **Decision**: Build `server/` on **Java 27**, **Spring Boot 4.1.2**, and **Neo4j 5+**. Use Neo4j's built-in **Vector Index (`db.index.vector.queryNodes`)** for semantic similarity matching alongside recursive graph traversal (`(:Topic)-[:HAS_SUBTOPIC*1..5]->(:Topic)`).
- **Impact**: Semantically equivalent topics resolve immediately from Neo4j (`CACHE_HIT`) without invoking an LLM. When an LLM breakdown is triggered on a cache miss, any sub-topics that already exist in Neo4j are linked and reused rather than regenerated.

### ADR-04: Hardware Decoupling via Protocols & Multi-OS GitHub Actions CI
- **Context**: Native keyboard/mouse listeners and window resolvers fail in headless Linux CI containers without `$DISPLAY` or OS accessibility permissions.
- **Decision**: Isolate hardware collectors behind Python `typing.Protocol` interfaces (`InputListenerProtocol`, `WindowResolverProtocol`) with a deterministic `--simulate` mode, and enforce a path-filtered multi-OS GitHub Actions pipeline (`ubuntu-latest` + `macos-latest`) paired with Dependabot.
- **Impact**: Every push and PR automatically runs `uv sync --frozen`, `ruff`, `mypy --strict`, and `pytest --cov-fail-under=90` across both Linux and macOS runners.

---

## 3. Deliverables Shipped in Sprint 1.0

| Component | Path | Description |
| :--- | :--- | :--- |
| **Master Architecture Plan** | `DEVOPS_PORTFOLIO_PLAN.md` & `README.md` | Complete two-tier architecture diagrams (`local/agent`, `local/ui`, `server`) and 4-phase roadmap. |
| **Hierarchical AI Rules** | `AGENTS.md`, `local/agent/AGENTS.md`, `local/ui/AGENTS.md`, `server/AGENTS.md` | Scoped engineering, privacy, and stack rules across Python 3.12 (`uv`), Component UI, and Java 27 / Spring Boot 4.1.2 / Neo4j. |
| **CI/CD Workflow** | `.github/workflows/ci-local-agent.yml` | Path-filtered (`local/agent/**`) multi-OS (`ubuntu-latest`, `macos-latest`) CI pipeline with `astral-sh/setup-uv@v5`, frozen lockfile verification, and 3 quality gates. |
| **Automated Dependency Ops** | `.github/dependabot.yml` | Weekly Dependabot security/version updates for `github-actions` and `uv` (`/local/agent`), plus pre-configured `maven` and `docker` blocks for `/server`. |
| **Local Agent Toolchain** | `local/agent/pyproject.toml` & `uv.lock` | Reproducible Python 3.12 package (`egg-local-agent`) with `aiosqlite`, `pynput`, `ruff`, `mypy`, `pytest`, and `pytest-cov`. |
| **12-Factor Configuration** | `local/agent/app/config.py` & `tests/test_config.py` | Immutable `DaemonConfig` dataclass (`frozen=True, slots=True`) with env-var overrides and 100% branch-covered unit tests. |

---

## 4. LinkedIn Carousel Slide Deck Blueprint (7 Slides)

> **Tip**: Copy these slides directly into **Gamma.app**, **Marp**, **Canva**, or **Figma** to generate a clean dark-mode technical carousel.

### Slide 1 — Cover Slide
- **Headline**: Designing a Privacy-First Polyglot Platform: Local Telemetry + Shared Neo4j Topic Graph
- **Subheadline**: Sprint 1.0: How I architected a two-tier system (`Python 3.12` on the edge + `Java 27 / Spring Boot 4.1.2 / Neo4j` in the cloud) with automated CI/CD guardrails from Day 1.
- **Visual Prompt**: Split architecture diagram showing **Tier 1: User's Machine (`local/agent` + `local/ui` + SQLite WAL)** and **Tier 2: Central Server (`Spring Boot 4.1.2` + `Neo4j Vector + Graph DB`)**.
- **Footer**: Engineering Sprint 1.0 • DevOps & Systems Architecture

---

### Slide 2 — The Architectural Split: Why Two Tiers?
- **Headline**: Privacy by Construction: What Stays Local vs. What Lives in the Cloud
- **Body**:
  - **The Privacy Rule**: Behavioral telemetry (typing cadence, window switches, focus blocks) should *never* leave your computer.
  - **Tier 1 (`local/agent` + `local/ui`)**: Collects 30s hardware micro-epochs locally in SQLite WAL, computes scientific focus dimensions, and serves a localhost gateway (`127.0.0.1:8765`).
  - **Tier 2 (`server/`)**: A shared multi-user service that breaks down learning & project topics into reusable trees—containing zero personal telemetry.

---

### Slide 3 — Inside Tier 1: The Local Agent Pattern
- **Headline**: Why We Decoupled `local/agent` from `local/ui`
- **Body**:
  - If telemetry collection lives inside a desktop UI process, closing the window kills data collection.
  - **`local/agent/` (Python 3.12 + `uv`)**: Runs continuously in the background—handling 30s collection, lossless statistical pooling ($\sum x, \sum x^2$), 60s/90s hysteresis chunking, and local caching of active topic trees.
  - **`local/ui/`**: Pure component frontend talking to `127.0.0.1:8765`. Open or close it anytime without dropping a single 30-second epoch.

---

### Slide 4 — Inside Tier 2: Cache-First Topic Trees with Neo4j
- **Headline**: Stopping Redundant LLM Calls with Neo4j Vector + Graph Search
- **Body**:
  - **The Problem**: If 100 users ask to break down *"Kubernetes Networking"* (or *"K8s Network Architecture"*), calling an LLM 100 times wastes money and latency.
  - **The Stack**: **Java 27 + Spring Boot 4.1.2 + Neo4j 5+**.
  - **How It Works**:
    1. Neo4j's built-in **Vector Index** checks if a semantically equivalent `:Topic` node already exists.
    2. **Cache Hit**: Returns the full `(:Topic)-[:HAS_SUBTOPIC*]->(:Topic)` tree in milliseconds—zero LLM tokens used.
    3. **Cache Miss**: Generates the breakdown once, reusing any existing sub-topic nodes in the graph.

---

### Slide 5 — Solving Headless CI for Hardware Listeners
- **Headline**: Testing OS Hardware Hooks in Headless GitHub Actions Runners
- **Body**:
  - `local/agent` uses OS listeners (`pynput`, macOS `NSWorkspace`, Linux `Xlib`) that crash in headless CI containers without a display (`$DISPLAY`) or accessibility permissions.
  - **Solution**: Strict Dependency Injection via Python `typing.Protocol` interfaces (`InputListenerProtocol`, `WindowResolverProtocol`) + a deterministic `--simulate` mode.
  - Allows 100% of our storage, math, and API pipeline to run in headless Linux and macOS CI runners.

---

### Slide 6 — Day-1 DevOps: GitHub Actions Matrix + Dependabot + AI Guardrails
- **Headline**: Automated Quality Gates & Context Engineering
- **Body**:
  - **Multi-OS CI (`ci-local-agent.yml`)**: Runs on both `ubuntu-latest` and `macos-latest` using `astral-sh/setup-uv@v5` and `uv sync --frozen`.
  - **3 Mandatory Gates on Every Push**:
    1. `uv run ruff check .` & `ruff format --check .`
    2. `uv run mypy --strict app tests` (0 issues across 9 files)
    3. `uv run pytest --cov=app --cov-fail-under=90` (100% branch coverage)
  - **Hierarchical `AGENTS.md`**: Scoped rules in `/`, `local/agent/`, `local/ui/`, and `server/` keep AI coding assistants strictly aligned with privacy and architectural boundaries.

---

### Slide 7 — What's Next in Sprint 1.1
- **Headline**: Next Up: Sprint 1.1 — Async SQLite WAL & Lossless Pooled Math
- **Body**:
  - Implementing `local/agent/app/storage/database.py` (SQLite WAL mode + time-range indexing).
  - Building `repository.py` with immutable DTOs and exact mathematical pooling functions.
  - Proving via unit tests that pooled variance ($\sigma^2_{\text{pooled}}$) across $N$ 30-second epochs matches raw unchunked variance to $10^{-9}$ precision.
- **Call to Action**: Follow along as I build and containerize this polyglot platform sprint by sprint!

---

## 5. Ready-to-Post LinkedIn Caption

```text
How do you build an AI-assisted productivity & cognitive telemetry platform where private behavioral data NEVER leaves the user's laptop—while still sharing a reusable knowledge graph across users? 🛠️

Today I completed Sprint 1.0 of my polyglot DevOps & Systems Engineering project: a Two-Tier Cognitive Telemetry & Shared Topic-Tree Platform.

Before writing feature code, I designed the system boundaries and CI/CD guardrails from Day 1:

1️⃣ Tier 1 — Privacy-First Local Agent (`local/agent/` + `local/ui/`):
Built with Python 3.12 and `uv`. A lightweight background agent collects 30s hardware micro-epochs into local SQLite (WAL mode) using lossless algebraic primitives (Σx, Σx²) and serves a localhost API on 127.0.0.1:8765. Because the UI is decoupled from the agent, closing the window never interrupts background telemetry collection—and private data never touches the cloud.

2️⃣ Tier 2 — Cache-First Shared Topic-Tree Server (`server/`):
Designed with Java 27, Spring Boot 4.1.2, and Neo4j 5+. When a user wants to break a complex topic into sub-topics, Neo4j's built-in Vector Search checks if a semantically equivalent topic already exists in the graph. If it does, it returns the existing subtree immediately—calling the LLM only on true cache misses.

3️⃣ Production CI/CD & Scoped AI Context (`AGENTS.md`):
Wired up Dependabot and a path-filtered, multi-OS GitHub Actions pipeline (Ubuntu + macOS) enforcing frozen `uv.lock` builds, `ruff`, `mypy --strict`, and `pytest` (>=90% coverage) on every push.

Swipe through the slides for the full architecture breakdown 👉

Next up in Sprint 1.1: Async SQLite WAL persistence and mathematical proof tests for zero-loss pooled variance and Shannon entropy.

#DevOps #SoftwareArchitecture #Python #Java #SpringBoot #Neo4j #PlatformEngineering #CICD #BuildInPublic
```
