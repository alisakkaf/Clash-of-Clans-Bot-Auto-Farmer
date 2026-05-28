# Logic Module (`/logic`)

This directory coordinates target selections, troop/spell drops, hero skill triggers, and state routines.

---

## File Overview

### 1. `home_village.py`
Manages Main Village gameplay:
- Handles standard search phases: reads loot via OCR; clicks "Next" if resources are too low, and initiates attacks once criteria are met.
- Performs attack deployment loops, tracks hero usage, and executes emergency taps if surrender button templates fail.
- Auto-handles the difference between standard and Ranked matchmaking states.

### 2. `builder_base.py`
Manages Builder Village combat stages:
- Coordinates search flows and launches matchmaking.
- Supports Stage 1 and Stage 2 transitions.
- **Fresh Screenshot Re-scan:** Re-screens the battlefield immediately after dropping heroes to update template indexes, bypass HP bar overlays, and deploy remaining troops accurately.
- Periodically activates Hero skills based on user profile timing configurations.

### 3. `smart_v2_logic.py`
Wrapper coordinating V2 attack steps:
- Dispatches execution tasks to the `V2Orchestrator`.
- Acts as a fallback proxy: if the orchestrator fails, it drops down to the legacy V36 single-cluster deployment method.

### 4. `v2_orchestrator.py`
The dispatcher for the Config-Skills-Rules (CSR) attack system:
- Monitors file modification timestamps (`mtime`) on configuration files (`config/*.json`) to auto-reload parameters.
- Allocates vision/logic skills.
- Resolves the best strategy rule (Air, Ground Funnel, Snipe) matching the current troop profile.
- Adjusts zoom ratios prior to starting vision checks.

---

## Subfolders

### Rules (`/logic/rules`)
Includes specialized strategy executors inheriting from `BaseRule`:
- **`air_attack_rule.py`:** Drops air units along safe vectors.
- **`ground_funnel_rule.py`:** Deploys units in a two-sided pattern to clear secondary defenses before launching main waves.
- **`th_snipe_rule.py`:** Pins down coordinates closest to the target Town Hall.
- **`resource_raid_rule.py`:** Drops scouts on individual storage points.
- **`smart_default_rule.py`:** Uses the widest safe path corridor to deploy.

### Skills (`/logic/skills`)
Coordinates mechanical troop/spell deployments:
- **`funnel_planner.py`:** Calculates funnel drop targets.
- **`fan_planner.py`:** Distributes troops evenly.
- **`hero_planner.py`:** Manages hero placements and ability timings.
- **`spell_planner.py`:** Positions support spells along army push lines.
- **`human_touch.py`:** Adds delays and coordinate jitter offsets.
