"""
Template Manager — FULLY DYNAMIC manifest-driven asset system.

V4 Changes:
  • DEFAULT_ASSETS is now just a SUGGESTION catalogue — not enforced.
  • The manifest.json is the single source of truth.
  • Users can add any custom asset (troop, spell, UI element, etc.).
  • Readiness is determined by whether the user's attack SEQUENCES
    contain only mapped assets — not by a hardcoded "required" list.
"""

import json
import os
from pathlib import Path

import cv2
import numpy as np

from core.logger import BotLogger

log = BotLogger.get("templates")

TEMPLATES_DIR = Path("assets/templates")
MANIFEST_FILE = TEMPLATES_DIR / "manifest.json"

# ═══════════════════════════════════════════════════════════════════════
#  DEFAULT ASSET CATALOGUE  (suggestions only — user can add/remove)
#  Used by the AssetManager UI to pre-populate the tree for convenience.
#  These are NOT enforced as required.
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_ASSETS: dict[str, tuple[str, str]] = {
    # (category, human_label)
    # ── UI Elements ─────────────────────────────────────────────────────
    "attack_button":         ("ui_elements", "Attack Button"),
    "attack_button2":        ("ui_elements", "Attack Button 2 (Find a Match)"),
    "next_button":           ("ui_elements", "Next Button"),
    "end_battle_button":     ("ui_elements", "End Battle Button"),
    "surrender_button":      ("ui_elements", "Surrender Button"),
    "end_battle_confirm":    ("ui_elements", "End Battle / Surrender Confirm"),
    "return_home":           ("ui_elements", "Return Home Button"),
    "confirm_button":        ("ui_elements", "Confirm / OK Button"),
    "ranked_mode_btn":       ("ui_elements", "Ranked Mode Button"),
    "normal_mode_btn":       ("ui_elements", "Normal Mode Button"),
    "searching_indicator":   ("ui_elements", "Searching Indicator"),
    "connection_error":      ("ui_elements", "Connection Error Popup"),
    "reload_button":         ("ui_elements", "Reload / Retry Button"),
    "loading_screen":        ("ui_elements", "Loading Screen"),

    # ── Troops ──────────────────────────────────────────────────────────
    "barbarian":             ("troops", "Barbarian"),
    "archer":                ("troops", "Archer"),
    "giant":                 ("troops", "Giant"),
    "goblin":                ("troops", "Goblin"),
    "wall_breaker":          ("troops", "Wall Breaker"),
    "balloon":               ("troops", "Balloon"),
    "wizard":                ("troops", "Wizard"),
    "healer":                ("troops", "Healer"),
    "dragon":                ("troops", "Dragon"),
    "pekka":                 ("troops", "P.E.K.K.A"),
    "baby_dragon":           ("troops", "Baby Dragon"),
    "miner":                 ("troops", "Miner"),
    "electro_dragon":        ("troops", "Electro Dragon"),
    "yeti":                  ("troops", "Yeti"),
    "hog_rider":             ("troops", "Hog Rider"),
    "valkyrie":              ("troops", "Valkyrie"),
    "golem":                 ("troops", "Golem"),
    "witch":                 ("troops", "Witch"),
    "lava_hound":            ("troops", "Lava Hound"),
    "bowler":                ("troops", "Bowler"),
    "ice_golem":             ("troops", "Ice Golem"),

    # ── Heroes ──────────────────────────────────────────────────────────
    "barbarian_king":        ("heroes", "Barbarian King"),
    "archer_queen":          ("heroes", "Archer Queen"),
    "grand_warden":          ("heroes", "Grand Warden"),
    "royal_champion":        ("heroes", "Royal Champion"),

    # ── Spells ──────────────────────────────────────────────────────────
    "lightning_spell":       ("spells", "Lightning Spell"),
    "heal_spell":            ("spells", "Heal Spell"),
    "rage_spell":            ("spells", "Rage Spell"),
    "freeze_spell":          ("spells", "Freeze Spell"),
    "jump_spell":            ("spells", "Jump Spell"),
    "poison_spell":          ("spells", "Poison Spell"),
    "earthquake_spell":      ("spells", "Earthquake Spell"),
    "haste_spell":           ("spells", "Haste Spell"),
    "bat_spell":             ("spells", "Bat Spell"),
    "totem_spell":           ("spells", "Totem Spell"),

    # ── Buildings ───────────────────────────────────────────────────────
    "town_hall":             ("buildings", "Town Hall"),
    "gold_storage":          ("buildings", "Gold Storage"),
    "elixir_storage":        ("buildings", "Elixir Storage"),
    "dark_elixir_storage":   ("buildings", "Dark Elixir Storage"),
    "gold_mine":             ("buildings", "Gold Mine"),
    "elixir_collector":      ("buildings", "Elixir Collector"),

    # ── Builder Base ────────────────────────────────────────────────────
    "bb_home_indicator":     ("builder_base", "BB Home Indicator"),
    "bb_find_match":         ("builder_base", "BB Find Match Button"),
    "bb_battle_hud":         ("builder_base", "BB Battle HUD"),
    "bb_stage2_indicator":   ("builder_base", "BB Stage 2 Indicator"),
    "bb_battle_result":      ("builder_base", "BB Battle Result"),
    "bb_return_home":        ("builder_base", "BB Return Home"),
    "bb_troop_slot":         ("builder_base", "BB Troop Slot"),
}

