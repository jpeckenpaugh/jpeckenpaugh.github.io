"""Main loop helpers for the game runtime."""

import random
import time
from typing import Optional

from app.commands.keymap import map_key_to_command
from app.commands.registry import CommandContext, dispatch_command
from app.commands.router import CommandState, handle_boost_confirm, handle_command
from app.commands.scene_commands import scene_commands
from app.combat import battle_action_delay, cast_spell, primary_opponent_index, roll_damage
from app.state import GameState
from app.ui.ansi import ANSI
from app.ui.rendering import (
    animate_battle_end,
    animate_battle_start,
    animate_spell_overlay,
    flash_opponent,
    melt_opponent,
    render_scene_frame,
)
from app.ui.text import format_text


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
        state.inventory_mode,
        state.inventory_items,
        state.hall_mode,
        state.hall_view,
        state.inn_mode,
        state.spell_mode,
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
    return read_keypress()


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
            color_map_override=ctx.colors.all(),
            flash_index=flash_index,
            flash_color=ANSI.FG_YELLOW,
            suppress_actions=True,
            show_target_prompt=True,
        )
        ch = read_keypress_timeout(0.4)
        if ch is None:
            blink_on = not blink_on
            continue
        if ch in ("ENTER", "\r", "\n"):
            state.target_select = False
            return state.target_command
        if ch in ("LEFT", "RIGHT"):
            direction = -1 if ch == "LEFT" else 1
            state.target_index = _advance_index(indices, state.target_index, direction)
            continue
        if ch.lower() == "b":
            state.target_select = False
            state.target_command = None
            state.target_index = None
            return None
    return None


def available_commands_for_state(ctx, state: GameState) -> Optional[list]:
    if state.title_mode:
        title_scene = ctx.scenes.get("title", {})
        if getattr(state.player, "title_confirm", False):
            return title_scene.get("confirm_commands", [])
        return scene_commands(
            ctx.scenes,
            ctx.commands_data,
            "title",
            state.player,
            state.opponents
        )
    if state.inn_mode:
        venue = ctx.venues.get("town_inn", {})
        return venue.get("commands", [])
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
            state.opponents
        )
    return None


def map_input_to_command(ctx, state: GameState, ch: str) -> tuple[Optional[str], Optional[dict]]:
    available_commands = available_commands_for_state(ctx, state)
    cmd = map_key_to_command(ch, available_commands)
    command_meta = None
    if available_commands and cmd:
        command_meta = next(
            (entry for entry in available_commands if entry.get("command") == cmd),
            None
        )
    return cmd, command_meta


def maybe_begin_target_select(ctx, state: GameState, cmd: Optional[str]) -> bool:
    if not cmd:
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
        inventory_mode=state.inventory_mode,
        inventory_items=state.inventory_items,
        hall_mode=state.hall_mode,
        hall_view=state.hall_view,
        inn_mode=state.inn_mode,
        spell_mode=state.spell_mode,
        action_cmd=action_cmd,
        target_index=state.target_index,
    )
    if not handle_command(cmd, cmd_state, ctx.router_ctx, key=ch):
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
    state.inventory_mode = cmd_state.inventory_mode
    state.inventory_items = cmd_state.inventory_items
    state.hall_mode = cmd_state.hall_mode
    state.hall_view = cmd_state.hall_view
    state.inn_mode = cmd_state.inn_mode
    state.spell_mode = cmd_state.spell_mode
    action_cmd = cmd_state.action_cmd
    target_index = cmd_state.target_index
    if state.player.location == "Title" and cmd_state.player.location != "Title":
        state.title_mode = False
    state.player = cmd_state.player
    if command_meta and command_meta.get("anim") == "battle_start" and state.opponents:
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
            color_map_override=ctx.colors.all()
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
    spell_entry = ctx.spells.by_command_id(cmd)
    if spell_entry:
        spell_id, spell = spell_entry
        name = spell.get("name", spell_id.title())
        if spell.get("requires_target") and not any(opponent.hp > 0 for opponent in state.opponents):
            state.last_message = "There is nothing to target."
            return None
        if spell_id == "healing" and state.player.hp == state.player.max_hp:
            state.last_message = "Your HP is already full."
            return None
        mp_cost = int(spell.get("mp_cost", 2))
        boosted_mp_cost = int(spell.get("boosted_mp_cost", mp_cost))
        if state.player.mp < mp_cost:
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
        )
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
    message = _status_message(state, None)
    target_index = state.target_index
    if target_index is None:
        target_index = primary_opponent_index(state.opponents)
    spell_entry = ctx.spells.by_command_id(action_cmd) if action_cmd else None
    effect = None
    if spell_entry:
        _, spell = spell_entry
        effect = spell.get("effect") if isinstance(spell, dict) else None
    if isinstance(effect, dict) and effect.get("type") == "overlay":
        animate_spell_overlay(
            ctx.scenes,
            ctx.commands_data,
            "forest",
            state.player,
            state.opponents,
            message,
            target_index,
            effect,
            objects_data=ctx.objects,
            color_map_override=ctx.colors.all()
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
            color_map_override=ctx.colors.all()
        )
    defeated_indices = [
        i for i, m in enumerate(state.opponents)
        if m.hp <= 0 and not m.melted
    ]
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
            color_map_override=ctx.colors.all()
        )
        state.opponents[index].melted = True


def run_opponent_turns(ctx, render_frame, state: GameState, generate_frame, action_cmd: Optional[str]) -> bool:
    if action_cmd not in ctx.combat_actions or not any(opponent.hp > 0 for opponent in state.opponents):
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
            damage, crit, miss = roll_damage(m.atk, state.player.defense)
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
        animate_battle_end(
            ctx.scenes,
            ctx.commands_data,
            "forest",
            state.player,
            state.opponents,
            state.last_message,
            objects_data=ctx.objects,
            color_map_override=ctx.colors.all()
        )
    state.opponents = []
    state.battle_log = []
    if state.loot_bank["xp"] or state.loot_bank["gold"]:
        state.player.gain_xp(state.loot_bank["xp"])
        state.player.gold += state.loot_bank["gold"]
        push_battle_message(state, (
            f"You gain {state.loot_bank['xp']} XP and "
            f"{state.loot_bank['gold']} gold."
        ))
        if state.player.needs_level_up():
            state.leveling_mode = True
        push_battle_message(state, "All is quiet. No enemies in sight.")
    else:
        state.last_message = ""
        push_battle_message(state, "All is quiet. No enemies in sight.")
    state.loot_bank = {"xp": 0, "gold": 0}
