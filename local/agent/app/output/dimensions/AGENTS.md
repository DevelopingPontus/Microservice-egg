# `local/agent/app/output/dimensions/` Context & Interface Contract

> **Pluggable 4-Dimension Scientific Engine: Temporal Dynamics, Attentional Fragmentation, Psychomotor Mechanics, and Circadian Load.**

---

## 1. Scope & Responsibilities

Evaluates pooled 30-second epochs across 4 independent scientific dimensions registered in `DimensionRegistry`:

1. **[`temporal.py`](./temporal.py) (`TemporalDynamicsDimension`)**: Duty cycle ($T_{\text{active}} / T_{\text{total}}$), continuous focus duration, micro-pause frequency, and active reading detection (scrolling).
2. **[`attentional.py`](./attentional.py) (`AttentionalFragmentationDimension`)**: Application Shannon entropy ($H = -\sum p_k \ln p_k$), primary process dwell share ($p_{\max}$), and context switches per minute.
3. **[`psychomotor.py`](./psychomotor.py) (`PsychomotorMechanicsDimension`)**: Exact pooled Inter-Keystroke Interval Coefficient of Variation ($CV = \sigma_{\text{pooled}} / \mu_{\text{pooled}}$) and backspace/delete correction ratio, guarded by `is_psychomotor_valid` ($N \ge 10$).
4. **[`circadian.py`](./circadian.py) (`CircadianLoadDimension`)**: Diurnal phase slotting, post-prandial dip ($13:00\text{--}15:00$), and cumulative unbroken active load without a $\ge 30\text{ min}$ recovery reset.

---

## 2. File Inventory

| File | Primary Exports | Responsibility |
| :--- | :--- | :--- |
| [`base.py`](./base.py) | `BaseDimension`, `DimensionContext`, `DimensionRegistry`, `clamp_score` | Abstract base plugin contract, input context builder, and deterministic registry. |
| [`temporal.py`](./temporal.py) | `TemporalDynamicsDimension` | Dimension 1: Pacing, duty cycle, and reading vs. stalling modality. |
| [`attentional.py`](./attentional.py) | `AttentionalFragmentationDimension` | Dimension 2: Window dispersion (Shannon entropy) and switch rate. |
| [`psychomotor.py`](./psychomotor.py) | `PsychomotorMechanicsDimension` | Dimension 3: Keystroke cadence variability (IKI CV) and correction friction. |
| [`circadian.py`](./circadian.py) | `CircadianLoadDimension`, `compute_continuous_load_minutes` | Dimension 4: Biological time-of-day window and cumulative load since last 30m reset. |
| [`__init__.py`](./__init__.py) | `create_default_registry` and all dimension classes | Clean package facade. |
