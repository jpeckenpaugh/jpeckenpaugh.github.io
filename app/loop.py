"""Main loop helpers for the game runtime."""

import random
import time
from typing import Optional

from app.commands.registry import CommandContext, dispatch_command
from app.commands.router import CommandState, handle_boost_confirm, handle_command
from app.commands.scene_commands import command_is_enabled, scene_commands
from app.combat import battle_action_delay, cast_spell, primary_opponent_index, roll_damage
from app.state import GameState
from app.ui.ansi import ANSI
from app.ui.constants import ACTION_LINES
from app.ui.rendering import (
    animate_battle_end,
    animate_battle_start,
    animate_spell_overlay,
    animate_spell_overlay_multi,
    element_color_map,
    flash_opponent,
    melt_opponent,
    melt_opponents_multi,
    render_scene_frame,
)
from app.ui.text import format_text
from app.shop import shop_commands


def _spell_effect_with_art(ctx, spell: dict) -> Optional[dict]:
    if not isinstance(spell, dict):
        return None
    effect = spell.get("effect")
    if not isinstance(effect, dict):
        return None
    effect_override = dict(effect)
    art_id = effect_override.get("art_id")
    if art_id and hasattr(ctx, "spells_art"):
        art = ctx.spells_art.get(art_id)
        if isinstance(art, dict):
            merged = dict(art)
            merged.update(effect_override)
            effect_override = merged
    element = spell.get("element")
    if element and hasattr(ctx, "elements"):
        colors = ctx.elements.colors_for(element)
        if len(colors) >= 3:
            effect_override["color_map"] = {"1": colors[0], "2": colors[1], "3": colors[2]}
            effect_override["color_key"] = colors[0]
    return effect_override


def _status_message(state: GameState, message: Optional[str]) -> str:
    if message is not None:
        return message
    if state.player.location == "Forest" and state.battle_log:
        return "\n".join(state.battle_log)
    return state.last_message


def render_frame_state(ctx, render_frame, state: GameState, generate_frame, message: Optional[str] = None, suppress_actions: bool = False) -> None:
    frame = generate_frame(
        ctx.screen_ctx,
        state.player,
        state.opponents,
        _status_message(state, message),
        state.leveling_mode,
        state.shop_mode,
        state.shop_view,
        state.inventory_mode,
        state.inventory_items,
        state.hall_mode,
        state.hall_view,
        state.inn_mode,
        state.spell_mode,
        state.element_mode,
        state.alchemist_mode,
        state.alchemy_first,
        state.temple_mode,
        state.smithy_mode,
        state.portal_mode,
        state.options_mode,
        state.action_cursor,
        state.menu_cursor,
        state.level_cursor,
        state.level_up_notes,
        suppress_actions=suppress_actions,
    )
    render_frame(frame)


def render_battle_pause(ctx, render_frame, state: GameState, generate_frame, message: str) -> None:
    log_message = "\n".join(state.battle_log) if state.battle_log else message
    render_frame_state(ctx, render_frame, state, generate_frame, message=log_message, suppress_actions=True)
    time.sleep(battle_action_delay(state.player))


def read_boost_prompt_input(ctx, render_frame, state: GameState, generate_frame, read_keypress_timeout) -> str:
    spell_id = state.boost_prompt
    spell_data = ctx.spells.get(spell_id, {})
    prompt_seconds = int(spell_data.get("boost_prompt_seconds", 3))
    default_choice = str(spell_data.get("boost_default", "N")).lower()
    choice = None
    for remaining in range(prompt_seconds, 0, -1):
        countdown_message = f"{state.last_message} ({remaining})"
        render_frame_state(ctx, render_frame, state, generate_frame, message=countdown_message)
        choice = read_keypress_timeout(1.0)
        if choice and choice.lower() in ("y", "n"):
            break
    return choice if choice else default_choice


def read_input(ctx, render_frame, state: GameState, generate_frame, read_keypress, read_keypress_timeout) -> str:
    if state.spell_mode:
        ch = read_keypress_timeout(0.2)
        return ch or ""
    return read_keypress()


def normalize_input_action(ch: str) -> Optional[str]:
    if not ch:
        return None
    if ch in ("UP", "DOWN", "LEFT", "RIGHT"):
        return ch
    if ch in ("ENTER", "\r", "\n"):
        return "START"
    if ch in ("SHIFT", "Shift"):
        return "SELECT"
    lower = ch.lower()
    if lower == "a":
        return "CONFIRM"
    if lower == "s":
        return "BACK"
    return None


