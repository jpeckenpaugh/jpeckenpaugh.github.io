"""Main loop helpers for the game runtime."""

import random
import time
from typing import Optional
import json

from app.commands.registry import CommandContext, dispatch_command
from app.commands.router import CommandState, handle_command
from app.commands.scene_commands import command_is_enabled, scene_commands
from app.combat import battle_action_delay, cast_spell, primary_opponent_index, roll_damage, try_stun
from app.questing import build_follower_from_entry, evaluate_quests, handle_event, ordered_quest_ids, quest_entries, start_quest
from app.state import GameState
from app.models import Player
from app.ui.ansi import ANSI
from app.ui.constants import ACTION_LINES, SCREEN_HEIGHT
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
from app.venues import venue_actions, venue_id_from_state


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
    if hasattr(ctx, "audio"):
        audio_key = None
        if state.quest_detail_mode:
            audio_key = f"quest_detail:{state.quest_detail_id}"
        elif state.quest_mode:
            audio_key = "quest_list"
        elif state.player.location == "Town" and not state.title_mode:
            audio_key = "town"
        if audio_key and audio_key != state.screen_audio_key:
            if audio_key == "quest_list":
                ctx.audio.play_song_once("quest_open")
            elif audio_key.startswith("quest_detail:"):
                order = []
                if hasattr(ctx, "continents"):
                    order = list(ctx.continents.order() or [])
                first = order[0] if order else "base"
                if getattr(state.player, "current_element", "base") == first:
                    ctx.audio.play_song_once("continent_1_quest")
            elif audio_key == "town":
                order = []
                if hasattr(ctx, "continents"):
                    order = list(ctx.continents.order() or [])
                first = order[0] if order else "base"
                if getattr(state.player, "current_element", "base") == first:
                    ctx.audio.play_song_once("town_continent_1")
            state.screen_audio_key = audio_key
        if not audio_key:
            state.screen_audio_key = None
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
        state.stats_mode,
        state.followers_mode,
        state.spell_mode,
        state.element_mode,
        state.alchemist_mode,
        state.alchemy_first,
        state.alchemy_selecting,
        state.temple_mode,
        state.smithy_mode,
        state.portal_mode,
        state.quest_mode,
        state.quest_detail_mode,
        state.title_menu_stack,
        state.options_mode,
        state.action_cursor,
        state.menu_cursor,
        state.followers_focus,
        state.followers_action_cursor,
        state.spell_cast_rank,
        state.spell_target_mode,
        state.spell_target_cursor,
        state.spell_target_command,
        state.quest_continent_index,
        state.quest_detail_id,
        state.quest_detail_page,
        state.level_cursor,
        state.level_up_notes,
        suppress_actions=suppress_actions,
    )
    render_frame(frame)


def render_battle_pause(ctx, render_frame, state: GameState, generate_frame, message: str) -> None:
    log_message = "\n".join(state.battle_log) if state.battle_log else message
    render_frame_state(ctx, render_frame, state, generate_frame, message=log_message, suppress_actions=True)
    time.sleep(battle_action_delay(state.player))


def animate_strength_gain(ctx, render_frame, state: GameState, generate_frame, gain: int) -> None:
    if gain <= 0:
        return
    delay = max(0.05, battle_action_delay(state.player) / 3) / 4
    for _ in range(gain):
        state.player.temp_atk_bonus += 1
        state.player.temp_def_bonus += 1
        render_frame_state(ctx, render_frame, state, generate_frame, message=_status_message(state, None))
        time.sleep(delay)


def animate_life_boost_gain(ctx, render_frame, state: GameState, generate_frame, gain: int) -> None:
    if gain <= 0:
        return
    delay = max(0.05, battle_action_delay(state.player) / 3) / 4
    for _ in range(gain):
        state.player.temp_hp_bonus += 1
        max_hp = state.player.total_max_hp()
        if state.player.hp < max_hp:
            state.player.hp += 1
        render_frame_state(ctx, render_frame, state, generate_frame, message=_status_message(state, None))
        time.sleep(delay)


def animate_follower_life_boost_gain(
    ctx,
    render_frame,
    state: GameState,
    generate_frame,
    follower: dict,
    gain: int,
) -> None:
    if gain <= 0:
        return
    delay = max(0.05, battle_action_delay(state.player) / 3) / 4
    for _ in range(gain):
        follower["temp_hp_bonus"] = int(follower.get("temp_hp_bonus", 0) or 0) + 1
        max_hp = state.player.follower_total_max_hp(follower)
        hp = int(follower.get("hp", max_hp) or max_hp)
        if hp < max_hp:
            follower["hp"] = hp + 1
        render_frame_state(ctx, render_frame, state, generate_frame, message=_status_message(state, None))
        time.sleep(delay)


def animate_follower_strength_gain(
    ctx,
    render_frame,
    state: GameState,
    generate_frame,
    follower: dict,
    gain: int,
) -> None:
    if gain <= 0:
        return
    delay = max(0.05, battle_action_delay(state.player) / 3) / 4
    for _ in range(gain):
        follower["temp_atk_bonus"] = int(follower.get("temp_atk_bonus", 0) or 0) + 1
        follower["temp_def_bonus"] = int(follower.get("temp_def_bonus", 0) or 0) + 1
        render_frame_state(ctx, render_frame, state, generate_frame, message=_status_message(state, None))
        time.sleep(delay)


def read_input(ctx, render_frame, state: GameState, generate_frame, read_keypress, read_keypress_timeout) -> str:
    if state.spell_mode or state.portal_mode or state.quest_mode:
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


def _title_screen_state_key(player) -> str:
    if getattr(player, "title_name_input", False):
        return "title_name_input"
    if getattr(player, "title_name_select", False):
        return "title_name"
    if getattr(player, "title_start_confirm", False):
        return "title_start_confirm"
    if getattr(player, "title_confirm", False):
        return "title_confirm"
    if getattr(player, "title_fortune", False):
        return "title_fortune"
    if getattr(player, "title_slot_select", False):
        return "title_slot_select"
    return ""


def _title_menu_id_from_state(title_data: dict, player, menu_stack: list[str]) -> str:
    menu_id = menu_stack[-1] if menu_stack else title_data.get("root_menu", "title_root")
    override = _title_screen_state_key(player)
    if override:
        menu_id = override
    return menu_id


def _asset_explorer_info_lines(ctx, state: GameState, asset_type: str, asset_id: Optional[str]) -> list[str]:
    assets = {}
    if asset_type == "objects":
        assets = ctx.objects.all()
    elif asset_type == "opponents":
        opp_data = ctx.opponents.all()
        if isinstance(opp_data, dict):
            assets = opp_data
    elif asset_type == "items":
        assets = ctx.items.all()
    elif asset_type == "spells":
        assets = ctx.spells.all()
    elif asset_type == "spells_art":
        assets = ctx.spells_art.all()
    elif asset_type == "glyphs":
        assets = ctx.glyphs.all()
    elif asset_type in ("music", "sfx"):
        assets = _asset_explorer_music_assets(ctx, asset_type)
    if not isinstance(assets, dict):
        assets = {}
    asset = assets.get(asset_id, {}) if asset_id else {}
    info_lines = []
    if isinstance(asset, dict) and state.asset_explorer_show_stats:
        stats = []
        for key in ("level", "hp", "atk", "defense", "speed", "mp_cost", "price"):
            if key in asset:
                stats.append(f"{key}:{asset.get(key)}")
        if stats:
            info_lines.append("Stats: " + " ".join(stats))
    if state.asset_explorer_show_json:
        raw = json.dumps(asset, indent=2, ensure_ascii=True)
        info_lines.extend(raw.splitlines())
    return info_lines


def _asset_explorer_music_assets(ctx, asset_type: str) -> dict:
    data = {}
    if hasattr(ctx, "music"):
        data = ctx.music.all()
    if not isinstance(data, dict):
        data = {}
    if asset_type == "music":
        songs = data.get("songs", {})
        return songs if isinstance(songs, dict) else {}
    if asset_type == "sfx":
        sequences = data.get("sequences", {})
        songs = data.get("songs", {})
        listed = {}
        if isinstance(sequences, dict):
            for key, value in sequences.items():
                if "sfx" in str(key).lower():
                    listed[key] = value
        if isinstance(songs, dict):
            for key, value in songs.items():
                if isinstance(value, dict) and value.get("sfx"):
                    listed[key] = value
        return listed
    return {}


def _asset_explorer_preview_audio(ctx, state: GameState, asset_type: str, asset_id: Optional[str]) -> None:
    if not asset_id or asset_type not in ("music", "sfx"):
        return
    if not hasattr(ctx, "audio"):
        return
    key = f"{asset_type}:{asset_id}"
    if key == (state.asset_explorer_preview_key or ""):
        return
    if asset_type == "music":
        ctx.audio.play_song_once(asset_id)
    else:
        ctx.audio.play_sfx_once(asset_id, "C4")
    state.asset_explorer_preview_key = key

