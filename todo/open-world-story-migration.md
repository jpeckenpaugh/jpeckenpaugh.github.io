# Open World Story Migration Checklist

Goal: create an English-only sprint prototype that folds the open-world travel feel of `travel_v01.py` into the story and battle progression from `ui_v08.py`.

Working target: `world_story_v01.py`

Clean working directory target: `prototype/world_story/`

Primary sources:
- `travel_v01.py`: movement, camera, world rendering, NPC/world actors, road/crossroad layout.
- `ui_v08.py`: English story beats, party progression, battle stages, ally actions, Hawking Feather flow.
- `cottage_v04.py`: shared travel/world asset helpers used by `travel_v01.py`.
- `legacy/main.py` and `legacy/data/*.json`: richer older content catalog, especially venues, quest arcs, scenes, objects, NPCs, opponents, players, glyphs, and color/art definitions.

Agreed sprint decisions:
- Use `world_story_v01.py` as the new prototype filename.
- Put reusable new code in a clean working directory such as `prototype/world_story/`, with the root script acting as a thin launcher.
- Use on-map street battles over the open-world travel map, not a separate `ui_v08.py` battle backdrop.
- Use current story placements unless changed during implementation: Mushy at `#10 Ave A`, Sharoom at `#9 Ave A`, Roomy at `#8 Ave A`, Hawking at a later wide street/crossroad, fairies after Hawking.
- Use `a` as interact/confirm in travel and dialogs; keep arrow keys for movement/selection.
- Leave `ui_v08.py` as the English reference and reuse/extract its battle flow before writing replacement mechanics.
- Preserve JSON artwork assets at minimum; do not discard legacy art/object data during the sprint.
- Treat legacy systems as content/reference material first, not as runtime dependencies for the first clean prototype.

## 0. Clean Core And Asset Preservation

- [x] Create a clean working package at `prototype/world_story/`.
- [x] Keep `world_story_v01.py` as a tiny launcher that imports and runs the clean package.
- [x] Add focused modules only when they remove clutter from the launcher: `input.py`, `travel.py`, `story.py`, `dialog.py`, `battle.py`, `assets.py`.
- [x] Keep old experiments in place; do not move, delete, or rewrite `travel_v01.py`, `ui_v08.py`, or `legacy/` during this sprint.
- [x] Add an `assets.py` adapter that can load selected JSON assets without importing the legacy app runtime.
- [x] Preserve at least these legacy JSON art/data assets for future reuse: `legacy/data/objects.json`, `legacy/data/colors.json`, `legacy/data/glyphs.json`, `legacy/data/players.json`, `legacy/data/opponents.json`, `legacy/data/spells_art.json`, `legacy/data/frames.json`, and `legacy/data/npc_parts.json`.
- [x] Keep references to legacy JSON paths explicit and easy to replace later.
- [ ] Add a dropped/deferred inventory section to this TODO whenever a useful legacy or experiment feature is intentionally left out.

Acceptance:
- [x] New sprint code has a clear home that is not mixed into old experiments.
- [x] JSON artwork assets remain available through a small loader or documented migration path.
- [ ] Anything useful that is not ported yet is named in the deferred inventory instead of silently lost.

## 0.5. Legacy Content Review

- [ ] Review `legacy/main.py` as an architecture reference, not as code to directly merge.
- [ ] Review `legacy/data/venues.json` for town service locations: Shop, Hall, Inn, Alchemist, Temple, Smithy, Portal.
- [ ] Review `legacy/data/scenes.json` for scene concepts: Town, Forest, Title.
- [ ] Review `legacy/data/stories.json` for high-level arcs: intro arc and portal arc.
- [ ] Review `legacy/data/quests.json`, `quest_events.json`, and `quest_objectives.json` for future quest/event data design.
- [ ] Review `legacy/data/continents.json` and `elements.json` for later world-region progression.
- [ ] Review `legacy/data/npcs.json`, `followers.json`, `characters.json`, `players.json`, and `opponents.json` for recruitable characters and encounter ideas.
- [ ] Review `legacy/data/text.json`, `commands.json`, and `menus.json` for reusable wording and command vocabulary.

