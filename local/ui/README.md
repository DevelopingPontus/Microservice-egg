# `local/ui` — Standalone Mobile-First ADHD Client Interface

User-facing local frontend for **EGG** (*"Don't crack under pressure"*), grounded in **Julia Ermanbriks' UX Research & Brand Identity**. Connects to the local telemetry gateway (`http://127.0.0.1:8765/api/v1/state`) to adapt task step sizes to real-time cognitive energy.

---

## 1. UX Principles & Brand Palette

- **Design for the Worst Days**: Calm, low-clutter, progressive views that prevent working-memory overload (*What*), time blindness (*When*), task paralysis (*Why*), and unrecognized fatigue (*Who*).
- **Brand Palette**:
  - **Cobalt Blue (`#1648CE`)**: Primary brand anchor for structure and navigation.
  - **Warm Eggshell Cream (`#F5F2EB`)**: Soft, low-glare background surface.
  - **Yolk Gold (`#F2B705`)**: Encouraging highlight for active steps and energy awareness.

---

## 2. Internal Feature Packages

`local/ui/` combines 3 internal feature packages inside the root `App` shell:

1. **`energy_bar/`**: Gentle cognitive capacity indicators and blameless recovery prompts driven by `local/telemetry` strain scores.
2. **`focus_timeline/`**: Passive work-category blocks (`producing`, `consuming`, `communicating`, `idle`) and active session timers without manual logging friction.
3. **`task_tree/`**: Bite-sized step cards with one-tap "unzip" actions to decompose overwhelming goals into micro-steps.
