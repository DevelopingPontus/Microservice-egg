"""Stateless work-category & application-category rule classifier for `app/analysis/workflow/`."""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from app.collector import PooledTelemetryMetrics

EDITOR_TERMINAL_KEYWORDS: tuple[str, ...] = (
    "code",
    "cursor",
    "terminal",
    "iterm",
    "warp",
    "alacritty",
    "kitty",
    "wezterm",
    "zed",
    "vim",
    "nvim",
    "emacs",
    "idea",
    "pycharm",
    "webstorm",
    "goland",
    "clion",
    "rider",
    "xcode",
    "sublime",
    "powershell",
    "cmd",
    "zsh",
    "bash",
)

COMMS_APP_KEYWORDS: tuple[str, ...] = (
    "slack",
    "teams",
    "discord",
    "zoom",
    "mail",
    "outlook",
    "thunderbird",
    "messages",
    "telegram",
    "whatsapp",
    "signal",
    "webex",
    "meet",
    "skype",
)

BROWSER_VIEWER_KEYWORDS: tuple[str, ...] = (
    "firefox",
    "chrome",
    "safari",
    "arc",
    "brave",
    "edge",
    "opera",
    "vivaldi",
    "preview",
    "acrobat",
    "skim",
    "zathura",
    "evince",
    "okular",
    "obsidian",
    "notion",
)

ALL_WORK_CATEGORIES: tuple[str, ...] = (
    "producing",
    "consuming",
    "communicating",
    "navigating",
    "idle",
    "unclassified",
)


@dataclass(frozen=True, slots=True)
class WorkCategoryClassification:
    """Work category and label classification from the parallel Overview plan."""

    activity: str
    app_category: str
    time_block: str
    session_length_bucket: str
    device: str
    is_borderline: bool
    failed_rule: str
    keystroke_bucket: str
    switches_in_5m: int
    scroll_to_input_ratio: float


def classify_app_category(process_name: str) -> str:
    """Map a sanitized process basename to a non-sensitive application category."""
    lower = process_name.strip().lower()
    if not lower or lower in ("idle", "unknown"):
        return "system_other"
    if any(token in lower for token in COMMS_APP_KEYWORDS):
        return "comms"
    if any(token in lower for token in EDITOR_TERMINAL_KEYWORDS):
        return "editor_terminal"
    if any(token in lower for token in BROWSER_VIEWER_KEYWORDS):
        return "browser_viewer"
    return "system_other"


def resolve_time_block(hour: int) -> str:
    """Group an hour of the day [0..23] into a coarse diurnal time block."""
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 14:
        return "midday"
    if 14 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 22:
        return "evening"
    return "night"


def resolve_session_length_bucket(session_seconds: float) -> str:
    """Bucket focus session duration for low-cardinality Prometheus/Loki labels."""
    minutes = session_seconds / 60.0
    if minutes < 5.0:
        return "lt_5m"
    if minutes < 15.0:
        return "5m_15m"
    if minutes < 25.0:
        return "15m_25m"
    return "25m_plus"


def resolve_keystroke_bucket(keystrokes_per_min: float) -> str:
    """Bucket keystroke rate per minute for unclassified gap analysis in Loki."""
    if keystrokes_per_min <= 0.0:
        return "0_kpm"
    if keystrokes_per_min < 15.0:
        return "1_14_kpm"
    if keystrokes_per_min < 30.0:
        return "15_29_kpm"
    if keystrokes_per_min < 80.0:
        return "30_79_kpm"
    return "80_plus_kpm"


def classify_work_category(
    *,
    now: float,
    app_cat: str,
    kpm: float,
    spm: float,
    scroll_to_input_ratio: float,
    switches_5m: int,
    idle_seconds: float,
    focus_len_sec: float,
    metrics: PooledTelemetryMetrics,
    idle_threshold_seconds: float,
    navigating_switch_override_5m: int,
    producing_min_kpm: float,
    consuming_min_spm: float,
    device_label: str,
) -> WorkCategoryClassification:
    """Evaluate rules in strict order: idle -> comms -> consuming -> producing -> navigating."""
    dt_obj = datetime.datetime.fromtimestamp(now, tz=datetime.UTC)
    time_block = resolve_time_block(dt_obj.hour)
    session_bucket = resolve_session_length_bucket(focus_len_sec)
    key_bucket = resolve_keystroke_bucket(kpm)

    def _build(
        activity: str,
        *,
        is_borderline: bool = False,
        failed_rule: str = "none",
    ) -> WorkCategoryClassification:
        return WorkCategoryClassification(
            activity=activity,
            app_category=app_cat,
            time_block=time_block,
            session_length_bucket=session_bucket,
            device=device_label,
            is_borderline=is_borderline,
            failed_rule=failed_rule,
            keystroke_bucket=key_bucket,
            switches_in_5m=switches_5m,
            scroll_to_input_ratio=scroll_to_input_ratio,
        )

    is_empty_idle = (
        metrics.primary_process == "idle"
        and metrics.total_keystrokes == 0
        and metrics.total_mouse_clicks == 0
        and metrics.total_scroll_events == 0
        and metrics.duty_cycle == 0.0
    )
    if idle_seconds >= idle_threshold_seconds or is_empty_idle:
        return _build("idle")

    if switches_5m > navigating_switch_override_5m:
        return _build("navigating")

    if app_cat == "comms":
        return _build("communicating")

    if spm >= consuming_min_spm and kpm < producing_min_kpm:
        if kpm >= (producing_min_kpm * 0.90):
            return _build(
                "unclassified",
                is_borderline=True,
                failed_rule="consuming_borderline_keystroke_rate",
            )
        return _build("consuming")

    if kpm >= producing_min_kpm and app_cat in ("editor_terminal", "browser_viewer"):
        return _build("producing")

    if metrics.switches_per_minute >= 3.0 and metrics.primary_process_ratio < 0.65:
        return _build("navigating")

    failed = (
        "producing_below_keystroke_threshold"
        if app_cat == "editor_terminal"
        else "consuming_no_scroll_signal"
        if app_cat == "browser_viewer"
        else "no_category_rule_matched"
    )
    is_border = (0.80 * producing_min_kpm) <= kpm < producing_min_kpm
    return _build("unclassified", is_borderline=is_border, failed_rule=failed)