def action_grid_dimensions(count: int) -> tuple[int, int]:
    if count <= 3:
        cols = 1
    elif count <= 6:
        cols = 2
    else:
        cols = 3
    return ACTION_LINES, cols


def _find_valid_in_column(row: int, col: int, count: int, rows: int, commands: list[dict]) -> Optional[int]:
    for offset in range(rows):
        candidate_row = (row + offset) % rows
        idx = candidate_row + col * rows
        if idx < count and not commands[idx].get("_disabled"):
            return idx
    return None


def _enabled_indices(commands: list[dict]) -> list[int]:
    return [i for i, cmd in enumerate(commands) if not cmd.get("_disabled")]


def move_action_cursor(index: int, direction: str, commands: list[dict]) -> int:
    count = len(commands)
    if count <= 0:
        return -1
    enabled = _enabled_indices(commands)
    if not enabled:
        return -1
    rows, cols = action_grid_dimensions(count)
    if index not in enabled:
        index = enabled[0]
    row = index % rows
    col = index // rows
    if direction in ("UP", "DOWN"):
        step = -1 if direction == "UP" else 1
        for _ in range(rows):
            row = (row + step) % rows
            candidate = row + col * rows
            if candidate < count and not commands[candidate].get("_disabled"):
                return candidate
        return index
    if direction in ("LEFT", "RIGHT"):
        step = -1 if direction == "LEFT" else 1
        for _ in range(cols):
            col = (col + step) % cols
            candidate = _find_valid_in_column(row, col, count, rows, commands)
            if candidate is not None:
                return candidate
        return index
    return index


def action_commands_for_state(ctx, state: GameState) -> list[dict]:
    if state.title_mode:
        title_scene = ctx.scenes.get("title", {})
        if getattr(state.player, "title_confirm", False):
            return title_scene.get("confirm_commands", [])
        return scene_commands(
            ctx.scenes,
            ctx.commands_data,
            "title",
            state.player,
            state.opponents,
        )
    if state.shop_mode:
        venue = ctx.venues.get("town_shop", {})
        element = getattr(state.player, "current_element", "base")
        return shop_commands(venue, ctx.items, element, state.shop_view, state.player)
    if state.hall_mode:
        venue = ctx.venues.get("town_hall", {})
        return venue.get("commands", [])
    if state.inn_mode:
        venue = ctx.venues.get("town_inn", {})
        return venue.get("commands", [])
    if state.temple_mode:
        venue = ctx.venues.get("town_temple", {})
        return venue.get("commands", [])
    if state.smithy_mode:
        venue = ctx.venues.get("town_smithy", {})
        return venue.get("commands", [])
    if state.inventory_mode or state.spell_mode or state.options_mode or state.element_mode or state.alchemist_mode or state.portal_mode:
        return []
    if not any(
        (
            state.leveling_mode,
            state.shop_mode,
            state.inventory_mode,
            state.hall_mode,
            state.inn_mode,
            state.spell_mode,
            state.boost_prompt,
        )
    ):
        scene_id = "town" if state.player.location == "Town" else "forest"
        return scene_commands(
            ctx.scenes,
            ctx.commands_data,
            scene_id,
            state.player,
            state.opponents,
        )
    return []


def clamp_action_cursor(state: GameState, commands: list[dict]) -> None:
    enabled = _enabled_indices(commands)
    if not commands or not enabled:
        state.action_cursor = -1
        return
    if state.action_cursor not in enabled:
        state.action_cursor = enabled[0]
        return
    state.action_cursor = max(0, min(state.action_cursor, len(commands) - 1))


def spell_menu_keys(ctx, player) -> list[str]:
    entries = ctx.spells.available(player.level)
    return [spell.get("command_id") for _, spell in entries if spell.get("command_id")]


def find_command_meta(commands: list[dict], command_id: Optional[str]) -> Optional[dict]:
    if not command_id:
        return None
    return next((entry for entry in commands if entry.get("command") == command_id), None)

def _alive_indices(opponents) -> list[int]:
    return [i for i, opp in enumerate(opponents) if opp.hp > 0]


def _advance_index(indices: list[int], current: int, direction: int) -> int:
    if not indices:
        return current
    if current not in indices:
        return indices[0]
    pos = indices.index(current)
    next_pos = (pos + direction) % len(indices)
    return indices[next_pos]


