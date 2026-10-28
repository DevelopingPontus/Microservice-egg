# Service Rules: `telemetry/daemon` (Epoch Ingestion Service)

These rules apply specifically to `telemetry/daemon/` and extend the root `Microservice-egg/AGENTS.md` standards. Refer to `epoch_telemetry_plan.md` in this directory for full component specifications.

## 1. Domain Responsibility & Boundary

- `telemetry/daemon` is strictly responsible for **30-second micro-epoch ingestion** into the `epoch_metrics_30s` table in SQLite (`WAL` mode).
- Do **not** put high-level 60s/90s Activity Block chunking, FastAPI HTTP routes, or scientific insight evaluation in this service—those belong in `telemetry/api/`.

## 2. Mathematical & Storage Invariants

1. **No Raw Event Ticks in SQLite**: High-frequency keystroke deltas and mouse events must exist only in ephemeral RAM inside `EpochBuffer` (`app/engine/buffer.py`) and be cleared on every 30-second harvest.
2. **Preserve Lossless Algebraic Primitives**: Never store pre-divided averages or standard deviations alone in `epoch_metrics_30s`. Always store:
   - `iki_count` ($N$), `iki_sum_ms` ($\sum x$), and `iki_sum_sq_ms` ($\sum x^2$) so downstream consumers can compute exact pooled variance ($\sigma_{\text{pooled}}^2 = \frac{\sum x^2}{N} - \mu_{\text{pooled}}^2$) and Coefficient of Variation ($CV$) across arbitrary time windows.
   - `dwell_distribution_json` (`{"process": seconds}`) and `context_switch_count` so downstream consumers can compute exact Shannon entropy ($H = -\sum p_k \ln p_k$).
   - `active_seconds` and `micro_pause_count` ($1.0\text{--}5.0\text{ s}$ gaps).
3. **IKI Outlier Filtering**: Inter-keystroke intervals $> 5000\text{ ms}$ must be dropped from psychomotor IKI calculations (they represent pauses/idle gaps, not typing biomechanics).

## 3. Hardware Decoupling & Dependency Injection

- All OS-specific listeners (`pynput`, `NSWorkspace`, `win32gui`, `Xlib`) **must** implement the protocols defined in `app/collectors/protocols.py` (`InputListenerProtocol`, `WindowResolverProtocol`).
- `EpochBuffer`, `Scheduler`, and `Service` must depend only on those `Protocol` interfaces, never on concrete OS libraries directly.
- Always maintain working `SyntheticInputListener` and `SyntheticWindowResolver` implementations so `uv run pytest` and `python run_daemon.py --simulate` work in headless Docker containers and CI pipelines.