Acceptance:
- [ ] The first playable prototype still follows the `ui_v08.py` Mushy/Sharoom/Roomy/Hawking path.
- [ ] Legacy lore is represented as a future content backlog, not allowed to balloon the sprint.
- [ ] The prototype architecture leaves room for legacy venues, quests, and portal/continent progression to come back later.

## 1. Create Sprint Prototype

- [x] Add `world_story_v01.py` as the English-only integration prototype.
- [ ] Make `world_story_v01.py` delegate to `prototype/world_story/main.py` or an equivalent clean entrypoint.
- [ ] Start from the `travel_v01.py` runtime loop instead of `ui_v08.py`.
- [ ] Preserve arrow-key movement, camera scrolling, road constraints, avatar animation, clouds, houses, crows, pebbles, and existing terminal cleanup behavior.
- [x] Remove or disable language variants for this prototype.
- [x] Keep `ui_v08.py` intact as the reference implementation until the new prototype is playable.

Acceptance:
- [x] `python3 world_story_v01.py` launches into the `travel_v01.py` travel world.
- [ ] The player can walk/strafe exactly as in `travel_v01.py`.
- [ ] No `ui_v08.py` menu/title flow is required before entering the world.

## 2. Define Story State

- [x] Add a small `story_state` dict or dataclass owned by `world_story_v01.py`.
- [x] Track `story_stage`.
- [x] Track completed trigger ids.
- [x] Track party members: `player`, `mushy`, `sharoom`, `roomy`.
- [x] Track inventory/story flags: `mycostaff`, `hawking_feather`, `hawking_feather_owner`, `summon_hawking_unlocked`.
- [x] Track current objective text.
- [x] Track battle state handoff fields copied from `ui_v08.py` only as needed.

Suggested initial fields:

```python
story_state = {
    "stage": "find_mushy",
    "completed_triggers": set(),
    "party": ["player"],
    "items": [],
    "current_objective": "Follow the road and investigate the commotion.",
    "hawking_feather_owner": "",
    "summon_hawking_unlocked": False,
}
```

Acceptance:
- [x] Story progress is data/state driven, not inferred only from screen names.
- [x] A single state object can answer: where should the player go next, who is in the party, and what has been completed?

## 3. Add Trigger Model

- [x] Add a simple trigger registry near the top of `world_story_v01.py`.
- [x] Each trigger should define: `id`, required stage, world position or address, radius, prompt text, dialog ids, completion action.
- [x] Trigger only when the player is close enough and presses `a`.
- [x] Display a compact prompt such as `[A Talk]` or `[A Investigate]` when in range.
- [x] Prevent completed triggers from firing again unless explicitly repeatable.

Suggested trigger route:

- [x] `mushy_commotion`: knock at `#10 Ave A`; starts Mushy/crow intro and stage 1 street fight.
- [ ] `second_crow_ambush`: farther down the road; teaches staff charges and Mushroom Tea.
- [x] `sharoom_house`: knock at `#9 Ave A`; recruits Sharoom.
- [x] `roomy_house`: knock at `#8 Ave A`; recruits Roomy.
- [ ] `hawking_crossroad`: open crossroad/clearing; starts Hawking miniboss.
- [ ] `fairy_roadblock`: after Hawking Feather assignment; starts fairy battle.

Acceptance:
- [x] Walking near a story location shows a prompt.
- [x] Pressing `a` opens the correct story interaction.
- [ ] Leaving and returning does not retrigger completed one-shot events.

## 4. Dialog Overlay

- [x] Extract or recreate a minimal dialog box renderer for travel mode.
- [ ] Use English text from `ui_v08.py` story screens.
- [x] Support speaker/title, body text, and action labels.
- [x] Freeze player movement while dialog is open.
- [x] Advance dialog with `a`.
- [ ] Cancel/back only where the flow explicitly allows it.

