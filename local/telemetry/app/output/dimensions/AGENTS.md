# `local/telemetry/app/output/dimensions/` Context & Interface Contract

> **Pluggable 4-Dimension Scientific Engine: Temporal Dynamics, Attentional Fragmentation, Psychomotor Mechanics, and Session Uptime.**

---

## 1. Scope & Responsibilities

Evaluates pooled sliding window telemetry across 4 independent physical dimensions registered in `DimensionRegistry`:

1. **[`temporal.py`](./temporal.py) (`TemporalDynamicsDimension`)**: Duty cycle ($T_{\text{active}} / T_{\text{total}}$), continuous focus duration, micro-pause frequency, and active reading detection (scrolling).
2. **[`attentional.py`](./attentional.py) (`AttentionalFragmentationDimension`)**: Application Shannon entropy ($H = -\sum p_k \ln p_k$), primary process dwell share ($p_{\max}$), and context switches per minute.
3. **[`psychomotor.py`](./psychomotor.py) (`PsychomotorMechanicsDimension`)**: Exact pooled Inter-Keystroke Interval Coefficient of Variation ($CV = \sigma_{\text{pooled}} / \mu_{\text{pooled}}$) and backspace/delete correction ratio, guarded by `is_psychomotor_valid` ($N \ge 10$).
4. **[`uptime.py`](./uptime.py) (`SessionUptimeDimension`)**: Continuous active load uptime, fatigue ceilings, and recovery break detection.

---

## 2. File Inventory

| File | Primary Exports | Responsibility |
| :--- | :--- | :--- |
| [`base.py`](./base.py) | `BaseDimension`, `DimensionContext`, `DimensionRegistry`, `clamp_score` | Abstract base plugin contract, input context builder, and deterministic registry. |
| [`temporal.py`](./temporal.py) | `TemporalDynamicsDimension` | Dimension 1: Pacing, duty cycle, and reading vs. stalling modality. |
| [`attentional.py`](./attentional.py) | `AttentionalFragmentationDimension` | Dimension 2: Window dispersion (Shannon entropy) and switch rate. |
| [`psychomotor.py`](./psychomotor.py) | `PsychomotorMechanicsDimension` | Dimension 3: Keystroke cadence variability (IKI CV) and correction friction. |
| [`uptime.py`](./uptime.py) | `SessionUptimeDimension` | Dimension 4: Continuous session duration and fatigue thresholds. |
| [`__init__.py`](./__init__.py) | `create_default_registry` and all dimension classes | Clean package facade. |