def run_target_select(ctx, render_frame, state: GameState, generate_frame, read_keypress_timeout) -> Optional[str]:
    color_override = element_color_map(ctx.colors.all(), state.player.current_element)
    indices = _alive_indices(state.opponents)
    if not indices:
        state.target_select = False
        state.target_command = None
        state.target_index = None
        return None
    if state.target_index not in indices:
        state.target_index = indices[0]
    blink_on = True
    while state.target_select:
        message = "\n".join(state.battle_log)
        flash_index = state.target_index if blink_on else None
        gap_target = ctx.scenes.get("forest", {}).get("gap_width", 0)
        if isinstance(gap_target, str):
            try:
                gap_target = int(gap_target)
            except ValueError:
                gap_target = 0
        render_scene_frame(
            ctx.scenes,
            ctx.commands_data,
            "forest",
            state.player,
            state.opponents,
            message,
            gap_override=gap_target,
            objects_data=ctx.objects,
            color_map_override=color_override,
            flash_index=flash_index,
            flash_color=ANSI.FG_YELLOW,
            suppress_actions=True,
            show_target_prompt=True,
        )
        ch = read_keypress_timeout(0.4)
        if ch is None:
            blink_on = not blink_on
            continue
        if ch in ("ENTER", "\r", "\n", "A", "a"):
            state.target_select = False
            return state.target_command
        if ch in ("LEFT", "RIGHT"):
            direction = -1 if ch == "LEFT" else 1
            state.target_index = _advance_index(indices, state.target_index, direction)
            continue
        if ch.lower() == "s":
            state.target_select = False
            state.target_command = None
            state.target_index = None
            return None
    return None


