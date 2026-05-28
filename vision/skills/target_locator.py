"""
TargetLocatorSkill — finds named asset positions on screen.

Wraps ScreenReader.find_template_by_name with two extras:
    1. Prefix expansion (e.g. "gold_storage" → all level variants).
    2. Multi-target listing (one match per prefix that hits).

Used by:
    • CornerSelector (to score corners by distance to defenses)
    • ResourceRaidRule (to scout each storage)
    • THSnipeRule    (to find the Town Hall)
    • SpellPlanner   (to find inferno_tower / air_defense / etc.)
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

import numpy as np

from core.logger import BotLogger
from vision.screen_reader import ScreenReader
from vision.template_manager import _load_manifest

log = BotLogger.get("v2.target_locator")


class TargetLocatorSkill:
    name = "target_locator"

    def __init__(self, screen_reader: ScreenReader) -> None:
        self._sr = screen_reader

    def find_one(
        self, screenshot: np.ndarray, asset_key: str,
    ) -> tuple[int, int] | None:
        return self._sr.find_template_by_name(screenshot, asset_key)

    def find_first_of(
        self,
        screenshot: np.ndarray,
        asset_keys: Iterable[str],
    ) -> tuple[str, int, int] | None:
        for key in asset_keys:
            hit = self._sr.find_template_by_name(screenshot, key)
            if hit:
                return key, hit[0], hit[1]
        return None

    def expand_prefix(self, prefix: str) -> List[str]:
        if not prefix:
            return []
        manifest = _load_manifest()
        keys = [
            k for k in manifest.keys()
            if k == prefix or k.startswith(prefix + "_")
        ]
        return sorted(keys)

    def find_all_by_prefix(
        self,
        screenshot: np.ndarray,
        prefixes: Iterable[str],
    ) -> List[Tuple[str, int, int]]:
        out: List[Tuple[str, int, int]] = []
        for prefix in prefixes:
            keys = self.expand_prefix(prefix) or [prefix]
            for k in keys:
                hit = self._sr.find_template_by_name(screenshot, k)
                if hit:
                    out.append((k, hit[0], hit[1]))
                    break
        return out

    def find_targets(
        self,
        screenshot: np.ndarray,
        priority_list: List[str],
    ) -> List[Tuple[str, int, int]]:
        """Return one location per top-level asset in priority order.
        Falls through level variants automatically."""
        out: List[Tuple[str, int, int]] = []
        for asset in priority_list:
            hit = self.find_first_of(
                screenshot, self.expand_prefix(asset) or [asset],
            )
            if hit:
                out.append(hit)
        return out
