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

## 1. Executive Summary

In Sprint 1.0, we designed and set up the project structure and automated DevOps pipeline for **`Microservice-egg`**—a **Cognitive Telemetry & Shared Topic-Tree Platform**.

Before jumping into feature code, we solved four practical engineering problems:
1. **How do we keep personal telemetry on the user's computer while sharing broken-down learning/work topics across users on a server?**
2. **How do we make sure closing the UI doesn't stop background telemetry collection?**
3. **How can the server reuse topic breakdowns when two users search for the same thing using different words?**
4. **How do we test hardware listeners in GitHub Actions cloud runners that don't have a keyboard or monitor?**

---

## 2. Key Architectural & DevOps Decisions (ADRs)

### ADR-01: Two-Tier Privacy-Split Monorepo (`local/` vs. `server/`)
- **Context**: Personal telemetry (typing cadence, window switches, in-progress work) should never leave the user's computer, while factual topic trees broken down by an LLM can be shared by everyone.
- **Decision**: Split the monorepo into **`local/`** (runs on the user's machine) and **`server/`** (central shared topic service).
- **Impact**: Keeps private data 100% local while saving LLM costs and response time on shared topics.

### ADR-02: Local Background Agent (`local/agent/`) Separate from UI (`local/ui/`)
- **Context**: If telemetry collection runs inside the UI, closing the window stops data collection.
- **Decision**: Run `local/agent/` (Python 3.12 + `uv`) as an independent background service with a localhost API (`127.0.0.1:8765`), and keep `local/ui/` as a separate frontend talking to it over HTTP.
- **Impact**: `local/agent/` keeps collecting telemetry and storing local progress even when the UI is closed.

### ADR-03: Cache-First Topic Graph (`server/` — Java 27 + Spring Boot 4.1.2 + Neo4j 5+)
- **Context**: An LLM acts like a "word unzipper" that expands a topic into a tree of sub-topics. Calling the LLM again when another user searches for the same topic in slightly different words wastes money and time.
- **Decision**: Use **Neo4j 5+** with **Vector Embeddings** in `server/`. Compare the *meaning* of a search using vector similarity, and traverse Neo4j's nested graph relations (`:HAS_SUBTOPIC`) to return existing topic trees.
- **Impact**: Reuses previously defined topics immediately without calling the LLM.

### ADR-04: Swappable Collector Interfaces (`Protocol` + Factory) & Day-1 CI/CD
- **Context**: GitHub Actions cloud servers have no physical keyboard, mouse, or display.
- **Decision**: Use a Factory pattern + Python `typing.Protocol` interfaces so we can swap between real OS listeners and simulated (`--simulate`) listeners, backed by `uv.lock`, Dependabot, and GitHub Actions CI.
- **Impact**: Automated linting, strict type checking, and tests run reliably on every push.

---

## 3. Deliverables Shipped in Sprint 1.0

| Component | Path | Description |
| :--- | :--- | :--- |
| **Master Architecture Plan** | `DEVOPS_PORTFOLIO_PLAN.md` & `README.md` | Two-tier architecture diagrams (`local/agent`, `local/ui`, `server`) and 4-phase roadmap. |
| **Hierarchical AI Rules** | `AGENTS.md`, `local/agent/AGENTS.md`, `local/ui/AGENTS.md`, `server/AGENTS.md` | Scoped engineering, privacy, and stack rules across Python 3.12 (`uv`), Component UI, and Java 27 / Spring Boot 4.1.2 / Neo4j. |
| **CI/CD Workflow** | `.github/workflows/ci-local-agent.yml` | Path-filtered (`local/agent/**`) multi-OS (`ubuntu-latest`, `macos-latest`) CI pipeline with `uv sync --frozen` and 3 quality gates. |
| **Automated Dependency Ops** | `.github/dependabot.yml` | Weekly Dependabot updates for `github-actions`, `uv`, `maven`, and `docker`. |
| **Local Agent Toolchain** | `local/agent/pyproject.toml` & `uv.lock` | Reproducible Python 3.12 package (`egg-local-agent`) with `aiosqlite`, `pynput`, `ruff`, `mypy`, `pytest`, and `pytest-cov`. |
| **12-Factor Configuration** | `local/agent/app/config.py` & `tests/test_config.py` | Immutable `DaemonConfig` dataclass (`frozen=True, slots=True`) with env-var overrides and 100% branch-covered unit tests. |

---

## 4. Developer Walkthrough (`What / Why / How` in My Own Words)

### Part 1: Splitting `local/` (`agent` + `ui`) and `server/`
- **What**: A two-part architecture with a **local side** (`local/agent` + `local/ui`) on the user's computer and a **server side** (`server/`) in the cloud.
- **Why**: Privacy and a better product. Personal data (telemetry and in-progress work) stays on the user's computer and never leaves their environment. And because `local/agent` is a background service separate from `local/ui`, it keeps running even if the user closes the UI window. Meanwhile, the server handles factual topics broken down by an LLM—if a topic was already defined by someone else, the server doesn't need to call the LLM again, saving cost and improving speed.
- **How**: Each component runs independently and communicates through HTTP requests (`local/ui` talks to `local/agent` on localhost `127.0.0.1:8765`, and `local/agent` fetches topic trees from `server/` and saves active progress locally in SQLite).

### Part 2: Using Neo4j + Vector Embeddings as a Shared "Word Unzipper"
- **What**: A **Java 27 + Spring Boot 4.1.2** backend using **Neo4j** as both a graph database and vector store for topic nodes.
- **Why**: I like to think of an LLM as a **"word unzipper"**—you give it a topic, and it unzips it into a tree of sub-topics. Once a topic is unzipped, we shouldn't pay the LLM to unzip it again just because another user phrased their search slightly differently. Also, topic trees are deeply nested relations, which is exactly what a graph database is built for.
- **How**: When a user searches for a topic, we turn the search into a **vector embedding** (numbers representing its *meaning* rather than exact spelling). If someone searches for the same thing using different words, the meaning coordinates match and point to the same `:Topic` node in Neo4j, which returns the linked sub-topic tree right away.

### Part 3: 30-Second Telemetry Blocks & Cloud Testing with a Factory Pattern
- **What**: Collecting telemetry in **30-second blocks** of raw math components, and using a **Factory pattern + Protocol interface ("swappable plugs")** for the hardware listeners.
- **Why**:
  1. Collecting every 30 seconds instead of saving every single keystroke or pre-calculating every dimension is much more balanced for storage and calculations—we store the raw components ($\sum x, \sum x^2$, count, app time) needed to calculate our 4 scientifically backed work dimensions across any timeframe later.
  2. Cloud CI runners (like GitHub Actions) don't have keyboards or screens, so real OS listeners would crash in the cloud.
- **How**: Every 30 seconds, the in-memory buffer summarizes the raw math components into a single SQLite row and resets. For testing in the cloud, our collector factory swaps out the real OS listener for a simulated (`--simulate`) listener that implements the exact same `Protocol` interface.

### Part 4: Reliable Development with `uv`, `uv.lock`, GitHub Actions & Dependabot
- **What**: A CI pipeline in GitHub Actions, Dependabot, scoped `AGENTS.md` files, and Python package management with `uv` (`pyproject.toml` + `uv.lock`).
- **Why**: To develop reliably without pushing breaking commits, keep security vulnerabilities handled automatically, and make sure every machine runs the exact same library versions.
- **How**:
  - `pyproject.toml` works like Maven's `pom.xml` to list our dependencies, while `uv.lock` is auto-generated and stores the exact versions and security hashes of every library—if any library's content changes, the hash won't match and `uv` alerts us.
  - On every push, GitHub Actions installs from `uv.lock` and runs linting (`ruff`), strict type checking (`mypy`), and unit tests (`pytest`).
  - `AGENTS.md` files keep the AI workflow structured and secure inside each folder.

---

## 5. LinkedIn Carousel Slide Deck (6 Slides — `What / Why / How` Format)

> **Note**: Written directly from the Sprint 1.0 walkthrough in a clean, straightforward **What / Why / How** structure.

### Slide 1 — Cover Slide
- **Headline**: Sprint 1.0: Designing a Privacy-First Telemetry & Shared Topic-Tree App
- **Subheadline**: How I structured my polyglot monorepo (`Python` locally + `Java / Spring Boot / Neo4j` on the server) before writing feature code.
- **Visual Prompt**: Simple diagram showing **User's Computer (`local/ui` $\leftrightarrow$ `local/agent` + SQLite)** talking over HTTP to **Central Server (`Spring Boot` + `Neo4j`)**.
- **Footer**: Sprint 1.0 Walkthrough • What, Why & How

---

### Slide 2 — Question 1: Splitting Local vs. Server (and Agent vs. UI)
- **Headline**: 1. Why Split the App into Local (`agent` + `ui`) and Server?
- **WHAT**:
  - A **local part** (`local/agent` + `local/ui`) that runs on the user's computer, and a **server part** (`server/`) that shares broken-down learning/work topics.
- **WHY**:
  - **Privacy**: Personal telemetry and in-progress data never leave the user's environment.
  - **Always-On Collection**: Because `local/agent` is a background service separate from `local/ui`, it keeps running even if the UI window is closed.
  - **Cost & Speed**: The server only holds factual topics broken down by an LLM. If a topic was already defined, we don't need to call the LLM again.
- **HOW**:
  - The components run independently and communicate over HTTP (`local/ui` $\leftrightarrow$ `local/agent` on localhost, and `local/agent` $\leftrightarrow$ `server/`).

---

### Slide 3 — Question 2: Neo4j + Vector Search ("The LLM Word Unzipper")
- **Headline**: 2. Treating the LLM as a "Word Unzipper" with Neo4j
- **WHAT**:
  - A **Java 27 + Spring Boot 4.1.2** server using **Neo4j** and **vector embeddings** to store and look up topic trees.
- **WHY**:
  - An LLM works like a **"word unzipper"** when generating a tree of sub-topics from a single subject.
  - If two users search for the same topic using different words, we want to reuse the existing tree instead of calling the LLM twice.
  - Topic breakdowns are deeply nested relationships, which fits a graph database naturally.
- **HOW**:
  - We convert the user's search into a **vector embedding** based on its *meaning* rather than exact text.
  - Different phrasings with the same meaning point to the same topic node in Neo4j and return its nested sub-topics immediately.

---

### Slide 4 — Question 3: 30-Second Telemetry Blocks & Cloud Testing
- **Headline**: 3. Collecting 30s Math Blocks & Testing Hardware in the Cloud
- **WHAT**:
  - A 30-second telemetry buffer that saves raw math components to SQLite, paired with "swappable" hardware listeners.
- **WHY**:
  - Saving data in **30-second blocks** (instead of every single input or pre-calculated scores) is much more balanced for storage and lets us calculate 4 scientifically backed work dimensions later.
  - Cloud CI servers don't have keyboards or screens, so real hardware listeners would crash during automated tests.
- **HOW**:
  - We use a **Factory pattern + Protocol interface** (like a swappable plug): on a real computer it uses real OS input listeners, and in cloud tests (`--simulate`) it swaps in a simulated listener.

---

### Slide 5 — Question 4: Reliable DevOps (`uv.lock`, CI Pipeline & Dependabot)
- **Headline**: 4. Preventing Breaking Commits with CI, Dependabot & `uv.lock`
- **WHAT**:
  - GitHub Actions CI pipeline, Dependabot security updates, scoped `AGENTS.md` rules, and `uv` package management.
- **WHY**:
  - To catch broken code before it gets merged, keep dependency vulnerabilities handled automatically, and make sure every environment runs the exact same library versions.
- **HOW**:
  - `pyproject.toml` works like Maven's `pom.xml` for listing dependencies, while `uv.lock` is generated with security hashes—if a library's content changes, the hash won't match.
  - Every push triggers GitHub Actions to run linting (`ruff`), type checking (`mypy`), and tests (`pytest`), while `AGENTS.md` keeps the AI workflow structured and secure.

---

### Slide 6 — Next Up: Sprint 1.1
- **Headline**: Next Step: Sprint 1.1 — SQLite Storage & Math Pooling
- **WHAT**:
  - Building `database.py` and `repository.py` inside `local/agent/` and writing unit tests to verify the math pooling.
- **WHY**:
  - To prove that combining multiple 30-second blocks produces the exact same statistical results as calculating over raw inputs.
- **HOW**:
  - Async SQLite in WAL mode (`aiosqlite`) + `pytest` verification tests.

---

## 6. Ready-to-Post LinkedIn Caption (Authentic Voice)

```text
Just finished Sprint 1.0 of my new project—setting up the architecture and CI/CD pipeline before diving into the feature code. 🛠️

Here is the What, Why, and How behind the setup:

1️⃣ Splitting Local (`agent` + `ui`) and Server:
Personal data like telemetry should never leave the user's computer, so that all stays local. I also separated the background `agent` from the `ui` so telemetry collection keeps working even if the UI is closed.
The server side only handles factual topic trees broken down by an LLM. If a topic has already been defined by another user, the server reuses it without calling the LLM again—saving cost and improving responsiveness.

2️⃣ Using an LLM as a "Word Unzipper" + Neo4j:
I like to think of an LLM as a word unzipper when it breaks a topic down into a tree of sub-topics. On the server (Java 27 + Spring Boot + Neo4j), we use vector embeddings so we compare the *meaning* of a search instead of the exact spelling. If two people search for the same thing in different words, it points to the same topic node in Neo4j—which is built to handle nested graph relations.

3️⃣ 30-Second Telemetry Blocks & Swappable Listeners for Cloud Testing:
Instead of storing every single input or pre-calculating every work dimension, the local agent collects raw math components in 30-second blocks to keep storage and calculations balanced. And since GitHub Actions cloud runners don't have keyboards or screens, we use a Factory pattern with a Protocol interface to swap in simulated inputs during cloud tests.

4️⃣ Reliable DevOps (`uv.lock`, GitHub Actions & Dependabot):
To avoid pushing breaking commits, GitHub Actions runs linting (`ruff`), strict type checks (`mypy`), and tests (`pytest`) on every push, while Dependabot handles dependency updates. For Python packages, `pyproject.toml` acts like Maven's `pom.xml`, and `uv.lock` locks the exact versions and hashes so we know immediately if any library content changes.

Swipe through the slides for the full breakdown 👉 Next up in Sprint 1.1: SQLite WAL storage and testing the pooled math calculations!

#SoftwareEngineering #DevOps #Python #Java #SpringBoot #Neo4j #CICD #BuildInPublic #JuniorDeveloper
```
