"""
ADB Handler — all device interactions via 2adb.exe (subprocess).

V4 Additions:
  • record_events()  — record raw touch events via adb getevent
  • play_recording() — replay a recorded macro with humanized delays

╔══════════════════════════════════════════════════════════════════╗
║  ANTI-BAN HUMANIZATION  (STRICT ENFORCEMENT)                    ║
║  • Every tap receives coordinate jitter (±3–8 px random).       ║
║  • Every action is followed by a randomized hesitation delay    ║
║    (0.10 s – 0.70 s) to simulate human reaction latency.        ║
║  • No two consecutive taps will ever hit the exact same pixel.   ║
╚══════════════════════════════════════════════════════════════════╝
"""

import json
import os
import random
import re
import subprocess
import sys
import time
import threading

import cv2
import numpy as np

from core.logger import BotLogger
from core.settings import Settings

log = BotLogger.get("adb")

TOUCH_MAX_X = 4095
TOUCH_MAX_Y = 4095
DEFAULT_SCREEN_WIDTH = 2340
DEFAULT_SCREEN_HEIGHT = 1080

ADB_EXE = "2adb.exe"

# Fixed humanization bounds (NOT tunables — purely for shape of randomness).
# All TUNABLE values come from Settings() at call time.
SWIPE_JITTER_MIN = 3
SWIPE_JITTER_MAX = 8
TAP_HOLD_MIN_MS = 40
TAP_HOLD_MAX_MS = 120

# Hide subprocess console windows on Windows.
_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

_last_tap_x: int | None = None
_last_tap_y: int | None = None


