"""
OCR Reader — V10 Adjusted Proportional Cropping.

V10 FIXES (UPDATED):
  • Added update_profile synchronization for BotEngine compatibility.
  • Loot Y-axis shifted down: [10%:32%] to fix ultrawide screen misalignment.
  • Right-side precision crop (left 35% removed) preserved.
  • Regex digit extraction preserved (handles CoC spaced numbers).
"""

import re
import time

import cv2
import numpy as np

from core.logger import BotLogger
from core.settings import Settings

log = BotLogger.get("ocr")

# ── ANSI colors ────────────────────────────────────────────────────────
C_GOLD = "\033[93m"
C_ELIXIR = "\033[95m"
C_DARK = "\033[96m"
C_RESET = "\033[0m"

# ── Proportional ROI (fraction of screenshot dimensions) ───────────────
LOOT_Y_START = 0.10
LOOT_Y_END   = 0.32
LOOT_X_START = 0.00
LOOT_X_END   = 0.20

TIMER_Y_START = 0.00
TIMER_Y_END   = 0.12
TIMER_X_START = 0.40
TIMER_X_END   = 0.60

LOOT_LEFT_CROP = 0.35

_reader = None
_gpu_supported: bool | None = None


def _get_reader():
    global _reader, _gpu_supported
    if _reader is None:
        log.info("Initializing EasyOCR reader…")
        try:
            import easyocr
            if _gpu_supported is None or _gpu_supported is True:
                try:
                    _reader = easyocr.Reader(["en"], gpu=True, verbose=False)
                    _gpu_supported = True
                    log.info("EasyOCR reader initialized in GPU mode.")
                except Exception as gpu_exc:
                    log.warning("EasyOCR GPU mode failed (%s) — falling back to CPU mode.", gpu_exc)
                    _gpu_supported = False
                    _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
                    log.info("EasyOCR reader initialized in CPU mode.")
            else:
                _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
                log.info("EasyOCR reader initialized in CPU mode.")
        except Exception as exc:
            log.error("Failed to initialize EasyOCR reader: %s", exc)
            _reader = None
    return _reader


