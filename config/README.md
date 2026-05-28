# Config Module (`/config`)

This directory contains the configurations for the Smart V2 CSR (Config-Skills-Rules) attack system. The orchestrator monitors these files and automatically hot-reloads them when modifications are made.

---

## File Overview

### 1. `v2_attack_rules.json`
Specifies global combat limits, image recognition values, and rule configurations:
- **`stand_off_px`:** Safe spacing distance kept from red boundary lines when dropping troops.
- **`polygon`:** Parameters for base boundary detection (HSV thresholds, morphology kernels).
- **`isometric`:** Scale values for mapping flat pixels to isometric dimensions.
- **`deploy_pattern`:** Delay offsets between troop drops (measured in milliseconds).
- **`funnel`:** Target ranges and delays used for clearing secondary structures.
- **`spell_path_fractions`:** Flight distances for spells relative to target lines.
- **`rule_priorities`:** Rules evaluation ordering list.

### 2. `v2_troop_profiles.json`
A directory of settings detailing troop behaviors:
- **`kind`:** Unit type (`ground` vs `air`).
- **`style`:** Drop strategy (e.g. `scout_pairs` to clear traps, `funnel` to clear sides, `fan_wide` for spreads, `cluster` for focused waves).
- **`deployment_spacing_ms`:** Interval time between individual unit placements.

### 3. `v2_spell_profiles.json`
Specifies coordinates logic for spells:
- Maps support spells to deployment parameters (e.g. dropping Rage spells ahead of unit clusters, casting Freeze spells on major defenses).