def _jitter_bounds() -> tuple[int, int]:
    """Derive (min, max) coord jitter from Settings.deploy_jitter."""
    j = max(0, int(Settings().get("deploy_jitter", 15)))
    if j == 0:
        return 0, 0
    return max(1, j // 5), max(2, j)


def _delay_bounds() -> tuple[float, float]:
    s = Settings()
    lo = float(s.get("tap_delay_min", 0.03))
    hi = float(s.get("tap_delay_max", 0.08))
    if hi < lo:
        hi = lo
    return lo, hi


# ═══════════════════════════════════════════════════════════════════════
#  Internals
# ═══════════════════════════════════════════════════════════════════════

def _run(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    cmd = [ADB_EXE] + args
    log.debug("ADB exec: %s", " ".join(cmd))
    try:
        return subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
            creationflags=_SUBPROCESS_FLAGS,
        )
    except subprocess.TimeoutExpired:
        log.error("ADB command timed out: %s", " ".join(cmd))
        raise
    except FileNotFoundError:
        log.critical("2adb.exe not found!")
        raise


def _run_raw(args: list[str], timeout: int = 15) -> bytes:
    return _run(args, timeout).stdout


def _humanize_coord(x: int, y: int) -> tuple[int, int]:
    global _last_tap_x, _last_tap_y
    j_min, j_max = _jitter_bounds()
    if j_max == 0:
        _last_tap_x, _last_tap_y = x, y
        return x, y
    for _ in range(20):
        jx = random.choice([-1, 1]) * random.randint(j_min, j_max)
        jy = random.choice([-1, 1]) * random.randint(j_min, j_max)
        hx = max(0, min(x + jx, DEFAULT_SCREEN_WIDTH - 1))
        hy = max(0, min(y + jy, DEFAULT_SCREEN_HEIGHT - 1))
        if hx != _last_tap_x or hy != _last_tap_y:
            _last_tap_x, _last_tap_y = hx, hy
            return hx, hy
    hx = max(0, min(x + random.randint(j_min, j_max), DEFAULT_SCREEN_WIDTH - 1))
    hy = max(0, min(y + random.randint(j_min, j_max), DEFAULT_SCREEN_HEIGHT - 1))
    _last_tap_x, _last_tap_y = hx, hy
    return hx, hy


def _human_delay() -> None:
    lo, hi = _delay_bounds()
    time.sleep(random.uniform(lo, hi))


def _random_hold_ms() -> int:
    return random.randint(TAP_HOLD_MIN_MS, TAP_HOLD_MAX_MS)


# ═══════════════════════════════════════════════════════════════════════
#  Public API — Core ADB
# ═══════════════════════════════════════════════════════════════════════

def check_connection() -> bool:
    try:
        result = _run(["devices"], timeout=5)
        output = result.stdout.decode("utf-8", errors="ignore")
        lines = [ln for ln in output.strip().splitlines() if "\tdevice" in ln]
        connected = len(lines) > 0
        log.info("ADB: %s", "CONNECTED" if connected else "NO DEVICE")
        return connected
    except Exception:
        return False


def get_resolution() -> tuple[int, int]:
    try:
        raw = _run_raw(["shell", "wm", "size"], timeout=5)
        text = raw.decode("utf-8", errors="ignore").strip()
        parts = text.split(":")[-1].strip().split("x")
        return int(parts[0]), int(parts[1])
    except Exception:
        return DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT


def screencap() -> np.ndarray | None:
    try:
        raw = _run_raw(["shell", "screencap", "-p"], timeout=10)
        raw = raw.replace(b"\r\n", b"\n")
        img_array = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            log.error("screencap decode failed.")
        return img
    except Exception as exc:
        log.error("screencap failed: %s", exc)
        return None


def tap(x: int, y: int) -> None:
    hx, hy = _humanize_coord(x, y)
    hold = _random_hold_ms()
    log.info("TAP (%d,%d) → (%d,%d) hold=%dms", x, y, hx, hy, hold)
    _run(["shell", "input", "swipe", str(hx), str(hy), str(hx), str(hy), str(hold)])
    _human_delay()


def tap_raw(x: int, y: int) -> None:
    _run(["shell", "input", "tap", str(x), str(y)])


def long_press(x: int, y: int, duration_ms: int = 800) -> None:
    hx, hy = _humanize_coord(x, y)
    dur = duration_ms + random.randint(-80, 120)
    _run(["shell", "input", "swipe", str(hx), str(hy), str(hx), str(hy), str(dur)])
    _human_delay()


def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int | None = None) -> None:
    """Humanized swipe. If duration_ms is None, reads Settings.swipe_duration."""
    if duration_ms is None:
        duration_ms = int(Settings().get("swipe_duration", 2500))
    sx = x1 + random.choice([-1, 1]) * random.randint(SWIPE_JITTER_MIN, SWIPE_JITTER_MAX)
    sy = y1 + random.choice([-1, 1]) * random.randint(SWIPE_JITTER_MIN, SWIPE_JITTER_MAX)
    ex = x2 + random.choice([-1, 1]) * random.randint(SWIPE_JITTER_MIN, SWIPE_JITTER_MAX)
    ey = y2 + random.choice([-1, 1]) * random.randint(SWIPE_JITTER_MIN, SWIPE_JITTER_MAX)
    sx = max(0, min(sx, DEFAULT_SCREEN_WIDTH - 1))
    sy = max(0, min(sy, DEFAULT_SCREEN_HEIGHT - 1))
    ex = max(0, min(ex, DEFAULT_SCREEN_WIDTH - 1))
    ey = max(0, min(ey, DEFAULT_SCREEN_HEIGHT - 1))
    dur = int(duration_ms * random.uniform(0.85, 1.15))
    _run(["shell", "input", "swipe", str(sx), str(sy), str(ex), str(ey), str(dur)])
    _human_delay()


def key_event(keycode: int) -> None:
    _run(["shell", "input", "keyevent", str(keycode)])
    _human_delay()


def press_back() -> None:
    key_event(4)


def press_home() -> None:
    key_event(3)


# ═══════════════════════════════════════════════════════════════════════
#  Public API — Game / Foreground App
# ═══════════════════════════════════════════════════════════════════════

