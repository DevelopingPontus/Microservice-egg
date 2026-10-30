# Scoped Rules: `local/ui/` (Mobile-First ADHD-Friendly Client Interface)

You are working inside `local/ui/`, the user-facing local application frontend for **EGG** (*"Don't crack under pressure"*), grounded in **Julia Ermanbriks' UX Research & Brand Identity**.

## 1. UX Design Principles (ADHD & Executive Function)

- **Design for the Worst Days**: Users with ADHD often experience working-memory overload (*What*), time blindness (*When*), task paralysis (*Why*), and unrecognised fatigue (*Who*). Views must remain calm, low-clutter, and progressive—never overwhelm the user with dense telemetry tables or guilt-inducing red alerts.
- **Brand Palette & Visual Language**:
  - **Cobalt Blue (`#1648CE`)**: Primary brand anchor for clear structure and navigation.
  - **Warm Eggshell Cream (`#F5F2EB`)**: Soft, low-glare background surface.
  - **Yolk Gold (`#F2B705`)**: Warm, encouraging highlight for active steps, progress bars, and energy awareness.
- **Mobile-First & Component-Driven**: Build modular, reusable UI components optimized for mobile-first scannability (interactive Topic Tree step cards, passive Activity Block timelines, and gentle energy/effort indicators).

## 2. Architecture & Communication Rules

- **Single Local Gateway**: `local/ui/` communicates strictly with `local/agent/` over `http://127.0.0.1:8765/api/v1/`. Never connect directly from the UI to external servers; `local/agent/` proxies and caches shared topic trees from `server/` in local SQLite.
- **Decoupled Lifecycle**: Closing or refreshing `local/ui/` must never interrupt `local/agent/` background telemetry collection.