# Valid categories (used by Add Custom Asset dialog)
VALID_CATEGORIES = [
    "ui_elements", "troops", "heroes", "spells",
    "buildings", "builder_base", "custom",
]


# ═══════════════════════════════════════════════════════════════════════
#  Manifest I/O
# ═══════════════════════════════════════════════════════════════════════

def _ensure_dirs() -> None:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def _load_manifest() -> dict:
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _save_manifest(data: dict) -> None:
    _ensure_dirs()
    with open(MANIFEST_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


# ═══════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════

def save_template(name: str, image: np.ndarray, category: str = "misc") -> str:
    """Save a cropped image as a named template."""
    cat_dir = TEMPLATES_DIR / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    filepath = cat_dir / f"{name}.png"
    cv2.imwrite(str(filepath), image)

    manifest = _load_manifest()
    manifest[name] = {
        "category": category,
        "label": name.replace("_", " ").title(),
        "file": str(filepath),
        "width": image.shape[1],
        "height": image.shape[0],
    }
    _save_manifest(manifest)
    log.info("Template saved: '%s' -> %s (%dx%d)", name, filepath, image.shape[1], image.shape[0])
    return str(filepath)


def import_template_from_file(name: str, source_path: str, category: str = "misc") -> str:
    """Import a template from a local image file."""
    _ensure_dirs()
    cat_dir = TEMPLATES_DIR / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    dest = cat_dir / f"{name}.png"

    img = cv2.imread(source_path, cv2.IMREAD_COLOR)
    if img is None:
        log.error("Could not read image: %s", source_path)
        return ""

    h, w = img.shape[:2]
    max_dim = 300
    if w > max_dim or h > max_dim:
        scale = max_dim / max(w, h)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    cv2.imwrite(str(dest), img)

    manifest = _load_manifest()
    manifest[name] = {
        "category": category,
        "label": name.replace("_", " ").title(),
        "file": str(dest),
        "width": img.shape[1],
        "height": img.shape[0],
    }
    _save_manifest(manifest)
    log.info("Template imported: '%s' <- %s", name, source_path)
    return str(dest)


def register_asset(name: str, category: str, label: str = "") -> None:
    """
    Register an asset key in the manifest WITHOUT an image.
    Used by "Add Custom Asset" to create a placeholder entry.
    """
    manifest = _load_manifest()
    if name in manifest:
        return  # already exists
    manifest[name] = {
        "category": category,
        "label": label or name.replace("_", " ").title(),
        "file": "",
        "width": 0,
        "height": 0,
    }
    _save_manifest(manifest)
    log.info("Asset registered (no image yet): '%s' in '%s'", name, category)


def load_template(name: str) -> np.ndarray | None:
    manifest = _load_manifest()
    entry = manifest.get(name)
    if entry is None:
        return None
    filepath = entry.get("file", "")
    if not filepath or not os.path.isfile(filepath):
        return None
    img = cv2.imread(filepath, cv2.IMREAD_COLOR)
    return img


def load_template_grayscale(name: str) -> np.ndarray | None:
    img = load_template(name)
    if img is not None:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return None


def template_exists(name: str) -> bool:
    """Check if a template has both a manifest entry AND a valid image file."""
    manifest = _load_manifest()
    entry = manifest.get(name)
    if entry is None:
        return False
    f = entry.get("file", "")
    return bool(f) and os.path.isfile(f)


def asset_registered(name: str) -> bool:
    """Check if an asset key exists in the manifest (image may be missing)."""
    return name in _load_manifest()


def list_templates(category: str | None = None) -> list[dict]:
    manifest = _load_manifest()
    results = []
    for name, meta in manifest.items():
        if category and meta.get("category") != category:
            continue
        results.append({"name": name, **meta})
    return results


def list_assets_by_category(category: str) -> list[tuple[str, str, bool]]:
    """
    Return all known assets in a category (from DEFAULT + manifest).
    Returns list of (key, label, has_image).
    """
    combined: dict[str, tuple[str, bool]] = {}

    # Start with defaults
    for key, (cat, label) in DEFAULT_ASSETS.items():
        if cat == category:
            combined[key] = (label, False)

    # Override with manifest (may add custom ones)
    manifest = _load_manifest()
    for key, meta in manifest.items():
        if meta.get("category") == category:
            has_img = bool(meta.get("file")) and os.path.isfile(meta.get("file", ""))
            combined[key] = (meta.get("label", key), has_img)

    return [(k, label, mapped) for k, (label, mapped) in sorted(combined.items())]


def delete_template(name: str) -> bool:
    manifest = _load_manifest()
    entry = manifest.pop(name, None)
    if entry is None:
        return False
    filepath = entry.get("file", "")
    if filepath and os.path.isfile(filepath):
        os.remove(filepath)
    _save_manifest(manifest)
    log.info("Template '%s' deleted.", name)
    return True


def delete_asset(name: str) -> bool:
    """Remove an asset entirely from the manifest (+ delete image if exists)."""
    return delete_template(name)


def get_template_path(name: str) -> str | None:
    manifest = _load_manifest()
    entry = manifest.get(name)
    if entry:
        return entry.get("file")
    return None


def get_all_categories() -> list[str]:
    """Return all categories present in DEFAULT_ASSETS + manifest."""
    cats = set(VALID_CATEGORIES)
    manifest = _load_manifest()
    for meta in manifest.values():
        c = meta.get("category", "")
        if c:
            cats.add(c)
    return sorted(cats)


def get_full_asset_catalogue() -> dict[str, tuple[str, str, bool]]:
    """
    Merge DEFAULT_ASSETS + manifest into one dict.
    Returns {key: (category, label, has_image)}.
    """
    result: dict[str, tuple[str, str, bool]] = {}

    # Defaults first (no image)
    for key, (cat, label) in DEFAULT_ASSETS.items():
        result[key] = (cat, label, False)

    # Manifest overrides
    manifest = _load_manifest()
    for key, meta in manifest.items():
        cat = meta.get("category", "custom")
        label = meta.get("label", key.replace("_", " ").title())
        has_img = bool(meta.get("file")) and os.path.isfile(meta.get("file", ""))
        result[key] = (cat, label, has_img)

    return result


def get_sequence_readiness(hv_sequence: list[str], bb_sequence: list[str]) -> tuple[bool, list[str]]:
    """
    Check if all assets referenced by the user's attack sequences are mapped.
    Returns (ready, list_of_missing_keys).
    """
    all_keys = set(hv_sequence) | set(bb_sequence)
    missing = [k for k in all_keys if not template_exists(k)]
    return len(missing) == 0, missing