def map_input_to_command(ctx, state: GameState, ch: str) -> tuple[Optional[str], Optional[dict]]:
    action = normalize_input_action(ch)
    if action is None:
        return None, None

    if action in ("START", "SELECT"):
        if state.options_mode:
            state.options_mode = False
            state.menu_cursor = 0
        else:
            state.options_mode = True
            menu = ctx.menus.get("options", {})
            actions = []
            for entry in menu.get("actions", []):
                if not entry.get("command"):
                    continue
                cmd_entry = dict(entry)
                if not command_is_enabled(cmd_entry, state.player, state.opponents):
                    cmd_entry["_disabled"] = True
                actions.append(cmd_entry)
            enabled = [i for i, cmd in enumerate(actions) if not cmd.get("_disabled")]
            state.menu_cursor = enabled[0] if enabled else -1
            state.inventory_mode = False
            state.spell_mode = False
            state.element_mode = False
            state.alchemist_mode = False
            state.temple_mode = False
            state.smithy_mode = False
            state.portal_mode = False
            state.shop_mode = False
            state.hall_mode = False
            state.inn_mode = False
        return None, None

    if state.leveling_mode:
        options = ["NUM1", "NUM2", "NUM3", "NUM4", "B_KEY", "X_KEY"]
        if action in ("UP", "DOWN"):
            direction = -1 if action == "UP" else 1
            state.level_cursor = (state.level_cursor + direction) % len(options)
            return None, None
        if action == "CONFIRM":
            cmd = options[state.level_cursor]
            return cmd, None
        if action == "BACK":
            return "B_KEY", None
        return None, None

    if state.options_mode:
        menu = ctx.menus.get("options", {})
        actions = []
        for entry in menu.get("actions", []):
            if not entry.get("command"):
                continue
            cmd_entry = dict(entry)
            if not command_is_enabled(cmd_entry, state.player, state.opponents):
                cmd_entry["_disabled"] = True
            actions.append(cmd_entry)
        if not actions:
            return None, None
        enabled = [i for i, cmd in enumerate(actions) if not cmd.get("_disabled")]
        if not enabled:
            state.menu_cursor = -1
        elif state.menu_cursor not in enabled:
            state.menu_cursor = enabled[0]
        else:
            state.menu_cursor = max(0, min(state.menu_cursor, len(actions) - 1))
        if action in ("UP", "DOWN"):
            direction = -1 if action == "UP" else 1
            if enabled:
                pos = enabled.index(state.menu_cursor) if state.menu_cursor in enabled else 0
                pos = (pos + direction) % len(enabled)
                state.menu_cursor = enabled[pos]
            return None, None
        if action == "BACK":
            state.options_mode = False
            return None, None
        if action == "CONFIRM":
            if state.menu_cursor < 0:
                return None, None
            if actions[state.menu_cursor].get("_disabled"):
                return None, None
            cmd = actions[state.menu_cursor].get("command")
            state.options_mode = False
            return cmd, None
        return None, None

    if state.inventory_mode:
        items = state.inventory_items or []
        count = min(len(items), 9)
        if count == 0:
            if action == "BACK":
                return "B_KEY", None
            return None, None
        state.menu_cursor = max(0, min(state.menu_cursor, count - 1))
        if action in ("UP", "DOWN"):
            direction = -1 if action == "UP" else 1
            state.menu_cursor = (state.menu_cursor + direction) % count
            return None, None
        if action == "CONFIRM":
            cmd = f"NUM{state.menu_cursor + 1}"
            return cmd, None
        if action == "BACK":
            return "B_KEY", None
        return None, None

    if state.spell_mode:
        keys = spell_menu_keys(ctx, state.player)
        if not keys:
            if action == "BACK":
                return "B_KEY", None
            return None, None
        state.menu_cursor = max(0, min(state.menu_cursor, len(keys) - 1))
        if action in ("UP", "DOWN"):
            direction = -1 if action == "UP" else 1
            state.menu_cursor = (state.menu_cursor + direction) % len(keys)
            return None, None
        if action == "CONFIRM":
            cmd = keys[state.menu_cursor]
            return cmd, None
        if action == "BACK":
            return "B_KEY", None
        return None, None

    if state.element_mode:
        elements = list(getattr(state.player, "elements", []) or [])
        if hasattr(ctx, "continents"):
            order = list(ctx.continents.order() or [])
            elements = [e for e in order if e in elements] or elements
        if hasattr(ctx, "continents"):
            order = list(ctx.continents.order() or [])
            elements = [e for e in order if e in elements] or elements
        if not elements:
            if action == "BACK":
                return "B_KEY", None
            return None, None
        state.menu_cursor = max(0, min(state.menu_cursor, len(elements) - 1))
        if action in ("UP", "DOWN"):
            direction = -1 if action == "UP" else 1
            state.menu_cursor = (state.menu_cursor + direction) % len(elements)
            return None, None
        if action == "CONFIRM":
            element_id = elements[state.menu_cursor]
            return f"ELEMENT:{element_id}", None
        if action == "BACK":
            return "B_KEY", None
        return None, None

    if state.alchemist_mode:
        gear_items = [g for g in state.player.gear_inventory if isinstance(g, dict)]
        if not gear_items:
            if action == "BACK":
                return "B_KEY", None
            return None, None
        state.menu_cursor = max(0, min(state.menu_cursor, len(gear_items) - 1))
        if action in ("UP", "DOWN"):
            direction = -1 if action == "UP" else 1
            state.menu_cursor = (state.menu_cursor + direction) % len(gear_items)
            return None, None
        if action == "CONFIRM":
            gear_id = gear_items[state.menu_cursor].get("id")
            if gear_id:
                return f"ALCHEMY_PICK:{gear_id}", None
            return None, None
        if action == "BACK":
            return "B_KEY", None
        return None, None

    if state.portal_mode:
        elements = list(getattr(state.player, "elements", []) or [])
        if hasattr(ctx, "continents"):
            order = list(ctx.continents.order() or [])
            elements = [e for e in order if e in elements] or elements
        if hasattr(ctx, "continents"):
            order = list(ctx.continents.order() or [])
            elements = [e for e in order if e in elements] or elements
        if not elements:
            if action == "BACK":
                return "B_KEY", None
            return None, None
        state.menu_cursor = max(0, min(state.menu_cursor, len(elements) - 1))
        if action in ("UP", "DOWN"):
            direction = -1 if action == "UP" else 1
            state.menu_cursor = (state.menu_cursor + direction) % len(elements)
            return None, None
        if action == "CONFIRM":
            element_id = elements[state.menu_cursor]
            return f"PORTAL:{element_id}", None
        if action == "BACK":
            return "B_KEY", None
        return None, None

    commands = action_commands_for_state(ctx, state)
    clamp_action_cursor(state, commands)
    if action in ("UP", "DOWN", "LEFT", "RIGHT"):
        state.action_cursor = move_action_cursor(state.action_cursor, action, commands)
        return None, None
    if action == "BACK":
        cmd = "B_KEY"
        command_meta = find_command_meta(commands, cmd)
        return cmd if command_meta else None, command_meta
    if action == "CONFIRM":
        if not commands or state.action_cursor < 0:
            return None, None
        command_meta = commands[state.action_cursor]
        if command_meta.get("_disabled"):
            return None, None
        cmd = command_meta.get("command")
        return cmd, command_meta
    return None, None