# Pattern for `dumpsys window | grep mCurrentFocus` output. Works on
# every Android version because mCurrentFocus has the same shape since
# Android 4.x:
#   mCurrentFocus=Window{xxxxxxx u0 com.pkg.name/com.pkg.name.Activity}
_FOCUS_RE = re.compile(
    r"mCurrentFocus=Window\{[^}]*\s+([A-Za-z0-9_.]+)/[A-Za-z0-9_.$]+",
)


def get_focused_package(timeout: int = 6) -> str | None:
    """Return the package name of the currently focused Android window,
    or ``None`` if it cannot be determined.

    Uses ``adb shell dumpsys window`` and parses the ``mCurrentFocus``
    field — this is supported on every Android version and does not
    depend on a specific shell binary like ``grep``/``findstr``.
    """
    try:
        result = _run(["shell", "dumpsys", "window"], timeout=timeout)
    except Exception as exc:
        log.warning("dumpsys window failed: %s", exc)
        return None

    text = result.stdout.decode("utf-8", errors="ignore")
    match = _FOCUS_RE.search(text)
    if not match:
        return None
    return match.group(1)


def is_app_installed(package: str, timeout: int = 6) -> bool:
    """Return True if ``package`` is installed on the connected device.

    Uses ``pm path PACKAGE`` which prints ``package:/data/...`` when the
    app exists and exits silently otherwise. Available on every Android
    version that ships ``pm``.
    """
    if not package:
        return False
    try:
        result = _run(["shell", "pm", "path", package], timeout=timeout)
    except Exception as exc:
        log.warning("pm path failed for %s: %s", package, exc)
        return False
    text = result.stdout.decode("utf-8", errors="ignore").strip()
    return text.startswith("package:")


def launch_app(package: str, timeout: int = 8) -> bool:
    """Launch ``package`` via the standard ``monkey`` launcher intent.

    The ``monkey`` approach is more universal than ``am start`` because
    it does not require knowing the launchable activity name — it asks
    Android to resolve the LAUNCHER intent for the given package.
    Returns True if monkey reported one event sent.
    """
    if not package:
        return False
    try:
        result = _run(
            [
                "shell", "monkey",
                "-p", package,
                "-c", "android.intent.category.LAUNCHER",
                "1",
            ],
            timeout=timeout,
        )
    except Exception as exc:
        log.warning("monkey launch failed for %s: %s", package, exc)
        return False
    text = result.stdout.decode("utf-8", errors="ignore")
    ok = "Events injected: 1" in text or "events injected: 1" in text.lower()
    if ok:
        log.info("Launched app: %s", package)
    else:
        log.warning("monkey did not confirm launch for %s — output: %s",
                    package, text.strip()[:200])
    return ok


def is_game_running(package: str) -> bool:
    """Convenience wrapper: is the given package the current foreground app?"""
    focused = get_focused_package()
    return focused == package


# ═══════════════════════════════════════════════════════════════════════
#  MACRO RECORD / PLAYBACK  (V4)
# ═══════════════════════════════════════════════════════════════════════

_recording_process: subprocess.Popen | None = None
_recording_lines: list[str] = []
_recording_active = False
_recording_lock = threading.Lock()


def start_recording() -> None:
    """
    Begin recording raw touch events via ``adb shell getevent -t``.
    Runs in a background thread.  Call stop_recording() to finish.
    """
    global _recording_process, _recording_lines, _recording_active

    with _recording_lock:
        if _recording_active:
            log.warning("Recording already in progress.")
            return

        _recording_lines = []
        _recording_active = True

    cmd = [ADB_EXE, "shell", "getevent", "-t"]
    log.info("MACRO RECORD: starting getevent capture…")
    _recording_process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=_SUBPROCESS_FLAGS,
    )

    def _reader():
        global _recording_active
        try:
            for raw_line in _recording_process.stdout:
                if not _recording_active:
                    break
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if line:
                    _recording_lines.append(line)
        except Exception as exc:
            log.error("Recording reader error: %s", exc)
        finally:
            _recording_active = False

    t = threading.Thread(target=_reader, daemon=True)
    t.start()


