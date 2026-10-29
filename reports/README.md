# Engineering Sprint Reports & LinkedIn Slide Decks (`reports/`)

This directory tracks the chronological engineering progress of `Microservice-egg` (`Cognitive Telemetry & Shared Topic-Tree Platform`).

Each report combines an **Engineering Sprint Review / Architecture Decision Record (ADR)** with an **Interactive Developer Walkthrough (`What / Why / How`)** that powers a **ready-to-render LinkedIn Carousel Slide Deck** written in the developer's authentic voice.

## Report Naming Convention

```text
reports/
├── README.md
├── 01-sprint-1.0-monorepo-and-devops-guardrails.md
├── 02-sprint-1.1-sqlite-wal-and-pooled-math.md
└── ...
```

## End-of-Sprint Routine (3 Steps)

1. **Step 1 — Technical Summary & Metrics**: The agent writes the technical sprint summary, verification metrics (`ruff`, `mypy --strict`, `pytest` coverage), and deliverables table.
2. **Step 2 — Interactive Walkthrough (One Part at a Time)**: The agent and user step through the sprint's core concepts one question at a time. The user explains each concept in their own words (asking questions where needed), and the agent helps structure their explanation into **What / Why / How**.
3. **Step 3 — Authentic LinkedIn Carousel & Post Copy**: Using the user's own explanations, analogies, and junior-developer perspective from Step 2, the agent updates the report with:
   - The **Structured Walkthrough Notes (`What / Why / How`)**.
   - A **LinkedIn Carousel Slide Deck** with **one slide per walkthrough question** structured explicitly into **What / Why / How** (plus a Cover slide and Next Steps slide).
   - A **LinkedIn Post Caption** that reads genuinely like the developer wrote it.
