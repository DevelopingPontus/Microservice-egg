# Service Rules: `telemetry/api` (Dimensions, Chunker & REST API)

These rules apply specifically to `telemetry/api/` and extend the root `Microservice-egg/AGENTS.md` standards. Refer to `/Users/pontus/projects/Microservice-egg/telemetry_engine_detailed_plan.pdf` for full specifications.

## 1. Domain Responsibility & Boundary

- `telemetry/api` consumes 30-second micro-epochs from `epoch_metrics_30s`, orchestrates the **4 Scientific Dimensions**, executes the **60s/90s Activity Block Chunker**, persists sealed blocks into `activity_blocks`, and serves the **FastAPI REST interface** on `127.0.0.1:8765`.
- Never import hardware hooks (`pynput`, `NSWorkspace`, `win32gui`, `Xlib`) inside `telemetry/api`.

## 2. Open-Closed Pluggable Dimension Contract

- Every telemetry dimension must subclass `BaseDimension` (`app/dimensions/base.py`) and register with `DimensionRegistry` (`app/dimensions/registry.py`).
- The chunker, database schema (`dimensions_json`, `triggered_insights_json`), and FastAPI endpoints must remain completely agnostic to specific dimension implementations so new dimensions can be added without modifying storage or routing code.
- **Empirical Objectivity**: `InsightPrompt` outputs must contain strictly objective behavioral observations, validated scientific mechanisms/citations, and low-friction adjustments—never speculative emotional or mood inferences.

## 3. Exact Mathematical Formulations

1. **Temporal Dynamics**:
   - $\text{Duty Cycle} = \frac{\sum \text{active\_seconds}}{\sum \text{total\_epoch\_seconds}}$
2. **Attentional Fragmentation**:
   - Merge `dwell_distribution_json` maps across the target window, compute proportions $p_k = \frac{T_k}{T_{\text{total}}}$, and calculate Shannon Entropy: $H = -\sum_{k} p_k \ln(p_k)$ (handling $p_k = 0$ safely as $0$).
3. **Psychomotor Mechanics**:
   - Correction Ratio: $R_{\text{corr}} = \frac{\sum K_{\text{del}}}{\sum K_{\text{total}}}$
   - Pooled Rhythm Stability ($CV$):
     $$\mu_{\text{pooled}} = \frac{\sum \text{iki\_sum\_ms}}{\sum N_{\text{iki}}}, \quad \sigma_{\text{pooled}}^2 = \max\left(0.0, \frac{\sum \text{iki\_sum\_sq\_ms}}{\sum N_{\text{iki}}} - \mu_{\text{pooled}}^2\right), \quad CV = \frac{\sqrt{\sigma_{\text{pooled}}^2}}{\mu_{\text{pooled}}}$$
4. **Circadian & Cumulative Load**:
   - Flag post-prandial alertness dip when local hour $\in [13, 15)$.
   - Track cumulative daily work duration without a $>30\text{ min}$ ($1800\text{ s}$) idle reset.

## 4. Activity Block Debounce Hysteresis

- **Transient Interruption ($<60\text{ s}$)**: Switching away from the primary process for less than 60 seconds must be absorbed into the active block and logged only as internal context switches.
- **Definitive Block Boundary ($\ge 90\text{ s}$)**: Switching to a different primary application or remaining idle for $\ge 90\text{ seconds}$ seals the current block at the transition timestamp, aggregates all registered dimensions, evaluates scientific insights, and commits the `ActivityBlock` to SQLite.
