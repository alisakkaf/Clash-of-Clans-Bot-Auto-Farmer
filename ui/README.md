# UI Module (`/ui`)

This directory houses the PyQt5 user interface components. It uses custom **QSS stylesheets** to provide a premium dark-themed experience with golden accents.

---

## File Overview

### 1. `main_window.py`
The master application dashboard.
- Connects the background worker thread (`BotEngine`) with visual controls.
- Manages navigation tabs and handles user status signals (e.g. state changes, error notifications, assist requests).

### 2. `styles.py`
Contains the `DARK_THEME_QSS` stylesheet. Uses deep navy (`#1a1a2e`), surfaces (`#16213e`), card surfaces (`#0f3460`), warning tones (`#e94560`), and golden details (`#e9b44c`).

### 3. `settings_tab.py`
Exposes global configuration parameters (timers, swipe durations, template matching thresholds, and game packages). It enables performance preset switching (Low, Medium, High, Ultra) and saves updates directly to `settings.json`.

### 4. `console_widget.py`
A custom logger terminal pane that reads from the logging module. Uses colored text formatting (ANSI translations) to display logs and includes scroll locks and clear buttons.

### 5. `home_village_tab.py` & `builder_base_tab.py`
Provides configuration settings for each village (attack selections, hero checkboxes, target limits, and spell combinations).

### 6. `sequence_builder_tab.py`
Visual sequence builder enabling users to drag, drop, and construct custom sequences (like clicking barracks, opening shops, or selecting bases).

### 7. `asset_manager_tab.py` & `interactive_assist.py`
- **Asset Manager:** Displays the manifest template database and allows users to check template matches.
- **Interactive Assist:** A setup assistant that displays screenshots and prompts users to click missing reference coordinates, saving crops directly back to the database.

### 8. `smart_v2_panel.py`
Exposes the advanced computer-vision rules options, allowing users to select deployment patterns, rules, and target priorities.
