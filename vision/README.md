# Vision Module (`/vision`)

This directory processes screenshot frames, extracts values via text recognition, and performs coordinate segmentations.

---

## File Overview

### 1. `screen_reader.py`
The primary image processing engine. Takes screenshots and scans for templates:
- **UI Elements:** Employs standard template matching with high thresholds (e.g. `0.80`) to identify static menu assets.
- **Troop/Spell/Hero Cards:** Scrapes the lower HUD strip (below the battlefield cutoff), converting screenshots to grayscale, resizing assets using multiple search scales (from `0.7x` to `1.1x` by default), and matching elements.
- **Battlefield Bounding Box:** Detects red boundary lines using HSV threshold ranges to find safe grid coordinates.
- **Deployment Line Generator:** Calculates coordinate lists around the detected battlefield grid margins to drop troops.

### 2. `ocr_reader.py`
Integrates **EasyOCR** for text readings.
- **Loot Reading:** Isolates the top-left area, dividing it into three horizontal bars (Gold, Elixir, Dark Elixir). Pre-processes these regions using CUBIC interpolation and Otsu's thresholding, runs the character recognition reader, and filters characters to extract clean digits.
- **Timer Reading:** Identifies battle time strings (e.g. `2m 45s`, `02:45`, `45s`) to track battle progress.
- **Button Finder:** Uses keyword list searches within region boundaries to locate dynamic text buttons (like dynamic translations of "End Battle", "Surrender", "Exit").

### 3. `smart_vision_v2.py`
Advanced computer vision segmenter. It processes HSV masks of the red deployment lines, projects contours onto an isometric coordinate grid, and determines the closest deployment node to target structures.

### 4. `template_manager.py`
Helper module checking file paths. Reads `assets/templates/manifest.json` and loads image template arrays into a caching map to prevent redundant read operations from disk.

---

## Skills Subfolder (`/vision/skills`)
Contains modular computer vision functions:
- **`red_zone_polygon.py`:** Generates coordinates describing the boundaries of red zones.
- **`isometric_grid.py`:** Standard grid projection maps translating flat 2D pixels to angled 3D isometric tiles.
- **`target_locator.py`:** Scans for structural templates (like Town Halls or resource storages).
- **`obstacle_detector.py`:** Identifies obstacles (trees, rocks, etc.) that block screen views.
- **`safe_corridor.py`:** Isolates paths between the outer boundary and target nodes.
