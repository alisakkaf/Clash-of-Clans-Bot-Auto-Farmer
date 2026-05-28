# Strategies Module (`/strategies`)

This directory contains user-created custom action sequences used to navigate menus or execute custom tasks.

---

## File Overview

### `example_strategy.json`
A template demonstrating how to chain action steps together:
- Each step is parsed as an image detection target or coordinate action.
- If a target is matched on-screen, the framework clicks it and pauses for the specified duration before executing the next step in the sequence.
- This is useful for automating routine tasks such as collecting resources, opening shops, training troops, or closing game announcements.
