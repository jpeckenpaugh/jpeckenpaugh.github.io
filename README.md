# Lokarta - World Maker — Terminal RPG Prototype

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
- `docs/` — web build (Pyodide assets + terminal UI)
- `tests/` — unit tests

---

## Current Features (Snapshot)

- Title screen with Continue/New/Quit, save slot selection, and overwrite confirmation
- Title screen uses a scrolling panorama with a centered logo overlay
- Save slots (`saves/slot1.json` → `slot5.json`) + created/last played metadata
- ANSI color rendering and ASCII scene art
- Town hub with Inn, Shop, Hall, Temple, Alchemist, Smithy, and Portal
- Elemental continents + portal travel; town/forest palettes shift by element
- Spellbook with rank selection and MP scaling (cost = base * rank)
- Support spells (Life Boost, Strength) with temporary buffs
- Items + elemental gear variants; element-aligned shops per continent
- Inventory equip/unequip workflow with actions menu
- Multi-opponent encounters (up to 3) with level-budget spawns
- Combat with variance, crits, misses, stuns, defend, and flee
- Followers: recruit via Socialize, follower abilities, end-of-round effects
- Leveling with stat allocation + banked points via Stats menu
- Forest does not auto-spawn a battle on entry; use Seek out monsters
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

## Controls (Gamepad-like)

Title Screen:
- D-pad to move selection
- `A` / `Enter` to confirm
- `S` / `Esc` to cancel/back
- `Shift` / `Tab` opens Options

Town/Forest/Menus:
- Controls are data-driven from `data/commands.json`, `data/scenes.json`,
  `data/venues.json`, and `data/menus.json`.
- The action panel reflects the active commands and their conditions.
- Target selection (Attack/Socialize/targeted spells) uses ←/→ to cycle, `A` to confirm, `S` to cancel.
- Forest encounters are started via the Seek out monsters action (no auto-spawn on entry).

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
- `data/continents.json` — continent names, unlock levels, descriptions
- `data/elements.json` — element palettes and metadata
- `data/glyphs.json` — glyph art (atlas, etc.)
- `data/spells_art.json` — reusable spell animation art
- `data/abilities.json` — follower ability definitions

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