def maybe_begin_target_select(ctx, state: GameState, cmd: Optional[str]) -> bool:
    if not cmd:
        return False
    if cmd in ctx.targeted_spell_commands:
        spell_entry = ctx.spells.by_command_id(cmd)
        if spell_entry:
            _, spell = spell_entry
            rank = ctx.spells.rank_for(spell, state.player.level)
            if rank >= 2:
                return False
    targeted = cmd == "ATTACK" or cmd in ctx.targeted_spell_commands
    if not targeted:
        return False
    indices = _alive_indices(state.opponents)
    if not indices:
        return False
    state.target_select = True
    state.target_command = cmd
    if state.target_index not in indices:
        state.target_index = indices[0]
    return True


def push_battle_message(state: GameState, message: str, max_lines: int = 7) -> None:
    state.last_message = message
    if state.player.location != "Forest":
        return
    if message:
        if state.battle_log and state.battle_log[-1] == message:
            return
        if not state.battle_log and _is_arrival_message(state, message):
            return
        state.battle_log.append(message)
        if len(state.battle_log) > max_lines:
            state.battle_log = state.battle_log[-max_lines:]


def _is_arrival_message(state: GameState, message: str) -> bool:
    if message == "Opponents emerge from the forest.":
        return True
    if message.startswith("A ") and message.endswith("."):
        return True
    return False


def spell_level_up_notes(ctx, prev_level: int, new_level: int) -> list[str]:
    notes = []
    for _, spell in ctx.spells.available(new_level):
        name = spell.get("name", "Spell")
        old_rank = ctx.spells.rank_for(spell, prev_level)
        new_rank = ctx.spells.rank_for(spell, new_level)
        if old_rank == 0 and new_rank > 0:
            notes.append(f"New spell: {name} (Rank {new_rank})")
        elif new_rank > old_rank:
            notes.append(f"{name} rank up: {old_rank} → {new_rank}")
    return notes


def element_unlock_notes(ctx, player, prev_level: int, new_level: int) -> list[str]:
    unlocks = {}
    if hasattr(ctx, "continents"):
        unlocks = ctx.continents.unlocks() if hasattr(ctx.continents, "unlocks") else {}
    if not unlocks:
        unlocks = ctx.spells.element_unlocks()
    notes = []
    order = []
    if hasattr(ctx, "continents"):
        order = list(ctx.continents.order() or [])
    if not order:
        order = ["base"]
    for element, level_required in unlocks.items():
        if prev_level < level_required <= new_level:
            element_name = ctx.continents.name_for(element) if hasattr(ctx, "continents") else element.title()
            if element not in player.elements:
                player.elements.append(element)
            notes.append(f"Element unlocked: {element_name}")
    if not player.elements:
        player.elements.append(order[0])
    if order:
        player.elements = [e for e in order if e in player.elements]
    return notes


def apply_boost_confirm(ctx, state: GameState, ch: str, action_cmd: Optional[str]) -> tuple[bool, Optional[str], bool]:
    return False, action_cmd, False


