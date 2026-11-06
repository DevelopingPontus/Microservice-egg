# Global Monorepo & Product Context (`Microservice-egg` — EGG)

You are working inside `Microservice-egg`, the polyglot monorepo for **EGG** (*"Don't crack under pressure"*). Always adhere to these global product, privacy, and architectural boundaries, and load the scoped `AGENTS.md` inside your active working folder before executing a task.

## 1. Product & UX Brief (The "Why")

**EGG** is an AI-assisted task decomposition and passive cognitive telemetry platform designed to help people with **ADHD and executive dysfunction** translate overwhelming goals into manageable steps and plan around their real energy levels.

- **Team & Attribution**:
  - **Pontus Olsson**: DevOps, Backend & System Architecture (`local/telemetry/`, `server/`, CI/CD).
  - **Julia Ermanbriks**: UX Research, ADHD Executive Function Brief, Brand Identity, and Mobile-First UI Design (`local/ui/`).
- **Neuropsychological Foundation**: Grounded in Dr. Russell A. Barkley's **4 Prefrontal Cortex Executive Circuits**:
  1. **What** (Working Memory & Planning)
  2. **When** (Time Blindness & Sequencing)
  3. **Why** (Emotional Regulation & Task Initiation)
  4. **Who** (Self-Awareness of Energy & Fatigue)
- **The 3 Core Pillars of EGG** (*"Your plan should be based on your worst days"*):
  1. **Pillar 1 — Cognitive Load Management**: Break overwhelming goals into concrete, bite-sized steps (`server/` Neo4j Shared Topic-Tree + calm, low-clutter `local/ui/`).
  2. **Pillar 2 — Time & Flow Management**: Passively estimate effort and time spent in 30-second micro-epochs (`local/telemetry/`) without requiring manual timers or logging friction.
  3. **Pillar 3 — Emotional & Energy Regulation**: Passively detect fatigue and cognitive strain 100% locally (`local/telemetry/` Scientific Dimension Engine) so users can adapt their plan on low-energy days.
- **Core Philosophy — "SRE & Observability for the ADHD Brain"**:
  - EGG applies **DevOps and Site Reliability Engineering (SRE)** principles directly to human executive function:
    1. **Passive Observability Over Manual Logging**: Never ask an overloaded "server" (or brain) to manually log its own status; infer utilization (`Duty Cycle`), context-switch thrashing (`Shannon Entropy`), and error rates (`Psychomotor CV & Correction Ratio`) passively.
    2. **Blameless Postmortems**: Replace ADHD guilt and self-blame with objective systems analysis (e.g., *"Attention fragmented at 14:00 after 3 hours of unbroken load—let's resize the task"*).
    3. **Load Shedding & Auto-Scaling**: When cognitive capacity dips, dynamically break large tasks into smaller micro-steps via the Topic-Tree "word unzipper".
    4. **Alert Debouncing (60s/90s Hysteresis)**: Absorb brief $<60\text{s}$ excursions just like Prometheus alert `for:` windows to prevent fragmentation and alert fatigue.

## 2. Scoped Folder Architecture (Separation of Concerns)

To keep context focused on the active task, detailed toolchain commands, schemas, and workflows live in each folder's `AGENTS.md`:

- **[`.github/AGENTS.md`](.github/AGENTS.md) (CI/CD & Automation)**: GitHub Actions workflows, path-filtered PR gates, and Dependabot configuration.
- **[`local/AGENTS.md`](local/AGENTS.md) (Client Tier Umbrella)**: High-level boundary for the user's machine (`telemetry/` + `ui/`).
- **[`local/telemetry/AGENTS.md`](local/telemetry/AGENTS.md) (Python 3.12 + `uv`)**: Self-contained background service & containerized SRE observability suite. Owns rolling window ingestion, the 4-Dimension Physical SRE Engine, OTLP exporters, the localhost API (`127.0.0.1:8765`), and Python quality gates (`ruff`, `mypy --strict`, `pytest`).
  - *Child contracts:* [`app/`](local/telemetry/app/AGENTS.md) ([`common/`](local/telemetry/app/common/AGENTS.md), [`intake/`](local/telemetry/app/intake/AGENTS.md), [`output/`](local/telemetry/app/output/AGENTS.md)), [`tests/`](local/telemetry/tests/AGENTS.md).
