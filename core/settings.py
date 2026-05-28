"""
Centralized Settings — Global configuration singleton.

All tunable parameters live here. The Settings tab UI writes here,
and bot_engine / home_village / screen_reader read from here.
Persisted to JSON on every change.
"""

import json
import os
import threading

_SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "profiles", "settings.json",
)

# ── Performance Presets ─────────────────────────────────────────────────
PRESETS: dict[str, dict] = {
    "ultra": {
        "label": "⚡ Ultra (Dedicated GPU)",
        "tick_interval": 0.5,
        "tap_delay_min": 0.01,
        "tap_delay_max": 0.03,
        "swipe_duration": 1800,
        "template_scales": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3],
        "ocr_workers": 4,
        "description": "Maximum speed. For powerful GPUs & fast CPUs.",
    },
    "high": {
        "label": "🔥 High (Good GPU)",
        "tick_interval": 0.8,
        "tap_delay_min": 0.02,
        "tap_delay_max": 0.05,
        "swipe_duration": 2200,
        "template_scales": [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2],
        "ocr_workers": 2,
        "description": "Fast & reliable. For mid-range GPUs.",
    },
    "medium": {
        "label": "💻 Medium (CPU Only)",
        "tick_interval": 1.0,
        "tap_delay_min": 0.03,
        "tap_delay_max": 0.08,
        "swipe_duration": 2500,
        "template_scales": [0.7, 0.8, 0.9, 1.0, 1.1],
        "ocr_workers": 2,
        "description": "Balanced. For strong CPUs without dedicated GPU.",
    },
    "low": {
        "label": "🐢 Low (Weak CPU)",
        "tick_interval": 1.5,
        "tap_delay_min": 0.05,
        "tap_delay_max": 0.12,
        "swipe_duration": 3000,
        "template_scales": [0.8, 0.9, 1.0, 1.1],
        "ocr_workers": 1,
        "description": "Safe & slow. For older / low-end hardware.",
    },
}

# ── Default Settings ────────────────────────────────────────────────────
_DEFAULTS: dict = {
    # Performance
    "preset": "medium",
    "tick_interval": 1.0,
    "tap_delay_min": 0.03,
    "tap_delay_max": 0.08,
    "swipe_duration": 2500,
    "template_scales": [0.7, 0.8, 0.9, 1.0, 1.1],
    "ocr_workers": 2,

    # Vision toggles
    "skip_loot_ocr": False,
    "skip_timer_ocr": False,
    "vision_troop_threshold": 0.35,
    "vision_ui_threshold": 0.80,
    "vision_building_threshold": 0.40,
    "vision_bb_card_threshold": 0.45,

    # OCR
    "ocr_min_interval": 2.0,

    # Deployment
    "hero_ability_delay": 3.0,
    "taps_per_swipe": 25,
    "deploy_jitter": 15,

    # Console
    "console_max_lines": 5000,
    "console_font_size": 12,
    "console_show_debug": True,

    # Smart Vision V2  (Red-Zone-Aware planner — opt-in per village)
    "v2_enabled_hv":      False,
    "v2_enabled_bb":      False,
    "v2_mode_hv":         "smart",        # smart | building | storage
    "v2_mode_bb":         "smart",
    "v2_target_hv":       "",
    "v2_target_bb":       "",
    "v2_zoom_out_steps":  2,
    "v2_decoration_wait": 5.0,
    "v2_show_briefing":   True,
    # Smart Vision V2 — CSR rule selection
    #   auto            → Orchestrator picks best rule for army+target.
    #   smart_default   → Plain widest-corridor long-press dump.
    #   air_attack      → Fan along the safest air corridor.
    #   ground_funnel   → 2-prong funnel + main wave.
    #   resource_raid   → Scout each storage, then dump.
    #   th_snipe        → Closest safe corridor to the target building.
    "v2_rule_hv":         "auto",
    "v2_rule_bb":         "auto",

    # Game Presence (ADB foreground app monitoring)
    #   game_package         → Android package name of Clash of Clans.
    #   game_check_interval  → seconds between periodic foreground checks
    #                          inside the bot loop (CHANGE HERE — clearly
    #                          named so the user can tune it freely).
    #   auto_launch_game     → if True the bot will try to launch the game
    #                          when it isn't focused.
    "game_package": "com.supercell.clashofclans",
    "game_check_interval": 60,
    "auto_launch_game": True,
}


class Settings:
    """Thread-safe global settings singleton."""

    _instance: "Settings | None" = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = dict(_DEFAULTS)
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        if os.path.isfile(_SETTINGS_FILE):
            try:
                with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                for k, v in saved.items():
                    if k in _DEFAULTS:
                        self._data[k] = v
            except Exception:
                pass

    def save(self) -> None:
        os.makedirs(os.path.dirname(_SETTINGS_FILE), exist_ok=True)
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default=None):
        return self._data.get(key, default if default is not None else _DEFAULTS.get(key))

    def set(self, key: str, value) -> None:
        self._data[key] = value

    def apply_preset(self, preset_name: str) -> None:
        preset = PRESETS.get(preset_name)
        if preset is None:
            return
        self._data["preset"] = preset_name
        for k in ("tick_interval", "tap_delay_min", "tap_delay_max",
                   "swipe_duration", "template_scales", "ocr_workers"):
            if k in preset:
                self._data[k] = preset[k]
        self.save()

    def to_dict(self) -> dict:
        return dict(self._data)

    def reset(self) -> None:
        self._data = dict(_DEFAULTS)
        self.save()
