"""
SpellPlannerSkill — chooses a drop coordinate for each selected spell.

Inputs:
    cluster_xy   — main army cluster (deploy anchor).
    target_xy    — base centroid OR specific target (TH / Inferno / ...).
    spell_name   — selected spell key (rage_spell, freeze_spell, ...).
    config       — v2_attack_rules + v2_spell_profiles.
    target_locator — used to find on-screen defenses for spell-on-target
                     placements.

Behaviour by placement:
    "ahead"     → along (cluster→target) at config.path_fraction.
    "on_army"   → near cluster (small jitter).
    "on_target" → on the closest match of target_priority assets.
    "on_wall"   → middle of the cluster→target line (jump/earthquake).
"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

import numpy as np

from core.logger import BotLogger
from vision.skills.target_locator import TargetLocatorSkill

log = BotLogger.get("v2.spell_planner")


class SpellPlannerSkill:
    name = "spell_planner"

    def __init__(self, target_locator: TargetLocatorSkill) -> None:
        self._tl = target_locator

    def plan_spell(
        self,
        screenshot: np.ndarray,
        spell_name: str,
        cluster_xy: tuple[int, int],
        target_xy: tuple[int, int],
        config: dict | None = None,
        spell_profiles: dict | None = None,
    ) -> List[Tuple[int, int]]:
        cfg = config or {}
        profiles = spell_profiles or {}
        profile = profiles.get(spell_name) or self._guess_profile(spell_name, cfg)
        if profile is None:
            return [self._on_path(cluster_xy, target_xy, 0.55)]

        placement = profile.get("placement", "ahead")
        drop_count = max(1, int(profile.get("drop_count", 1)))
        out: List[Tuple[int, int]] = []

        if placement == "ahead":
            frac = float(profile.get("path_fraction", 0.65))
            out.append(self._on_path(cluster_xy, target_xy, frac))

        elif placement == "on_army":
            cx, cy = cluster_xy
            for _ in range(drop_count):
                out.append((cx + random.randint(-30, 30), cy + random.randint(-30, 30)))

        elif placement == "on_target":
            priority = profile.get("target_priority", []) or []
            hit = self._tl.find_first_of(screenshot, priority)
            if hit is not None:
                _, hx, hy = hit
                for i in range(drop_count):
                    jitter = 25 + 15 * i
                    out.append((hx + random.randint(-jitter, jitter),
                                hy + random.randint(-jitter, jitter)))
            else:
                frac = float(profile.get("path_fraction", 0.55))
                out.append(self._on_path(cluster_xy, target_xy, frac))

        elif placement == "on_wall":
            frac = float(profile.get("path_fraction", 0.45))
            base_pt = self._on_path(cluster_xy, target_xy, frac)
            for i in range(drop_count):
                bx, by = base_pt
                out.append((bx + random.randint(-20, 20), by + random.randint(-20, 20)))

        else:
            out.append(self._on_path(cluster_xy, target_xy, 0.55))

        return out

    @staticmethod
    def _on_path(
        cluster_xy: tuple[int, int],
        target_xy: tuple[int, int],
        frac: float,
    ) -> tuple[int, int]:
        cx, cy = cluster_xy
        tx, ty = target_xy
        return int(round(cx + (tx - cx) * frac)), int(round(cy + (ty - cy) * frac))

    @staticmethod
    def _guess_profile(spell_name: str, cfg: dict) -> Optional[dict]:
        path_fracs = cfg.get("spell_path_fractions", {}) or {}
        key = spell_name.lower()
        for prefix, value in path_fracs.items():
            if key == prefix or key.startswith(prefix + "_") or prefix in key:
                if isinstance(value, (int, float)):
                    return {"placement": "ahead", "path_fraction": float(value), "drop_count": 1}
                if isinstance(value, str):
                    if "inferno" in value or "eagle" in value:
                        return {
                            "placement": "on_target",
                            "target_priority": ["inferno_tower", "eagle_artillery"],
                            "drop_count": 1,
                        }
                    if "air_defense" in value:
                        return {
                            "placement": "on_target",
                            "target_priority": ["air_defense", "x_bow"],
                            "drop_count": 3,
                        }
                    if "wall" in value:
                        return {"placement": "on_wall", "path_fraction": 0.45, "drop_count": 1}
        return None
