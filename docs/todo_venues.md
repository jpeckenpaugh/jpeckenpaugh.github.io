# Venue Refactor TODO

## Status
- Core venue routing/rendering is in place; remaining notes are cleanup/QA.

## Phase 1 — Discovery + Inventory
- [x] Audit current venue modes, inputs, and render paths (shop/hall/inn/alchemist/temple/smithy/portal)
- [x] List all venue-specific commands and services in `data/venues.json`
- [x] Identify menu-based venue flows in `data/menus.json`
- [x] Document current back/leave behavior and mode flags in `app/loop.py` + `app/commands/router.py`

## Phase 2 — New Venue Module
- [x] Create `app/venues.py` with shared helpers and dataclasses for venue context/state
- [x] Implement `venue_actions()` to return standardized actions + injected Leave
- [x] Implement `handle_venue_command()` with per-venue-type handlers
- [x] Implement `render_venue_body()` to centralize venue narrative + NPC + art

## Phase 3 — Routing + Input Unification
- [x] Replace `app/shop.py` usage with `app/venues.py` handlers
- [x] Route venue commands through `handle_venue_command()` in `app/commands/router.py`
- [x] Update `action_commands_for_state()` to use `venue_actions()` for any venue mode
- [x] Remove venue-specific menu handling in `map_input_to_command()` (e.g., alchemist)

## Phase 4 — Screen Composition
- [x] Update `app/ui/screens.py` to render all venues via `render_venue_body()`
- [x] Remove venue-specific render branches (hall/inn/temple/smithy/alchemist/portal)
- [x] Ensure venue titles always prepend continent name dynamically

## Phase 5 — Cleanup + Safety
- [ ] Remove dead code in `app/shop.py` (or delete file if fully migrated)
- [ ] Clean up any unused menu definitions or venue commands
- [ ] Verify leave/back behavior works uniformly in every venue
- [ ] Add regression notes/tests (manual checklist in TODO footer)

## Notes (append as work proceeds)
- [ ] Phase 1 audit: venue modes live in `app/state.py`, `app/loop.py`, `app/commands/router.py`, render branches in `app/ui/screens.py`.
- [ ] Venue data summary: shop/hall/inn/temple have commands; inn/temple have services; alchemist/smithy/portal have no commands; `scene_id` varies per venue.
- [ ] Menu-driven venues: `menus.alchemist` and `menus.portal` (menus.json) still drive UI/actions.
- [ ] Back/Leave behavior: injected in UI helpers and shop commands; B_KEY handled in router by venue modes.
- [ ] Phase 2 draft: added `app/venues.py` with actions/render/handler stubs (not wired yet).
- [ ] Phase 3 wiring: router + loop now use `app/venues.py`; alchemist/portal actions now come from action grid (screens still use menu rendering until Phase 4).
- [ ] Phase 4 partial: unified venue render branch in `app/ui/screens.py`; portal atlas now uses action cursor; `render_venue_body()` not yet wired.
- [ ] Phase 4: venue rendering now calls `render_venue_body()` from `app/venues.py` (portal atlas + hall/inn/shop/alchemist centralized).
- [ ] Phase 4: venue render logic moved into `app/venues.py` (portal atlas + hall info + alchemist first selection) and screens now delegate to it.
