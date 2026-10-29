# Scoped Rules: `local/ui` (Component-Based Local Client Interface)

You are working inside `local/ui/`, the user-facing local application frontend for `Microservice-egg`.

## 1. Architecture & Communication Rules

- **Single Local Gateway**: `local/ui/` communicates strictly with `local/agent/` over `http://127.0.0.1:8765/api/v1/`. Never connect directly from the UI to external telemetry servers; `local/agent/` acts as the local gateway that fetches shared topic trees from `server/` and caches the user's active topic steps locally in SQLite.
- **Component-Driven Design**: Build all views using modular, reusable UI components (e.g., interactive Topic Tree node graph components, Activity Block timeline cards, and non-judgmental cognitive telemetry indicators).
- **Decoupled Lifecycle**: Closing the `local/ui/` window must never terminate `local/agent/` background telemetry collection.
