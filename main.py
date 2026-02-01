import copy
import shutil
import os
import sys
import json
from json import JSONDecodeError
from typing import Optional

WEB_MODE = os.environ.get("LOKARTA_WEB") == "1"

if os.name != 'nt' and not WEB_MODE:
    import termios

from app.bootstrap import create_app
from app.config import DATA_DIR
from app.loop import (
    apply_router_command,
    animate_life_boost_gain,
    animate_strength_gain,
    handle_battle_end,
    handle_offensive_action,
    map_input_to_command,
    maybe_begin_target_select,
    read_input,
    render_frame_state,
    run_target_select,
    run_opponent_turns,
    resolve_player_action,
)
from app.input import read_keypress, read_keypress_timeout
from app.models import Player
from app.player_sync import sync_player_elements
from app.state import GameState
from app.ui.constants import SCREEN_HEIGHT, SCREEN_WIDTH
from app.ui.rendering import animate_art_transition, animate_portal_departure, clear_screen, render_frame
from app.ui.screens import generate_frame

def warn_on_invalid_json(data_dir: str) -> None:
    if not os.path.isdir(data_dir):
        return
    for name in sorted(os.listdir(data_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(data_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                json.load(f)
        except (OSError, JSONDecodeError) as exc:
            print(f"WARNING: Invalid JSON in {path}: {exc}")


warn_on_invalid_json(DATA_DIR)
APP = create_app()
ITEMS = APP.items
SAVE_DATA = APP.save_data

# -----------------------------
# Main loop
# -----------------------------

def main():
    if os.name != 'nt' and not WEB_MODE:
        sys.stdout.write("\033[?1049h")
        sys.stdout.flush()
    if not WEB_MODE:
        cols, rows = shutil.get_terminal_size(fallback=(0, 0))
        if cols < SCREEN_WIDTH or rows < SCREEN_HEIGHT:
            print(f"WARNING: Terminal size is {cols}x{rows}. Recommended is 100x30.")
            print("Resize your terminal for best results.")
            input("Press Enter to continue anyway...")

    state = GameState(
        player=Player.from_dict({}),
        opponents=[],
        loot_bank={"xp": 0, "gold": 0},
        last_message="",
        leveling_mode=False,
        shop_mode=False,
        inventory_mode=False,
        inventory_items=[],
        hall_mode=False,
        hall_view="menu",
        inn_mode=False,
        stats_mode=False,
        spell_mode=False,
        followers_mode=False,
        follower_equip_mode=False,
        follower_equip_target=None,
        element_mode=False,
        alchemist_mode=False,
        alchemy_first=None,
        temple_mode=False,
        smithy_mode=False,
        portal_mode=False,
        quest_mode=False,
        quest_detail_mode=False,
        quit_confirm=False,
        title_mode=True,
        spell_cursor=0,
        battle_cursor=0,
        current_venue_id=None,
        title_menu_stack=[],
        spell_target_mode=False,
        spell_target_cursor=0,
        spell_target_command=None,
        team_target_index=None,
        last_team_target_player=None,
        quest_continent_index=0,
        quest_detail_id=None,
        quest_detail_page=0,
    )
    state.player.location = "Title"
    state.player.sync_items(ITEMS)
    sync_player_elements(APP, state.player)

    if os.name != 'nt' and not WEB_MODE:
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)

    while True:
        if state.title_mode:
            state.player.has_save = SAVE_DATA.exists()
        if state.inventory_mode:
            state.inventory_items = state.player.list_inventory_items(ITEMS)
        render_frame_state(APP, render_frame, state, generate_frame)
        if state.title_mode:
            ch = read_keypress_timeout(1.0)
            if ch is None:
                continue
        else:
            ch = read_input(APP, render_frame, state, generate_frame, read_keypress, read_keypress_timeout)
        action_cmd = None
        command_meta = None
        handled_by_router = False
        cmd, command_meta = map_input_to_command(APP, state, ch)

        if cmd == "QUIT":
            if state.title_mode or state.player.location == "Title":
                SAVE_DATA.save_player(state.player)
                clear_screen()
                print("Goodbye.")
                if os.name != 'nt' and not WEB_MODE:
                    sys.stdout.write("\033[?1049l")
                    sys.stdout.flush()
                return
            pre_frame = generate_frame(
                APP.screen_ctx,
                state.player,
                state.opponents,
                state.last_message,
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
                state.level_cursor,
                state.level_up_notes,
            )
            state.title_mode = True
            state.player.location = "Title"
            state.player.title_confirm = False
            state.player.title_name_select = False
            state.player.title_name_input = False
            state.player.title_start_confirm = False
            state.player.title_pending_name = None
            state.player.title_pending_fortune = None
            state.player.title_name_cursor = (0, 0)
            state.player.title_name_shift = True
            state.player.has_save = SAVE_DATA.exists()
            state.leveling_mode = False
            state.shop_mode = False
            state.shop_view = "menu"
            state.inventory_mode = False
            state.inventory_items = []
            state.hall_mode = False
            state.hall_view = "menu"
            state.inn_mode = False
            state.stats_mode = False
            state.spell_mode = False
            state.spell_target_mode = False
            state.spell_target_cursor = 0
            state.spell_target_command = None
            state.followers_mode = False
            state.follower_equip_mode = False
            state.follower_equip_target = None
            state.element_mode = False
            state.alchemist_mode = False
            state.alchemy_first = None
            state.temple_mode = False
            state.smithy_mode = False
            state.portal_mode = False
            state.quest_mode = False
            state.quest_detail_mode = False
            state.options_mode = False
            state.target_select = False
            state.target_index = None
            state.target_command = None
            state.opponents = []
            state.loot_bank = {"xp": 0, "gold": 0}
            state.battle_log = []
            state.last_message = ""
            state.action_cursor = 0
            state.menu_cursor = 0
            state.level_cursor = 0
            state.level_up_notes = []
            state.last_spell_targets = []
            state.team_target_index = None
            state.last_team_target_player = None
            state.follower_dismiss_pending = None
            state.followers_focus = "list"
            state.followers_action_cursor = 0
            state.title_menu_stack = []
            state.quest_continent_index = 0
            state.quest_detail_id = None
            state.quest_detail_page = 0
            post_frame = generate_frame(
                APP.screen_ctx,
                state.player,
                state.opponents,
                state.last_message,
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
                state.level_cursor,
                state.level_up_notes,
            )
            animate_art_transition(pre_frame, post_frame, state.player, pause_ticks=2)
            continue

        if cmd is None:
            continue

        if state.leveling_mode:
            state.last_message, leveling_done = state.player.handle_level_up_input(cmd)
            if leveling_done:
                state.leveling_mode = False
                state.level_up_notes = []
            continue

        if cmd == "B_KEY" and not (
            state.shop_mode
            or state.hall_mode
            or state.inn_mode
            or state.spell_mode
            or state.inventory_mode
            or state.portal_mode
        ):
            continue
        if cmd == "X_KEY":
            continue

        pre_snapshot = None
        if (
            cmd in ("ENTER_VENUE", "ENTER_SCENE")
            or cmd.startswith("TITLE_")
            or cmd.startswith("PORTAL:")
            or (cmd in ("B_KEY", "LEAVE") and (
                state.shop_mode
                or state.hall_mode
                or state.inn_mode
                or state.temple_mode
                or state.smithy_mode
                or state.alchemist_mode
                or state.portal_mode
            ))
        ):
            pre_snapshot = {
                "player": copy.deepcopy(state.player),
                "opponents": copy.deepcopy(state.opponents),
                "message": state.last_message,
                "leveling_mode": state.leveling_mode,
                "shop_mode": state.shop_mode,
                "shop_view": state.shop_view,
                "inventory_mode": state.inventory_mode,
                "inventory_items": list(state.inventory_items),
                "hall_mode": state.hall_mode,
                "hall_view": state.hall_view,
                "inn_mode": state.inn_mode,
                "stats_mode": state.stats_mode,
                "followers_mode": state.followers_mode,
                "spell_mode": state.spell_mode,
                "element_mode": state.element_mode,
                "alchemist_mode": state.alchemist_mode,
                "alchemy_first": state.alchemy_first,
                "alchemy_selecting": state.alchemy_selecting,
                "temple_mode": state.temple_mode,
                "smithy_mode": state.smithy_mode,
                "portal_mode": state.portal_mode,
                "quest_mode": state.quest_mode,
                "quest_detail_mode": state.quest_detail_mode,
                "options_mode": state.options_mode,
                "action_cursor": state.action_cursor,
                "menu_cursor": state.menu_cursor,
                "followers_focus": state.followers_focus,
                "followers_action_cursor": state.followers_action_cursor,
                "spell_cast_rank": state.spell_cast_rank,
                "spell_target_mode": state.spell_target_mode,
                "spell_target_cursor": state.spell_target_cursor,
                "spell_target_command": state.spell_target_command,
                "quest_continent_index": state.quest_continent_index,
                "quest_detail_id": state.quest_detail_id,
                "quest_detail_page": state.quest_detail_page,
                "level_cursor": state.level_cursor,
                "level_up_notes": list(state.level_up_notes),
                "title_menu_stack": list(state.title_menu_stack),
            }
            pre_in_venue = (
                state.shop_mode
                or state.hall_mode
                or state.inn_mode
                or state.temple_mode
                or state.smithy_mode
                or state.alchemist_mode
                or state.portal_mode
            )
            pre_location = state.player.location

        handled_by_router, action_cmd, cmd, should_continue, target_index = apply_router_command(
            APP,
            state,
            cmd,
            ch,
            command_meta,
            action_cmd,
        )
        if pre_snapshot is not None:
            post_in_venue = (
                state.shop_mode
                or state.hall_mode
                or state.inn_mode
                or state.temple_mode
                or state.smithy_mode
                or state.alchemist_mode
                or state.portal_mode
            )
            post_location = state.player.location
            if pre_in_venue != post_in_venue or pre_location != post_location:
                pre_frame = generate_frame(
                    APP.screen_ctx,
                    pre_snapshot["player"],
                    pre_snapshot["opponents"],
                    pre_snapshot["message"],
                    pre_snapshot["leveling_mode"],
                    pre_snapshot["shop_mode"],
                    pre_snapshot.get("shop_view", "menu"),
                    pre_snapshot["inventory_mode"],
                    pre_snapshot["inventory_items"],
                    pre_snapshot["hall_mode"],
                    pre_snapshot["hall_view"],
                    pre_snapshot["inn_mode"],
                    pre_snapshot.get("stats_mode", False),
                    pre_snapshot.get("followers_mode", False),
                    pre_snapshot["spell_mode"],
                    pre_snapshot.get("element_mode", False),
                    pre_snapshot.get("alchemist_mode", False),
                    pre_snapshot.get("alchemy_first", None),
                    pre_snapshot.get("alchemy_selecting", False),
                    pre_snapshot.get("temple_mode", False),
                    pre_snapshot.get("smithy_mode", False),
                    pre_snapshot.get("portal_mode", False),
                    pre_snapshot.get("quest_mode", False),
                    pre_snapshot.get("quest_detail_mode", False),
                    pre_snapshot.get("title_menu_stack", []),
                    pre_snapshot.get("options_mode", False),
                    pre_snapshot.get("action_cursor", 0),
                    pre_snapshot.get("menu_cursor", 0),
                    pre_snapshot.get("followers_focus", "list"),
                    pre_snapshot.get("followers_action_cursor", 0),
                    pre_snapshot.get("spell_cast_rank", 1),
                    pre_snapshot.get("spell_target_mode", False),
                    pre_snapshot.get("spell_target_cursor", 0),
                    pre_snapshot.get("spell_target_command", None),
                    pre_snapshot.get("quest_continent_index", 0),
                    pre_snapshot.get("quest_detail_id", None),
                    pre_snapshot.get("quest_detail_page", 0),
                    pre_snapshot.get("level_cursor", 0),
                    pre_snapshot.get("level_up_notes", []),
                )
                post_frame = generate_frame(
                    APP.screen_ctx,
                    state.player,
                    state.opponents,
                    state.last_message,
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
                )
                if cmd and cmd.startswith("PORTAL:"):
                    animate_portal_departure(pre_frame, post_frame, state.player, pause_ticks=1)
                else:
                    animate_art_transition(pre_frame, post_frame, state.player, pause_ticks=2)
        if should_continue:
            continue
        if target_index is not None:
            state.target_index = target_index

        target_cmd = cmd
        if action_cmd in APP.targeted_spell_commands or action_cmd in ("ATTACK", "SOCIALIZE"):
            target_cmd = action_cmd
        if maybe_begin_target_select(APP, state, target_cmd):
            confirmed = run_target_select(APP, render_frame, state, generate_frame, read_keypress_timeout)
            if not confirmed:
                continue
            cmd = confirmed
            action_cmd = confirmed

        action_cmd = resolve_player_action(
            APP,
            render_frame,
            state,
            cmd,
            command_meta,
            action_cmd,
            handled_by_router,
            generate_frame,
        )
        in_battle = state.player.location == "Forest" and any(opp.hp > 0 for opp in state.opponents)
        if (
            state.spell_mode
            and not in_battle
            and action_cmd in ("STRENGTH", "HEAL")
        ):
            state.spell_target_mode = True
            if not state.spell_target_command:
                state.spell_target_command = action_cmd
        if action_cmd in ("STRENGTH", "HEAL") and state.last_team_target_player:
            spell_entry = APP.spells.by_command_id(action_cmd)
            if spell_entry:
                _, spell = spell_entry
                rank = APP.spells.rank_for(spell, state.player.level)
                gain_per_cast = max(0, 10 * rank)
                max_stack = gain_per_cast * 5
                if action_cmd == "STRENGTH":
                    current = min(state.player.temp_atk_bonus, state.player.temp_def_bonus)
                    remaining = max(0, max_stack - current)
                    gain = min(gain_per_cast, remaining)
                    animate_strength_gain(APP, render_frame, state, generate_frame, gain)
                else:
                    current = state.player.temp_hp_bonus
                    remaining = max(0, max_stack - current)
                    gain = min(gain_per_cast, remaining)
                    animate_life_boost_gain(APP, render_frame, state, generate_frame, gain)
        if action_cmd in ("STRENGTH", "HEAL"):
            state.last_team_target_player = None
        handle_offensive_action(APP, state, action_cmd)
        if action_cmd:
            state.target_index = None
            state.target_command = None

        player_defeated = run_opponent_turns(APP, render_frame, state, generate_frame, action_cmd)

        if player_defeated:
            SAVE_DATA.save_player(state.player)
            continue

        handle_battle_end(APP, state, action_cmd)

        if action_cmd in APP.combat_actions:
            SAVE_DATA.save_player(state.player)


if __name__ == "__main__":
    try:
        main()
    finally:
        if os.name != 'nt' and not WEB_MODE:
            sys.stdout.write("\033[?1049l")
            sys.stdout.flush()
