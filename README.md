# Lokarta - World Maker — Local Terminal POC

## Overview

This project is a **local-first proof of concept** for a retro, BBS-style ASCII RPG. The goal is to validate:
- screen layout
- rendering approach
- input model
- engine/UI separation

Once validated locally, the same engine and assets can be migrated to:
- a web-based terminal UI
- an SSH-based BBS-style interface

---

## Design Goals

- Fixed-size ASCII screen (**100 columns × 30 rows**)
- Deterministic rendering (no scrolling UI in core gameplay screens)
- Single-key input (no Enter required)
- Nostalgic presentation with modern code structure
- Clean separation between game logic and presentation

---

## Code Structure

- `main.py` — game loop and state orchestration
- `app/bootstrap.py` — app initialization and wiring
- `app/config.py` — filesystem paths and config
- `app/models.py` — core dataclasses (`Player`, `Opponent`, `Frame`)
- `app/combat.py` — combat helpers and timing
- `app/input.py` — single-key input handling
- `app/shop.py` — shop interaction helpers
- `app/commands/` — command registry and command modules
- `app/loop.py` — main loop helper functions
- `app/ui/` — layout, rendering, and screen composition helpers
- `app/data_access/` — JSON data loaders
- `data/` — JSON content packs
- `saves/` — local save slots
- `docs/` — schema and design notes
- `tests/` — unit tests

---

## Current Features

- Title screen with Continue/New/Quit and save overwrite confirmation
- Title screen uses a scrolling panorama with a centered logo overlay
- Persistent save file (`saves/slot1.json`)
- ANSI color rendering and ASCII scene art
- Town hub with Inn, Shop, Hall, and Inventory (scene assembled from objects)
- Spellbook (Healing / Spark) and boosted casting prompts
- Items (Rations, Herbal Tea, Elixir) and purchasing via the shop
- Inn services (Rest and Hot Meal)
- Inventory item usage with numbered selection
- Multi-opponent encounters (up to 3) with level-budget spawns
- Combat with variance, crits, misses, and Spark stun
- Leveling: +10 stat points per level, allocation screen, auto-heal
- Boosted spell prompts auto-time out after 3 seconds
- Forest does not auto-spawn a battle on entry; use Find to spawn opponents
- Scene/venue transitions use a melt-down/build-up animation

---

## Screen Layout Contract (100x30)

Top to bottom:
- Top border (1)
- Location line (centered) (1)
- Separator border (1)
- Body area (variable)
  - Art block (if present)
  - Divider (if art present)
  - Narrative block with status lines
- Actions panel header (1)
- Actions panel content (3, auto-columns)
- Player stats header (1)
- Player stats (2)
- Bottom border (1)

---

## Controls

Title Screen:
- `C` Continue (if save exists)
- `N` New Game (confirm overwrite if save exists)
- `Q` Quit
- `Y/N` confirm/cancel overwrite

Town/Forest/Menus:
- Controls are data-driven from `data/commands.json`, `data/scenes.json`,
  `data/venues.json`, and `data/menus.json`.
- The action panel reflects the active commands and their conditions.
- Command schema notes: `docs/commands.md`.
- Boost prompts and timing are driven by `data/spells.json`.
- Target selection (Attack/Spark) uses ←/→ to cycle and Enter to confirm.
- Forest encounters are started via the Find action (no auto-spawn on entry).

---

## Assets

Game data is externalized into JSON:
- `data/opponents.json` — opponent stats, art, descriptions
- `data/items.json` — item effects, prices, descriptions
- `data/scenes.json` — scene configuration, object composition, commands
- `data/npcs.json` — NPC names and dialog snippets
- `data/npc_parts.json` — NPC part definitions (hat/face/torso/legs/shoes)
- `data/venues.json` — venue metadata and NPC links
- `data/spells.json` — spell definitions and costs
- `data/commands.json` — global action commands
- `data/menus.json` — inventory/spellbook UI text and actions
- `data/text.json` — message templates for battle text
- `data/objects.json` — object art, color masks, dynamic object defs
- `data/colors.json` — color palette, gradient, random bands

---

## Running the POC

1. Resize your terminal to **at least 100 columns × 30 rows**
2. Run:

```bash
python3 main.py
```

## Utilities

- `python3 color_map.py` — print the current color map (including random bands)
- `python3 render.py` — render objects/NPCs/opponents/venues/spells from JSON

---

## Platform Support

### Currently Supported
- macOS terminal
- Linux terminal
- Windows terminal (uses `msvcrt.getch()` for single-key input)

### Not Yet Supported
- Web UI
- SSH/BBS frontend

---

## Status

This repository represents an **exploratory prototype**.
Expect rapid iteration, breaking changes, and intentional simplicity.
