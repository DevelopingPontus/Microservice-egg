# `Microservice-egg` — Cognitive Telemetry & Shared Topic-Tree Platform

> **Privacy-by-Construction Local Telemetry Engine (`Python`) & Shared Semantic Topic-Tree Service (`Java / Spring Boot / Neo4j`) for Executive Function.**

[![CI — Local Agent](https://github.com/DevelopingPontus/Microservice-egg/actions/workflows/ci-local-agent.yml/badge.svg)](https://github.com/DevelopingPontus/Microservice-egg/actions/workflows/ci-local-agent.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Toolchain: uv](https://img.shields.io/badge/uv-managed-DE5FE9?logo=astral&logoColor=white)](https://docs.astral.sh/uv/)
[![Java 27 / Spring Boot 4.1.2](https://img.shields.io/badge/Spring%20Boot-4.1.2-6DB33F?logo=springboot&logoColor=white)](https://spring.io/projects/spring-boot)
[![Graph DB: Neo4j](https://img.shields.io/badge/Neo4j-Graph%20%2B%20Vector-008CC1?logo=neo4j&logoColor=white)](https://neo4j.com/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-261230?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)
[![Typed: mypy --strict](https://img.shields.io/badge/types-mypy%20--strict-blue)](https://mypy-lang.org/)

---

## 1. Platform Overview & Two-Tier Architecture

`Microservice-egg` is a polyglot platform designed to help knowledge workers—particularly individuals with ADHD—manage cognitive load, break down complex topics into actionable steps, and gain empirical self-insight into their work patterns.

The repository is structured at the root into **`local/`** (running on the user's computer) and **`server/`** (running as a centralized multi-user service) along a strict **privacy and compute boundary**:

```mermaid
flowchart TD
    subgraph Local["LOCAL TIER: /local (Runs on User's Computer — 100% Private)"]
        UI["local/ui (Component Frontend)<br/>• Interactive Topic Tree & Focus Views<br/>• Can open & close freely"]
        Agent["local/agent (Python 3.12 Background Service)<br/>• 30s Hardware/Window Protocol Collectors<br/>• 60s/90s Activity Block Chunker<br/>• 4 Pluggable Scientific Dimensions<br/>• Localhost FastAPI Gateway (127.0.0.1:8765)"]
        SQLite[("Local SQLite WAL<br/>• epoch_metrics_30s<br/>• activity_blocks<br/>• cached_topic_trees")]
        UI <-->|127.0.0.1:8765| Agent
        Agent <--> SQLite
    end

    subgraph Server["SERVER TIER: /server (Centralized Multi-User Service)"]
        Spring["server (Java 27 + Spring Boot 4.1.2)<br/>• Topic Tree REST API<br/>• Semantic Vector Matcher<br/>• Recursive LLM Decomposition (Cache Miss Only)"]
        Neo4j[("Shared Neo4j 5+ Graph DB<br/>• (:Topic)-[:HAS_SUBTOPIC]->(:Topic)<br/>• Built-in Vector Similarity Index")]
        Spring <--> Neo4j
    end

    Agent <-->|HTTPS Topic Query / Sync| Spring
```

### Architectural Tiers

| Directory | Stack | Responsibility | Status |
| :--- | :--- | :--- | :--- |
| **`/local/agent`** | Python 3.12, `uv`, `aiosqlite`, `pynput`, `FastAPI` | Always-on background daemon collecting 30s epochs, chunking 60s/90s activity blocks, evaluating scientific dimensions, caching active topic trees in local SQLite, and serving `127.0.0.1:8765`. | In Progress (`Phase 1–2`) |
| **`/local/ui`** | Component Frontend | User-facing local interface consuming `127.0.0.1:8765` for viewing focus telemetry and interacting with broken-down topic trees. | Planned (`Phase 4`) |
| **`/server`** | Java 27, Spring Boot 4.1.2, Spring Data Neo4j, Neo4j 5+ | Central Shared Topic-Tree Service. Uses Neo4j vector similarity search to match semantically equivalent topics and reuse existing topic subtrees without redundant LLM calls. | Planned (`Phase 3`) |

---

## 2. Core Engineering & DevOps Pillars

1. **Uncompromised Privacy by Construction (`local/agent`)**:
   - **Telemetry Never Leaves the Machine**: All 30s epochs and activity blocks stay strictly in local SQLite on the user's computer.
   - **Zero Keystroke Content**: Key characters, key codes, scancodes, and clipboard text are never inspected, buffered, or stored.
   - **Executable Sanitization**: Window polling resolves strictly to executable/bundle names (`Code.exe`, `iTerm2`, `firefox`)—stripping all window titles, file names, and URLs.
2. **Cache-First Graph & Vector Topic Resolution (`server`)**:
   - Topic breakdowns are stored in a shared **Neo4j** graph database (`(:Topic)-[:HAS_SUBTOPIC]->(:Topic)`).
   - Using Neo4j Vector Indexes, if a user requests a topic phrased slightly differently from an existing topic, the Spring Boot service resolves it to the existing `:Topic` node and returns its tree immediately without calling an LLM.
3. **Hardware Decoupling via Python Protocols (`--simulate`)**:
   - Hardware hooks (`pynput`, `NSWorkspace`, `win32gui`, `Xlib`) fail inside headless Linux Docker containers and CI runners.
   - All collectors implement `InputListenerProtocol` and `WindowResolverProtocol`, enabling deterministic synthetic workloads in Docker Compose and GitHub Actions.
4. **Lossless Algebraic Pooling**:
   - Every 30-second epoch stores `iki_count` ($N$), `iki_sum_ms` ($\sum x$), and `iki_sum_sq_ms` ($\sum x^2$) so downstream queries compute exact pooled variance ($\sigma^2_{\text{pooled}} = \frac{\sum x^2}{N} - \mu^2_{\text{pooled}}$) across arbitrary time windows without distortion.

---

## 3. Repository Documentation

- **[`DEVOPS_PORTFOLIO_PLAN.md`](./DEVOPS_PORTFOLIO_PLAN.md)**: Full system architecture (`local/` + `server/`) and 4-phase implementation roadmap.
- **[`local/agent/epoch_telemetry_plan.md`](./local/agent/epoch_telemetry_plan.md)**: Detailed technical specification for the 30s epoch ingestion engine.
- **[`telemetry_engine_detailed_plan.pdf`](./telemetry_engine_detailed_plan.pdf)**: Scientific literature grounding, `BaseDimension` specification, and localhost API blueprint.
- **[`reports/`](./reports/README.md)**: Chronological Engineering Sprint Reports & Architecture Decision Records (ADRs):
  - [Sprint 1.0 — Monorepo Architecture, Privacy-by-Construction & DevOps Guardrails](./reports/01-sprint-1.0-monorepo-and-devops-guardrails.md)

---

## 4. Quickstart (`local/agent`)

```bash
cd local/agent

# 1. Install locked dependencies via uv
uv sync

# 2. Run the mandatory verification loop
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict app tests
uv run pytest --cov=app --cov-fail-under=90
```