def apply_router_command(
    ctx,
    state: GameState,
    cmd: Optional[str],
    ch: str,
    command_meta: Optional[dict],
    action_cmd: Optional[str],
) -> tuple[bool, Optional[str], Optional[str], bool, Optional[int]]:
    if not cmd:
        return False, action_cmd, cmd, False, None
    pre_in_forest = state.player.location == "Forest"
    pre_alive = any(m.hp > 0 for m in state.opponents)
    cmd_state = CommandState(
        player=state.player,
        opponents=state.opponents,
        loot_bank=state.loot_bank,
        last_message=state.last_message,
        shop_mode=state.shop_mode,
        shop_view=state.shop_view,
        inventory_mode=state.inventory_mode,
        inventory_items=state.inventory_items,
        hall_mode=state.hall_mode,
        hall_view=state.hall_view,
        inn_mode=state.inn_mode,
        spell_mode=state.spell_mode,
        element_mode=state.element_mode,
        alchemist_mode=state.alchemist_mode,
        alchemy_first=state.alchemy_first,
        temple_mode=state.temple_mode,
        smithy_mode=state.smithy_mode,
        portal_mode=state.portal_mode,
        options_mode=state.options_mode,
        action_cmd=action_cmd,
        target_index=state.target_index,
        command_target_override=command_meta.get("target") if command_meta else None,
        command_service_override=command_meta.get("service_id") if command_meta else None,
    )
    if not handle_command(cmd, cmd_state, ctx.router_ctx, key=None):
        return False, action_cmd, cmd, False, None
    state.opponents = cmd_state.opponents
    state.loot_bank = cmd_state.loot_bank
    post_in_forest = state.player.location == "Forest"
    post_alive = any(m.hp > 0 for m in state.opponents)
    if not pre_in_forest and post_in_forest:
        state.battle_log = []
    if pre_in_forest and not post_in_forest:
        state.battle_log = []
    if post_in_forest and post_alive and not pre_alive:
        state.battle_log = []
    push_battle_message(state, cmd_state.last_message)
    state.shop_mode = cmd_state.shop_mode
    state.shop_view = cmd_state.shop_view
    state.inventory_mode = cmd_state.inventory_mode
    state.inventory_items = cmd_state.inventory_items
    state.hall_mode = cmd_state.hall_mode
    state.hall_view = cmd_state.hall_view
    state.inn_mode = cmd_state.inn_mode
    state.spell_mode = cmd_state.spell_mode
    state.element_mode = cmd_state.element_mode
    state.alchemist_mode = cmd_state.alchemist_mode
    state.alchemy_first = cmd_state.alchemy_first
    state.temple_mode = cmd_state.temple_mode
    state.smithy_mode = cmd_state.smithy_mode
    state.portal_mode = cmd_state.portal_mode
    action_cmd = cmd_state.action_cmd
    target_index = cmd_state.target_index
    if state.player.location == "Title" and cmd_state.player.location != "Title":
        state.title_mode = False
    state.player = cmd_state.player
    if command_meta and command_meta.get("anim") == "battle_start" and state.opponents:
        color_override = element_color_map(ctx.colors.all(), state.player.current_element)
        if not state.battle_log and _is_arrival_message(state, state.last_message):
            state.last_message = ""
        animate_battle_start(
            ctx.scenes,
            ctx.commands_data,
            "forest",
            state.player,
            state.opponents,
            state.last_message,
            objects_data=ctx.objects,
            color_map_override=color_override
        )
    if action_cmd not in ctx.combat_actions:
        return True, action_cmd, cmd, True, target_index
    if action_cmd in ctx.spell_commands:
        return False, action_cmd, action_cmd, False, target_index
    return False, action_cmd, cmd, False, target_index


