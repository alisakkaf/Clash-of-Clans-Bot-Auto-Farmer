# Core Module (`/core`)

This directory contains the runtime engine, device interface layers, and state tracking structures. It handles process executions and schedules bot events.

---

## File Overview

### 1. `adb_handler.py`
The low-level interface communicating with `2adb.exe` (Android Debug Bridge). It starts subprocess processes, pulls screenshot framebuffers directly to memory via OpenCV, and issues touchscreen inputs.
- **Humanization Features:** 
  - Generates coordinate jitter offsets.
  - Pauses execution with human-like hesitation delays after swipes or taps.
  - Implements coordinate-history memory to prevent double tapping identical screen coordinates.
- **Macros Engine:** Captures shell events from `/dev/input/event*` on the device and parses them into JSON trajectories, which can be replayed to execute custom loops.

### 2. `adb_gestures.py`
Provides high-level multi-finger gesture emulations by invoking multiple parallel coordinates swipes via ADB:
- Pinch-to-zoom out (compresses or expands coordinate spaces).
- Camera panning (dragging across coordinates to pan the camera view in 4 cardinal directions).

### 3. `bot_engine.py`
Runs a background `QThread` execution loop. Controls start, pause, resume, and stop events. 
- Performs health-checks on the Android emulator connection.
- Assures the target game is running in the foreground (attempts auto-launching if it is minimized).
- Evaluates if the bot is locked or frozen on unknown screens and signals user-assistance prompts.

### 4. `state_machine.py`
Encapsulates state-transitions using a finite state machine logic.
- Verifies screen changes (e.g., `HOME` ➔ `CONFIRMING` ➔ `SEARCHING` ➔ `IN_BATTLE`).
- Rejects invalid state transitions and reports warnings to prevent stuck loops.

### 5. `settings.py`
Singleton managing settings parameters. Automatically loads from and serializes updates to `profiles/settings.json`. Integrates hardware optimization presets (e.g., CPU-only vs Dedicated GPU) to scale search intervals and template limits.

### 6. `logger.py`
Sets up logging directories, formatting models, and redirects warning/info logs to both the standard output and `assets/logs/bot.log`.