- **[`local/ui/AGENTS.md`](local/ui/AGENTS.md) (Mobile-First Frontend)**: User-facing interface designed by Julia Ermanbriks. Communicates strictly with `local/telemetry/` (`127.0.0.1:8765`).
- **[`server/AGENTS.md`](server/AGENTS.md) (Java 27 + Spring Boot 4.1.2 + Neo4j)**: Central Shared Topic-Tree Service. Uses Neo4j graph persistence and vector similarity search to reuse existing broken-down topic trees across users and invoke the LLM ("word unzipper") only on cache misses.
- **[`reports/AGENTS.md`](reports/AGENTS.md) (Professional Sprint Reports & Roadmap Presentation Slides)**: Local-only directory (`reports/`). Owns the end-of-sprint professional IMRaD engineering paper and the automated roadmap/rationale slide generator (`reports/generate_slides.py`).

## 3. Global Privacy, Security & Git Hygiene Invariants

1. **Private Telemetry Never Leaves `local/`**: Behavioral telemetry and personal task states stay 100% on the user's device. `server/` only handles universal topic-tree queries.
2. **Zero Content Capture**: Never capture, log, buffer, or store key characters, key codes, scancodes, clipboard text, window titles, file names, or URLs anywhere in any service.
3. **Localhost Binding Only**: Local services (`local/telemetry/`, `local/ui/`) must bind strictly to `127.0.0.1` by default—never `0.0.0.0` on host interfaces.
4. **Headless CI Readiness**: Every service must run deterministically in headless Linux/macOS CI runners and Docker containers without requiring a physical display (`$DISPLAY`), accessibility permissions, or physical input hardware.
5. **Atomic Git Hygiene**: Keep commits atomic and scoped to a single service or infrastructure concern. Never commit `reports/` (local-only), `.env*` secrets, `.venv/`, `__pycache__/`, `target/`, `node_modules/`, or `*.db*` SQLite files.
6. **Markdown Linting & List Formatting (`MD032`)**: All Markdown documentation (`*.md`, `AGENTS.md`) must strictly adhere to `MD032 / blanks-around-lists`. Lists (bulleted or numbered) must always be preceded and followed by a blank line. Never attach a list directly adjacent to a heading (e.g. `### Heading\n- Item`), paragraph, or table without an empty line.
7. **Hourglass Data Architecture & LCA Crossroads Contracts ("When vs. What")**:
   - **Downward Control ("I'll say when")**: Each service has a single root supervisor (`service.py` in `local/telemetry/`, `TopicTreeService` in `server/`, `App` in `local/ui/`) that controls execution timing and wires child packages together.
   - **Upward Contracts ("What do you want?")**: Shared immutable data shapes (DTOs), configuration constants, and structural interfaces (`protocols`) live at the Lowest Common Ancestor Crossroads folder (`common/`). Leaf packages may import upward from `common/`, but `common/` must have zero I/O and zero imports from behavioral packages.
   - **Zero Sibling Behavioral Imports & Zero Middleman Pass-Throughs**: Behavioral leaf packages must never import from sibling packages or from the root supervisor. Backend data services (`local/telemetry/`, `server/`) organize behavioral packages into the self-documenting **Hourglass Layout**: `intake/` (raw signal/AI ingestion), `storage/` (raw material store: SQLite WAL or Neo4j Graph), and `output/` (value creation branches: scientific dimensions, REST APIs, metrics). Frontend UI (`local/ui/`) applies the same `common/` LCA rule with feature-scoped view folders.