def resolve_player_action(
    ctx,
    state: GameState,
    cmd: Optional[str],
    command_meta: Optional[dict],
    action_cmd: Optional[str],
    handled_boost: bool,
    handled_by_router: bool,
) -> Optional[str]:
    if handled_boost or handled_by_router:
        return action_cmd
    if cmd != "DEFEND":
        state.defend_active = False
        state.defend_bonus = 0
        state.defend_evasion = 0.0
        state.action_effect_override = None
        state.last_spell_targets = []
    if cmd == "DEFEND":
        alive = [opp for opp in state.opponents if opp.hp > 0]
        highest = max((opp.level for opp in alive), default=state.player.level)
        lower_level = highest < state.player.level
        defense_bonus = max(2, state.player.total_defense() // 2)
        evasion_bonus = 0.15 if lower_level else 0.05
        state.defend_active = True
        state.defend_bonus = defense_bonus
        state.defend_evasion = evasion_bonus
        push_battle_message(state, "You brace for impact.")
        return cmd
    spell_entry = ctx.spells.by_command_id(cmd)
    if spell_entry:
        spell_id, spell = spell_entry
        name = spell.get("name", spell_id.title())
        rank = ctx.spells.rank_for(spell, state.player.level)
        if rank >= 2:
            state.last_spell_targets = [
                i for i, opp in enumerate(state.opponents) if opp.hp > 0
            ]
        else:
            if state.target_index is not None:
                state.last_spell_targets = [state.target_index]
        if spell.get("requires_target") and not any(opponent.hp > 0 for opponent in state.opponents):
            state.last_message = "There is nothing to target."
            return None
        if spell_id == "healing" and state.player.hp == state.player.max_hp:
            state.last_message = "Your HP is already full."
            return None
        mp_cost = int(spell.get("mp_cost", 2))
        boosted_mp_cost = int(spell.get("boosted_mp_cost", mp_cost))
        element = spell.get("element")
        has_charge = False
        if element:
            charges = state.player.wand_charges()
            has_charge = int(charges.get(str(element), 0)) > 0
        if state.player.mp < mp_cost and not has_charge:
            state.last_message = f"Not enough MP to cast {name}."
            return None
        if state.player.mp >= boosted_mp_cost:
            pass
        message = cast_spell(
            state.player,
            state.opponents,
            spell_id,
            boosted=False,
            loot=state.loot_bank,
            spells_data=ctx.spells,
            target_index=state.target_index,
            rank=rank,
        )
        effect_override = _spell_effect_with_art(ctx, spell) if isinstance(spell, dict) else None
        if isinstance(effect_override, dict):
            if rank >= 3:
                rank3_key = spell.get("overlay_color_key_rank3")
                if rank3_key:
                    effect_override["color_key"] = rank3_key
            elif rank >= 2:
                rank2_key = spell.get("overlay_color_key_rank2")
                if rank2_key:
                    effect_override["color_key"] = rank2_key
            loops = effect_override.get("loops")
            if rank >= 3 and spell.get("effect_loops_rank3") is not None:
                loops = spell.get("effect_loops_rank3")
            elif rank >= 2 and spell.get("effect_loops_rank2") is not None:
                loops = spell.get("effect_loops_rank2")
            if loops is not None:
                effect_override["loops"] = loops
            state.action_effect_override = effect_override
        push_battle_message(state, message)
        return cmd

    message = dispatch_command(
        ctx.registry,
        cmd,
        CommandContext(
            player=state.player,
            opponents=state.opponents,
            loot=state.loot_bank,
            spells_data=ctx.spells,
            items_data=ctx.items,
            target_index=state.target_index,
        ),
    )
    push_battle_message(state, message)
    if command_meta and command_meta.get("type") == "combat":
        return cmd
    if command_meta and command_meta.get("anim") == "battle_start":
        return cmd
    return action_cmd


def handle_offensive_action(ctx, state: GameState, action_cmd: Optional[str]) -> None:
    if action_cmd not in ctx.offensive_actions:
        return
    color_override = element_color_map(ctx.colors.all(), state.player.current_element)
    message = _status_message(state, None)
    target_index = state.target_index
    if target_index is None:
        target_index = primary_opponent_index(state.opponents)
    spell_entry = ctx.spells.by_command_id(action_cmd) if action_cmd else None
    effect = None
    spell = None
    rank = 1
    if spell_entry:
        _, spell = spell_entry
        rank = ctx.spells.rank_for(spell, state.player.level)
        effect = _spell_effect_with_art(ctx, spell) if isinstance(spell, dict) else None
    if state.action_effect_override:
        effect = state.action_effect_override
    if isinstance(effect, dict) and effect.get("type") == "overlay":
        targets = state.last_spell_targets or [i for i, opp in enumerate(state.opponents) if opp.hp > 0]
        if spell and rank >= 3:
            effect_override = dict(effect)
            effect_override["loops"] = 3
            animate_spell_overlay_multi(
                ctx.scenes,
                ctx.commands_data,
                "forest",
                state.player,
                state.opponents,
                message,
                targets,
                effect_override,
                objects_data=ctx.objects,
                color_map_override=color_override
            )
        elif spell and rank >= 2:
            for idx in targets:
                effect_override = dict(effect)
                effect_override["loops"] = 1
                animate_spell_overlay(
                    ctx.scenes,
                    ctx.commands_data,
                    "forest",
                    state.player,
                    state.opponents,
                    message,
                    idx,
                    effect_override,
                    objects_data=ctx.objects,
                    color_map_override=color_override
                )
        else:
            animate_spell_overlay(
                ctx.scenes,
                ctx.commands_data,
                "forest",
                state.player,
                state.opponents,
                message,
                targets[0] if targets else target_index,
                effect,
                objects_data=ctx.objects,
                color_map_override=color_override
            )
    else:
        flash_opponent(
            ctx.scenes,
            ctx.commands_data,
            "forest",
            state.player,
            state.opponents,
            message,
            target_index,
            ANSI.FG_YELLOW,
            objects_data=ctx.objects,
            color_map_override=color_override
        )
    state.action_effect_override = None
    defeated_indices = [
        i for i, m in enumerate(state.opponents)
        if m.hp <= 0 and not m.melted
    ]
    if len(defeated_indices) > 1:
        melt_opponents_multi(
            ctx.scenes,
            ctx.commands_data,
            "forest",
            state.player,
            state.opponents,
            message,
            defeated_indices,
            objects_data=ctx.objects,
            color_map_override=color_override
        )
        for index in defeated_indices:
            state.opponents[index].melted = True
    else:
        for index in defeated_indices:
            melt_opponent(
                ctx.scenes,
                ctx.commands_data,
                "forest",
                state.player,
                state.opponents,
                message,
                index,
                objects_data=ctx.objects,
                color_map_override=color_override
            )
            state.opponents[index].melted = True


def run_opponent_turns(ctx, render_frame, state: GameState, generate_frame, action_cmd: Optional[str]) -> bool:
    if action_cmd not in ctx.combat_actions or not any(opponent.hp > 0 for opponent in state.opponents):
        return False
    if action_cmd == "FLEE":
        return False
    if state.player.location == "Forest":
        render_battle_pause(ctx, render_frame, state, generate_frame, _status_message(state, None))
    acting = [(i, m) for i, m in enumerate(state.opponents) if m.hp > 0]
    for idx, (opp_index, m) in enumerate(acting):
        if m.stunned_turns > 0:
            m.stunned_turns -= 1
            template = ctx.texts.get("battle", "opponent_stunned", "The {name} is stunned.")
            push_battle_message(state, format_text(template, name=m.name))
        elif random.random() > m.action_chance:
            template = ctx.texts.get("battle", "opponent_hesitates", "The {name} hesitates.")
            push_battle_message(state, format_text(template, name=m.name))
        else:
            defense_value = state.player.total_defense() + state.defend_bonus
            damage, crit, miss = roll_damage(m.atk, defense_value)
            if not miss:
                element = getattr(m, "element", "base")
                if element and element != "base":
                    block = state.player.element_points_total(str(element), slots=["shield", "armor"])
                    damage = max(1, damage - int(block))
            if miss:
                template = ctx.texts.get("battle", "opponent_miss", "The {name} misses you.")
                push_battle_message(state, format_text(template, name=m.name))
            else:
                state.player.hp = max(0, state.player.hp - damage)
                if crit:
                    template = ctx.texts.get("battle", "opponent_crit", "Critical hit! The {name} hits you for {damage}.")
                    push_battle_message(state, format_text(template, name=m.name, damage=damage))
                else:
                    template = ctx.texts.get("battle", "opponent_hit", "The {name} hits you for {damage}.")
                    push_battle_message(state, format_text(template, name=m.name, damage=damage))
            flash_opponent(
                ctx.scenes,
                ctx.commands_data,
                "forest",
                state.player,
                state.opponents,
                _status_message(state, None),
                opp_index,
                ANSI.FG_RED,
                objects_data=ctx.objects,
                color_map_override=ctx.colors.all()
            )
            if state.player.hp == 0:
                lost_gp = state.player.gold // 2
                state.player.gold -= lost_gp
                state.player.location = "Town"
                state.player.hp = state.player.max_hp
                state.player.mp = state.player.max_mp
                state.opponents = []
                state.loot_bank = {"xp": 0, "gold": 0}
                push_battle_message(state, (
                    "You were defeated and wake up at the inn. "
                    f"You lost {lost_gp} GP."
                ))
                return True
        if state.player.location == "Forest" and idx < len(acting) - 1:
            render_battle_pause(ctx, render_frame, state, generate_frame, state.last_message)
    return False


def handle_battle_end(ctx, state: GameState, action_cmd: Optional[str]) -> None:
    if action_cmd not in ctx.offensive_actions:
        return
    if any(opponent.hp > 0 for opponent in state.opponents):
        return
    if ctx.battle_end_commands:
        color_override = element_color_map(ctx.colors.all(), state.player.current_element)
        animate_battle_end(
            ctx.scenes,
            ctx.commands_data,
            "forest",
            state.player,
            state.opponents,
            state.last_message,
            objects_data=ctx.objects,
            color_map_override=color_override
        )
    state.opponents = []
    state.battle_log = []
    if state.loot_bank["xp"] or state.loot_bank["gold"]:
        pre_level = state.player.level
        state.player.gain_xp(state.loot_bank["xp"])
        state.player.gold += state.loot_bank["gold"]
        push_battle_message(state, (
            f"You gain {state.loot_bank['xp']} XP and "
            f"{state.loot_bank['gold']} gold."
        ))
        if state.player.needs_level_up():
            state.leveling_mode = True
            spell_notes = spell_level_up_notes(ctx, pre_level, state.player.level)
            element_notes = element_unlock_notes(ctx, state.player, pre_level, state.player.level)
            state.level_up_notes = spell_notes + element_notes
        push_battle_message(state, "All is quiet. No enemies in sight.")
    else:
        state.last_message = ""
        push_battle_message(state, "All is quiet. No enemies in sight.")
    state.loot_bank = {"xp": 0, "gold": 0}
