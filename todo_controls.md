# Controls Redesign Plan

## Phase 1: Control Model + UX
- [x] Confirm final key mapping: D-pad arrows, A/S for confirm/back, Enter=Start, Shift=Select.
- [x] Define Options menu contents (Inventory, Spellbook, Settings, Quit, Back).
- [x] Define navigation model for action list (grid vs list) and targeting flow.
- [x] Decide whether Enter is allowed as confirm outside targeting (default: no).

## Phase 2: Input Routing + State
- [x] Add input modes (actions, menu, targeting, system/options).
- [x] Implement D-pad navigation and cursor state.
- [x] Map A/S/Enter/Shift to confirm/back/start/select.
- [x] Keep current command routing as data-driven.

## Phase 3: UI Rendering
- [x] Add cursor/highlight for actions panel and menus.
- [x] Update on-screen help text to reflect new controls.
- [ ] Ensure 100x30 layout integrity and truncation safety.

## Phase 4: Data + Commands
- [x] Add Options menu data in `data/menus.json`.
- [x] Wire Start/Select to menu routing (router support).
- [x] Remove action key display and drop command keys from JSON schema.

## Phase 5: Validation
- [ ] Test title/town/forest/combat/menu flows.
- [ ] Test targeting with D-pad + A/S.
- [ ] Verify web input mapping in `docs` build (optional).

---

## Notes (2026-01-30)
- Confirmed mapping: D-pad = arrows, A = confirm, S = back/cancel, Start = Enter, Select = Shift.
- Options menu contents (current): Inventory, Spellbook, Quit, Back.
- Action navigation model: grid (left/right switches columns, up/down moves within column).
- Targeting: left/right cycles targets, A confirms, S cancels. Enter does not confirm outside targeting.
- Phase 2 implementation: added cursors and input routing in `app/loop.py`; target select now accepts A/S.
- Web input: Shift now maps to `SHIFT` in `docs/main.js`.
- Phase 3 implementation: added action/menu highlights in `app/ui/layout.py` + `app/ui/screens.py`; updated footer hints.
- Phase 4 implementation: added Options menu in `data/menus.json`, routed options close in `app/commands/router.py`.
- Action keys removed from UI; command entries no longer require `key` in JSON.
- Note: terminal input cannot detect Shift alone; Select currently only works in web until we add a terminal fallback.
