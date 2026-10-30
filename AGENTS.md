# Global Monorepo & Product Context (`Microservice-egg` — EGG)

You are working inside `Microservice-egg`, the polyglot monorepo for **EGG** (*"Don't crack under pressure"*). Always adhere to these global product, privacy, and architectural boundaries, and load the scoped `AGENTS.md` inside your active working folder before executing a task.

## 1. Product & UX Brief (The "Why")

**EGG** is an AI-assisted task decomposition and passive cognitive telemetry platform designed to help people with **ADHD and executive dysfunction** translate overwhelming goals into manageable steps and plan around their real energy levels.

- **Team & Attribution**:
  - **Pontus Olsson**: DevOps, Backend & System Architecture (`local/agent/`, `server/`, CI/CD).
  - **Julia Ermanbriks**: UX Research, ADHD Executive Function Brief, Brand Identity, and Mobile-First UI Design (`local/ui/`).
- **Neuropsychological Foundation**: Grounded in Dr. Russell A. Barkley's **4 Prefrontal Cortex Executive Circuits**:
  1. **What** (Working Memory & Planning)
  2. **When** (Time Blindness & Sequencing)
  3. **Why** (Emotional Regulation & Task Initiation)
  4. **Who** (Self-Awareness of Energy & Fatigue)
- **The 3 Core Pillars of EGG** (*"Your plan should be based on your worst days"*):
  1. **Pillar 1 — Cognitive Load Management**: Break overwhelming goals into concrete, bite-sized steps (`server/` Neo4j Shared Topic-Tree + calm, low-clutter `local/ui/`).
  2. **Pillar 2 — Time & Flow Management**: Passively estimate effort and time spent in 30-second micro-epochs (`local/agent/`) without requiring manual timers or logging friction.
  3. **Pillar 3 — Emotional & Energy Regulation**: Passively detect fatigue and cognitive strain 100% locally (`local/agent/` Scientific Dimension Engine) so users can adapt their plan on low-energy days.

## 2. Scoped Folder Architecture (Separation of Concerns)

To keep context focused on the active task, detailed toolchain commands, schemas, and workflows live in each folder's `AGENTS.md`:

- **[`local/agent/AGENTS.md`](local/agent/AGENTS.md) (Python 3.12 + `uv`)**: Always-on local background service. Owns 30s hardware/window micro-epoch ingestion, SQLite WAL persistence, the 4-Dimension Scientific Engine, the 60s/90s Activity Block Chunker, the localhost API (`127.0.0.1:8765`), and Python quality gates (`ruff`, `mypy --strict`, `pytest`).
- **[`local/ui/AGENTS.md`](local/ui/AGENTS.md) (Mobile-First Frontend)**: User-facing interface designed by Julia Ermanbriks. Communicates strictly with `local/agent/` (`127.0.0.1:8765`).
- **[`server/AGENTS.md`](server/AGENTS.md) (Java 27 + Spring Boot 4.1.2 + Neo4j)**: Central Shared Topic-Tree Service. Uses Neo4j graph persistence and vector similarity search to reuse existing broken-down topic trees across users and invoke the LLM ("word unzipper") only on cache misses.
- **[`reports/AGENTS.md`](reports/AGENTS.md) (Scientific Sprint Reports & LinkedIn Slides)**: Local-only directory (`reports/`). Owns the end-of-sprint IMRaD Scientific Paper template, the interactive developer walkthrough routine, and the automated slide generator (`reports/generate_slides.py`).

## 3. Global Privacy, Security & Git Hygiene Invariants

1. **Private Telemetry Never Leaves `local/`**: Behavioral telemetry (`epoch_metrics_30s`, `activity_blocks`) and personal task states stay 100% on the user's device. `server/` only handles universal topic-tree queries.
2. **Zero Content Capture**: Never capture, log, buffer, or store key characters, key codes, scancodes, clipboard text, window titles, file names, or URLs anywhere in any service.
3. **Localhost Binding Only**: Local services (`local/agent/`, `local/ui/`) must bind strictly to `127.0.0.1` by default—never `0.0.0.0` on host interfaces.
4. **Headless CI Readiness**: Every service must run deterministically in headless Linux/macOS CI runners and Docker containers without requiring a physical display (`$DISPLAY`), accessibility permissions, or physical input hardware.
5. **Atomic Git Hygiene**: Keep commits atomic and scoped to a single service or infrastructure concern. Never commit `reports/` (local-only), `.env*` secrets, `.venv/`, `__pycache__/`, `target/`, `node_modules/`, or `*.db*` SQLite files.