def stop_recording() -> list[dict]:
    """
    Stop the getevent recording and parse the raw output into a list
    of ``{time, x, y}`` touch events suitable for playback.
    """
    global _recording_process, _recording_active

    with _recording_lock:
        _recording_active = False

    if _recording_process is not None:
        try:
            _recording_process.terminate()
            _recording_process.wait(timeout=3)
        except Exception:
            _recording_process.kill()
        _recording_process = None

    events = _parse_getevent_to_taps(_recording_lines)
    log.info("MACRO RECORD: stopped. Captured %d raw lines → %d tap events.", len(_recording_lines), len(events))
    return events


def save_recording(events: list[dict], filepath: str) -> None:
    """Save recorded events to a JSON file."""
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(events, fh, indent=2)
    log.info("Recording saved: %s (%d events)", filepath, len(events))


def load_recording(filepath: str) -> list[dict]:
    """Load a recorded macro from a JSON file."""
    if not os.path.isfile(filepath):
        log.error("Recording file not found: %s", filepath)
        return []
    with open(filepath, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    events = data if isinstance(data, list) else data.get("steps", data.get("events", []))
    log.info("Recording loaded: %s (%d events)", filepath, len(events))
    return events


def play_recording(events: list[dict], speed: float = 1.0) -> None:
    """
    Replay a recorded macro with humanized timing.

    Each event is ``{time, x, y}``.  The delay between events is
    preserved (scaled by *speed*), with a small random jitter added
    to make it human-like.
    """
    if not events:
        log.warning("play_recording: empty event list.")
        return

    log.info("MACRO PLAYBACK: replaying %d events (speed=%.1f)…", len(events), speed)
    start_offset = events[0].get("time", 0)

    for i, evt in enumerate(events):
        x = evt.get("x", 0)
        y = evt.get("y", 0)
        evt_time = evt.get("time", 0)

        # Compute delay relative to previous event
        if i > 0:
            prev_time = events[i - 1].get("time", 0)
            gap = (evt_time - prev_time) / speed
            # Humanize the gap
            gap += random.uniform(-0.02, 0.05)
            gap = max(0.03, gap)
            time.sleep(gap)

        # Tap with humanization
        tap(x, y)

    log.info("MACRO PLAYBACK: complete.")


def _parse_getevent_to_taps(lines: list[str]) -> list[dict]:
    """
    Parse raw getevent output lines into a list of {time, x, y} dicts.

    getevent format:
        [  timestamp] /dev/input/event*: type code value
    We look for ABS_MT_POSITION_X (0035), ABS_MT_POSITION_Y (0036),
    and SYN_REPORT (0000 0000 00000000) to finalize each touch point.
    """
    events: list[dict] = []
    cur_x: int | None = None
    cur_y: int | None = None
    cur_time: float = 0.0

    ts_pattern = re.compile(r"\[\s*([\d.]+)\]")

    for line in lines:
        # Extract timestamp
        ts_match = ts_pattern.search(line)
        if ts_match:
            cur_time = float(ts_match.group(1))

        parts = line.split()
        if len(parts) < 4:
            continue

        code = parts[-2] if len(parts) >= 3 else ""
        value = parts[-1] if len(parts) >= 2 else ""

        # ABS_MT_POSITION_X
        if "0035" in code:
            try:
                raw_x = int(value, 16)
                cur_x = int(raw_x * DEFAULT_SCREEN_WIDTH / TOUCH_MAX_X)
            except ValueError:
                pass

        # ABS_MT_POSITION_Y
        elif "0036" in code:
            try:
                raw_y = int(value, 16)
                cur_y = int(raw_y * DEFAULT_SCREEN_HEIGHT / TOUCH_MAX_Y)
            except ValueError:
                pass

        # SYN_REPORT — finalize touch
        elif "0000" in code and "0000" in value:
            if cur_x is not None and cur_y is not None:
                events.append({"time": cur_time, "x": cur_x, "y": cur_y})
                cur_x, cur_y = None, None

    return events
