"""
Multi-finger gestures and human-like camera helpers for Smart Vision V2.

ADB single-shell `input swipe` cannot natively produce a real two-finger
pinch. We approximate it by issuing TWO simultaneous swipes from two
threads — most modern Android emulators (BlueStacks, MEmu, LDPlayer,
Genymotion) honor this as a true multi-touch gesture. If a particular
device does not, the V2 panel exposes a setting to disable the pinch
step gracefully.
"""

import random
import threading
import time

from core.adb_handler import _run, swipe, DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT
from core.logger import BotLogger

log = BotLogger.get("gestures")


def _swipe_raw(sx: int, sy: int, ex: int, ey: int, dur: int) -> None:
    _run(["shell", "input", "swipe", str(sx), str(sy), str(ex), str(ey), str(dur)])


def pinch_zoom_out(
    center_x: int | None = None,
    center_y: int | None = None,
    span_px: int = 380,
    duration_ms: int = 600,
) -> None:
    """Two-finger pinch INWARD (which CoC interprets as zoom OUT).

    The two swipes start far apart and slide toward the center, run on
    separate threads so they overlap in time on the device.
    """
    cx = center_x if center_x is not None else DEFAULT_SCREEN_WIDTH // 2
    cy = center_y if center_y is not None else DEFAULT_SCREEN_HEIGHT // 2

    span = max(120, span_px)
    j = random.randint(-15, 15)

    a_start = (max(40, cx - span + j), cy + random.randint(-25, 25))
    a_end   = (cx - 30, cy)
    b_start = (min(DEFAULT_SCREEN_WIDTH - 40, cx + span - j), cy + random.randint(-25, 25))
    b_end   = (cx + 30, cy)

    dur_a = duration_ms + random.randint(-60, 60)
    dur_b = duration_ms + random.randint(-60, 60)

    log.debug("PINCH-OUT center=(%d,%d) span=%d dur=%dms", cx, cy, span, duration_ms)

    t1 = threading.Thread(target=_swipe_raw, args=(*a_start, *a_end, dur_a), daemon=True)
    t2 = threading.Thread(target=_swipe_raw, args=(*b_start, *b_end, dur_b), daemon=True)
    t1.start(); t2.start()
    t1.join(timeout=duration_ms / 1000 + 2.0)
    t2.join(timeout=duration_ms / 1000 + 2.0)
    time.sleep(0.25)


def pan_camera(
    direction: str,
    distance_px: int = 280,
    duration_ms: int = 550,
    center_x: int | None = None,
    center_y: int | None = None,
) -> None:
    """Pan the in-game camera with a single, slow, slightly noisy swipe.

    `direction` ∈ {"up","down","left","right"} — moves the VIEWPORT in
    that direction (i.e., contents move opposite). Slow + jitter so the
    motion looks human rather than instant teleportation.
    """
    cx = center_x if center_x is not None else DEFAULT_SCREEN_WIDTH // 2
    cy = center_y if center_y is not None else DEFAULT_SCREEN_HEIGHT // 2
    d = max(100, distance_px)

    if direction == "up":
        sx, sy, ex, ey = cx, cy + d // 2, cx, cy - d // 2
    elif direction == "down":
        sx, sy, ex, ey = cx, cy - d // 2, cx, cy + d // 2
    elif direction == "left":
        sx, sy, ex, ey = cx + d // 2, cy, cx - d // 2, cy
    elif direction == "right":
        sx, sy, ex, ey = cx - d // 2, cy, cx + d // 2, cy
    else:
        return

    swipe(sx, sy, ex, ey, duration_ms=duration_ms)
    time.sleep(0.20)
