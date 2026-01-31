# Elemental Expansion Plan

## Status
- Largely implemented; verify remaining phase notes below.

## Phase 1: Element Unlocks
- [x] Define element unlock levels (tie to spell unlocks).
- [x] Add element fields to player state and save data.
- [x] Add unlock notifications (level-up notes).

## Phase 2: Scene Variants (Single Scene + Elemental Skins)
- [x] Add element-aware rendering for town/forest (palette swap).
- [x] Map element to color palettes for objects and overlays.
- [ ] Add element-aware scene text variants (optional).

## Phase 3: Opponent Variants
- [x] Create elemental opponent variants (e.g., Fire Ant).
- [x] Increase stats per element tier.
- [x] Update spawn logic to use element variants.

## Phase 4: Items + Shops
- [x] Add equipment item types: rings, bracelets, swords, shields, armor.
- [x] Create elemental variants of equipment.
- [x] Add elemental shop inventory lists.

## Phase 5: Balancing + Validation
- [ ] Review combat pacing per element tier.
- [ ] Ensure shop progression and gear power curves align with spell tiers.
- [ ] Validate saves + unlock flow.

---

## Notes (2026-01-30)
- Single scene approach approved; elements handled as palette/variant layers.
- Element unlocks tied to spell unlock levels.
- Elemental shops should stock elemental gear variants.
- Phase 1 implemented: player tracks `elements` + `current_element`, unlock notes on level-up.
- Phase 2 implemented: element palette remap applied to town/forest/venues + combat renders.
- Phase 3 implemented: fire variants added; spawner prefers element pool.
- Phase 4 implemented: gear items + elemental gear variants added, shop uses element-based inventory sets.
