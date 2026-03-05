# AGENTS.md

## Project Overview
- Terminal-based ASCII RPG prototype.
- Main entry: `main.py`.
- Core code lives under `app/`.
- Data assets: `data/opponents.json`, `data/items.json`, `data/scenes.json`, `data/npcs.json`, `data/venues.json`, `data/spells.json`, `data/commands.json`, `data/menus.json`, `data/text.json`.
- Save file: `saves/slot1.json` (generated at runtime).

## Conventions
- Keep UI within 100x30 layout constraints.
- Single-key input only; Enter is reserved for target selection prompts.
- Town/Forest actions are listed in the Actions panel.
- Spells are accessed via the Spellbook (Magic).
- Persist changes to player state via `SaveData.save_player()`.

## Editing Guidelines
- Update JSON assets instead of hardcoding data.
- Avoid introducing non-ASCII characters unless already used.
- Keep UI text concise to avoid truncation.
- Keep commands data-driven; avoid hard-coded keys in `main.py`.
- Place loop helpers in `app/loop.py` to keep the entrypoint thin.
- Route menu actions through the router to avoid duplicate input handling.
- Preserve trailing spaces in ASCII art JSON (alignment depends on them).
- When adding venues, wire `scenes.json` → `venues.json` → router support.

## Quick Start
- Run: `python3 main.py`.
- If testing UI changes, ensure terminal size >= 100x30.