Dialog source map:

- [ ] Mushy intro: `story_1`, `story_4`, `story_5`, `story_6`.
- [ ] More crows tutorial: `story_more_crows`, `story_more_crows_2`, `story_more_crows_3`.
- [ ] Sharoom recruitment: `story_sharoom_1` through `story_sharoom_5`.
- [ ] Roomy recruitment: `story_battle_victory`, `story_roomy_2` through `story_roomy_4b`.
- [ ] Hawking intro/post: `story_hawk_intro_1` through `story_hawk_intro_5`, then `story_hawk_post_1` through `story_hawk_post_3`.
- [ ] Post-Hawking fairies: `story_post_hawk_fairy_intro`.

Acceptance:
- [x] Story can be read and advanced in travel mode without entering `ui_v08.main()`.
- [x] Dialog overlay does not corrupt the world render after closing.

## 5. Battle Handoff

- [x] Do not call `ui_v08.main()`.
- [x] Reuse only the needed battle helpers from `ui_v08.py`.
- [x] Keep battle logic from `ui_v08.py`, but replace the battle presentation with an open-world street battle overlay.
- [x] Freeze travel movement during battle, but continue rendering the same `travel_v01.py` world frame.
- [ ] Place party and enemy formations directly on the road, side street, crossroad, or clearing where the story trigger fired.
- [ ] Avoid using the older `ui_v08.py` battle background art or tree styles.
- [x] Reuse `ui_v08.py` stage numbers and party ordering.
- [x] Return a battle result signal/dict to travel mode.

On-map battle presentation:

- [x] Add a battle mode flag/state to the travel loop.
- [x] Add battle formation anchors to story triggers.
- [ ] Project battle actor world positions into screen coordinates each frame.
- [ ] Lock or gently recenter the camera while battle mode is active so both party and enemy groups fit on screen.
- [x] Render party actors on one side of the street/clearing and enemies on the other.
- [x] Overlay command menus and HP/MP HUD on top of the travel world.
- [ ] Use small local action animations over the map: Magic Spark, hit blink, crow flee, melt/defeat, Hawking swoop, Birdcall.
- [x] Resume travel from the same world location after victory or retry.

Required battle stages:

- [x] Stage 1: Player + Mushy vs 1 Baby Crow.
- [ ] Stage 2: Player + Mushy vs 2 Baby Crows.
- [ ] Stage 3: Sharoom + Player + Mushy vs 3 Baby Crows.
- [ ] Stage 4: Sharoom + Player + Mushy + Roomy vs Hawking.
- [ ] Stage 5: Sharoom + Player + Mushy + Roomy vs 5 Baby Fairies.

Acceptance:
- [x] Winning stage 1 advances the travel story state.
- [x] Losing uses a simple retry prompt for the current sprint.
- [ ] Party HP/MP and unlocked abilities persist across travel/battle transitions for the sprint.
- [ ] The world does not visually disappear when a town/street encounter begins.
- [ ] Battle actors are not squeezed into narrow street space; story battle triggers use widened side streets, crossroads, or clearings.

## 6. Party And Ability Unlocks

- [x] After Mushy intro, add `mushy` to the battle party for stage 1.
- [x] After accepting Mycostaff, enable Magic Spark for the player during stage 1.
- [x] After stage 1, increase player MP as in `ui_v08.py`.
- [ ] After stage 2, unlock upgraded Magic Spark behavior as in `ui_v08.py`.
- [ ] After Sharoom recruitment, add `sharoom` and enable Healing Touch.
- [ ] After Roomy recruitment, add `roomy` and enable Concentric.
- [ ] After Hawking victory, show feather assignment menu.
- [ ] Assign Hawking Feather to one party member.
- [ ] Apply +4 Max HP and +4 Max MP to the selected owner.
- [ ] Enable Summon Hawking only on the selected owner.

Acceptance:
- [ ] The party list and battle command menus match the story progression.
- [ ] Hawking is a summon via feather assignment, not a normal walking party member.

