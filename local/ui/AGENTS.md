# Scoped Rules: `local/ui/` (Mobile-First ADHD-Friendly Client Interface)

You are working inside `local/ui/`, the user-facing local application frontend for **EGG** (*"Don't crack under pressure"*), grounded in **Julia Ermanbriks' UX Research & Brand Identity**.

## 1. UX Design Principles (ADHD & Executive Function)

- **Design for the Worst Days**: Users with ADHD often experience working-memory overload (*What*), time blindness (*When*), task paralysis (*Why*), and unrecognised fatigue (*Who*). Views must remain calm, low-clutter, and progressive—never overwhelm the user with dense telemetry tables or guilt-inducing red alerts.
- **Brand Palette & Visual Language**:
  - **Cobalt Blue (`#1648CE`)**: Primary brand anchor for clear structure and navigation.
  - **Warm Eggshell Cream (`#F5F2EB`)**: Soft, low-glare background surface.
  - **Yolk Gold (`#F2B705`)**: Warm, encouraging highlight for active steps, progress bars, and energy awareness.
- **Mobile-First & Component-Driven**: Build modular, reusable UI components optimized for mobile-first scannability (interactive Topic Tree step cards, passive Activity Block timelines, and gentle energy/effort indicators).

## 2. Architecture, LCA Contracts & Communication Rules

- **Single Local Gateway**: `local/ui/` communicates strictly with `local/agent/` over `http://127.0.0.1:8765/api/v1/`. Never connect directly from the UI to external servers; `local/agent/` proxies and caches shared topic trees from `server/` in local SQLite.
- **Decoupled Lifecycle**: Closing or refreshing `local/ui/` must never interrupt `local/agent/` background telemetry collection.
- **LCA Crossroads Contracts (`common/`) + Feature Folders ("When vs. What")**:
  - **`common/` ("What do you want?")**: Shared TypeScript/UI data types, brand theme tokens (`#1648CE`, `#F5F2EB`, `#F2B705`), and API client interfaces.
  - **Feature Folders (`topic-tree/`, `activity-timeline/`, `energy-status/`)**: Isolated UI feature modules with zero sibling imports. They import shared types/tokens upward from `common/` without importing sibling feature folders.
  - **Root Container (`App` — "I'll say when")**: Top-level application view that wires data from the localhost API gateway into the feature views.
