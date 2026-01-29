# Architecture Overview

## Runtime Flow

- `main.py` owns the game loop and user input.
- `app/bootstrap.py` creates an `AppContext` that wires data loaders, command registry, and UI contexts.
- `app/loop.py` hosts the loop helpers used by the entrypoint.
- `app/config.py` holds file path configuration (`data/`, `saves/`).
- `app/state.py` defines the `GameState` container for runtime state.

## Key Modules

- `app/data_access/` loads JSON content packs (scenes, opponents, items, commands, menus).
- `app/commands/` hosts the command registry, router, and command helpers.
- `app/ui/` builds frames, renders ASCII art, and handles animations.
- `app/combat.py` handles combat math and spell resolution.

## Data-Driven Commands

- Commands are defined in JSON and filtered at runtime (`app/commands/scene_commands.py`).
- The router (`app/commands/router.py`) executes stateful transitions and menu actions.
- Animation hints are stored in JSON and interpreted by the main loop.

## Scene Composition

- Town/Forest scenes can be assembled from object strips (left/right/bottom) rather than static art.
- Object composition supports dynamic labels (e.g., house signs) and per-object overrides.
- Forest layout is regenerated on entry and when spawning an encounter.
- Scenes can add dynamic scatter objects (e.g., pebbles/grass) via object definitions and scene wiring.
- Art rendering supports per-object jitter/variation and stable randomness.
- Title screen uses a scrolling panorama with a centered logo overlay.