def _title_screen_config(ctx, state: GameState) -> tuple[list[str], list[dict]]:
    title_data = ctx.title_screen.all() if hasattr(ctx, "title_screen") else {}
    if title_data.get("version") != 2:
        title_scene = ctx.scenes.get("title", {})
        return title_scene.get("narrative", []), scene_commands(
            ctx.scenes,
            ctx.commands_data,
            "title",
            state.player,
            state.opponents,
        )
    menus = title_data.get("menus", {}) if isinstance(title_data, dict) else {}
    root_menu = title_data.get("root_menu", "title_root")
    if not state.title_menu_stack:
        state.title_menu_stack = [root_menu]
    menu_id = state.title_menu_stack[-1] if state.title_menu_stack else root_menu
    override = _title_screen_state_key(state.player)
    if override:
        menu_id = override
    menu_data = menus.get(menu_id, {}) if isinstance(menus, dict) else {}
    narrative = menu_data.get("narrative", [])
    if not isinstance(narrative, list):
        narrative = []
    items = menu_data.get("items", [])
    if menu_id == "title_assets_list":
        asset_type = state.asset_explorer_type or ""
        if not asset_type:
            narrative = ["Asset Explorer", "Select an asset type."]
            items = [
                {"label": "Objects", "command": "TITLE_ASSET_TYPE:objects"},
                {"label": "Opponents", "command": "TITLE_ASSET_TYPE:opponents"},
                {"label": "Items", "command": "TITLE_ASSET_TYPE:items"},
                {"label": "Spells", "command": "TITLE_ASSET_TYPE:spells"},
                {"label": "Spells Art", "command": "TITLE_ASSET_TYPE:spells_art"},
                {"label": "Glyphs", "command": "TITLE_ASSET_TYPE:glyphs"},
                {"label": "Music", "command": "TITLE_ASSET_TYPE:music"},
                {"label": "SFX", "command": "TITLE_ASSET_TYPE:sfx"},
                {"label": "Back", "command": "TITLE_ASSET_BACK"},
            ]
        else:
            asset_label = {
                "objects": "Objects",
                "opponents": "Opponents",
                "items": "Items",
                "spells": "Spells",
                "spells_art": "Spells Art",
                "glyphs": "Glyphs",
                "music": "Music",
                "sfx": "SFX",
            }.get(asset_type, "Assets")
            narrative = [f"Asset Explorer: {asset_label}"]
            assets = {}
            if asset_type == "objects":
                assets = ctx.objects.all()
            elif asset_type == "opponents":
                opp_data = ctx.opponents.all()
                if isinstance(opp_data, dict):
                    assets = opp_data
            elif asset_type == "items":
                assets = ctx.items.all()
            elif asset_type == "spells":
                assets = ctx.spells.all()
            elif asset_type == "spells_art":
                assets = ctx.spells_art.all()
            elif asset_type == "glyphs":
                assets = ctx.glyphs.all()
            elif asset_type in ("music", "sfx"):
                assets = _asset_explorer_music_assets(ctx, asset_type)
            if not isinstance(assets, dict):
                assets = {}
            asset_ids = sorted(str(key) for key in assets.keys())
            items = [{"label": asset_id, "command": f"TITLE_ASSET_SELECT:{asset_id}"} for asset_id in asset_ids]
            items.append({
                "label": f"Show Art: {'On' if state.asset_explorer_show_art else 'Off'}",
                "command": "TITLE_ASSET_TOGGLE:art",
            })
            items.append({
                "label": f"Show Stats: {'On' if state.asset_explorer_show_stats else 'Off'}",
                "command": "TITLE_ASSET_TOGGLE:stats",
            })
            items.append({
                "label": f"Show JSON: {'On' if state.asset_explorer_show_json else 'Off'}",
                "command": "TITLE_ASSET_TOGGLE:json",
            })
            items.append({"label": "Back", "command": "TITLE_ASSET_BACK"})
            selected_id = None
            if asset_ids:
                if 0 <= state.action_cursor < len(asset_ids):
                    selected_id = asset_ids[state.action_cursor]
                else:
                    selected_id = asset_ids[0]
            asset = assets.get(selected_id, {}) if selected_id is not None else {}
            if isinstance(asset, dict):
                name = asset.get("name")
                if name:
                    narrative.append(str(name)[:64])
                desc = asset.get("description") or asset.get("desc")
                if desc:
                    narrative.append(str(desc)[:80])
                if state.asset_explorer_show_stats:
                    stats = []
                    for key in ("level", "hp", "atk", "defense", "speed", "mp_cost", "price"):
                        if key in asset:
                            stats.append(f"{key}:{asset.get(key)}")
                    if stats:
                        narrative.append("Stats: " + " ".join(stats))
                if state.asset_explorer_show_art:
                    art = asset.get("art")
                    if isinstance(art, list):
                        narrative.append("")
                        narrative.extend(str(line)[:80] for line in art[:10])
                if state.asset_explorer_show_json:
                    raw = json.dumps(asset, indent=2, ensure_ascii=True)
                    lines = raw.splitlines()[:8]
                    if lines:
                        narrative.append("")
                        narrative.extend(line[:80] for line in lines)
    if items == "slot_select":
        mode = getattr(state.player, "title_slot_mode", "continue")
        summaries = ctx.save_data.slot_summaries_sorted(max_slots=100)
        built = []
        for summary in summaries:
            slot_num = summary.get("slot", 0)
            if summary.get("empty"):
                label = f"{slot_num}.) Empty"
            else:
                level = summary.get("level", 1)
                location = summary.get("location", "Town")
                gold = summary.get("gold", 0)
                name = summary.get("name", "WARRIOR")
                element = summary.get("current_element")
                if hasattr(ctx, "continents") and element:
                    location = ctx.continents.name_for(str(element)) or location
                label = f"{slot_num}.) {name} Lv{level} {location} GP{gold}"
            entry = {"label": label, "command": f"TITLE_SLOT_{slot_num}"}
            built.append(entry)
        if not built:
            narrative = list(narrative)
            narrative.append("No save data found.")
        built.append({"label": "Back", "command": "TITLE_SLOT_BACK"})
        items = built
    if not isinstance(items, list):
        items = []
    commands = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        cmd_entry = dict(entry)
        if cmd_entry.get("submenu"):
            cmd_entry["command"] = f"TITLE_MENU_SUB:{cmd_entry.get('submenu')}"
        if cmd_entry.get("back"):
            cmd_entry["command"] = "TITLE_MENU_BACK"
        commands.append(cmd_entry)
    filtered = []
    for entry in commands:
        if not isinstance(entry, dict):
            continue
        when = entry.get("when")
        if when == "has_save" and not getattr(state.player, "has_save", False):
            continue
        cmd_entry = dict(entry)
        if not command_is_enabled(cmd_entry, state.player, state.opponents):
            cmd_entry["_disabled"] = True
        filtered.append(cmd_entry)
    commands = filtered
    return narrative, commands


