# Assets Module (`/assets`)

This directory houses the graphical templates, asset catalogues, and logging directories. It uses a dynamic JSON-manifest database model that avoids hardcoding files and allows for dynamic asset calibration.

---

## 📂 Directory Structure

```directory
.
├── logs/                         # Execution logs created during runtime
│   └── bot.log                   # Active session logging file (Ignored in Git)
└── templates/                    # Image template library
    ├── builder_base/             # Templates for Builder Base cards and indicators
    ├── buildings/                # Templates for defenses, Town Halls, and collectors
    ├── buttons/                  # Standard button triggers
    ├── heroes/                   # Hero cards and ability icons
    ├── spells/                   # Spell cards
    ├── troops/                   # Troop selection cards
    ├── ui_elements/              # UI popups, loading indicators, and error panels
    └── manifest.json             # Single source of truth database mapping keys to files
```

---

## ⚙️ The Manifest-Driven Architecture

Instead of searching paths on the hard drive or using hardcoded file strings, the framework loads assets dynamically. The `assets/templates/manifest.json` file records all templates as database entries:

```json
"grand_warden": {
  "category": "heroes",
  "label": "Grand Warden",
  "file": "assets\\templates\\heroes\\grand_warden.png",
  "width": 104,
  "height": 100
}
```

This dynamic approach offers several key benefits:
1. **Dynamic Addition:** Custom assets can be registered instantly in the UI or Python scripts without modifying core files.
2. **Safe Resolution:** The template engine checks the manifest for files before loading them, preventing runtime file errors.
3. **Sequence Validation:** Before starting, the bot engine verifies that all targets used in the active attack sequence exist in the manifest via `get_sequence_readiness()`.

---

## 🐍 Programmatic Management via Python

Developers can interact with, add, and register templates programmatically by importing the [template_manager.py](file:///vision/template_manager.py) module.

### 1. Saving a Template from a NumPy Array (`cv2` frame)
If you have cropped a region of interest from a game screen and want to save it as a reference template:
```python
import cv2
from vision.template_manager import save_template

# 1. Load or capture a frame
frame = cv2.imread("screencap.png")

# 2. Crop your target element (e.g. Town Hall 15)
town_hall_crop = frame[250:380, 500:620]

# 3. Save and register in manifest
# Saves to: assets/templates/buildings/town_hall_15.png
# Registers: "town_hall_15" in manifest.json under category "buildings"
path = save_template(
    name="town_hall_15",
    image=town_hall_crop,
    category="buildings"
)
print(f"Registered and saved template to: {path}")
```

### 2. Importing a Template from an Existing File
If you have a template image on your disk and want to import it into the project, the manager will scale it down if it exceeds `300px` to optimize search performance:
```python
from vision.template_manager import import_template_from_file

# Import and scale image
# Dest path: assets/templates/troops/super_dragon.png
path = import_template_from_file(
    name="super_dragon",
    source_path="C:/Downloads/my_crop.png",
    category="troops"
)

if path:
    print(f"Successfully imported custom troop: {path}")
```

### 3. Registering a Placeholder Asset Key
If you want to add a key to the catalogue without providing an image file immediately (allowing it to be calibrated by the user in the UI at a later time):
```python
from vision.template_manager import register_asset

# Registers key in manifest.json with an empty file path
register_asset(
    name="ice_spell",
    category="spells",
    label="Ice Spell Placeholder"
)
```

### 4. Dynamic Loading and Deleting
To verify a template exists, load it, or remove it programmatically:
```python
import cv2
from vision.template_manager import template_exists, load_template, delete_template

# Check if registered and file exists
if template_exists("archer_queen"):
    # Load image as BGR NumPy array
    img = load_template("archer_queen")
    
    # Process or inspect image dimensions
    h, w = img.shape[:2]
    print(f"Archer Queen template size: {w}x{h}")
    
# Remove a template from disk and delete its manifest entry
success = delete_template("temporary_scout_marker")
if success:
    print("Successfully deleted template.")
```

---

## 🔍 How the Vision Engine Loads Templates

During ticks, [ScreenReader](file:///vision/screen_reader.py) resolves targets using the manager:
1. It requests the file path from `get_template_path(name)`.
2. It reads the image file and caches the BGR image, alpha mask, and category in a memory map `_template_cache` to avoid repeated disk reads.
3. It performs matching based on the category thresholds (e.g. `_troop_thr` for troops, `_ui_thr` for UI elements).
4. If settings or assets are modified, the engine clears the cache using `clear_cache()` and re-reads files on the next tick.
