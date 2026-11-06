# EGG (`Microservice-egg`) — *"Don't crack under pressure"*

> **AI-Assisted Task Decomposition & Passive Local Cognitive Telemetry Platform for ADHD Executive Function Support.**

[![CI — Local Agent](https://github.com/DevelopingPontus/Microservice-egg/actions/workflows/ci-local-agent.yml/badge.svg)](https://github.com/DevelopingPontus/Microservice-egg/actions/workflows/ci-local-agent.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Toolchain: uv](https://img.shields.io/badge/uv-managed-DE5FE9?logo=astral&logoColor=white)](https://docs.astral.sh/uv/)
[![Java 27 / Spring Boot 4.1.2](https://img.shields.io/badge/Spring%20Boot-4.1.2-6DB33F?logo=springboot&logoColor=white)](https://spring.io/projects/spring-boot)
[![Graph DB: Neo4j](https://img.shields.io/badge/Neo4j-Graph%20%2B%20Vector-008CC1?logo=neo4j&logoColor=white)](https://neo4j.com/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-261230?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)
[![Typed: mypy --strict](https://img.shields.io/badge/types-mypy%20--strict-blue)](https://mypy-lang.org/)

---

## 1. Product Brief & Neuropsychological Foundation (The "Why")

Standard productivity tools often fail users with ADHD because manual planning and timer logging add mental friction when executive function is already taxed. Grounded in Dr. Russell A. Barkley's **4 Prefrontal Cortex Executive Circuits** (*What, When, Why, Who*), **EGG** is built around **3 Core Pillars** (*"Your plan should be based on your worst days"*):

| Core Pillar | Brain Circuit | User Problem | Engineering Solution in `Microservice-egg` |
| :--- | :--- | :--- | :--- |
| **1. Cognitive Load** | *What Circuit* (Working Memory) | Big goals overwhelm working memory and cause task paralysis. | **`server/` Shared Topic-Tree Graph** (LLM "word unzipper" + Neo4j vector cache) & low-clutter **Mobile-First UI** (`local/ui`). |
| **2. Time & Flow** | *When Circuit* (Time Blindness) | Time blindness makes estimating task duration and effort difficult. | **`local/telemetry/` Sliding Windows** passively linking time to actual cognitive effort via OpenTelemetry. |
| **3. Emotional Weight & Energy** | *Why & Who Circuits* (Emotion & Self-Awareness) | Manual timer/fatigue logging causes burnout on low-energy days. | **4 Scientific SRE Dimensions** computed 100% locally on the user's device to estimate strain passively. |

### Team & Attribution

- **Pontus Olsson**: DevOps, Backend & System Architecture (`local/telemetry/`, `server/`, CI/CD).
- **Julia Ermanbriks**: UX Research, ADHD Executive Function Brief, Brand Identity, and Mobile-First UI Design (`local/ui/`).

---

## 2. Two-Tier Architecture (`local/` vs. `server/`)

The monorepo is structured at the root into **`local/`** (running on the user's computer — 100% private) and **`server/`** (running as a centralized multi-user service) along a strict **privacy and compute boundary**:

```mermaid
flowchart TD
    subgraph Local["LOCAL TIER: /local (Runs on User's Computer — 100% Private)"]
        UI["local/ui (Component Frontend)<br/>• Interactive Topic Tree & Focus Views<br/>• Can open & close freely"]
        Telemetry["local/telemetry (Python 3.12 SRE Service)<br/>• Stateless Hardware/Window Collectors<br/>• Sliding Window Engine<br/>• 4 Pluggable Scientific Dimensions<br/>• OpenTelemetry + Prometheus (127.0.0.1:8765)"]
        Stack[("Local Observability Stack<br/>• Prometheus & Grafana<br/>• Loki Logs & Tempo Traces")]
        UI <-->|127.0.0.1:8765| Telemetry
        Telemetry <--> Stack
    end

    subgraph Server["SERVER TIER: /server (Centralized Multi-User Service)"]
        Spring["server (Java 27 + Spring Boot 4.1.2)<br/>• Topic Tree REST API<br/>• Semantic Vector Matcher<br/>• Recursive LLM Decomposition (Cache Miss Only)"]
        Neo4j[("Shared Neo4j 5+ Graph DB<br/>• (:Topic)-[:HAS_SUBTOPIC]->(:Topic)<br/>• Built-in Vector Similarity Index")]
        Spring <--> Neo4j
    end

    Telemetry <-->|HTTPS Topic Query / Sync| Spring
```

### Architectural Tiers

| Directory | Stack | Responsibility | Status |
| :--- | :--- | :--- | :--- |
| **`/local/telemetry`** | Python 3.12, `uv`, `pynput`, `FastAPI`, OTel, Prometheus, Loki, Tempo, Grafana | Self-contained host telemetry daemon & SRE observability stack exporting to OTLP and serving `127.0.0.1:8765`. | In Progress (`Phase 1–2`) |
| **`/local/ui`** | Component Frontend | User-facing local interface consuming `127.0.0.1:8765` for viewing focus telemetry and interacting with broken-down topic trees. | Planned (`Phase 4`) |
| **`/server`** | Java 27, Spring Boot 4.1.2, Spring Data Neo4j, Neo4j 5+ | Central Shared Topic-Tree Service. Uses Neo4j vector similarity search to match semantically equivalent topics and reuse existing topic subtrees without redundant LLM calls. | Planned (`Phase 3`) |

---

## 3. Core Engineering & DevOps Guardrails

1. **Uncompromised Privacy by Construction (`local/telemetry`)**:
   - **Telemetry Never Leaves the Machine**: Private telemetry remains strictly on the user's computer.
   - **Zero Keystroke Content**: Key characters, key codes, scancodes, and clipboard text are never inspected, buffered, or stored.
   - **Executable Sanitization**: Window polling resolves strictly to executable/bundle names (`Code.exe`, `iTerm2`, `firefox`)—stripping all window titles, file names, and URLs.
2. **Cache-First Graph & Vector Topic Resolution (`server`)**:
   - Topic breakdowns unpacked by the LLM ("word unzipper") are stored in a shared **Neo4j** graph database (`(:Topic)-[:HAS_SUBTOPIC]->(:Topic)`).
   - Using Neo4j Vector Indexes, if a user requests a topic phrased slightly differently from an existing topic, the Spring Boot service resolves it to the existing `:Topic` node and returns its tree immediately without redundant LLM calls.
3. **Hardware Decoupling via Python Protocols (`--synthetic`)**:
   - Hardware hooks (`pynput`, `NSWorkspace`, `win32gui`, `Xlib`) fail inside headless Linux Docker containers and CI runners.
   - All collectors implement `InputListenerProtocol` and `WindowResolverProtocol`, enabling deterministic synthetic workloads in Docker Compose and GitHub Actions.
4. **Lossless Algebraic Pooling**:
   - Every sliding window stores `iki_count` ($N$), `iki_sum_ms` ($\sum x$), and `iki_sum_sq_ms` ($\sum x^2$) so downstream queries compute exact pooled variance ($\sigma^2_{\text{pooled}} = \frac{\sum x^2}{N} - \mu^2_{\text{pooled}}$) across arbitrary time windows without distortion.

---

## 4. Architecture & Scoped Context Documentation

- **[`AGENTS.md`](./AGENTS.md)**: Global product brief, neuropsychological foundation, and privacy/security invariants.
- **[`local/telemetry/AGENTS.md`](./local/telemetry/AGENTS.md)**: Scoped architecture, physical SRE dimensions, and quality gates for the telemetry service.
- **[`local/ui/AGENTS.md`](./local/ui/AGENTS.md)**: Mobile-first ADHD design principles and local API contract (`127.0.0.1:8765`).
- **[`server/AGENTS.md`](./server/AGENTS.md)**: Shared Topic-Tree service (`Java 27` + `Spring Boot 4.1.2` + `Neo4j` Vector Search) specification.
- **[`DEVOPS_PORTFOLIO_PLAN.md`](./DEVOPS_PORTFOLIO_PLAN.md)**: Full system architecture (`local/` + `server/`) and 4-phase implementation roadmap.

---

## 5. Quickstart (`local/telemetry`)

```bash
cd local/telemetry

# 1. Install locked dependencies via uv
uv sync

# 2. Run the complete stack (Docker observability containers + host telemetry daemon)
uv run run.py
```

# 2. Run the mandatory verification loop
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict app tests
uv run pytest --cov=app --cov-fail-under=90
```