def action_commands_for_state(ctx, state: GameState) -> list[dict]:
    if state.title_mode:
        _narrative, commands = _title_screen_config(ctx, state)
        return commands
    if state.portal_mode:
        elements = []
        if hasattr(ctx, "continents"):
            order = list(ctx.continents.order() or [])
            elements = order or list(ctx.continents.continents().keys())
        unlocked = set(getattr(state.player, "elements", []) or [])
        commands = []
        current_element = getattr(state.player, "current_element", None)
        for element in elements:
            label = ctx.continents.name_for(element) if hasattr(ctx, "continents") else str(element).title()
            entry = {"label": label, "command": f"PORTAL:{element}"}
            if element not in unlocked or element == current_element:
                entry["_disabled"] = True
            commands.append(entry)
        if not commands:
            commands.append({"label": "No continents available.", "_disabled": True})
        commands.append({"label": "Back", "command": "B_KEY"})
        return commands
    if state.shop_mode or state.hall_mode or state.inn_mode or state.temple_mode or state.smithy_mode or state.alchemist_mode or state.portal_mode:
        venue_id = venue_id_from_state(state)
        if venue_id:
            return venue_actions(ctx, state, venue_id)
    if state.inventory_mode or state.spell_mode or state.options_mode or state.element_mode or state.stats_mode or state.followers_mode:
        return []
    if not any(
        (
            state.leveling_mode,
            state.shop_mode,
            state.inventory_mode,
            state.hall_mode,
            state.inn_mode,
            state.spell_mode,
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
    entries = ctx.spells.available(player, ctx.items)
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
    if not hasattr(state.player, "_spells_data"):
        state.player._spells_data = ctx.spells
    if not hasattr(state.player, "_items_data"):
        state.player._items_data = ctx.items
    action = normalize_input_action(ch)
    if action is None:
        return None, None

    if state.title_mode and getattr(state.player, "title_name_input", False):
        keyboard = [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
            ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
            ["K", "L", "M", "N", "O", "P", "Q", "R", "S", "T"],
            ["U", "V", "W", "X", "Y", "Z", "-", "'", " ", "<"],
            ["SHIFT", "DONE", "CANCEL"],
        ]
        cursor = getattr(state.player, "title_name_cursor", (0, 0))
        try:
            row, col = int(cursor[0]), int(cursor[1])
        except (TypeError, ValueError, IndexError):
            row, col = 0, 0
        row = max(0, min(row, len(keyboard) - 1))
        col = max(0, min(col, len(keyboard[row]) - 1))
        if action in ("UP", "DOWN"):
            step = -1 if action == "UP" else 1
            row = (row + step) % len(keyboard)
            col = min(col, len(keyboard[row]) - 1)
            state.player.title_name_cursor = (row, col)
            return None, None
        if action in ("LEFT", "RIGHT"):
            step = -1 if action == "LEFT" else 1
            col = (col + step) % len(keyboard[row])
            state.player.title_name_cursor = (row, col)
            return None, None
        if action == "BACK":
            state.player.title_name_input = False
            state.player.title_name_select = True
            commands = action_commands_for_state(ctx, state)
            state.action_cursor = 0
            clamp_action_cursor(state, commands)
            return None, None
        if action == "CONFIRM":
            key = keyboard[row][col]
            buffer = str(getattr(state.player, "title_pending_name", "") or "")
            shift_lock = bool(getattr(state.player, "title_name_shift", True))
            if key == "DONE":
                if buffer.strip():
                    state.player.title_pending_name = buffer[:16]
                    state.player.title_name_input = False
                    state.player.title_name_select = False
                    state.player.title_fortune = True
                    commands = action_commands_for_state(ctx, state)
                    state.action_cursor = 0
                    clamp_action_cursor(state, commands)
                return None, None
            if key == "CANCEL":
                state.player.title_name_input = False
                state.player.title_name_select = True
                commands = action_commands_for_state(ctx, state)
                state.action_cursor = 0
                clamp_action_cursor(state, commands)
                return None, None
            if key == "SHIFT":
                state.player.title_name_shift = not shift_lock
                return None, None
            if key == "<":
                state.player.title_pending_name = buffer[:-1]
                return None, None
            if len(buffer) >= 16:
                return None, None
            if key == " ":
                if buffer.endswith(" ") or not buffer:
                    return None, None
            if key.isalpha():
                key = key.upper() if shift_lock else key.lower()
            state.player.title_pending_name = buffer + key
            return None, None
        return None, None

    if (
        action == "BACK"
        and state.player.location == "Forest"
        and not any(m.hp > 0 for m in state.opponents)
        and not (
            state.inventory_mode
            or state.spell_mode
            or state.options_mode
            or state.element_mode
            or state.stats_mode
            or state.followers_mode
            or state.quest_mode
            or state.shop_mode
            or state.hall_mode
            or state.inn_mode
            or state.alchemist_mode
            or state.temple_mode
            or state.smithy_mode
            or state.portal_mode
        )
    ):
        return "ENTER_SCENE", {"target": "town"}

    if action == "BACK" and (
        state.current_venue_id
        or state.shop_mode
        or state.hall_mode
        or state.inn_mode
        or state.alchemist_mode
        or state.temple_mode
        or state.smithy_mode
        or state.portal_mode
    ):
        return "LEAVE", None

    if action in ("START", "SELECT"):
        if state.options_mode:
            state.options_mode = False
            state.menu_cursor = 0
        else:
            state.options_mode = True
            menu = ctx.menus.get("options", {})
            actions = []
            available_spells = []
            if hasattr(ctx, "spells") and hasattr(ctx, "items"):
                available_spells = ctx.spells.available(state.player, ctx.items)
            for entry in menu.get("actions", []):
                if not entry.get("command"):
                    continue
                cmd_entry = dict(entry)
                if not command_is_enabled(cmd_entry, state.player, state.opponents):
                    cmd_entry["_disabled"] = True
                if cmd_entry.get("command") == "SPELLBOOK" and not available_spells:
                    cmd_entry["_disabled"] = True
                actions.append(cmd_entry)
            enabled = [i for i, cmd in enumerate(actions) if not cmd.get("_disabled")]
            state.menu_cursor = enabled[0] if enabled else -1
            state.inventory_mode = False
            state.stats_mode = False
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
        options = ["NUM1", "NUM2", "NUM3", "NUM4", "B_KEY", "X_KEY", "BANK"]
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

    if state.quest_mode:
        elements = list(getattr(state.player, "elements", []) or [])
        if hasattr(ctx, "continents"):
            order = list(ctx.continents.order() or [])
            if order:
                elements = [e for e in order if e in elements] or elements
        if not elements:
            elements = ["base"]
        if state.quest_detail_mode:
            dialog = []
            detail_quest = None
            if state.quest_detail_id and hasattr(ctx, "quests"):
                detail_quest = ctx.quests.get(state.quest_detail_id, {})
            if isinstance(detail_quest, dict):
                dialog = detail_quest.get("dialog", [])
            if not isinstance(dialog, list):
                dialog = []
            total_pages = max(1, len(dialog))
            state.quest_detail_page = max(0, min(state.quest_detail_page, total_pages - 1))
            if action in ("UP", "DOWN"):
                direction = -1 if action == "UP" else 1
                state.action_cursor = (state.action_cursor + direction) % 2
                return None, None
            if action == "CONFIRM":
                if state.action_cursor == 1:
                    state.quest_detail_mode = False
                    state.quest_detail_id = None
                    state.quest_detail_page = 0
                    return None, None
                is_last = state.quest_detail_page >= total_pages - 1
                if not is_last:
                    state.quest_detail_page += 1
                    return None, None
                quest_id = state.quest_detail_id
                if quest_id:
                    qstate = getattr(state.player, "quests", {}).get(quest_id, {}) if hasattr(state.player, "quests") else {}
                    if not isinstance(qstate, dict) or qstate.get("status") != "active":
                        quest_def = detail_quest if isinstance(detail_quest, dict) else {}
                        start_message = None
                        on_start = quest_def.get("on_start", {}) if isinstance(quest_def.get("on_start", {}), dict) else {}
                        if not hasattr(state.player, "flags") or not isinstance(state.player.flags, dict):
                            state.player.flags = {}
                        grant_flags = on_start.get("grant_flags", [])
                        if isinstance(grant_flags, list):
                            for flag in grant_flags:
                                state.player.flags[str(flag)] = True
                        recruit_only_types = on_start.get("recruit_only_types", [])
                        if isinstance(recruit_only_types, list) and recruit_only_types:
                            state.player.flags["recruit_only_types"] = [str(t) for t in recruit_only_types if t]
                        grant_follower = on_start.get("grant_follower", {})
                        grant_type = ""
                        if isinstance(grant_follower, dict):
                            grant_type = str(grant_follower.get("type", "") or "").strip()
                        follower_cap = on_start.get("follower_cap")
                        if isinstance(follower_cap, int) and follower_cap > 0:
                            state.player.flags["follower_cap"] = follower_cap
                        follower_cap_extra = on_start.get("follower_cap_extra")
                        if isinstance(follower_cap_extra, int) and follower_cap_extra > 0:
                            base_count = len(state.player.followers) if isinstance(state.player.followers, list) else 0
                            if grant_type:
                                base_count += 1
                            state.player.flags["follower_cap"] = base_count + follower_cap_extra
                        if grant_type and state.player.follower_slots_remaining() <= 0:
                            state.last_message = "No room for another follower."
                            return None, None
                        gp_cost = int(on_start.get("gp_cost", 0) or 0)
                        if gp_cost > 0:
                            if int(getattr(state.player, "gold", 0) or 0) < gp_cost:
                                state.last_message = "Not enough GP."
                                return None, None
                            state.player.gold = int(getattr(state.player, "gold", 0) or 0) - gp_cost
                        if grant_type:
                            follower = build_follower_from_entry(grant_follower)
                            if follower:
                                if not state.player.add_follower(follower):
                                    state.last_message = "No room for another follower."
                                    return None, None
                                if grant_follower.get("count_as_recruit") and hasattr(ctx, "quests") and ctx.quests is not None:
                                    handle_event(
                                        state.player,
                                        ctx.quests,
                                        "recruit_follower",
                                        {"follower_type": follower.get("type", ""), "count": 1},
                                        ctx.items,
                                    )
                        start_message = str(on_start.get("start_message", "") or "").strip() or None
                        if start_quest(state.player, quest_id):
                            title = quest_def.get("title", quest_id)
                            if start_message:
                                state.last_message = start_message
                            else:
                                state.last_message = f"Quest started: {title}."
                        if hasattr(ctx, "save_data") and ctx.save_data:
                            ctx.save_data.save_player(state.player)
                state.quest_detail_mode = False
                state.quest_detail_id = None
                state.quest_detail_page = 0
                return None, None
            if action == "BACK":
                state.quest_detail_mode = False
                state.quest_detail_id = None
                state.quest_detail_page = 0
                return None, None
            return None, None
        if action in ("LEFT", "RIGHT"):
            direction = -1 if action == "LEFT" else 1
            state.quest_continent_index = (state.quest_continent_index + direction) % len(elements)
            return None, None
        ordered_ids = ordered_quest_ids(ctx.stories, ctx.quests, elements[state.quest_continent_index]) if hasattr(ctx, "stories") else []
        entries = quest_entries(
            state.player,
            ctx.quests,
            ctx.items,
            continent=elements[state.quest_continent_index],
            include_locked_next=True,
            ordered_ids=ordered_ids,
        ) if hasattr(ctx, "quests") else []
        commands = [{"label": "Continent", "_disabled": True}, {"label": "", "_disabled": True}]
        if entries:
            for entry in entries:
                status = entry.get("status", "available")
                commands.append({
                    "quest_id": entry.get("id"),
                    "status": status,
                    "quest": entry.get("quest", {}),
                    "_disabled": status == "complete",
                })
        else:
            commands.append({"label": "No active quests.", "_disabled": True})
        commands.append({"label": "Back", "command": "B_KEY"})
        enabled = [i for i, cmd in enumerate(commands) if not cmd.get("_disabled")]
        if not enabled:
            state.action_cursor = -1
        elif state.action_cursor not in enabled:
            state.action_cursor = enabled[0]
        else:
            state.action_cursor = max(0, min(state.action_cursor, len(commands) - 1))
        state.action_cursor = max(0, min(state.action_cursor, len(commands) - 1))
        if action in ("UP", "DOWN"):
            direction = -1 if action == "UP" else 1
            if enabled:
                pos = enabled.index(state.action_cursor) if state.action_cursor in enabled else len(enabled) - 1
                pos = (pos + direction) % len(enabled)
                state.action_cursor = enabled[pos]
            return None, None
        if action == "CONFIRM":
            if 0 <= state.action_cursor < len(commands):
                entry = commands[state.action_cursor]
                if entry.get("command") == "B_KEY":
                    state.quest_mode = False
                    state.last_message = "Closed quests."
                    return None, None
                quest_id = entry.get("quest_id")
                if quest_id:
                    qstate = getattr(state.player, "quests", {}).get(quest_id, {}) if hasattr(state.player, "quests") else {}
                    if not isinstance(qstate, dict) or qstate.get("status") != "active":
                        if entry.get("status") == "locked":
                            return None, None
                        state.quest_detail_mode = True
                        state.quest_detail_id = quest_id
                        state.quest_detail_page = 0
                        state.action_cursor = 0
            return None, None
        if action == "BACK":
            state.quest_mode = False
            state.last_message = "Closed quests."
            return None, None
        return None, None

    if state.options_mode:
        menu = ctx.menus.get("options", {})
        actions = []
        available_spells = []
        if hasattr(ctx, "spells") and hasattr(ctx, "items"):
            available_spells = ctx.spells.available(state.player, ctx.items)
        for entry in menu.get("actions", []):
            if not entry.get("command"):
                continue
            cmd_entry = dict(entry)
            if not command_is_enabled(cmd_entry, state.player, state.opponents):
                cmd_entry["_disabled"] = True
            if cmd_entry.get("command") == "SPELLBOOK" and not available_spells:
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
            if cmd != "TOGGLE_AUDIO":
                state.options_mode = False
            return cmd, None
        return None, None

    if state.stats_mode:
        menu = ctx.menus.get("stats", {})
        actions = []
        for entry in menu.get("actions", []):
            if not entry.get("command"):
                continue
            cmd_entry = dict(entry)
            if cmd_entry.get("command", "").startswith("STAT_") and state.player.stat_points <= 0:
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
            state.stats_mode = False
            return None, None
        if action == "CONFIRM":
            if state.menu_cursor < 0:
                return None, None
            if actions[state.menu_cursor].get("_disabled"):
                return None, None
            cmd = actions[state.menu_cursor].get("command")
            return cmd, None
        return None, None

    if state.followers_mode:
        menu = ctx.menus.get("followers", {})
        followers = getattr(state.player, "followers", [])
        if not isinstance(followers, list):
            followers = []
        count = len(followers)
        if count == 0:
            if action == "BACK":
                state.follower_dismiss_pending = None
                state.followers_mode = False
            return None, None
        actions = []
        selected_type = None
        selected_follower = {}
        type_count = 0
        gear_items = state.player.list_gear_items()
        if followers and 0 <= state.menu_cursor < len(followers) and isinstance(followers[state.menu_cursor], dict):
            selected_follower = followers[state.menu_cursor]
            selected_type = selected_follower.get("type")
            if selected_type:
                type_count = sum(
                    1
                    for follower in followers
                    if isinstance(follower, dict) and follower.get("type") == selected_type
                )
        for entry in menu.get("actions", []):
            cmd_entry = dict(entry)
            if cmd_entry.get("command") == "FOLLOWER_DISMISS" and not followers:
                cmd_entry["_disabled"] = True
            if cmd_entry.get("command") == "FOLLOWER_FUSE" and type_count < 3:
                cmd_entry["_disabled"] = True
            if cmd_entry.get("command") == "FOLLOWER_EQUIP" and not gear_items:
                cmd_entry["_disabled"] = True
            if cmd_entry.get("command") == "FOLLOWER_UNEQUIP":
                equip = selected_follower.get("equipment", {}) if isinstance(selected_follower, dict) else {}
                if not isinstance(equip, dict) or not equip:
                    cmd_entry["_disabled"] = True
            actions.append(cmd_entry)
        actions.append({"label": "Back", "command": "FOLLOWER_BACK"})
        if not actions:
            actions = [{"label": "Back", "command": "B_KEY"}]

        state.menu_cursor = max(0, min(state.menu_cursor, count - 1))
        state.followers_action_cursor = max(0, min(state.followers_action_cursor, len(actions) - 1))

        if action in ("LEFT", "RIGHT"):
            state.followers_focus = "actions" if state.followers_focus == "list" else "list"
            state.follower_dismiss_pending = None
            return None, None
        if action in ("UP", "DOWN"):
            direction = -1 if action == "UP" else 1
            if state.followers_focus == "list":
                state.menu_cursor = (state.menu_cursor + direction) % count
                state.follower_dismiss_pending = None
            else:
                state.followers_action_cursor = (state.followers_action_cursor + direction) % len(actions)
            return None, None
        if action == "CONFIRM":
            if state.followers_focus == "list":
                state.followers_focus = "actions"
                state.follower_dismiss_pending = None
                return None, None
            cmd = actions[state.followers_action_cursor].get("command")
            if cmd == "FOLLOWER_BACK":
                state.followers_focus = "list"
                state.follower_dismiss_pending = None
                return None, None
            if cmd == "FOLLOWER_DISMISS":
                if state.follower_dismiss_pending != state.menu_cursor:
                    follower = followers[state.menu_cursor]
                    name = follower.get("name", "Follower") if isinstance(follower, dict) else "Follower"
                    state.follower_dismiss_pending = state.menu_cursor
                    state.last_message = f"Press A again to dismiss {name}."
                    return None, None
                follower = followers[state.menu_cursor]
                name = follower.get("name", "Follower") if isinstance(follower, dict) else "Follower"
                state.player.followers.pop(state.menu_cursor)
                state.last_message = f"{name} has departed."
                state.follower_dismiss_pending = None
                if state.menu_cursor >= len(state.player.followers):
                    state.menu_cursor = max(0, len(state.player.followers) - 1)
                return None, None
            if cmd == "FOLLOWER_FUSE":
                if state.current_venue_id != "town_temple":
                    state.last_message = "Fusing is only possible at the temple."
                    return None, None
                if not selected_type:
                    state.last_message = "Select a follower to fuse."
                    return None, None
                fused = state.player.fuse_followers(selected_type, 3)
                if not fused:
                    state.last_message = "Need three followers of the same type to fuse."
                    return None, None
                fused_name = fused.get("name", "Follower")
                fused_type = fused.get("type", "follower")
                state.last_message = f"{fused_name} is promoted to {fused_type.replace('_', ' ').title()}."
                if hasattr(ctx, "quests") and ctx.quests is not None:
                    quest_messages = handle_event(
                        state.player,
                        ctx.quests,
                        "fuse_followers",
                        {"follower_type": selected_type, "count": 3},
                        ctx.items,
                    )
                    if quest_messages:
                        state.last_message = f"{state.last_message} " + " ".join(quest_messages)
                        _open_quest_screen(ctx, state)
                state.follower_dismiss_pending = None
                return None, None
            if cmd == "FOLLOWER_EQUIP":
                if not followers or state.menu_cursor < 0 or state.menu_cursor >= len(followers):
                    state.last_message = "Select a follower to equip."
                    return None, None
                target_follower = followers[state.menu_cursor]
                state.follower_equip_mode = True
                state.follower_equip_target = state.menu_cursor
                state.inventory_mode = True
                state.followers_mode = False
                state.menu_cursor = 0
                state.inventory_items = gear_items
                target_name = target_follower.get("name", "Follower") if isinstance(target_follower, dict) else "Follower"
                state.last_message = f"Equip gear to {target_name}."
                return None, None
            if cmd == "FOLLOWER_UNEQUIP":
                if not selected_follower:
                    state.last_message = "Select a follower to unequip."
                    return None, None
                selected_follower["equipment"] = {}
                state.last_message = f"{selected_follower.get('name', 'Follower')} unequipped gear."
                return None, None
            if cmd == "B_KEY":
                state.follower_dismiss_pending = None
                state.followers_mode = False
                return None, None
            return None, None
        if action == "BACK":
            state.follower_dismiss_pending = None
            if state.followers_focus == "actions":
                state.followers_focus = "list"
            else:
                state.followers_mode = False
            return None, None
        return None, None

    if state.follower_equip_mode:
        items = state.inventory_items or []
        count = min(len(items), 9)
        if count == 0:
            if action == "BACK":
                state.follower_equip_mode = False
                state.inventory_mode = False
            return None, None
        state.menu_cursor = max(0, min(state.menu_cursor, count - 1))
        if action in ("UP", "DOWN"):
            direction = -1 if action == "UP" else 1
            state.menu_cursor = (state.menu_cursor + direction) % count
            return None, None
        if action == "CONFIRM":
            idx = state.menu_cursor
            if 0 <= idx < len(items):
                gear_id = items[idx][0]
                followers = getattr(state.player, "followers", [])
                target = state.follower_equip_target
                if isinstance(target, int) and 0 <= target < len(followers):
                    follower = followers[target]
                    if state.player.assign_gear_to_follower(follower, gear_id):
                        state.last_message = f"{follower.get('name', 'Follower')} equipped gear."
                    else:
                        state.last_message = "Unable to equip that gear."
                else:
                    state.last_message = "No follower selected."
            state.follower_equip_mode = False
            state.inventory_mode = False
            return None, None
        if action == "BACK":
            state.follower_equip_mode = False
            state.inventory_mode = False
            return None, None
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
        if state.spell_target_mode:
            targets = [state.player.name]
            followers = getattr(state.player, "followers", []) or []
            if isinstance(followers, list):
                for follower in followers:
                    if isinstance(follower, dict):
                        targets.append(follower.get("name", "Follower"))
            if not targets:
                state.spell_target_mode = False
                state.spell_target_command = None
                return None, None
            state.spell_target_cursor = max(0, min(state.spell_target_cursor, len(targets) - 1))
            if action in ("UP", "DOWN"):
                direction = -1 if action == "UP" else 1
                state.spell_target_cursor = (state.spell_target_cursor + direction) % len(targets)
                return None, None
            if action == "CONFIRM":
                cmd = state.spell_target_command
                state.team_target_index = state.spell_target_cursor
                state.spell_target_mode = False
                state.spell_target_command = None
                return cmd, None
            if action == "BACK":
                state.spell_target_mode = False
                state.spell_target_command = None
                return None, None
            return None, None

        keys = spell_menu_keys(ctx, state.player)
        if not keys:
            if action == "BACK":
                return "B_KEY", None
            return None, None
        state.spell_cursor = max(0, min(state.spell_cursor, len(keys) - 1))
        state.menu_cursor = state.spell_cursor
        spell_entry = ctx.spells.by_command_id(keys[state.spell_cursor])
        spell = spell_entry[1] if spell_entry else None
        max_rank = ctx.spells.rank_for(spell, state.player.level) if spell else 1
        base_cost = int(spell.get("mp_cost", 0)) if isinstance(spell, dict) else 0
        element = spell.get("element") if isinstance(spell, dict) else None
        has_charge = False
        if element:
            charges = state.player.wand_charges()
            has_charge = int(charges.get(str(element), 0)) > 0
        max_affordable = max_rank
        if not has_charge and base_cost > 0:
            max_affordable = min(max_rank, state.player.mp // base_cost)
        if max_affordable >= 1 and state.spell_cast_rank > max_affordable:
            state.spell_cast_rank = max_affordable
        if action in ("UP", "DOWN"):
            direction = -1 if action == "UP" else 1
            state.spell_cursor = (state.spell_cursor + direction) % len(keys)
            state.menu_cursor = state.spell_cursor
            spell_entry = ctx.spells.by_command_id(keys[state.spell_cursor])
            if spell_entry:
                _, spell = spell_entry
                max_rank = ctx.spells.rank_for(spell, state.player.level)
                base_cost = int(spell.get("mp_cost", 0))
                element = spell.get("element")
                has_charge = False
                if element:
                    charges = state.player.wand_charges()
                    has_charge = int(charges.get(str(element), 0)) > 0
                max_affordable = max_rank
                if not has_charge and base_cost > 0:
                    max_affordable = min(max_rank, state.player.mp // base_cost)
                state.spell_cast_rank = max(1, max_affordable) if max_affordable >= 1 else 1
            return None, None
        if action in ("LEFT", "RIGHT"):
            if max_affordable < 1:
                return None, None
            if action == "LEFT":
                state.spell_cast_rank = max(1, state.spell_cast_rank - 1)
            else:
                state.spell_cast_rank = min(max_affordable, state.spell_cast_rank + 1)
            return None, None
        if action == "CONFIRM":
            if max_affordable < 1:
                return None, None
            cmd = keys[state.spell_cursor]
            if spell and spell.get("class") == "support":
                state.spell_target_mode = True
                state.spell_target_command = cmd
                state.spell_target_cursor = 0
                return None, None
            return cmd, None
        if action == "BACK":
            state.spell_target_mode = False
            state.spell_target_command = None
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

    if state.temple_mode or state.smithy_mode:
        if action == "BACK":
            return "B_KEY", None

    if state.title_mode:
        commands = action_commands_for_state(ctx, state)
        clamp_action_cursor(state, commands)
        title_data = ctx.title_screen.all() if hasattr(ctx, "title_screen") else {}
        menu_id = _title_menu_id_from_state(title_data, state.player, state.title_menu_stack)
        if menu_id == "title_assets_list":
            asset_type = state.asset_explorer_type or ""
            if not asset_type:
                if action == "BACK":
                    if len(state.title_menu_stack) > 1:
                        state.title_menu_stack.pop()
                    commands = action_commands_for_state(ctx, state)
                    clamp_action_cursor(state, commands)
                    return None, None
            asset_ids = []
            if asset_type:
                assets = {}
                if asset_type == "objects":
                    assets = ctx.objects.all()
                elif asset_type == "opponents":
                    opp_data = ctx.opponents.all()
                    if isinstance(opp_data, dict):
                        assets = opp_data
                elif asset_type == "items":
                    assets = ctx.items.all()
                elif asset_type == "spells":
                    assets = ctx.spells.all()
                elif asset_type == "spells_art":
                    assets = ctx.spells_art.all()
                elif asset_type == "glyphs":
                    assets = ctx.glyphs.all()
                elif asset_type in ("music", "sfx"):
                    assets = _asset_explorer_music_assets(ctx, asset_type)
                if isinstance(assets, dict):
                    asset_ids = sorted(str(key) for key in assets.keys())
            selected_id = None
            if asset_ids and 0 <= state.action_cursor < len(asset_ids):
                selected_id = asset_ids[state.action_cursor]
            if action == "RIGHT" and asset_type:
                state.asset_explorer_focus = "info"
                setattr(state.player, "asset_explorer_focus", state.asset_explorer_focus)
                return None, None
            if action == "LEFT" and asset_type:
                state.asset_explorer_focus = "list"
                setattr(state.player, "asset_explorer_focus", state.asset_explorer_focus)
                return None, None
            if action in ("UP", "DOWN") and state.asset_explorer_focus == "info" and asset_type:
                info_lines = _asset_explorer_info_lines(ctx, state, asset_type, selected_id)
                left_h = SCREEN_HEIGHT
                top_h = 16
                bottom_h = max(4, left_h - top_h)
                inner_h = max(0, bottom_h - 2)
                max_scroll = max(0, len(info_lines) - inner_h)
                delta = -1 if action == "UP" else 1
                state.asset_explorer_info_scroll = max(0, min(max_scroll, state.asset_explorer_info_scroll + delta))
                setattr(state.player, "asset_explorer_info_scroll", state.asset_explorer_info_scroll)
                return None, None
            if action in ("UP", "DOWN") and state.asset_explorer_focus == "list" and asset_type in ("music", "sfx"):
                enabled = _enabled_indices(commands)
                if enabled:
                    pos = enabled.index(state.action_cursor) if state.action_cursor in enabled else 0
                    direction = -1 if action == "UP" else 1
                    pos = (pos + direction) % len(enabled)
                    state.action_cursor = enabled[pos]
                if commands and 0 <= state.action_cursor < len(commands):
                    cmd = commands[state.action_cursor].get("command", "")
                    if isinstance(cmd, str) and cmd.startswith("TITLE_ASSET_SELECT:"):
                        selected_id = cmd.split(":", 1)[1]
                        _asset_explorer_preview_audio(ctx, state, asset_type, selected_id)
                return None, None
        if action in ("UP", "DOWN"):
            enabled = _enabled_indices(commands)
            if enabled:
                pos = enabled.index(state.action_cursor) if state.action_cursor in enabled else 0
                direction = -1 if action == "UP" else 1
                pos = (pos + direction) % len(enabled)
                state.action_cursor = enabled[pos]
            return None, None
        if action in ("LEFT", "RIGHT"):
            return None, None
        if action == "BACK":
            if menu_id == "title_assets_list" and (state.asset_explorer_type or ""):
                state.asset_explorer_type = ""
                state.asset_explorer_focus = "list"
                state.asset_explorer_info_scroll = 0
                state.asset_explorer_preview_key = None
                setattr(state.player, "asset_explorer_type", state.asset_explorer_type)
                setattr(state.player, "asset_explorer_focus", state.asset_explorer_focus)
                setattr(state.player, "asset_explorer_info_scroll", state.asset_explorer_info_scroll)
                commands = action_commands_for_state(ctx, state)
                clamp_action_cursor(state, commands)
            else:
                if len(state.title_menu_stack) > 1:
                    state.title_menu_stack.pop()
                    commands = action_commands_for_state(ctx, state)
                    clamp_action_cursor(state, commands)
            return None, None
        if action == "CONFIRM":
            if not commands or state.action_cursor < 0:
                return None, None
            command_meta = commands[state.action_cursor]
            if command_meta.get("_disabled"):
                return None, None
            cmd = command_meta.get("command")
            if isinstance(cmd, str) and cmd.startswith("TITLE_ASSET_TYPE:"):
                state.asset_explorer_type = cmd.split(":", 1)[1]
                state.asset_explorer_focus = "list"
                state.asset_explorer_info_scroll = 0
                state.asset_explorer_preview_key = None
                setattr(state.player, "asset_explorer_type", state.asset_explorer_type)
                if menu_id != "title_assets_list":
                    state.title_menu_stack.append("title_assets_list")
                state.action_cursor = 0
                commands = action_commands_for_state(ctx, state)
                clamp_action_cursor(state, commands)
                if state.asset_explorer_type in ("music", "sfx"):
                    if commands and 0 <= state.action_cursor < len(commands):
                        cmd = commands[state.action_cursor].get("command", "")
                        if isinstance(cmd, str) and cmd.startswith("TITLE_ASSET_SELECT:"):
                            selected_id = cmd.split(":", 1)[1]
                            _asset_explorer_preview_audio(ctx, state, state.asset_explorer_type, selected_id)
                return None, None
            if cmd == "TITLE_ASSET_OPEN":
                state.asset_explorer_type = ""
                state.asset_explorer_focus = "list"
                state.asset_explorer_info_scroll = 0
                state.asset_explorer_preview_key = None
                setattr(state.player, "asset_explorer_type", state.asset_explorer_type)
                setattr(state.player, "asset_explorer_focus", state.asset_explorer_focus)
                setattr(state.player, "asset_explorer_info_scroll", state.asset_explorer_info_scroll)
                state.title_menu_stack.append("title_assets_list")
                state.action_cursor = 0
                if hasattr(ctx, "audio"):
                    ctx.audio.stop()
                commands = action_commands_for_state(ctx, state)
                clamp_action_cursor(state, commands)
                return None, None
            if cmd == "TITLE_ASSET_BACK":
                if state.asset_explorer_type:
                    state.asset_explorer_type = ""
                    state.asset_explorer_focus = "list"
                    state.asset_explorer_info_scroll = 0
                    state.asset_explorer_preview_key = None
                    setattr(state.player, "asset_explorer_type", state.asset_explorer_type)
                    setattr(state.player, "asset_explorer_focus", state.asset_explorer_focus)
                    setattr(state.player, "asset_explorer_info_scroll", state.asset_explorer_info_scroll)
                    state.action_cursor = 0
                else:
                    if len(state.title_menu_stack) > 1:
                        state.title_menu_stack.pop()
                commands = action_commands_for_state(ctx, state)
                clamp_action_cursor(state, commands)
                return None, None
            if isinstance(cmd, str) and cmd.startswith("TITLE_ASSET_TOGGLE:"):
                toggle = cmd.split(":", 1)[1]
                if toggle == "art":
                    state.asset_explorer_show_art = not state.asset_explorer_show_art
                    setattr(state.player, "asset_explorer_show_art", state.asset_explorer_show_art)
                elif toggle == "stats":
                    state.asset_explorer_show_stats = not state.asset_explorer_show_stats
                    setattr(state.player, "asset_explorer_show_stats", state.asset_explorer_show_stats)
                elif toggle == "json":
                    state.asset_explorer_show_json = not state.asset_explorer_show_json
                    setattr(state.player, "asset_explorer_show_json", state.asset_explorer_show_json)
                setattr(state.player, "asset_explorer_focus", state.asset_explorer_focus)
                setattr(state.player, "asset_explorer_info_scroll", state.asset_explorer_info_scroll)
                state.asset_explorer_info_scroll = 0
                commands = action_commands_for_state(ctx, state)
                clamp_action_cursor(state, commands)
                return None, None
            if isinstance(cmd, str) and cmd.startswith("TITLE_ASSET_SELECT:"):
                return None, None
            if isinstance(cmd, str) and cmd.startswith("TITLE_MENU_SUB:"):
                menu_id = cmd.split(":", 1)[1]
                if menu_id:
                    state.title_menu_stack.append(menu_id)
                    commands = action_commands_for_state(ctx, state)
                    clamp_action_cursor(state, commands)
                return None, None
            if cmd == "TITLE_MENU_BACK":
                if len(state.title_menu_stack) > 1:
                    state.title_menu_stack.pop()
                commands = action_commands_for_state(ctx, state)
                clamp_action_cursor(state, commands)
                return None, None
            return cmd, command_meta
        return None, None

    if state.portal_mode:
        commands = action_commands_for_state(ctx, state)
        clamp_action_cursor(state, commands)
        if action in ("UP", "DOWN"):
            enabled = _enabled_indices(commands)
            if enabled:
                pos = enabled.index(state.action_cursor) if state.action_cursor in enabled else 0
                direction = -1 if action == "UP" else 1
                pos = (pos + direction) % len(enabled)
                state.action_cursor = enabled[pos]
            return None, None
        if action in ("LEFT", "RIGHT"):
            return None, None
        if action == "BACK":
            cmd = "B_KEY"
            command_meta = find_command_meta(commands, cmd)
            return cmd if command_meta else cmd, command_meta
        if action == "CONFIRM":
            if not commands or state.action_cursor < 0:
                return None, None
            command_meta = commands[state.action_cursor]
            if command_meta.get("_disabled"):
                return None, None
            cmd = command_meta.get("command")
            return cmd, command_meta
        return None, None

    commands = action_commands_for_state(ctx, state)
    clamp_action_cursor(state, commands)
    if action in ("UP", "DOWN", "LEFT", "RIGHT"):
        state.action_cursor = move_action_cursor(state.action_cursor, action, commands)
        if state.player.location == "Forest" and any(opp.hp > 0 for opp in state.opponents):
            state.battle_cursor = state.action_cursor
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
        if state.player.location == "Forest" and any(opp.hp > 0 for opp in state.opponents):
            state.battle_cursor = state.action_cursor
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
    targeted = cmd in ("ATTACK", "SOCIALIZE") or cmd in ctx.targeted_spell_commands
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
    if message == "You flee to safety.":
        state.battle_log = []
    if message:
        if message == "There is nothing to flee from." and state.battle_log and state.battle_log[-1] == "You flee to safety.":
            return
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


def _follower_element_spell_id(element: str) -> Optional[str]:
    mapping = {
        "earth": "boulder",
        "wind": "tornado",
        "fire": "fireblast",
        "water": "tide",
        "lightning": "spark",
        "ice": "iceblast",
        "light": "radiance",
        "dark": "shade",
    }
    return mapping.get(element)


def _follower_wand_element(gear: Optional[dict]) -> Optional[str]:
    if not isinstance(gear, dict):
        return None
    points = gear.get("elem_points", {})
    if isinstance(points, dict) and points:
        element = max(points.items(), key=lambda entry: int(entry[1] or 0))[0]
        return str(element)
    element = gear.get("element")
    return str(element) if element else None


def _open_quest_screen(ctx, state: GameState) -> None:
    state.quest_mode = True
    state.quest_detail_mode = False
    state.quest_detail_id = None
    state.quest_detail_page = 0
    state.options_mode = False
    state.shop_mode = False
    state.hall_mode = False
    state.inn_mode = False
    state.inventory_mode = False
    state.spell_mode = False
    state.element_mode = False
    state.alchemist_mode = False
    state.temple_mode = False
    state.smithy_mode = False
    state.portal_mode = False
    state.followers_mode = False
    elements = list(getattr(state.player, "elements", []) or [])
    if hasattr(ctx, "continents"):
        order = list(ctx.continents.order() or [])
        if order:
            elements = [e for e in order if e in elements] or elements
    current = getattr(state.player, "current_element", None)
    if current in elements:
        state.quest_continent_index = elements.index(current)
    else:
        state.quest_continent_index = 0


def _follower_can_cast(player, follower: dict, spell: dict) -> tuple[bool, bool]:
    mp_cost = int(spell.get("mp_cost", 0) or 0)
    element = spell.get("element")
    if element:
        charges = player.follower_wand_charges(follower)
        if int(charges.get(str(element), 0) or 0) > 0:
            return True, True
    mp = int(follower.get("mp", 0) or 0)
    return mp >= mp_cost, False


def _run_follower_action(ctx, render_frame, state: GameState, generate_frame) -> None:
    if not state.player.followers or not any(opp.hp > 0 for opp in state.opponents):
        return
    for follower in state.player.followers:
        if not isinstance(follower, dict):
            continue
        follower_type = str(follower.get("type", ""))
        if follower_type in ("mushroom_baby", "fairy_baby"):
            ability_key = "mushroom_tea_brew" if follower_type == "mushroom_baby" else "fairy_tea_brew"
            fallback_item = "mushroom_tea" if follower_type == "mushroom_baby" else "fairy_tea"
            missing = _team_missing_total(state.player)
            ability = ctx.abilities.get(ability_key, {}) if hasattr(ctx, "abilities") else {}
            chance = float(ability.get("chance", 0.2) or 0.2) if isinstance(ability, dict) else 0.2
            if missing > 0 and random.random() < chance:
                item_id = str(ability.get("item_id", fallback_item) or fallback_item)
                item = ctx.items.get(item_id, {}) if hasattr(ctx, "items") else {}
                if isinstance(item, dict):
                    candidates = [("player", None, _team_missing_total(state.player, mode="combined"))]
                    for teammate in state.player.followers:
                        if not isinstance(teammate, dict):
                            continue
                        candidates.append(("follower", teammate, _team_missing_total(state.player, teammate, mode="combined")))
                    target_type, target_ref, _missing = max(candidates, key=lambda entry: entry[2])
                    healed_hp, healed_mp = _apply_item_heal(
                        target_ref if target_type == "follower" else "player",
                        item,
                        state.player,
                    )
                    if healed_hp > 0 or healed_mp > 0:
                        target_name = "you" if target_type == "player" else target_ref.get("name", "Follower")
                        name = follower.get("name", "Follower")
                        parts = []
                        if healed_hp:
                            parts.append(f"{healed_hp} HP")
                        if healed_mp:
                            parts.append(f"{healed_mp} MP")
                        restored = " and ".join(parts)
                        label = ability.get("label", "Tea") if isinstance(ability, dict) else "Tea"
                        push_battle_message(state, f"{name} uses {label} on {target_name}, restoring {restored}.")
                        continue
            alive = [opp for opp in state.opponents if opp.hp > 0]
            if not alive:
                continue
            opponent = min(alive, key=lambda opp: opp.hp)
            damage, crit, miss = roll_damage(state.player.follower_total_atk(follower), opponent.defense)
            name = follower.get("name", "Follower")
            if miss:
                push_battle_message(state, f"{name} misses the {opponent.name}.")
                continue
            opponent.hp = max(0, opponent.hp - damage)
            if opponent.hp == 0:
                push_battle_message(state, f"{name} strikes down the {opponent.name}.")
                continue
            if crit:
                push_battle_message(state, f"Critical hit! {name} hits the {opponent.name} for {damage}.")
            else:
                push_battle_message(state, f"{name} hits the {opponent.name} for {damage}.")
            continue
        spells = follower.get("spells", [])
        if not isinstance(spells, list):
            spells = []
        # Priority: healing if needed, then strength, then elemental
        if "healing" in spells:
            spell = ctx.spells.get("healing", {})
            can_cast, use_charge = _follower_can_cast(state.player, follower, spell)
            if can_cast and state.player.hp < state.player.total_max_hp():
                if not use_charge:
                    follower["mp"] = max(0, int(follower.get("mp", 0) or 0) - int(spell.get("mp_cost", 0) or 0))
                animate_life_boost_gain(ctx, render_frame, state, generate_frame, 1)
                name = follower.get("name", "Follower")
                push_battle_message(state, f"{name} casts Life Boost.")
                continue
        if "strength" in spells:
            spell = ctx.spells.get("strength", {})
            can_cast, use_charge = _follower_can_cast(state.player, follower, spell)
            if can_cast and (state.player.temp_atk_bonus <= 0 or state.player.temp_def_bonus <= 0):
                if not use_charge:
                    follower["mp"] = max(0, int(follower.get("mp", 0) or 0) - int(spell.get("mp_cost", 0) or 0))
                animate_strength_gain(ctx, render_frame, state, generate_frame, 1)
                name = follower.get("name", "Follower")
                push_battle_message(state, f"{name} casts Strength.")
                continue
        wand = state.player.follower_gear_instance(follower, "wand")
        element = _follower_wand_element(wand)
        spell_id = _follower_element_spell_id(element) if element else None
        if spell_id:
            spell = ctx.spells.get(spell_id, {})
            can_cast, use_charge = _follower_can_cast(state.player, follower, spell)
            if can_cast:
                if use_charge:
                    state.player.consume_follower_wand_charge(follower, str(element))
                else:
                    follower["mp"] = max(0, int(follower.get("mp", 0) or 0) - int(spell.get("mp_cost", 0) or 0))
                target = primary_opponent_index(state.opponents)
                if target is None:
                    continue
                opponent = state.opponents[target]
                atk_bonus = int(spell.get("atk_bonus", 2) or 2)
                if element:
                    atk_bonus += state.player.follower_element_points_total(follower, str(element))
                damage_mult = float(spell.get("rank3_damage_mult", 1.25)) if spell.get("rank3_damage_mult") else 1.0
                damage, crit, miss = roll_damage(state.player.follower_total_atk(follower) + atk_bonus, opponent.defense)
                damage = int(damage * damage_mult)
                name = follower.get("name", "Follower")
                spell_name = spell.get("name", spell_id.title())
                if miss:
                    push_battle_message(state, f"{name}'s {spell_name} misses the {opponent.name}.")
                    continue
                opponent.hp = max(0, opponent.hp - damage)
                if opponent.hp == 0:
                    push_battle_message(state, f"{name}'s {spell_name} fells the {opponent.name}.")
                    continue
                stun_chance = float(spell.get("stun_chance", 0.0) or 0.0)
                stunned_turns = try_stun(opponent, stun_chance) if stun_chance > 0 else 0
                if crit:
                    message = f"{name} lands a critical {spell_name} for {damage}."
                else:
                    message = f"{name} hits the {opponent.name} with {spell_name} for {damage}."
                if stunned_turns > 0:
                    message += f" It is stunned for {stunned_turns} turn(s)."
                push_battle_message(state, message)
                continue
        # fallback attack
        target = primary_opponent_index(state.opponents)
        if target is None:
            continue
        opponent = state.opponents[target]
        damage, crit, miss = roll_damage(state.player.follower_total_atk(follower), opponent.defense)
        name = follower.get("name", "Follower")
        if miss:
            push_battle_message(state, f"{name} misses the {opponent.name}.")
            continue
        opponent.hp = max(0, opponent.hp - damage)
        if opponent.hp == 0:
            push_battle_message(state, f"{name} strikes down the {opponent.name}.")
            continue
        if crit:
            push_battle_message(state, f"Critical hit! {name} hits the {opponent.name} for {damage}.")
        else:
            push_battle_message(state, f"{name} hits the {opponent.name} for {damage}.")


def _team_missing_total(player, follower: Optional[dict] = None, *, mode: str = "combined") -> int:
    if follower is None:
        max_hp = player.total_max_hp()
        max_mp = int(player.max_mp)
        missing_hp = max_hp - int(player.hp)
        missing_mp = max_mp - int(player.mp)
        if mode == "hp":
            return missing_hp
        return missing_hp + missing_mp
    if not isinstance(follower, dict):
        return 0
    max_hp = int(follower.get("max_hp", 0) or 0)
    max_mp = int(follower.get("max_mp", 0) or 0)
    hp = int(follower.get("hp", max_hp) or max_hp)
    mp = int(follower.get("mp", max_mp) or max_mp)
    missing_hp = max(0, max_hp - hp)
    missing_mp = max(0, max_mp - mp)
    if mode == "hp":
        return missing_hp
    return missing_hp + missing_mp


def _apply_item_heal(target, item: dict, player: Player) -> tuple[int, int]:
    hp_gain = int(item.get("hp", 0) or 0)
    mp_gain = int(item.get("mp", 0) or 0)
    healed_hp = 0
    healed_mp = 0
    if target == "player":
        if hp_gain > 0:
            max_hp = player.total_max_hp()
            healed_hp = min(hp_gain, max_hp - player.hp)
            player.hp += healed_hp
        if mp_gain > 0:
            max_mp = player.max_mp
            healed_mp = min(mp_gain, max_mp - player.mp)
            player.mp += healed_mp
        return healed_hp, healed_mp
    if isinstance(target, dict):
        if hp_gain > 0:
            max_hp = int(target.get("max_hp", 0) or 0)
            current_hp = int(target.get("hp", max_hp) or max_hp)
            healed_hp = min(hp_gain, max(0, max_hp - current_hp))
            target["hp"] = current_hp + healed_hp
        if mp_gain > 0:
            max_mp = int(target.get("max_mp", 0) or 0)
            current_mp = int(target.get("mp", max_mp) or max_mp)
            healed_mp = min(mp_gain, max(0, max_mp - current_mp))
            target["mp"] = current_mp + healed_mp
    return healed_hp, healed_mp


def spell_level_up_notes(ctx, player, prev_level: int, new_level: int) -> list[str]:
    notes = []
    for _, spell in ctx.spells.available(player, ctx.items):
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
            notes.append(f"Portal Unlocked: {element_name}")
    if not player.elements:
        player.elements.append(order[0])
    if order:
        player.elements = [e for e in order if e in player.elements]
    return notes


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
    pre_location = state.player.location
    pre_in_forest = state.player.location == "Forest"
    pre_alive = any(m.hp > 0 for m in state.opponents)
    pre_spell_mode = state.spell_mode
    pre_title_slot_select = getattr(state.player, "title_slot_select", False)
    pre_title_fortune = getattr(state.player, "title_fortune", False)
    pre_title_confirm = getattr(state.player, "title_confirm", False)
    pre_portal_mode = state.portal_mode
    pre_quest_mode = state.quest_mode
    pre_quest_detail_mode = state.quest_detail_mode
    pre_quest_detail_id = state.quest_detail_id
    pre_quest_detail_page = state.quest_detail_page
    pre_title_name_select = getattr(state.player, "title_name_select", False)
    pre_title_start_confirm = getattr(state.player, "title_start_confirm", False)
    cmd_state = CommandState(
        player=state.player,
        opponents=state.opponents,
        loot_bank=state.loot_bank,
        last_message=state.last_message,
        current_venue_id=state.current_venue_id,
        shop_mode=state.shop_mode,
        shop_view=state.shop_view,
        inventory_mode=state.inventory_mode,
        inventory_items=state.inventory_items,
        hall_mode=state.hall_mode,
        hall_view=state.hall_view,
        inn_mode=state.inn_mode,
        stats_mode=state.stats_mode,
        spell_mode=state.spell_mode,
        followers_mode=state.followers_mode,
        element_mode=state.element_mode,
        alchemist_mode=state.alchemist_mode,
        alchemy_first=state.alchemy_first,
        alchemy_selecting=state.alchemy_selecting,
        temple_mode=state.temple_mode,
        smithy_mode=state.smithy_mode,
        portal_mode=state.portal_mode,
        quest_mode=state.quest_mode,
        quest_detail_mode=state.quest_detail_mode,
        options_mode=state.options_mode,
        action_cmd=action_cmd,
        quest_continent_index=state.quest_continent_index,
        quest_detail_id=state.quest_detail_id,
        quest_detail_page=state.quest_detail_page,
        target_index=state.target_index,
        command_target_override=command_meta.get("target") if command_meta else None,
        command_service_override=command_meta.get("service_id") if command_meta else None,
    )
    if not handle_command(cmd, cmd_state, ctx.router_ctx, key=None):
        return False, action_cmd, cmd, False, None
    state.opponents = cmd_state.opponents
    state.loot_bank = cmd_state.loot_bank
    state.current_venue_id = cmd_state.current_venue_id
    post_in_forest = state.player.location == "Forest"
    post_alive = any(m.hp > 0 for m in state.opponents)
    if hasattr(ctx, "audio"):
        player_alive = bool(getattr(state.player, "hp", 1) > 0)
        ctx.audio.on_battle_change(pre_alive, post_alive, post_in_forest, player_alive, pre_in_forest)
    if not pre_in_forest and post_in_forest:
        state.battle_log = []
    if pre_in_forest and not post_in_forest:
        state.battle_log = []
    if post_in_forest and post_alive and not pre_alive:
        state.battle_log = []
        commands = scene_commands(ctx.scenes, ctx.commands_data, "forest", state.player, state.opponents)
        state.action_cursor = state.battle_cursor
        clamp_action_cursor(state, commands)
    if cmd == "FLEE" and cmd_state.last_message == "You flee to safety.":
        state.battle_log = []
    push_battle_message(state, cmd_state.last_message)
    state.shop_mode = cmd_state.shop_mode
    state.shop_view = cmd_state.shop_view
    state.inventory_mode = cmd_state.inventory_mode
    state.inventory_items = cmd_state.inventory_items
    state.hall_mode = cmd_state.hall_mode
    state.hall_view = cmd_state.hall_view
    state.inn_mode = cmd_state.inn_mode
    state.stats_mode = cmd_state.stats_mode
    state.spell_mode = cmd_state.spell_mode
    state.followers_mode = cmd_state.followers_mode
    state.element_mode = cmd_state.element_mode
    state.alchemist_mode = cmd_state.alchemist_mode
    state.alchemy_first = cmd_state.alchemy_first
    state.alchemy_selecting = cmd_state.alchemy_selecting
    state.temple_mode = cmd_state.temple_mode
    state.smithy_mode = cmd_state.smithy_mode
    state.portal_mode = cmd_state.portal_mode
    state.quest_mode = cmd_state.quest_mode
    state.quest_detail_mode = cmd_state.quest_detail_mode
    state.options_mode = cmd_state.options_mode
    action_cmd = cmd_state.action_cmd
    state.quest_continent_index = cmd_state.quest_continent_index
    state.quest_detail_id = cmd_state.quest_detail_id
    state.quest_detail_page = cmd_state.quest_detail_page
    target_index = cmd_state.target_index
    post_title_slot_select = getattr(state.player, "title_slot_select", False)
    post_title_fortune = getattr(state.player, "title_fortune", False)
    post_title_confirm = getattr(state.player, "title_confirm", False)
    post_portal_mode = state.portal_mode
    post_quest_mode = state.quest_mode
    post_quest_detail_mode = state.quest_detail_mode
    post_quest_detail_id = state.quest_detail_id
    post_quest_detail_page = state.quest_detail_page
    post_title_name_select = getattr(state.player, "title_name_select", False)
    post_title_start_confirm = getattr(state.player, "title_start_confirm", False)
    if post_title_slot_select and not pre_title_slot_select:
        commands = action_commands_for_state(ctx, state)
        state.action_cursor = 0
        clamp_action_cursor(state, commands)
    if post_title_fortune and not pre_title_fortune:
        state.action_cursor = 0
    if post_title_confirm and not pre_title_confirm:
        state.action_cursor = 0
    if post_title_name_select and not pre_title_name_select:
        state.action_cursor = 0
    if post_title_start_confirm and not pre_title_start_confirm:
        state.action_cursor = 0
    if post_portal_mode and not pre_portal_mode:
        commands = action_commands_for_state(ctx, state)
        enabled = _enabled_indices(commands)
        state.action_cursor = enabled[0] if enabled else 0
    if post_quest_mode and not pre_quest_mode:
        state.quest_audio_played = True
    if post_quest_mode and not pre_quest_mode:
        elements = list(getattr(state.player, "elements", []) or [])
        if hasattr(ctx, "continents"):
            order = list(ctx.continents.order() or [])
            if order:
                elements = [e for e in order if e in elements] or elements
        if not elements:
            elements = ["base"]
        state.quest_continent_index = max(0, min(state.quest_continent_index, len(elements) - 1))
        entries = quest_entries(
            state.player,
            ctx.quests,
            ctx.items,
            continent=elements[state.quest_continent_index],
        ) if hasattr(ctx, "quests") else []
        commands = [{"_disabled": True}]
        if entries:
            for entry in entries:
                commands.append({"_disabled": False})
        else:
            commands.append({"_disabled": True})
        commands.append({"_disabled": False})
        enabled = [i for i, cmd in enumerate(commands) if not cmd.get("_disabled")]
        state.action_cursor = enabled[0] if enabled else -1
    if post_quest_detail_mode:
        detail_key = f"{post_quest_detail_id}:{post_quest_detail_page}"
        if detail_key != (state.quest_detail_audio_key or ""):
            state.quest_detail_audio_key = detail_key
    if (
        (pre_title_fortune and not post_title_fortune)
        or (pre_title_confirm and not post_title_confirm)
        or (pre_title_slot_select and not post_title_slot_select)
        or (pre_title_name_select and not post_title_name_select)
        or (pre_title_start_confirm and not post_title_start_confirm)
    ):
        commands = action_commands_for_state(ctx, state)
        state.action_cursor = 0
        clamp_action_cursor(state, commands)
    if state.spell_mode and not pre_spell_mode:
        state.menu_cursor = state.spell_cursor
        keys = spell_menu_keys(ctx, state.player)
        if keys and 0 <= state.menu_cursor < len(keys):
            spell_entry = ctx.spells.by_command_id(keys[state.menu_cursor])
            if spell_entry:
                _, spell = spell_entry
                max_rank = ctx.spells.rank_for(spell, state.player.level)
                base_cost = int(spell.get("mp_cost", 0))
                element = spell.get("element")
                has_charge = False
                if element:
                    charges = state.player.wand_charges()
                    has_charge = int(charges.get(str(element), 0)) > 0
                max_affordable = max_rank
                if not has_charge and base_cost > 0:
                    max_affordable = min(max_rank, state.player.mp // base_cost)
                state.spell_cast_rank = max(1, max_affordable) if max_affordable >= 1 else 1
    if cmd == "ENTER_VENUE":
        commands = action_commands_for_state(ctx, state)
        state.action_cursor = 0
        clamp_action_cursor(state, commands)
    if state.player.location == "Title" and cmd_state.player.location != "Title":
        state.title_mode = False
    state.player = cmd_state.player
    post_location = state.player.location
    if hasattr(ctx, "audio"):
        ctx.audio.set_mode(state.player.flags.get("audio_mode"))
        ctx.audio.on_location_change(pre_location, post_location)
    if post_location == "Town" and pre_location != "Town":
        commands = scene_commands(ctx.scenes, ctx.commands_data, "town", state.player, state.opponents)
        state.action_cursor = 0
        clamp_action_cursor(state, commands)
    if post_location == "Forest" and pre_location != "Forest":
        commands = scene_commands(ctx.scenes, ctx.commands_data, "forest", state.player, state.opponents)
        state.action_cursor = 0
        clamp_action_cursor(state, commands)
    if pre_location == "Forest" and post_location == "Forest" and pre_alive and not post_alive:
        commands = scene_commands(ctx.scenes, ctx.commands_data, "forest", state.player, state.opponents)
        state.action_cursor = 0
        clamp_action_cursor(state, commands)
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
    render_frame,
    state: GameState,
    cmd: Optional[str],
    command_meta: Optional[dict],
    action_cmd: Optional[str],
    handled_by_router: bool,
    generate_frame,
) -> Optional[str]:
    if handled_by_router:
        return action_cmd
    if cmd == "DEFEND":
        alive = [opp for opp in state.opponents if opp.hp > 0]
        highest = max((opp.level for opp in alive), default=state.player.level)
        lower_level = highest < state.player.level
        defense_bonus = max(2, state.player.total_defense() // 2)
        evasion_bonus = 0.15 if lower_level else 0.05
        state.defend_active = True
        state.defend_bonus = defense_bonus
        state.defend_evasion = evasion_bonus
        state.action_effect_override = None
        state.last_spell_targets = []
        push_battle_message(state, "You brace for impact.")
        return cmd
    state.defend_active = False
    state.defend_bonus = 0
    state.defend_evasion = 0.0
    state.action_effect_override = None
    state.last_spell_targets = []
    state.last_team_target_player = None
    spell_entry = ctx.spells.by_command_id(cmd)
    if spell_entry:
        spell_id, spell = spell_entry
        name = spell.get("name", spell_id.title())
        max_rank = ctx.spells.rank_for(spell, state.player.level)
        base_cost = int(spell.get("mp_cost", 2))
        element = spell.get("element")
        has_charge = False
        if element:
            charges = state.player.wand_charges()
            has_charge = int(charges.get(str(element), 0)) > 0
        max_affordable = max_rank
        if not has_charge and base_cost > 0:
            max_affordable = min(max_rank, state.player.mp // base_cost)
        if max_affordable < 1:
            state.last_message = f"Not enough MP to cast {name}."
            return None
        rank = max(1, min(state.spell_cast_rank, max_rank, max_affordable))
        state.spell_cast_rank = rank
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
        if spell_id in ("healing", "strength"):
            in_battle = state.player.location == "Forest" and any(opp.hp > 0 for opp in state.opponents)
            if state.spell_mode and not in_battle:
                state.spell_target_mode = True
                if not state.spell_target_command:
                    state.spell_target_command = cmd
            if state.player.mp < base_cost and not has_charge:
                state.last_message = f"Not enough MP to cast {name}."
                return None
            if state.team_target_index is not None:
                if state.team_target_index == 0:
                    target_type, target_ref = "player", state.player
                else:
                    followers = getattr(state.player, "followers", []) or []
                    idx = state.team_target_index - 1
                    if isinstance(followers, list) and 0 <= idx < len(followers):
                        target_type, target_ref = "follower", followers[idx]
                    else:
                        target_type, target_ref = state.player.select_team_target(mode="combined")
            else:
                target_type, target_ref = state.player.select_team_target(mode="combined")
            state.team_target_index = None
            if target_type == "none":
                state.last_message = "HP and MP are already full."
                return None
            if not has_charge:
                state.player.mp -= base_cost
            state.last_team_target_player = (target_type == "player")
            if target_type != "player":
                gain_per_cast = max(0, 10 * rank)
                max_stack = gain_per_cast * 5
                if spell_id == "healing":
                    current = int(target_ref.get("temp_hp_bonus", 0) or 0)
                    remaining = max(0, max_stack - current)
                    gain = min(gain_per_cast, remaining)
                    if gain > 0:
                        animate_follower_life_boost_gain(
                            ctx,
                            render_frame,
                            state,
                            generate_frame,
                            target_ref,
                            gain,
                        )
                else:
                    current_atk = int(target_ref.get("temp_atk_bonus", 0) or 0)
                    current_def = int(target_ref.get("temp_def_bonus", 0) or 0)
                    current = min(current_atk, current_def)
                    remaining = max(0, max_stack - current)
                    gain = min(gain_per_cast, remaining)
                    if gain > 0:
                        animate_follower_strength_gain(
                            ctx,
                            render_frame,
                            state,
                            generate_frame,
                            target_ref,
                            gain,
                        )
            target_name = "you" if target_type == "player" else target_ref.get("name", "Follower")
            spell_label = "Life Boost" if spell_id == "healing" else "Strength"
            state.last_message = f"You cast {spell_label} on {target_name}."
            return cmd
        mp_cost = base_cost * max(1, rank)
        if state.player.mp < mp_cost and not has_charge:
            state.last_message = f"Not enough MP to cast {name}."
            return None
        message = cast_spell(
            state.player,
            state.opponents,
            spell_id,
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
        max_rank = ctx.spells.rank_for(spell, state.player.level)
        rank = max(1, min(state.spell_cast_rank, max_rank))
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
            ai = getattr(m, "ai", None)
            if isinstance(ai, dict) and ai.get("type") == "support_heal_then_attack":
                chance = float(ai.get("heal_chance", 0.0) or 0.0)
                item_id = str(ai.get("heal_item_id", "") or "")
                if item_id and chance > 0:
                    missing_targets = [
                        opp for opp in state.opponents
                        if opp.hp > 0 and opp.hp < opp.max_hp
                    ]
                    if missing_targets and random.random() < chance:
                        item = ctx.items.get(item_id, {}) if hasattr(ctx, "items") else {}
                        hp_gain = int(item.get("hp", 0) or 0) if isinstance(item, dict) else 0
                        if hp_gain > 0:
                            if str(ai.get("heal_target", "")) == "most_missing_hp":
                                target = max(missing_targets, key=lambda opp: (opp.max_hp - opp.hp))
                            else:
                                target = missing_targets[0]
                            healed = min(hp_gain, target.max_hp - target.hp)
                            target.hp += healed
                            label = item.get("name", "Item") if isinstance(item, dict) else "Item"
                            push_battle_message(state, f"The {m.name} uses {label} on the {target.name}, restoring {healed} HP.")
                            continue
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
    _run_follower_action(ctx, render_frame, state, generate_frame)
    if state.player.temp_atk_bonus > 0:
        state.player.temp_atk_bonus = max(0, state.player.temp_atk_bonus - 1)
    if state.player.temp_def_bonus > 0:
        state.player.temp_def_bonus = max(0, state.player.temp_def_bonus - 1)
    if state.player.temp_hp_bonus > 0:
        state.player.temp_hp_bonus = max(0, state.player.temp_hp_bonus - 1)
        max_hp = state.player.total_max_hp()
        if state.player.hp > max_hp:
            state.player.hp = max_hp
    if state.player.followers:
        for follower in state.player.followers:
            if not isinstance(follower, dict):
                continue
            if int(follower.get("temp_atk_bonus", 0) or 0) > 0:
                follower["temp_atk_bonus"] = max(0, int(follower.get("temp_atk_bonus", 0) or 0) - 1)
            if int(follower.get("temp_def_bonus", 0) or 0) > 0:
                follower["temp_def_bonus"] = max(0, int(follower.get("temp_def_bonus", 0) or 0) - 1)
            if int(follower.get("temp_hp_bonus", 0) or 0) > 0:
                follower["temp_hp_bonus"] = max(0, int(follower.get("temp_hp_bonus", 0) or 0) - 1)
                max_hp = state.player.follower_total_max_hp(follower)
                hp = int(follower.get("hp", max_hp) or max_hp)
                if hp > max_hp:
                    follower["hp"] = max_hp
    if state.player.followers:
        for follower in state.player.followers:
            if not isinstance(follower, dict):
                continue
            if str(follower.get("type", "")) == "mushroom_baby":
                continue
            abilities_list = follower.get("abilities", [])
            if not isinstance(abilities_list, list):
                abilities_list = []
            ability_id = str(follower.get("active_ability", "") or "")
            if ability_id and ability_id not in abilities_list:
                ability_id = ""
            if not ability_id and abilities_list:
                ability_id = str(abilities_list[0])
                follower["active_ability"] = ability_id
            if not ability_id:
                continue
            ability = ctx.abilities.get(ability_id, {}) if hasattr(ctx, "abilities") else {}
            if not isinstance(ability, dict):
                continue
            if ability.get("timing") != "end_round":
                continue
            level = int(follower.get("level", 1) or 1)
            min_level = int(ability.get("min_level", 1) or 1)
            if level < min_level:
                fallback = ""
                for candidate_id in abilities_list:
                    candidate = ctx.abilities.get(candidate_id, {}) if hasattr(ctx, "abilities") else {}
                    if not isinstance(candidate, dict):
                        continue
                    req = int(candidate.get("min_level", 1) or 1)
                    if level >= req:
                        fallback = str(candidate_id)
                        ability = candidate
                        min_level = req
                        break
                if not fallback:
                    continue
                follower["active_ability"] = fallback
            base_min = int(ability.get("base_min", 0) or 0)
            base_max = int(ability.get("base_max", 0) or 0)
            bonus = int(ability.get("per_level_bonus", 0) or 0) * max(0, level - 1)
            heal_min = base_min + bonus
            heal_max = base_max + bonus
            if heal_max <= 0:
                continue
            amount = random.randint(heal_min, max(heal_min, heal_max))
            ability_type = ability.get("type")
            if ability_type == "heal":
                max_hp = state.player.total_max_hp()
                if state.player.hp >= max_hp:
                    continue
                healed = min(amount, max_hp - state.player.hp)
                state.player.hp += healed
                suffix = "HP"
            elif ability_type == "mana":
                max_mp = state.player.max_mp
                if state.player.mp >= max_mp:
                    continue
                healed = min(amount, max_mp - state.player.mp)
                state.player.mp += healed
                suffix = "MP"
            elif ability_type == "item":
                chance = float(ability.get("chance", 1.0) or 1.0)
                if random.random() > chance:
                    continue
                item_id = str(ability.get("item_id", "") or "")
                if not item_id:
                    continue
                item = ctx.items.get(item_id, {}) if hasattr(ctx, "items") else {}
                if not isinstance(item, dict):
                    continue
                target_mode = str(ability.get("target", "combined") or "combined")
                candidates = [("player", None, _team_missing_total(state.player, mode=target_mode))]
                for teammate in state.player.followers:
                    if not isinstance(teammate, dict):
                        continue
                    missing = _team_missing_total(state.player, teammate, mode=target_mode)
                    candidates.append(("follower", teammate, missing))
                target_type, target_ref, missing = max(candidates, key=lambda entry: entry[2])
                if missing <= 0:
                    continue
                healed_hp, healed_mp = _apply_item_heal(target_ref if target_type == "follower" else "player", item, state.player)
                if healed_hp <= 0 and healed_mp <= 0:
                    continue
                target_name = "you" if target_type == "player" else target_ref.get("name", "Follower")
                name = follower.get("name", "Follower")
                label = ability.get("label", "Item")
                parts = []
                if healed_hp:
                    parts.append(f"{healed_hp} HP")
                if healed_mp:
                    parts.append(f"{healed_mp} MP")
                restored = " and ".join(parts)
                push_battle_message(state, f"{name} uses {label} on {target_name}, restoring {restored}.")
                continue
            else:
                continue
            name = follower.get("name", "Follower")
            label = ability.get("label", "Ability")
            push_battle_message(state, f"{name} uses {label} and restores {healed} {suffix}.")
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
    state.battle_cursor = state.action_cursor
    if state.loot_bank["xp"] or state.loot_bank["gold"]:
        pre_level = state.player.level
        levels_gained = state.player.gain_xp(state.loot_bank["xp"])
        state.player.gold += state.loot_bank["gold"]
        if state.player.followers and state.loot_bank["xp"] > 0:
            share = int(state.loot_bank["xp"] * 0.5)
            if share > 0:
                for follower in state.player.followers:
                    if not isinstance(follower, dict):
                        continue
                    level = int(follower.get("level", 1) or 1)
                    max_level = int(follower.get("max_level", 5) or 5)
                    xp = int(follower.get("xp", 0) or 0) + share
                    start_level = level
                    threshold = 100
                    for _ in range(1, level):
                        threshold *= 2
                    stat_breakdown = {"HP": 0, "MP": 0, "ATK": 0, "DEF": 0}
                    while level < max_level and xp >= threshold:
                        xp -= threshold
                        level += 1
                        rolls = [random.choice(["HP", "MP", "ATK", "DEF"]) for _ in range(10)]
                        follower["stat_points"] = int(follower.get("stat_points", 0) or 0) + 10
                        for stat_roll in rolls:
                            stat_breakdown[stat_roll] = stat_breakdown.get(stat_roll, 0) + 1
                            if stat_roll == "HP":
                                max_hp = int(follower.get("max_hp", 0) or 0) + 1
                                follower["max_hp"] = max_hp
                                hp = int(follower.get("hp", max_hp) or max_hp)
                                follower["hp"] = min(max_hp, hp + 1)
                            elif stat_roll == "MP":
                                max_mp = int(follower.get("max_mp", 0) or 0) + 1
                                follower["max_mp"] = max_mp
                                mp = int(follower.get("mp", max_mp) or max_mp)
                                follower["mp"] = min(max_mp, mp + 1)
                            elif stat_roll == "ATK":
                                follower["atk"] = int(follower.get("atk", 0) or 0) + 1
                            else:
                                follower["defense"] = int(follower.get("defense", 0) or 0) + 1
                        threshold *= 2
                    follower["xp"] = xp
                    follower["level"] = level
                    if level > start_level:
                        name = follower.get("name", "Follower")
                        stat_parts = []
                        for key in ("HP", "MP", "ATK", "DEF"):
                            value = stat_breakdown.get(key, 0)
                            if value:
                                stat_parts.append(f"{key}+{value}")
                        bonus_text = " ".join(stat_parts) if stat_parts else "No stats"
                        push_battle_message(state, f"{name} leveled up to {level}! {bonus_text}")
        push_battle_message(state, (
            f"You gain {state.loot_bank['xp']} XP and "
            f"{state.loot_bank['gold']} gold."
        ))
        if levels_gained > 0:
            state.leveling_mode = True
            spell_notes = spell_level_up_notes(ctx, state.player, pre_level, state.player.level)
            element_notes = element_unlock_notes(ctx, state.player, pre_level, state.player.level)
            state.level_up_notes = spell_notes + element_notes
            if hasattr(ctx, "audio"):
                ctx.audio.play_song_once("level_up")
        else:
            if hasattr(ctx, "audio") and getattr(state.player, "hp", 0) > 0:
                ctx.audio.play_song_once("battle_victory")
        if hasattr(ctx, "quests") and ctx.quests is not None:
            quest_messages = evaluate_quests(state.player, ctx.quests, ctx.items)
            for message in quest_messages:
                push_battle_message(state, message)
            if quest_messages:
                _open_quest_screen(ctx, state)
        push_battle_message(state, "All is quiet. No enemies in sight.")
    else:
        state.last_message = ""
        push_battle_message(state, "All is quiet. No enemies in sight.")
    state.loot_bank = {"xp": 0, "gold": 0}
    commands = scene_commands(ctx.scenes, ctx.commands_data, "forest", state.player, state.opponents)
    state.action_cursor = 0
    clamp_action_cursor(state, commands)