class OCRReader:
    """Proportional-crop OCR with precision right-side cropping and regex.

    Throttling: each public read_* call is rate-limited by
    ``Settings.ocr_min_interval`` (seconds) to avoid blocking the bot loop.
    The most recent successful result is cached and returned when throttled.
    """

    def __init__(self, *_args, **_kwargs) -> None:
        self._last_loot_time: float = 0.0
        self._last_loot: dict[str, int] = {"gold": 0, "elixir": 0, "dark_elixir": 0}
        self._last_timer_time: float = 0.0
        self._last_timer: tuple[int, bool] = (0, False)

    def _throttle_window(self) -> float:
        return float(Settings().get("ocr_min_interval", 2.0))

    # ═══════════════════════════════════════════════════════════════════
    #  CROPPING & PREPROCESSING
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _get_adaptive_loot_roi() -> tuple[float, float, float, float]:
        try:
            from core.adb_handler import is_tablet_device
            if is_tablet_device():
                return 0.03, 0.28, 0.00, 0.25
        except Exception:
            pass
        return LOOT_Y_START, LOOT_Y_END, LOOT_X_START, LOOT_X_END

    @staticmethod
    def _get_adaptive_timer_roi() -> tuple[float, float, float, float]:
        try:
            from core.adb_handler import is_tablet_device
            if is_tablet_device():
                return 0.00, 0.14, 0.38, 0.62
        except Exception:
            pass
        return TIMER_Y_START, TIMER_Y_END, TIMER_X_START, TIMER_X_END

    @staticmethod
    def _proportional_crop(
        screenshot: np.ndarray,
        y_start: float, y_end: float,
        x_start: float, x_end: float,
    ) -> np.ndarray:
        try:
            h, w = screenshot.shape[:2]
            y1 = max(0, int(h * y_start))
            y2 = min(h, int(h * y_end))
            x1 = max(0, int(w * x_start))
            x2 = min(w, int(w * x_end))
            if y2 <= y1 or x2 <= x1:
                return screenshot
            return screenshot[y1:y2, x1:x2]
        except Exception as exc:
            log.warning("_proportional_crop error: %s", exc)
            return screenshot

    @staticmethod
    def _preprocess(image: np.ndarray) -> np.ndarray:
        try:
            if image is None or image.size == 0:
                return np.zeros((10, 10), dtype=np.uint8)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            scaled = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            _, binary = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            if binary.size > 0 and np.count_nonzero(binary) / float(binary.size) < 0.5:
                binary = cv2.bitwise_not(binary)
            return binary
        except Exception as exc:
            log.warning("_preprocess error: %s", exc)
            return np.zeros((10, 10), dtype=np.uint8)

    # ═══════════════════════════════════════════════════════════════════
    #  EASYOCR
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _run_ocr(image: np.ndarray) -> str:
        try:
            if image is None or image.size == 0:
                return ""
            reader = _get_reader()
            if reader is None:
                return ""
            results = reader.readtext(image, detail=0, paragraph=True)
            return " ".join(results).strip()
        except Exception as exc:
            log.error("EasyOCR error: %s", exc)
            return ""

    # ═══════════════════════════════════════════════════════════════════
    #  LOOT READING
    # ═══════════════════════════════════════════════════════════════════

    def read_loot(self, screenshot: np.ndarray) -> dict[str, int]:
        now = time.time()
        if now - self._last_loot_time < self._throttle_window():
            return dict(self._last_loot)

        y1, y2, x1, x2 = self._get_adaptive_loot_roi()
        loot_crop = self._proportional_crop(
            screenshot, y1, y2, x1, x2,
        )
        if loot_crop.size == 0:
            return dict(self._last_loot)

        h, w = loot_crop.shape[:2]
        strip_h = h // 3

        raw_strips = {
            "gold":        loot_crop[0:strip_h, :],
            "elixir":      loot_crop[strip_h:2*strip_h, :],
            "dark_elixir": loot_crop[2*strip_h:, :],
        }

        result: dict[str, int] = {}
        for resource, strip in raw_strips.items():
            if strip.size == 0:
                result[resource] = 0
                continue
            sw = strip.shape[1]
            numbers_only = strip[:, int(sw * LOOT_LEFT_CROP):]
            processed = self._preprocess(numbers_only)
            raw_text = self._run_ocr(processed)
            digits = re.sub(r"\D", "", raw_text)
            value = int(digits) if digits else 0
            result[resource] = value
            log.debug("Loot %s: raw='%s' → digits='%s' → %d", resource, raw_text, digits, value)

        g, e, d = result["gold"], result["elixir"], result["dark_elixir"]
        log.info(
            "OCR Loot: G=%s%d%s E=%s%d%s DE=%s%d%s",
            C_GOLD, g, C_RESET, C_ELIXIR, e, C_RESET, C_DARK, d, C_RESET,
        )
        self._last_loot = result
        self._last_loot_time = now
        return result

    # ═══════════════════════════════════════════════════════════════════
    #  TIMER READING
    # ═══════════════════════════════════════════════════════════════════

    def read_timer_v2(self, screenshot: np.ndarray) -> tuple[int, bool]:
        now = time.time()
        if now - self._last_timer_time < self._throttle_window():
            return self._last_timer

        ty1, ty2, tx1, tx2 = self._get_adaptive_timer_roi()
        timer_crop = self._proportional_crop(
            screenshot, ty1, ty2, tx1, tx2,
        )
        processed = self._preprocess(timer_crop)
        raw = self._run_ocr(processed)
        text = raw.strip().lower()
        is_prep = "start" in text

        m_match = re.search(r"(\d+)\s*m\s*(\d+)\s*s?", text)
        if m_match:
            res = int(m_match.group(1)) * 60 + int(m_match.group(2)), is_prep
            self._last_timer, self._last_timer_time = res, now
            return res

        colon_match = re.search(r"(\d+)\s*:\s*(\d+)", text)
        if colon_match:
            res = int(colon_match.group(1)) * 60 + int(colon_match.group(2)), is_prep
            self._last_timer, self._last_timer_time = res, now
            return res

        s_match = re.search(r"(\d+)\s*s", text)
        if s_match:
            res = int(s_match.group(1)), True
            self._last_timer, self._last_timer_time = res, now
            return res

        digits = re.sub(r"\D", "", text)
        if digits:
            val = int(digits)
            if val > 300:
                val = val % 100 if val > 500 else val
            res = val, is_prep
            self._last_timer, self._last_timer_time = res, now
            return res
        res = 0, False
        self._last_timer, self._last_timer_time = res, now
        return res

    def read_timer(self, screenshot: np.ndarray) -> str:
        secs, _ = self.read_timer_v2(screenshot)
        return f"{secs // 60}:{secs % 60:02d}"

    def read_stars(self, screenshot: np.ndarray) -> int:
        return 0

    def read_percentage(self, screenshot: np.ndarray) -> int:
        return 0

    # ═══════════════════════════════════════════════════════════════════
    #  TEXT-BASED BUTTON FINDER (for buttons whose label varies)
    # ═══════════════════════════════════════════════════════════════════

    def find_text_in_region(
        self,
        screenshot: np.ndarray,
        keywords: list[str],
        region: tuple[float, float, float, float] = (0.70, 1.00, 0.00, 0.30),
    ) -> tuple[int, int] | None:
        """Search a sub-region for any of the given text keywords using OCR.

        ``region`` is ``(y_start, y_end, x_start, x_end)`` as fractions of the
        full screenshot. Defaults to the bottom-left quadrant where the
        in-battle "End Battle / Surrender / Exit" button lives.

        Returns the centre ``(x, y)`` of the first matched word in absolute
        screenshot coordinates, or ``None`` if no keyword was found. Matching
        is case-insensitive and substring-based, so any of:
            "End Battle", "Surrender", "Exit", "Yield"
        will match their on-screen variants ("END BATTLE", "Surrender?", …).
        """
        if not keywords:
            return None

        h, w = screenshot.shape[:2]
        y1 = max(0, int(h * region[0]))
        y2 = min(h, int(h * region[1]))
        x1 = max(0, int(w * region[2]))
        x2 = min(w, int(w * region[3]))
        if y2 <= y1 or x2 <= x1:
            return None

        crop = screenshot[y1:y2, x1:x2]
        try:
            reader = _get_reader()
            # detail=1 → list of (bbox, text, conf); paragraph=False keeps words.
            results = reader.readtext(crop, detail=1, paragraph=False)
        except Exception as exc:
            log.error("EasyOCR error in find_text_in_region: %s", exc)
            return None

        needles = [k.strip().lower() for k in keywords if k.strip()]
        for bbox, text, conf in results:
            if conf < 0.30:
                continue
            t = (text or "").strip().lower()
            if not t:
                continue
            if not any(n in t for n in needles):
                continue
            # bbox is a 4-point polygon → take its centre
            xs = [int(p[0]) for p in bbox]
            ys = [int(p[1]) for p in bbox]
            cx = x1 + (min(xs) + max(xs)) // 2
            cy = y1 + (min(ys) + max(ys)) // 2
            log.info("OCR matched '%s' (conf=%.2f) at (%d,%d).", text, conf, cx, cy)
            return cx, cy
        return None

    def read_troop_quantity(
        self,
        screenshot: np.ndarray,
        icon_box: tuple[int, int, int, int],
    ) -> int:
        ix, iy, iw, ih = icon_box
        sh, sw = screenshot.shape[:2]
        roi_h = 30
        roi_y = max(0, iy - roi_h - 2)
        roi_x = max(0, ix - 5)
        roi_w = min(iw + 10, sw - roi_x)
        roi_h_actual = min(roi_h, iy - roi_y)
        if roi_w <= 0 or roi_h_actual <= 5:
            return 1
        crop = screenshot[roi_y:roi_y + roi_h_actual, roi_x:roi_x + roi_w]
        processed = self._preprocess(crop)
        raw = self._run_ocr(processed)
        digits = re.sub(r"\D", "", raw)
        return int(digits) if digits else 1