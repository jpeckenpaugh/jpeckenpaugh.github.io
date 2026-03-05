# UI Layout Reference

This document describes the current screen layouts for the new build.

## Global Constraints

- Terminal viewport: `100 x 30` (width x height).
- Rendering model: full-frame text redraw with ANSI color sequences.
- Input model (legacy mapping):
  - Arrow keys: navigation
  - `A`: confirm / yes
  - `S` or `Esc`: back / no
  - `Enter`: open Options menu

## Title Screen

File: `app/scenes/title.py`

### Regions

- Full screen canvas: `100 x 30`
- Panorama band:
  - Anchored to bottom of screen
  - Height: `15` rows
  - Source: `TitlePanorama(viewport_width=100, height=15, ...)`
- Logo region:
  - `lokarta_logo` art from `objects.json`
  - Starts near top (`y=1`)
  - Centered horizontally
  - `#` in logo art is treated as blocking/transparent
- Subtitle region:
  - One row under logo
  - Centered text:
    - `*-----<{([  AI World Engine  ])}>-----*`
  - Middle text is white; decorations use gradient
- Menu box region:
  - Box width: `46`
  - Centered horizontally
  - Starts at `y=8`
  - Uses `o` corners, `-` top/bottom, `|` sides

### Styling Properties

- Logo gradient: white -> blue -> grey (diagonal blend).
- Menu frame border uses same gradient family as logo.
- Menu interior text is white.
- Current selection format: `[ <label> ]`.

### Behaviors

- Menu options:
  - Continue
  - New Game
  - Asset Explorer
  - Quit
- `Continue` is disabled when no save exists (slot check).
- Panorama scrolls continuously and triggers redraw on offset change.
- Press `Enter` to open Options scene.
- Press `S`/`Esc` to exit from title.
- Press `A` to activate current menu option.

## Asset Explorer Screen

File: `app/scenes/asset_explorer.py`

### Regions

- Full screen canvas: `100 x 30`
- Shared outer frame with merged pane dividers.
- Vertical divider at `x=33`.
  - Left pane width: `33` columns including border
  - Right pane width: `67` columns including border
- Right horizontal divider at `y=16`.
  - Top-right preview pane height: `16` rows including divider
  - Bottom-right details pane height: `14` rows including bottom border

### Pane Responsibilities

- Left pane:
  - Category title + item list
  - Scroll window centered around selected item
- Top-right pane:
  - Preview header
  - Selected asset visual preview (category-specific)
  - Venues omit `Selected`/`Entries` metadata lines
- Bottom-right pane:
  - Control hints
  - JSON line range + clipped JSON payload
  - Status/reload message line

### Categories and Preview Sources

- Objects: `art` + `color_mask` (or `color_map`)
- Opponents: direct payload art/mask when present
- NPCs: composed from `parts` using `npc_parts.json`
- Venues: composed from `objects` token list in `venues.json`, includes `npc` token rendering
- SpellsArt: animated `frames` + `mask_frames`
- Items / Scenes: textual summary when art is absent

### Color and Animation

- Colors resolve from `colors.json` hex map.
- Spells digit masks (`0-9`) use fallback ANSI palette mapping.
- SpellsArt auto-animates:
  - `input_timeout_seconds = 0.08`
  - redraw when frame index changes by `frame_delay`.

### Behaviors

- Navigation:
  - Arrow Left/Right: category
  - Arrow Up/Down: item
- JSON scroll:
  - `U`: up
  - `J`: down
- `R`: reload active asset file
- `S`/`Esc`: back to Title
- `Enter`: open Options scene