## 7. World Placement

- [ ] Choose stable world locations for required story beats.
- [ ] Prefer obvious landmarks: crossroads, house labels, or unique NPCs.
- [ ] Prefer battle-capable landmarks with enough visual room for formations.
- [ ] Widen side streets/crossroads/clearings used for required battle triggers as needed.
- [ ] Add objective text to help the player navigate.
- [ ] Keep trigger distances forgiving.
- [ ] Use visible NPC sprites where possible.

Default first placements:

- [x] Mushy commotion: `#10 Ave A` door knock.
- [ ] Second crow ambush: next crossroad.
- [x] Sharoom: `#9 Ave A`.
- [x] Roomy: `#8 Ave A`.
- [ ] Hawking: a crossroad clearing after Roomy joins.
- [ ] Fairies: roadblock after Hawking Feather assignment.

Acceptance:
- [ ] A tester can follow objectives without knowing exact coordinates.
- [ ] Story locations feel like places in the world, not invisible menu steps.
- [ ] Battle-capable story locations have enough horizontal and vertical space for visible party/enemy groups.

## 8. HUD And Prompts

- [ ] Replace or augment the `travel_v01.py` debug HUD with story-relevant text.
- [ ] Show current objective.
- [ ] Show address/location.
- [ ] Show party summary.
- [ ] Show interaction prompt only when in range.
- [ ] Keep travel controls visible but compact.

Acceptance:
- [ ] The player always knows the next broad task.
- [ ] The HUD does not obscure important world/NPC art.

## 9. Keep Scope Tight

- [ ] English only.
- [ ] One new prototype file is acceptable.
- [ ] No save/load requirement for this sprint.
- [ ] No web/Pyodide requirement for this sprint.
- [ ] No full data-driven quest JSON requirement yet.
- [ ] No refactor into the current `app/` OO skeleton yet.
- [ ] No multilingual sync until the English prototype proves the flow.

Acceptance:
- [ ] The sprint produces a playable migration prototype, not a final engine architecture.

## 10. Verification

- [x] Run `python3 -m py_compile world_story_v01.py`.
- [x] Run `python3 world_story_v01.py` in a terminal at least 100x30.
- [ ] Walk from start to Mushy trigger.
- [ ] Complete stage 1 battle and return to travel.
- [ ] Complete stage 2 battle and reach Sharoom.
- [ ] Recruit Sharoom and complete stage 3.
- [ ] Recruit Roomy and start Hawking battle.
- [ ] Defeat Hawking and assign Hawking Feather.
- [ ] Confirm Summon Hawking appears only for the selected owner.
- [ ] Trigger fairy roadblock and start stage 5.
- [ ] Confirm terminal input does not echo arrow escape text.

## 11. Future Cleanup After Sprint

- [ ] Extract common terminal input helpers.
- [ ] Extract common dialog box rendering.
- [ ] Extract battle state and battle renderer from `ui_v08.py`.
- [ ] Move story trigger data to JSON or a small Python data module.
- [ ] Decide which legacy venues should become open-world locations.
- [ ] Decide which legacy quest arcs should merge with or follow the Mushy/Sharoom/Roomy/Hawking path.
- [ ] Decide which preserved JSON art assets should be copied, normalized, or replaced.
- [ ] Port the proven English flow to Spanish and Portuguese variants.
- [ ] Decide whether the prototype should enter the `app/` scene system or remain standalone.

## 12. Dropped Or Deferred Inventory

- [ ] Legacy town venue screens are deferred until the open-world path is playable.
- [ ] Legacy quest/fusion/portal systems are deferred until the sprint prototype has stable travel, triggers, dialog, and on-map battles.
- [ ] Legacy save/load, audio, shop, temple, alchemist, smithy, asset explorer, and title flows are deferred.
- [ ] Multilingual variants are deferred until the English prototype proves the flow.
- [ ] Any additional omitted art, lore, or mechanics discovered during migration should be added here before implementation moves past them.
