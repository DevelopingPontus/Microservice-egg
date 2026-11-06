# `local/telemetry/app/intake/` Context & Interface Contract

> **Intake Pillar: Converges raw OS/hardware signals (`collectors/`) and sliding window accumulation (`engine/`) into structured telemetry for evaluation.**

---

## 1. What, Why, When & How

### What (Scope)

`app/intake/` is the **Write/Ingestion Pillar** of the Hourglass Architecture. It contains two isolated child packages:

1. **[`collectors/`](./collectors/AGENTS.md)**: OS-native (`PynputInputListener`, `NativeWindowResolver`) and deterministic headless (`SyntheticInputListener`, `SyntheticWindowResolver`) signal collectors.
2. **[`engine/`](./engine/AGENTS.md)**: Thread-safe in-memory `SlidingWindowBuffer`.

### Why (Rationale)

- **Convergence to Raw Material**: All high-frequency hardware and window signals are sanitized and accumulated inside `intake/` before being evaluated as normalized, privacy-safe records.
- **Strict Isolation**: `collectors/` and `engine/` never import each other directly; they communicate strictly through `app/common/` protocols (`InputTickSinkProtocol`, `InputListenerProtocol`, `WindowResolverProtocol`) wired by `app/service.py`.

---

## 2. Subfolder Routing

- [`collectors/`](./collectors/AGENTS.md): Hardware keyboard/mouse hooks and foreground window process sanitization.
- [`engine/`](./engine/AGENTS.md): In-memory `SlidingWindowBuffer` maintaining monotonic counters and recent slices.
