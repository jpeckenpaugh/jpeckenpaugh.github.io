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
    apply_boost_confirm,
    apply_router_command,
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
from app.state import GameState
from app.ui.constants import SCREEN_HEIGHT, SCREEN_WIDTH
from app.ui.rendering import animate_art_transition, clear_screen, render_frame
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
        boost_prompt=None,
        shop_mode=False,
        inventory_mode=False,
        inventory_items=[],
        hall_mode=False,
        hall_view="menu",
        inn_mode=False,
        spell_mode=False,
        quit_confirm=False,
        title_mode=True,
    )
    state.player.location = "Title"

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
        handled_boost, action_cmd, should_continue = apply_boost_confirm(APP, state, ch, action_cmd)
        if should_continue:
            continue
        cmd = None
        if not handled_boost:
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
                state.inventory_mode,
                state.inventory_items,
                state.hall_mode,
                state.hall_view,
                state.inn_mode,
                state.spell_mode,
            )
            state.title_mode = True
            state.player.location = "Title"
            state.player.title_confirm = False
            state.leveling_mode = False
            state.boost_prompt = None
            state.shop_mode = False
            state.inventory_mode = False
            state.inventory_items = []
            state.hall_mode = False
            state.hall_view = "menu"
            state.inn_mode = False
            state.spell_mode = False
            state.target_select = False
            state.target_index = None
            state.target_command = None
            state.opponents = []
            state.loot_bank = {"xp": 0, "gold": 0}
            state.battle_log = []
            state.last_message = ""
            post_frame = generate_frame(
                APP.screen_ctx,
                state.player,
                state.opponents,
                state.last_message,
                state.leveling_mode,
                state.shop_mode,
                state.inventory_mode,
                state.inventory_items,
                state.hall_mode,
                state.hall_view,
                state.inn_mode,
                state.spell_mode,
            )
            animate_art_transition(pre_frame, post_frame, state.player, pause_ticks=2)
            continue

        if cmd is None and not handled_boost:
            continue

        if state.leveling_mode and not handled_boost:
            state.last_message, leveling_done = state.player.handle_level_up_input(cmd)
            if leveling_done:
                state.leveling_mode = False
            continue

        if cmd == "B_KEY" and not (state.shop_mode or state.hall_mode or state.inn_mode or state.spell_mode or state.inventory_mode):
            continue
        if cmd == "X_KEY":
            continue

        pre_snapshot = None
        if (
            cmd in ("ENTER_VENUE", "ENTER_SCENE")
            or cmd.startswith("TITLE_")
            or (cmd == "B_KEY" and (state.shop_mode or state.hall_mode or state.inn_mode))
        ):
            pre_snapshot = {
                "player": copy.deepcopy(state.player),
                "opponents": copy.deepcopy(state.opponents),
                "message": state.last_message,
                "leveling_mode": state.leveling_mode,
                "shop_mode": state.shop_mode,
                "inventory_mode": state.inventory_mode,
                "inventory_items": list(state.inventory_items),
                "hall_mode": state.hall_mode,
                "hall_view": state.hall_view,
                "inn_mode": state.inn_mode,
                "spell_mode": state.spell_mode,
            }
            pre_in_venue = state.shop_mode or state.hall_mode or state.inn_mode
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
            post_in_venue = state.shop_mode or state.hall_mode or state.inn_mode
            post_location = state.player.location
            if pre_in_venue != post_in_venue or pre_location != post_location:
                pre_frame = generate_frame(
                    APP.screen_ctx,
                    pre_snapshot["player"],
                    pre_snapshot["opponents"],
                    pre_snapshot["message"],
                    pre_snapshot["leveling_mode"],
                    pre_snapshot["shop_mode"],
                    pre_snapshot["inventory_mode"],
                    pre_snapshot["inventory_items"],
                    pre_snapshot["hall_mode"],
                    pre_snapshot["hall_view"],
                    pre_snapshot["inn_mode"],
                    pre_snapshot["spell_mode"],
                )
                post_frame = generate_frame(
                    APP.screen_ctx,
                    state.player,
                    state.opponents,
                    state.last_message,
                    state.leveling_mode,
                    state.shop_mode,
                    state.inventory_mode,
                    state.inventory_items,
                    state.hall_mode,
                    state.hall_view,
                    state.inn_mode,
                    state.spell_mode,
                )
                animate_art_transition(pre_frame, post_frame, state.player, pause_ticks=2)
        if should_continue:
            continue
        if target_index is not None:
            state.target_index = target_index

        target_cmd = cmd
        if action_cmd in APP.targeted_spell_commands or action_cmd == "ATTACK":
            target_cmd = action_cmd
        if maybe_begin_target_select(APP, state, target_cmd):
            confirmed = run_target_select(APP, render_frame, state, generate_frame, read_keypress_timeout)
            if not confirmed:
                continue
            cmd = confirmed
            action_cmd = confirmed

        action_cmd = resolve_player_action(
            APP,
            state,
            cmd,
            command_meta,
            action_cmd,
            handled_boost,
            handled_by_router,
        )
        if state.boost_prompt:
            continue
        if state.player.needs_level_up() and not any(opponent.hp > 0 for opponent in state.opponents):
            state.leveling_mode = True

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
