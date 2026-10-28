# Engineering Sprint Reports & LinkedIn Slide Decks (`reports/`)

This directory tracks the chronological engineering progress of `Microservice-egg` (`Cognitive Telemetry & Activity Block Platform`).

Each report is structured like an internal **Engineering Sprint Review / Architecture Decision Record (ADR)** combined with a **ready-to-render LinkedIn Carousel Slide Deck** (compatible with Marp, Gamma, Canva, or PDF export).

## Report Naming Convention

```text
reports/
├── README.md
├── 01-sprint-1.0-monorepo-and-devops-guardrails.md
├── 02-sprint-1.1-sqlite-wal-and-pooled-math.md
└── ...
```

## Standard Report Structure

Every sprint report includes:
1. **Sprint Metadata & Engineering Metrics**: Date, scope, test count, line/branch coverage %, static typing status, and dependencies locked.
2. **Problem Statement & Architectural Decisions**: Why specific patterns (e.g., Domain-Scoped Monorepo, Python `Protocol` DI, SQLite WAL algebraic primitives) were chosen over alternatives.
3. **What Was Shipped**: Concrete files, interfaces, and verification outputs.
4. **Slide-by-Slide Carousel Script (6–8 Slides)**: Concise, high-impact slide headlines, bullet points, and visual/diagram prompts tailored for LinkedIn technical audiences.
5. **LinkedIn Post Copy**: A ready-to-publish narrative post with technical hooks and hashtags.
