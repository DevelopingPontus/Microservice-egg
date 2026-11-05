# `local/agent/app/intake/` Context & Interface Contract

> **Intake Pillar: Converges raw OS/hardware signals (`collectors/`) and 30s/60s/90s accumulation (`engine/`) into normalized raw material for `app/storage/`.**

---

## 1. What, Why, When & How

### What (Scope)

`app/intake/` is the **Write/Ingestion Pillar** of the Hourglass Architecture. It contains two isolated child packages:

1. **[`collectors/`](./collectors/AGENTS.md)**: OS-native (`PynputInputListener`, `NativeWindowResolver`) and deterministic headless (`SyntheticInputListener`, `SyntheticWindowResolver`) signal collectors.
2. **[`engine/`](./engine/AGENTS.md)**: Thread-safe 30s `EpochBuffer`, drift-free monotonic `EpochScheduler`, 60s/90s hysteresis `ActivityBlockChunker`, and `SREObservabilityRecorder`.

### Why (Rationale)

- **Convergence to Raw Material**: All high-frequency hardware and window signals are sanitized and accumulated inside `intake/` before being flushed as normalized, privacy-safe records into `app/storage/`.
- **Strict Isolation**: `collectors/` and `engine/` never import each other directly; they communicate strictly through `app/common/` protocols (`InputTickSinkProtocol`, `InputListenerProtocol`, `WindowResolverProtocol`) wired by `app/service.py`.

---

## 2. Subfolder Routing

- [`collectors/`](./collectors/AGENTS.md): Hardware keyboard/mouse hooks and foreground window process sanitization.
- [`engine/`](./engine/AGENTS.md): 30s `EpochBuffer`, monotonic `EpochScheduler`, 60s/90s `ActivityBlockChunker`, and SRE Golden Signals.
