# Opponent Rework Todo

## Status
- Implemented with base opponents + element variants; refresh QA notes if needed.

## Phase 1 - Plan & Data Schema
- [x] Confirm base opponent list (slime, rat, ant, turtle)
- [x] Define element level offsets (+0 base, +1 earth, +2 wind, +3 fire, +4 water, +5 light, +6 lightning, +7 dark, +8 ice)
- [x] Define global stat multipliers per element (HP/ATK/DEF/SPEED)
- [x] Define per-base per-element names and short descriptions
- [x] Define color_map placeholder strategy (1/2/3 -> element palette)

## Phase 2 - Data Migration
- [x] Restructure data/opponents.json with base opponents + element_variants
- [x] Remove elemental duplicates from opponents.json
- [x] Add element variant names + descriptions
- [x] Add element scaling metadata

## Phase 3 - Runtime Generation
- [x] Update opponent spawn logic to build element variants on the fly
- [x] Apply level offsets + stat multipliers
- [x] Apply element color palette to 1/2/3 color_map keys
- [x] Preserve element field on opponent for combat bonuses

## Phase 4 - QA
- [ ] Verify spawn lists and level budgets still work
- [ ] Verify art renders with element palettes
- [ ] Confirm descriptions/names show for element variants
- [ ] Run through forest encounters at multiple levels

---
## Notes
- [x] 2026-01-31: Created todo for opponent rework.
- [x] 2026-01-31: Base opponents: slime, rat, ant, turtle.
- [x] 2026-01-31: Element level offsets: base +0, earth +1, wind +2, fire +3, water +4, light +5, lightning +6, dark +7, ice +8.
- [x] 2026-01-31: Element multipliers (hp/atk/def/speed):
  - base: 1.0/1.0/1.0/1.0
  - earth: 1.15/1.0/1.2/0.95
  - wind: 0.95/1.05/0.95/1.2
  - fire: 1.0/1.2/0.95/1.05
  - water: 1.1/1.0/1.1/1.0
  - light: 1.05/1.1/1.05/1.05
  - lightning: 0.95/1.25/0.9/1.25
  - dark: 1.05/1.15/1.1/0.95
  - ice: 1.1/1.05/1.2/0.9
- [x] 2026-01-31: Name pattern per base+element (examples):
  - slime: Slime, Stone Slime, Gale Slime, Ember Slime, Tide Slime, Lumen Slime, Storm Slime, Gloom Slime, Frost Slime.
  - rat: Rat, Stone Rat, Gale Rat, Ember Rat, Tide Rat, Lumen Rat, Storm Rat, Gloom Rat, Frost Rat.
  - ant: Ant, Stone Ant, Gale Ant, Ember Ant, Tide Ant, Lumen Ant, Storm Ant, Gloom Ant, Frost Ant.
  - turtle: Turtle, Stone Turtle, Gale Turtle, Ember Turtle, Tide Turtle, Lumen Turtle, Storm Turtle, Gloom Turtle, Frost Turtle.
- [x] 2026-01-31: Short element-themed descriptions will be authored per base+element in data/opponents.json.
- [x] 2026-01-31: color_map placeholders use keys "1","2","3" -> element primary palette.

- [x] 2026-01-31: Rewrote data/opponents.json with base_opponents + element_variants.
- [x] 2026-01-31: Opponent generation now builds element variants at spawn time with palette mapping.
