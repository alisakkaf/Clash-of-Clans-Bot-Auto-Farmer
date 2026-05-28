"""
HumanTouchSkill — humanized actuators that respect CoC's touch grammar.

CoC's behaviour depends on the SHAPE of the gesture:
    • A swipe of <30 px movement and >1.5 s hold is treated as a
      tap-and-hold (mass deploy at one point).
    • A swipe of >50 px in <500 ms is treated as a fast deploy along the
      path (line deploy).
    • Anything slower than ~800 ms over a long distance is read as a
      camera pan — the army is NOT deployed.

This skill exposes three primitives and one helper:
    tap(x, y)                       — single deploy / card select.
    long_press(x, y, dur_ms)        — mass deploy at one point.
    quick_swipe(x1, y1, x2, y2)     — line deploy along a short path.
    settle(min_ms, max_ms)          — randomized inter-action pause.

All primitives jitter coordinates ±tap_jitter_px and clamp to screen
bounds. Hold durations are randomized within ±15% to avoid
machine-perfect repetition.
"""

from __future__ import annotations

import random
import time

from core.adb_handler import _run as _adb_run, DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT
from core.logger import BotLogger

log = BotLogger.get("v2.human_touch")


class HumanTouchSkill:
    name = "human_touch"

    def tap(self, x: int, y: int, config: dict | None = None) -> None:
        cfg = self._cfg(config)
        hx, hy = self._jitter(x, y, cfg["tap_jitter_px"])
        hold = random.randint(cfg["tap_hold_min_ms"], cfg["tap_hold_max_ms"])
        log.debug("v2.tap (%d,%d)→(%d,%d) hold=%dms", x, y, hx, hy, hold)
        _adb_run(["shell", "input", "swipe",
                  str(hx), str(hy), str(hx), str(hy), str(hold)])
        self.settle(config)

    def long_press(
        self, x: int, y: int, dur_ms: int | None = None, config: dict | None = None,
    ) -> None:
        cfg = self._cfg(config)
        hx, hy = self._jitter(x, y, cfg["tap_jitter_px"])
        base = int(dur_ms) if dur_ms is not None else int(cfg["long_press_ms"])
        dur = max(1500, int(base * random.uniform(0.92, 1.10)))
        ox = random.choice([-1, 1]) * random.randint(6, 10)
        oy = random.choice([-1, 1]) * random.randint(6, 10)
        ex = max(0, min(hx + ox, DEFAULT_SCREEN_WIDTH - 1))
        ey = max(0, min(hy + oy, DEFAULT_SCREEN_HEIGHT - 1))
        log.info("v2.long_press (%d,%d)→(%d,%d) dur=%dms", x, y, ex, ey, dur)
        _adb_run(["shell", "input", "swipe",
                  str(hx), str(hy), str(ex), str(ey), str(dur)])
        self.settle(config)

    def quick_swipe(
        self, x1: int, y1: int, x2: int, y2: int,
        dur_ms: int | None = None, config: dict | None = None,
    ) -> None:
        cfg = self._cfg(config)
        sx, sy = self._jitter(x1, y1, cfg["tap_jitter_px"])
        ex, ey = self._jitter(x2, y2, cfg["tap_jitter_px"])
        base = int(dur_ms) if dur_ms is not None else int(cfg["quick_swipe_ms"])
        dur = max(120, int(base * random.uniform(0.85, 1.15)))
        log.debug("v2.quick_swipe (%d,%d)→(%d,%d) dur=%dms", sx, sy, ex, ey, dur)
        _adb_run(["shell", "input", "swipe",
                  str(sx), str(sy), str(ex), str(ey), str(dur)])
        self.settle(config)

    def double_tap(
        self, x: int, y: int, gap_ms: int = 120, config: dict | None = None,
    ) -> None:
        self.tap(x, y, config)
        time.sleep(max(0.05, gap_ms / 1000.0))
        self.tap(x, y, config)

    def settle(self, config: dict | None = None) -> None:
        cfg = self._cfg(config)
        lo = max(0, int(cfg["inter_action_min_ms"])) / 1000.0
        hi = max(lo, int(cfg["inter_action_max_ms"])) / 1000.0
        time.sleep(random.uniform(lo, hi))

    def pre_select_settle(self, config: dict | None = None) -> None:
        cfg = self._cfg(config)
        ms = max(0, int(cfg.get("pre_select_settle_ms", 180)))
        time.sleep(ms / 1000.0)

    def post_deploy_settle(self, config: dict | None = None) -> None:
        cfg = self._cfg(config)
        ms = max(0, int(cfg.get("post_deploy_settle_ms", 300)))
        time.sleep(ms / 1000.0)

    @staticmethod
    def _cfg(config: dict | None) -> dict:
        c = config or {}
        dp = c.get("deploy_pattern", {}) if isinstance(c, dict) else {}
        return {
            "tap_jitter_px":         int(c.get("tap_jitter_px", 12)),
            "tap_hold_min_ms":       int(dp.get("tap_hold_min_ms", 60)),
            "tap_hold_max_ms":       int(dp.get("tap_hold_max_ms", 110)),
            "long_press_ms":         int(dp.get("long_press_ms", 2500)),
            "quick_swipe_ms":        int(dp.get("quick_swipe_ms", 350)),
            "inter_action_min_ms":   int(dp.get("inter_action_min_ms", 150)),
            "inter_action_max_ms":   int(dp.get("inter_action_max_ms", 400)),
            "pre_select_settle_ms":  int(dp.get("pre_select_settle_ms", 180)),
            "post_deploy_settle_ms": int(dp.get("post_deploy_settle_ms", 300)),
        }

    @staticmethod
    def _jitter(x: int, y: int, jitter: int) -> tuple[int, int]:
        if jitter <= 0:
            return int(x), int(y)
        jx = random.randint(-jitter, jitter)
        jy = random.randint(-jitter, jitter)
        nx = max(0, min(int(x) + jx, DEFAULT_SCREEN_WIDTH - 1))
        ny = max(0, min(int(y) + jy, DEFAULT_SCREEN_HEIGHT - 1))
        return nx, ny
