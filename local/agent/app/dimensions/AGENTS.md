# `local/agent/app/dimensions/` Context & Interface Contract

> **Pluggable Scientific Dimension Engine for ADHD cognitive telemetry & executive-load scoring.**

---

## 1. What, Why, When & How

### What (Scope)
This package houses the **Pluggable Dimension Pattern** (`BaseDimension` and `DimensionRegistry`). It transforms losslessly pooled telemetry metrics (`PooledTelemetryMetrics`) into normalized scientific scores and actionable ADHD cognitive indicators.

### Why (Rationale)
1. **Open-Closed Principle (OCP)**: New scientific dimensions, neuropsychological models, or scoring algorithms can be added without modifying the core ingestion or persistence pipelines.
2. **Translating Observability to Executive Function**: Raw metrics (such as keystroke intervals or window dwell times) are meaningless to an end-user until converted into the 4 Barkley-aligned scientific dimensions:
   - **Temporal Dynamics**: How long the user sustains focus without cognitive stalls.
   - **Attentional Fragmentation**: Whether attention is stable or thrashing between apps.
   - **Psychomotor Mechanics**: Physical cognitive strain and motor fatigue inferred from key rhythm variability.
   - **Circadian & Cumulative Load**: Fatigue accumulated over hours of unbroken screen time and post-prandial dips.

### When (Lifecycle)
- Evaluated when an `ActivityBlock` is sealed (every 60s/90s) by the Chunker.
- Evaluated on-demand by FastAPI endpoints (`/api/v1/summary/today`) to generate user-facing focus reports.

### How (Mechanics)
- Subclasses implement `BaseDimension.evaluate(metrics: PooledTelemetryMetrics) -> DimensionResult`.
- Dimensions register automatically with `DimensionRegistry`.
- When called, the registry runs all active dimensions, bundling results into a comprehensive cognitive profile for the activity block.

---

## 2. Interface Contract (Inputs & Outputs)

```mermaid
flowchart LR
    subgraph Inputs["Inbound Aggregations (Inputs)"]
        POOL["app.storage.repository.PooledTelemetryMetrics<br/>• duty_cycle<br/>• shannon_entropy<br/>• iki_cv<br/>• correction_ratio"]
        TIME["Time Context<br/>• wall_start / wall_end"]
    end

    subgraph Dimensions["app/dimensions/"]
        REG["DimensionRegistry"]
        D1["TemporalDynamicsDimension"]
        D2["AttentionalFragmentationDimension"]
        D3["PsychomotorMechanicsDimension"]
        D4["CircadianLoadDimension"]
        REG --> D1 & D2 & D3 & D4
    end

    subgraph Outputs["Downstream Consumer (Outputs)"]
        RES["DimensionResult / Block Insights<br/>• Normalized Scores (0.0 - 1.0)<br/>• Blameless Systems Insights<br/>• SRE Focus Golden Signals"]
    end

    POOL --> REG
    TIME --> REG
    REG --> RES
```

### Inputs (Parameters)
- `PooledTelemetryMetrics` instance containing pooled metrics across the target time window.
- Epoch/block time bounds (`timestamp_start`, `timestamp_end`).

### Outputs (Exported Public API)
- `BaseDimension`: Abstract base class enforcing the dimension evaluation interface.
- `DimensionRegistry`: Registry managing registered dimensions and running batch evaluations.
- `DimensionResult`: Immutable dataclass containing score, confidence, and human-readable blameless insight.
- The 4 Core Dimension classes:
  - `TemporalDynamicsDimension`
  - `AttentionalFragmentationDimension`
  - `PsychomotorMechanicsDimension`
  - `CircadianLoadDimension`

### Invariants & Safety Guarantees
- **Blameless SRE Framing**: Insights must never use guilt-inducing language (e.g. *"You were distracted"*). Instead, provide objective systems telemetry (e.g. *"High application thrashing detected—task scope may need resizing"*).
- **Statistically Guarded**: Psychomotor scores must yield `confidence = 0.0` if `is_psychomotor_valid` is `False` ($N < 10$).

---

## 3. File Inventory

| File | Primary Exports & Classes | Responsibility |
| :--- | :--- | :--- |
| [`__init__.py`](./__init__.py) | Dimension exports | Public boundary for the pluggable dimension engine. |
| *(Sprint 2.1 planned)* `base.py` | `BaseDimension`, `DimensionResult` | Abstract class and result structure for all scientific scoring. |
| *(Sprint 2.1 planned)* `registry.py` | `DimensionRegistry` | Pluggable container for auto-discovery and batch evaluation. |
| *(Sprint 2.1 planned)* `temporal.py` | `TemporalDynamicsDimension` | Duty cycle, continuous focus duration, and micro-pause rate. |
| *(Sprint 2.1 planned)* `attentional.py` | `AttentionalFragmentationDimension` | Shannon entropy ($H$) and context-switches per minute. |
| *(Sprint 2.1 planned)* `psychomotor.py` | `PsychomotorMechanicsDimension` | Inter-keystroke interval CV and correction keystroke ratio. |
| *(Sprint 2.1 planned)* `circadian.py` | `CircadianLoadDimension` | Time-of-day slotting, post-prandial dip, and unbroken screen strain. |

---

## 4. Subfolder Routing
*This package has no child subdirectories. It consumes pooled telemetry from [`app/storage/`](../storage/AGENTS.md) and provides evaluated insights to [`app/engine/`](../engine/AGENTS.md) and [`app/api/`](../api/AGENTS.md).*
