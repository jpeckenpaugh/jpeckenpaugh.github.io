import copy
import os
import time
from typing import Dict, List

import cottage_v04 as world
import ui_v08 as ui


TITLE_LANDSCAPE_POSITION = 5
ADDRESS_LANDSCAPE_POSITIONS = {
    "#1 Ave A": 50,
}

SIMPLE_SMASH_FRAMES = [
    [" * ", "***", " * "],
    ["\\|/", "-*-", "/|\\"],
    [" x ", "xXx", " x "],
    ["\\ /", " X ", "/ \\"],
    [" . ", ".*.", " . "],
]


def build_player_cards(players: dict, color_codes: Dict[str, str]) -> List[dict]:
    preferred_ids = ["player_01", "player_02"]
    ordered_ids: List[str] = []
    for pid in preferred_ids:
        if isinstance(players.get(pid), dict):
            ordered_ids.append(pid)
    for pid in sorted(players.keys()):
        if isinstance(players.get(pid), dict) and pid not in ordered_ids:
            ordered_ids.append(pid)
    if not ordered_ids:
        ordered_ids = ["player_01", "player_02"]
    if len(ordered_ids) == 1:
        ordered_ids.append(ordered_ids[0])
    ordered_ids = ordered_ids[:2]

    player_cards: List[dict] = []
    for pid in ordered_ids:
        entry = players.get(pid, {}) if isinstance(players, dict) else {}
        label = str(entry.get("label", pid) if isinstance(entry, dict) else pid)
        names = entry.get("names", []) if isinstance(entry, dict) else []
        if not isinstance(names, list):
            names = []
        clean_names = [str(n).strip()[:16] for n in names if str(n).strip()]
        if not clean_names:
            clean_names = [label.upper()[:16] or "WARRIOR"]
        sprite = world.build_player_sprite(players, pid, color_codes)
        player_cards.append({"id": pid, "label": label, "names": clean_names, "sprite": sprite})
    return player_cards


def build_demo_flow(player_cards: List[dict]) -> dict:
    selected_card = player_cards[0]
    return {
        "screen": "root_menu",
        "next_screen": None,
        "camera_position": TITLE_LANDSCAPE_POSITION,
        "camera_target": TITLE_LANDSCAPE_POSITION,
        "camera_transition_screen": None,
        "lineup_transition": None,
        "menu_cursor": 0,
        "player_cards": player_cards,
        "player_index": 0,
        "avatar_label": selected_card["label"],
        "name_choices": list(selected_card["names"]),
        "name_choice_index": 0,
        "name_focus": 0,
        "typed_name": "",
        "selected_name": selected_card["names"][0],
        "fortune_cursor": 1,
        "fortune_choice": "Well-Off (100 GP)",
        "message_text": "",
        "battle_stage": 1,
        "battle_primary_hp": [10],
        "battle_primary_hp_max": [10],
        "battle_primary_kind": ["baby_crow"],
        "battle_secondary_hp": [20, 10],
        "battle_secondary_hp_max": [20, 10],
        "battle_secondary_mp": [0, 6],
        "battle_secondary_mp_max": [0, 6],
        "battle_staff_charges": 3,
        "battle_summon_used": False,
        "battle_round": 1,
        "battle_hawk_birdcall_next_round": 1,
        "battle_hawk_birdcall_gap": 2,
        "battle_hawk_birdcall_uses": 0,
        "battle_hawk_summoned_slots": [False],
        "unlock_summon_hawking": False,
        "hawking_feather_owner": "",
        "hawking_assign_cursor": 0,
        "player_items": [],
        "battle_player_cmd_idx": 0,
        "battle_mushy_cmd_idx": 0,
        "battle_sharoom_cmd_idx": 0,
        "battle_roomy_cmd_idx": 0,
        "battle_player_action": "Attack",
        "battle_mushy_action": "Attack",
        "battle_sharoom_action": "Attack",
        "battle_roomy_action": "Attack",
        "battle_secondary_boost_atk": [0, 0],
        "battle_secondary_boost_def": [0, 0],
        "battle_mushy_spell_target": 0,
        "battle_mushy_spell_target_mode": "single",
        "battle_sharoom_spell_target": 0,
        "battle_sharoom_spell_target_mode": "single",
        "battle_player_target": 0,
        "battle_mushy_target": 0,
        "battle_sharoom_target": 0,
        "battle_roomy_target": 0,
        "battle_target_cursor": 0,
        "battle_queue": [],
        "battle_queue_index": 0,
        "battle_action_t": 0.0,
        "battle_melt_index": None,
        "battle_melt_t": 0.0,
        "battle_log_lines": [],
        "battle_log_committed": [],
        "battle_log_pending": [],
        "battle_log_active": None,
        "battle_log_active_chars": 0,
        "battle_magic_spark_level": 1,
    }


def actor_sprites_from_keys(sprite_map: Dict[str, List[List[str]]], keys: List[str]) -> List[List[List[str]]]:
    sprites: List[List[List[str]]] = []
    for key in keys:
        rows = sprite_map.get(key, [])
        if isinstance(rows, list) and rows:
            sprites.append(rows)
    return sprites


def build_stage1_battle_log(flow: dict) -> List[str]:
    battle_flow = copy.deepcopy(flow)
    original_monotonic_ns = ui.time.monotonic_ns
    ui.time.monotonic_ns = lambda: 246813579
    try:
        ui._battle_log_start(battle_flow, 1)
        actions = ui._build_battle_round_actions(battle_flow)
    finally:
        ui.time.monotonic_ns = original_monotonic_ns
    lines = [str(line) for line in battle_flow.get("battle_log_pending", []) if str(line)]
    player_name = str(battle_flow.get("selected_name", battle_flow.get("avatar_label", "Player")))
    for action in actions[:3]:
        lines.extend(ui._battle_action_log_lines(action, 1, player_name))
    return lines[:6]


def build_battle_log_spec(lines: List[str]) -> ui.UIBoxSpec:
    return ui.UIBoxSpec(
        role="battle_log",
        border_style="heavy",
        title="Battle Log",
        body_text="\n".join(lines[:5]),
        center_x=50,
        center_y=17,
        max_body_width=58,
        body_align="left",
        wrap_mode="normal",
        actions=["[ A / Continue ]", "[ S / Back ]"],
        preserve_body_whitespace=True,
    )


def current_landscape_position(flow: dict) -> int:
    return int(flow.get("camera_position", TITLE_LANDSCAPE_POSITION))


def current_address_label(flow: dict) -> str:
    position = current_landscape_position(flow)
    return "#1 Ave A" if position >= ADDRESS_LANDSCAPE_POSITIONS["#1 Ave A"] else "Main Street"


def start_camera_transition(flow: dict, target: int, next_screen: str) -> None:
    flow["camera_target"] = int(target)
    flow["camera_transition_screen"] = str(next_screen)


def _interpolate_positions(start: Dict[str, dict], end: Dict[str, dict], t: float) -> List[dict]:
    te = max(0.0, min(1.0, float(t)))
    smooth = te * te * (3.0 - (2.0 * te))
    out: List[dict] = []
    for actor_id, start_actor in start.items():
        end_actor = end.get(actor_id)
        if not isinstance(start_actor, dict) or not isinstance(end_actor, dict):
            continue
        sx = int(start_actor.get("x", 0))
        sy = int(start_actor.get("y", 0))
        ex = int(end_actor.get("x", sx))
        ey = int(end_actor.get("y", sy))
        out.append({
            "id": actor_id,
            "x": int(round(sx + ((ex - sx) * smooth))),
            "y": int(round(sy + ((ey - sy) * smooth))),
            "rows": start_actor.get("rows", []),
        })
    return out


def _compute_story_formation_positions(zones: Dict[str, world.LayoutZone], player_sprite: List[List[str]], mushy_sprite: List[List[str]], crow_sprite: List[List[str]], formation: str) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    ground_zone = zones.get("ground_bg")
    if not isinstance(ground_zone, world.LayoutZone):
        return out
    primary_zone = world.build_primary_zone(world._treeline_lowest_row(ground_zone.y, world.TREELINE_ROWS) + 1)
    secondary_zone = world.build_secondary_zone()
    if formation == "pre":
        pri = world.layout_actor_strip(primary_zone, [crow_sprite, mushy_sprite], spacing=1, stagger_rows=1)
        sec = world.layout_actor_strip(secondary_zone, [player_sprite], spacing=1, stagger_rows=1, reverse_stagger=True)
        if sec:
            out["player"] = {"x": int(sec[0]["x"]), "y": int(sec[0]["y"]), "rows": player_sprite}
        if len(pri) >= 1:
            out["crow1"] = {"x": int(pri[0]["x"]), "y": int(pri[0]["y"]), "rows": crow_sprite}
        if len(pri) >= 2:
            out["mushy"] = {"x": int(pri[1]["x"]), "y": int(pri[1]["y"]), "rows": mushy_sprite}
    else:
        pri = world.layout_actor_strip(primary_zone, [crow_sprite], spacing=1, stagger_rows=1)
        sec = world.layout_actor_strip(secondary_zone, [player_sprite, mushy_sprite], spacing=1, stagger_rows=1, reverse_stagger=True)
        if sec:
            out["player"] = {"x": int(sec[0]["x"]), "y": int(sec[0]["y"]), "rows": player_sprite}
        if len(sec) >= 2:
            out["mushy"] = {"x": int(sec[1]["x"]), "y": int(sec[1]["y"]), "rows": mushy_sprite}
        if pri:
            out["crow1"] = {"x": int(pri[0]["x"]), "y": int(pri[0]["y"]), "rows": crow_sprite}
    return out


def show_title_logo(flow: dict) -> bool:
    screen = str(flow.get("screen", "root_menu"))
    return screen in ("root_menu", "avatar_select", "name_select", "fortune_select", "start_confirm", "info")


def current_primary_keys(flow: dict) -> List[str]:
    if isinstance(flow.get("lineup_transition"), dict):
        return []
    screen = str(flow.get("screen", "root_menu"))
    if screen in ("story_4", "story_5", "story_6"):
        return ["baby_crow", "mushy"]
    if screen in ("story_battle_cmd_player", "story_battle_cmd_mushy", "story_battle_resolve", "battle_log"):
        return ["baby_crow"]
    return []


def current_secondary_keys(flow: dict) -> List[str]:
    if isinstance(flow.get("lineup_transition"), dict):
        return []
    screen = str(flow.get("screen", "root_menu"))
    if screen in ("story_4", "story_5", "story_6"):
        return ["player"]
    if screen in ("story_battle_cmd_player", "story_battle_cmd_mushy", "story_battle_resolve", "battle_log", "story_battle_victory"):
        return ["player", "mushy"]
    return []


def _sync_selected_player(flow: dict) -> None:
    player_cards = flow["player_cards"]
    idx = int(flow.get("player_index", 0)) % len(player_cards)
    card = player_cards[idx]
    flow["avatar_label"] = card["label"]
    flow["name_choices"] = list(card["names"])
    flow["name_choice_index"] = 0
    flow["selected_name"] = card["names"][0]


def _battle_options(flow: dict, actor: str) -> List[str]:
    return ui._actor_action_options(actor, bool(flow.get("unlock_summon_hawking", False)), ui._hawking_owner(flow))


def handle_input(flow: dict, key: str | None) -> str | None:
    if key is None:
        return None
    screen = str(flow.get("screen", "root_menu"))
    confirm = key in ("a", "\r", "\n")
    back = key == "s"

    if screen == "root_menu":
        cursor = int(flow.get("menu_cursor", 0))
        if key == "up":
            flow["menu_cursor"] = (cursor - 1) % 3
        elif key == "down":
            flow["menu_cursor"] = (cursor + 1) % 3
        elif confirm:
            if cursor == 0:
                return "avatar_select"
            if cursor == 1:
                flow["message_text"] = "Saved Game menu selected. (Demo placeholder)"
                return "info"
            flow["message_text"] = "Asset Explorer selected. (Demo placeholder)"
            return "info"
        return None

    if screen == "info":
        if confirm or back:
            return "root_menu"
        return None

    if screen == "avatar_select":
        idx = int(flow.get("player_index", 0))
        if key in ("left", "up"):
            flow["player_index"] = 1 if idx == 0 else 0
            _sync_selected_player(flow)
        elif key in ("right", "down"):
            flow["player_index"] = 1 if idx == 0 else 0
            _sync_selected_player(flow)
        elif confirm:
            return "name_select"
        elif back:
            return "root_menu"
        return None

    if screen == "name_select":
        focus = int(flow.get("name_focus", 0))
        if key in ("up", "down"):
            flow["name_focus"] = 1 - focus
        elif focus == 0 and key == "left":
            count = max(1, len(flow["name_choices"]))
            flow["name_choice_index"] = (int(flow.get("name_choice_index", 0)) - 1) % count
            flow["selected_name"] = flow["name_choices"][flow["name_choice_index"]]
        elif focus == 0 and key == "right":
            count = max(1, len(flow["name_choices"]))
            flow["name_choice_index"] = (int(flow.get("name_choice_index", 0)) + 1) % count
            flow["selected_name"] = flow["name_choices"][flow["name_choice_index"]]
        elif confirm:
            if focus == 0:
                return "fortune_select"
            flow["message_text"] = "Custom name entry is not wired into this world prototype yet."
            return "info"
        elif back:
            return "avatar_select"
        return None

    if screen == "fortune_select":
        cursor = int(flow.get("fortune_cursor", 1))
        if key == "up":
            flow["fortune_cursor"] = (cursor - 1) % 3
        elif key == "down":
            flow["fortune_cursor"] = (cursor + 1) % 3
        elif confirm:
            options = ["Poor (10 GP)", "Well-Off (100 GP)", "Royalty (1000 GP)"]
            flow["fortune_choice"] = options[int(flow.get("fortune_cursor", 1)) % len(options)]
            return "start_confirm"
        elif back:
            return "name_select"
        return None

    if screen == "start_confirm":
        if confirm:
            return "story_1"
        if back:
            return "fortune_select"
        return None

    if screen == "story_1":
        if confirm:
            start_camera_transition(flow, ADDRESS_LANDSCAPE_POSITIONS["#1 Ave A"], "story_4")
        elif back:
            return "start_confirm"
        return None

    if screen == "story_4":
        if confirm:
            return "story_5"
        if back:
            return "story_1"
        return None

    if screen == "story_5":
        if confirm:
            return "story_6"
        if back:
            return "story_4"
        return None

    if screen == "story_6":
        if confirm:
            flow["battle_player_action"] = "Magic Spark"
            flow["battle_mushy_action"] = "Attack"
            flow["screen"] = "story_lineup_shift"
            return "story_lineup_shift"
        if back:
            return "story_5"
        return None

    if screen == "story_battle_cmd_player":
        pri_hp = [int(v) for v in flow.get("battle_primary_hp", [10])]
        options = _battle_options(flow, "player")
        enabled = ui._action_enabled_flags(flow, "player", options)
        cursor = int(flow.get("battle_player_cmd_idx", 0)) % max(1, len(options))
        if enabled and not enabled[cursor] and any(enabled):
            cursor = next((i for i, v in enumerate(enabled) if v), cursor)
            flow["battle_player_cmd_idx"] = cursor
        target_cursor = int(flow.get("battle_target_cursor", 0))
        if key == "up":
            flow["battle_player_cmd_idx"] = ui._next_enabled_option_index(enabled, cursor, -1)
        elif key == "down":
            flow["battle_player_cmd_idx"] = ui._next_enabled_option_index(enabled, cursor, 1)
        elif key == "left" and enabled[cursor] and options[cursor] in ("Attack", "Summon Hawking"):
            flow["battle_target_cursor"] = ui._next_alive_index(pri_hp, target_cursor, -1)
        elif key == "right" and enabled[cursor] and options[cursor] in ("Attack", "Summon Hawking"):
            flow["battle_target_cursor"] = ui._next_alive_index(pri_hp, target_cursor, 1)
        elif key == "left" and enabled[cursor] and options[cursor] == "Magic Spark" and int(flow.get("battle_magic_spark_level", 1)) < 2:
            flow["battle_target_cursor"] = ui._next_alive_index(pri_hp, target_cursor, -1)
        elif key == "right" and enabled[cursor] and options[cursor] == "Magic Spark" and int(flow.get("battle_magic_spark_level", 1)) < 2:
            flow["battle_target_cursor"] = ui._next_alive_index(pri_hp, target_cursor, 1)
        elif confirm:
            if not enabled[cursor]:
                return None
            pick = options[cursor]
            flow["battle_player_action"] = pick
            if pick in ("Attack", "Magic Spark", "Summon Hawking"):
                flow["battle_player_target"] = int(flow.get("battle_target_cursor", 0))
            flow["battle_target_cursor"] = ui._first_alive(pri_hp, int(flow.get("battle_player_target", 0)))
            return "story_battle_cmd_mushy"
        elif back:
            return "story_6"
        return None

    if screen == "story_battle_cmd_mushy":
        pri_hp = [int(v) for v in flow.get("battle_primary_hp", [10])]
        options = _battle_options(flow, "mushy")
        enabled = ui._action_enabled_flags(flow, "mushy", options)
        cursor = int(flow.get("battle_mushy_cmd_idx", 0)) % max(1, len(options))
        if enabled and not enabled[cursor] and any(enabled):
            cursor = next((i for i, v in enumerate(enabled) if v), cursor)
            flow["battle_mushy_cmd_idx"] = cursor
        target_cursor = int(flow.get("battle_target_cursor", 0))
        if key == "up":
            flow["battle_mushy_cmd_idx"] = ui._next_enabled_option_index(enabled, cursor, -1)
        elif key == "down":
            flow["battle_mushy_cmd_idx"] = ui._next_enabled_option_index(enabled, cursor, 1)
        elif key == "left" and enabled[cursor] and options[cursor] in ("Attack", "Summon Hawking"):
            flow["battle_target_cursor"] = ui._next_alive_index(pri_hp, target_cursor, -1)
        elif key == "right" and enabled[cursor] and options[cursor] in ("Attack", "Summon Hawking"):
            flow["battle_target_cursor"] = ui._next_alive_index(pri_hp, target_cursor, 1)
        elif confirm:
            if not enabled[cursor]:
                return None
            pick = options[cursor]
            flow["battle_mushy_action"] = pick
            if pick in ("Attack", "Summon Hawking"):
                flow["battle_mushy_target"] = int(flow.get("battle_target_cursor", 0))
            ui._battle_log_start(flow, int(flow.get("battle_stage", 1)))
            flow["battle_queue"] = ui._build_battle_round_actions(flow)
            flow["battle_queue_index"] = 0
            flow["battle_action_t"] = 0.0
            flow["battle_melt_index"] = None
            flow["battle_melt_t"] = 0.0
            return "story_battle_resolve"
        elif back:
            return "story_battle_cmd_player"
        return None

    if screen == "battle_log":
        if confirm:
            return "story_battle_victory"
        if back:
            return "story_battle_cmd_mushy"
        return None

    if screen == "story_battle_victory":
        if confirm:
            flow["message_text"] = "End of world_v01 prototype."
            return "info"
        if back:
            return "battle_log"
        return None

    return None


def render(
    clouds: List[dict],
    ground_rows: List[str],
    zones: Dict[str, world.LayoutZone],
    sky_bottom_anchor: int,
    foreground_split_label: str,
    landscape_position: int,
    world_treeline_sprites: List[dict],
    border_treeline_sprites: List[dict],
    crossroad_house_sprites: List[dict],
    primary_actor_sprites: List[List[List[str]]],
    secondary_actor_sprites: List[List[List[str]]],
    ui_active_box: ui.UIBoxSpec | None,
    beat_label: str,
    address_label: str,
    blink_on: bool,
    title_logo: dict | None = None,
    show_title: bool = False,
    ui_box_progress: float = 1.0,
    ui_avatar_overlay: dict | None = None,
    ui_actor_status: dict | None = None,
    wipe_progress: float = 1.0,
    story_transition_actors: List[dict] | None = None,
    story_target_primary_index: int | None = None,
    story_target_primary_blink: bool = False,
    story_spell: dict | None = None,
    story_smash: dict | None = None,
    story_primary_hp: List[int] | None = None,
    story_primary_hp_totals: List[int] | None = None,
    story_damage_hud: dict | None = None,
    battle_log_lines: List[str] | None = None,
) -> str:
    canvas = [[" " for _ in range(world.SCREEN_W)] for _ in range(world.SCREEN_H)]
    sky_zone = zones["sky_bg"]
    ground_zone = zones["ground_bg"]
    secondary_zone = world.build_secondary_zone()
    lowest_tree_row = world._treeline_lowest_row(ground_zone.y, world.TREELINE_ROWS)
    primary_zone = world.build_primary_zone(lowest_tree_row + 1)
    sky_layer_bottom = int(sky_bottom_anchor)
    sky_layer_top = sky_layer_bottom - (world.SKY_LAYER_HEIGHT - 1)
    hidden_ground_rows = world.landscape_hidden_ground_rows(landscape_position)
    ground_slice_start = world.landscape_ground_window_start(landscape_position)

    def draw_world_scene_sprites(draw_backside: bool) -> None:
        if world_treeline_sprites:
            for sprite in world_treeline_sprites:
                rows = sprite.get("rows", [])
                if not isinstance(rows, list):
                    continue
                x0 = int(sprite.get("x", 0))
                height = int(sprite.get("height", len(rows)))
                offset = min(world.TREELINE_ROWS - 1, max(0, int(sprite.get("anchor_offset", 0))))
                sprite_is_backside, y_base = world.horizon_depth_state(offset, hidden_ground_rows, ground_zone.y)
                if sprite_is_backside != draw_backside:
                    continue
                y_base = max(ground_zone.y, y_base)
                y0 = y_base - max(0, height - 1)
                for dy, row in enumerate(rows):
                    y = y0 + dy
                    if y < 0 or y >= world.SCREEN_H or not isinstance(row, list):
                        continue
                    for dx, cell in enumerate(row):
                        x = x0 + dx
                        if 0 <= x < world.SCREEN_W and cell != " ":
                            canvas[y][x] = cell
        if border_treeline_sprites:
            for sprite in border_treeline_sprites:
                rows = sprite.get("rows", [])
                if not isinstance(rows, list):
                    continue
                side = str(sprite.get("side", "left"))
                width = int(sprite.get("width", len(rows[0]) if rows else 0))
                height = int(sprite.get("height", len(rows)))
                horizon_depth = max(0, int(sprite.get("horizon_depth", 0)))
                if world.crossroad_row_phase(horizon_depth) is not None:
                    continue
                sprite_is_backside, y_base = world.horizon_depth_state(horizon_depth, hidden_ground_rows, ground_zone.y)
                if sprite_is_backside != draw_backside:
                    continue
                y_base = max(ground_zone.y, y_base)
                distance_from_horizon = max(0, y_base - ground_zone.y)
                road = world.road_geometry_for_horizon_distance(distance_from_horizon)
                column_band = max(0, min(2, int(sprite.get("side_column", 0))))
                column_jitter = max(-1, min(1, int(sprite.get("side_jitter", 0))))
                if side == "left":
                    x0 = (column_band * 3) + column_jitter - int(road.get("left_push", 0))
                else:
                    x0 = (world.SCREEN_W - max(1, width) - (column_band * 3) + column_jitter) + int(road.get("right_push", 0))
                y0 = y_base - max(0, height - 1)
                for dy, row in enumerate(rows):
                    y = y0 + dy
                    if y < 0 or y >= world.SCREEN_H or not isinstance(row, list):
                        continue
                    for dx, cell in enumerate(row):
                        x = x0 + dx
                        if 0 <= x < world.SCREEN_W and cell != " ":
                            canvas[y][x] = cell
        if crossroad_house_sprites:
            for sprite in crossroad_house_sprites:
                rows = sprite.get("rows", [])
                if not isinstance(rows, list):
                    continue
                side = str(sprite.get("side", "left"))
                width = int(sprite.get("width", len(rows[0]) if rows else 0))
                height = int(sprite.get("height", len(rows)))
                horizon_depth = max(0, int(sprite.get("horizon_depth", 0)))
                sprite_is_backside, y_base = world.horizon_depth_state(horizon_depth, hidden_ground_rows, ground_zone.y)
                if sprite_is_backside != draw_backside:
                    continue
                y_base = max(ground_zone.y, y_base)
                distance_from_horizon = max(0, y_base - ground_zone.y)
                road = world.road_geometry_for_horizon_distance(distance_from_horizon)
                if side == "left":
                    x0 = int(road.get("start", 0)) - width - 8
                else:
                    x0 = int(road.get("end", world.SCREEN_W - 1)) + 8
                y0 = y_base - max(0, height - 1)
                for dy, row in enumerate(rows):
                    y = y0 + dy
                    if y < 0 or y >= world.SCREEN_H or not isinstance(row, list):
                        continue
                    for dx, cell in enumerate(row):
                        x = x0 + dx
                        if 0 <= x < world.SCREEN_W and cell != " ":
                            canvas[y][x] = cell
                label = str(sprite.get("label", "")).strip()
                if label:
                    plaque_y = y0 + max(0, min(max(0, height - 1), 5) - 3)
                    plaque_x = x0 + max(0, (width - len(label)) // 2)
                    plaque_color = "\x1b[38;2;245;245;245m"
                    for idx, ch in enumerate(label):
                        x = plaque_x + idx
                        if 0 <= x < world.SCREEN_W and 0 <= plaque_y < world.SCREEN_H:
                            canvas[plaque_y][x] = f"{plaque_color}{ch}{world.ANSI_RESET}"

    for cloud in clouds:
        template = cloud["template"]
        x0 = int(cloud["x"])
        y0 = int(cloud["y"])
        for dy, row in enumerate(template["rows"]):
            layer_y = y0 + dy
            y = sky_layer_top + layer_y
            if y < sky_zone.y or y > sky_zone.y1:
                continue
            for dx, cell in enumerate(row):
                x = x0 + dx
                if 0 <= x < world.SCREEN_W and cell != " ":
                    canvas[y][x] = cell

    draw_world_scene_sprites(draw_backside=True)
    for i in range(ground_zone.height):
        y = ground_zone.y + i
        src_index = ground_slice_start + i
        src = ground_rows[src_index] if 0 <= src_index < len(ground_rows) else ""
        cells = world.ansi_line_to_cells(src, world.SCREEN_W)
        road_width = world.road_width_for_horizon_distance(i)
        crossroad_phase = world.crossroad_row_phase(src_index)
        row_cells = world.overlay_crossroad_row(cells, src_index, 12051701 + src_index)
        row_cells = world.build_road_pushed_row(row_cells, road_width, 9051701 + src_index, crossroad_phase=crossroad_phase)
        for x, cell in enumerate(row_cells):
            if cell != " ":
                canvas[y][x] = cell
    draw_world_scene_sprites(draw_backside=False)

    def _draw_actor_rows(x0: int, y0: int, rows: List[List[str]]) -> None:
        if not isinstance(rows, list):
            return
        for dy, row in enumerate(rows):
            y = y0 + dy
            if y < 0 or y >= world.SCREEN_H:
                continue
            for dx, cell in enumerate(row):
                x = x0 + dx
                if 0 <= x < world.SCREEN_W and cell != " ":
                    canvas[y][x] = cell

    primary_placements: List[dict] = []
    secondary_placements: List[dict] = []
    hidden_secondary_indices: set[int] = set()
    if isinstance(story_smash, dict):
        p = max(0.0, min(1.0, float(story_smash.get("progress", 0.0))))
        if p < 0.5:
            step = int((p / 0.5) * 4.0)
            if (step % 2) != 0 and str(story_smash.get("source_side", "secondary")).strip().lower() == "secondary":
                hidden_secondary_indices.add(int(story_smash.get("source_index", 0)))

    if isinstance(story_transition_actors, list) and story_transition_actors:
        for actor in story_transition_actors:
            rows = actor.get("rows", [])
            if not isinstance(rows, list):
                continue
            _draw_actor_rows(int(actor.get("x", 0)), int(actor.get("y", 0)), rows)
    else:
        if secondary_actor_sprites:
            secondary_placements = world.layout_actor_strip(secondary_zone, secondary_actor_sprites, spacing=1, stagger_rows=1, reverse_stagger=True)
            for idx, actor in enumerate(secondary_placements):
                if idx in hidden_secondary_indices:
                    continue
                _draw_actor_rows(int(actor.get("x", 0)), int(actor.get("y", 0)), actor.get("rows", []))
        if primary_actor_sprites:
            primary_placements = world.layout_actor_strip(primary_zone, primary_actor_sprites, spacing=1, stagger_rows=1)
            for idx, actor in enumerate(primary_placements):
                if story_target_primary_index is not None and idx == int(story_target_primary_index) and not story_target_primary_blink:
                    continue
                _draw_actor_rows(int(actor.get("x", 0)), int(actor.get("y", 0)), actor.get("rows", []))

    if isinstance(story_spell, dict) and primary_placements and secondary_placements:
        source_side = str(story_spell.get("source_side", "secondary"))
        target_side = str(story_spell.get("target_side", "primary"))
        source_index = int(story_spell.get("source_index", 0))
        target_index = int(story_spell.get("target_index", 0))
        progress = float(story_spell.get("progress", 0.0))

        def _center_of(actor: dict) -> tuple[int, int]:
            rows = actor.get("rows", [])
            w = max((len(row) for row in rows), default=0) if isinstance(rows, list) else 0
            h = len(rows) if isinstance(rows, list) else 0
            return (int(actor.get("x", 0)) + (w // 2), int(actor.get("y", 0)) + (h // 2))

        src_list = secondary_placements if source_side == "secondary" else primary_placements
        dst_list = secondary_placements if target_side == "secondary" else primary_placements
        if 0 <= source_index < len(src_list) and 0 <= target_index < len(dst_list):
            ui._draw_spell_throw(canvas, _center_of(src_list[source_index]), _center_of(dst_list[target_index]), progress)

    if isinstance(story_smash, dict) and primary_placements:
        target_index = int(story_smash.get("target_index", 0))
        progress = max(0.0, min(1.0, float(story_smash.get("progress", 0.0))))
        if 0 <= target_index < len(primary_placements) and progress >= 0.5:
            actor = primary_placements[target_index]
            rows = actor.get("rows", [])
            w = max((len(row) for row in rows), default=0) if isinstance(rows, list) else 0
            h = len(rows) if isinstance(rows, list) else 0
            center = (int(actor.get("x", 0)) + (w // 2), int(actor.get("y", 0)) + (h // 2))
            frame_idx = min(len(SIMPLE_SMASH_FRAMES) - 1, int(((progress - 0.5) / 0.5) * len(SIMPLE_SMASH_FRAMES)))
            ui._draw_smash_frame(canvas, SIMPLE_SMASH_FRAMES[max(0, frame_idx)], center)

    if isinstance(story_damage_hud, dict):
        target_huds = story_damage_hud.get("target_huds", [])
        if isinstance(target_huds, list) and target_huds:
            for hud in target_huds:
                if not isinstance(hud, dict):
                    continue
                t_idx = int(hud.get("target_index", -1))
                if 0 <= t_idx < len(primary_placements):
                    ui._draw_damage_hud_step(
                        canvas,
                        primary_placements[t_idx],
                        progress=float(hud.get("progress", story_damage_hud.get("progress", 0.0))),
                        pre_hp=max(0, int(hud.get("pre_hp", 0))),
                        post_hp=max(0, int(hud.get("post_hp", 0))),
                        total=max(1, int(hud.get("total", 10))),
                        damage=max(0, int(hud.get("damage", 0))),
                    )
        else:
            t_idx = int(story_damage_hud.get("target_index", -1))
            if 0 <= t_idx < len(primary_placements):
                ui._draw_damage_hud_step(
                    canvas,
                    primary_placements[t_idx],
                    progress=float(story_damage_hud.get("progress", 0.0)),
                    pre_hp=max(0, int(story_damage_hud.get("pre_hp", 0))),
                    post_hp=max(0, int(story_damage_hud.get("post_hp", 0))),
                    total=max(1, int(story_damage_hud.get("total", 10))),
                    damage=max(0, int(story_damage_hud.get("damage", 0))),
                )
    elif isinstance(story_primary_hp, list):
        hp_totals = story_primary_hp_totals if isinstance(story_primary_hp_totals, list) else []
        for idx, actor in enumerate(primary_placements):
            if idx >= len(story_primary_hp):
                continue
            rows = actor.get("rows", [])
            w = max((len(row) for row in rows), default=0) if isinstance(rows, list) else 0
            center_x = int(actor.get("x", 0)) + (w // 2)
            total = max(1, int(hp_totals[idx])) if idx < len(hp_totals) else max(1, int(story_primary_hp[idx]))
            ui._draw_health_bar_custom(canvas, center_x, int(actor.get("y", 0)) - 4, int(story_primary_hp[idx]), total=total, row_label="HP")

    if isinstance(ui_active_box, ui.UIBoxSpec):
        ui_active_box = ui._position_screen_box_for_actors(beat_label, ui_active_box, primary_placements, secondary_placements)

    if show_title and isinstance(title_logo, dict):
        ui._overlay_title_logo(canvas, title_logo)
    if isinstance(battle_log_lines, list):
        ui._draw_battle_log_panel(canvas, battle_log_lines, width=40, height=10)
    if ui_active_box is not None:
        progress = max(0.0, min(1.0, float(ui_box_progress)))
        if progress < 1.0:
            ui.draw_ui_box_animated(canvas, ui_active_box, progress, blink_on=blink_on)
        else:
            ui.draw_ui_box(canvas, ui_active_box, blink_on=blink_on)
        if isinstance(ui_actor_status, dict):
            ui._draw_actor_cmd_status_overlay(
                canvas,
                ui_active_box,
                hp=max(0, int(ui_actor_status.get("hp", 0))),
                hp_total=max(1, int(ui_actor_status.get("hp_total", 1))),
                mp=max(0, int(ui_actor_status.get("mp", 0))),
                mp_total=max(1, int(ui_actor_status.get("mp_total", 1))),
                progress=progress,
            )
        if isinstance(ui_avatar_overlay, dict) and progress >= 1.0:
            left_rows = ui_avatar_overlay.get("left_rows", [])
            right_rows = ui_avatar_overlay.get("right_rows", [])
            if isinstance(left_rows, list) and isinstance(right_rows, list):
                ui._draw_avatar_overlay(
                    canvas,
                    ui_active_box,
                    left_rows,
                    right_rows,
                    str(ui_avatar_overlay.get("left_label", "Left")),
                    str(ui_avatar_overlay.get("right_label", "Right")),
                    int(ui_avatar_overlay.get("selected", 0)),
                    blink_selected_on=blink_on,
                )

    footer = f"[background][{foreground_split_label}][address:{address_label}][beat:{beat_label}]"
    if len(footer) <= world.SCREEN_W:
        x0 = (world.SCREEN_W - len(footer)) // 2
        for idx, ch in enumerate(footer):
            canvas[world.SCREEN_H - 1][x0 + idx] = ch

    # Vertical wipe-in from bottom, matching ui_v08.py startup behavior.
    progress = max(0.0, min(1.0, float(wipe_progress)))
    if progress < 1.0:
        visible_rows = int(round(world.SCREEN_H * progress))
        top_hidden_rows = max(0, world.SCREEN_H - visible_rows)
        for y in range(top_hidden_rows):
            for x in range(world.SCREEN_W):
                canvas[y][x] = " "
    return "\n".join("".join(row) for row in canvas)


def main() -> None:
    base = os.getcwd()
    objects = world.load_json(os.path.join(base, "legacy", "data", "objects.json"))
    colors = world.load_json(os.path.join(base, "legacy", "data", "colors.json"))
    opponents = world.load_json(os.path.join(base, "legacy", "data", "opponents.json"))
    players = world.load_json(os.path.join(base, "legacy", "data", "players.json"))
    if not isinstance(objects, dict) or not isinstance(colors, dict):
        raise RuntimeError("Missing world data JSON")
    if not isinstance(opponents, dict) or not isinstance(players, dict):
        raise RuntimeError("Missing actor data JSON")

    color_codes = world._build_color_codes(colors)
    player_cards = build_player_cards(players, color_codes)
    flow = build_demo_flow(player_cards)
    title_logo = ui._logo_cells_from_objects(objects)
    sprite_map = {
        "player": player_cards[0]["sprite"],
        "mushy": world.build_opponent_sprite(opponents, "mushroom_baby", color_codes),
        "baby_crow": world.build_opponent_sprite(opponents, "baby_crow", color_codes),
    }
    clouds = world.spawn_clouds_full_canvas(world.cloud_templates(objects))
    ground_rows = world.build_ground_rows(row_count=world.LANDSCAPE_TOTAL_GROUND_ROWS, objects_data=objects, color_codes=color_codes, pebble_density=0.07)
    world_treeline_sprites = world.build_world_treeline_sprites(objects, colors, "house")
    border_treeline_sprites = world.build_border_treeline_sprites(objects, colors)
    crossroad_house_sprites = world.build_crossroad_house_sprites(objects, colors)

    anim_mode = "opening"
    pending_screen = None
    anim_step = 0
    camera_step_seconds = 0.06
    camera_accum = 0.0
    story_transition_actors = None
    wipe_duration = 1.0
    startup_blank_seconds = 0.20
    wipe_started_at = time.monotonic() + startup_blank_seconds

    def _tick_stage1_battle(dt: float) -> str | None:
        pri_hp = [int(v) for v in flow.get("battle_primary_hp", [10])]
        sec_hp = [int(v) for v in flow.get("battle_secondary_hp", [20, 10])]
        queue = flow.get("battle_queue", [])
        qidx = int(flow.get("battle_queue_index", 0))
        if not isinstance(queue, list):
            queue = []
        if qidx >= len(queue):
            if not ui._alive_indices(sec_hp):
                flow["message_text"] = "The party was defeated in this prototype run."
                return "info"
            if not ui._alive_indices(pri_hp):
                return "story_battle_victory"
            flow["battle_target_cursor"] = ui._first_alive(pri_hp, 0)
            ui._reset_battle_command_picks(flow, int(flow.get("battle_stage", 1)))
            return "story_battle_cmd_player"

        action = queue[qidx]
        action_kind = str(action.get("kind", "physical"))
        action_t = float(flow.get("battle_action_t", 0.0)) + dt
        flow["battle_action_t"] = action_t
        cast_kinds = ("spell", "summon", "mushroom_tea", "healing_touch_single", "healing_touch_team", "concentric", "birdcall", "flee")
        duration = 1.2 if action_kind in cast_kinds else 0.9
        if action_kind == "summon":
            duration = 2.4
        if action_t < duration:
            return None

        def _apply_hp_transition(t_side: str, t_idx: int, post_hp: int) -> None:
            if t_side == "primary" and 0 <= t_idx < len(pri_hp):
                pri_hp[t_idx] = max(0, int(post_hp))
                flow["battle_primary_hp"] = pri_hp
            elif t_side == "secondary" and 0 <= t_idx < len(sec_hp):
                sec_hp[t_idx] = max(0, int(post_hp))
                flow["battle_secondary_hp"] = sec_hp

        hits = action.get("hits", [])
        if isinstance(hits, list) and hits and str(action.get("target_side", "primary")) == "primary":
            for hit in hits:
                if not isinstance(hit, dict):
                    continue
                _apply_hp_transition("primary", int(hit.get("target_index", -1)), int(hit.get("post_hp", 0)))
        elif ("post_hp" in action) and ("target_side" in action) and ("target_index" in action):
            _apply_hp_transition(str(action.get("target_side", "primary")), int(action.get("target_index", 0)), int(action.get("post_hp", 0)))

        if action_kind == "spell":
            sec_mp = [int(v) for v in flow.get("battle_secondary_mp", [0, 6])]
            s_idx = int(action.get("source_index", 0))
            post_mp = max(0, int(action.get("post_mp", 0)))
            if 0 <= s_idx < len(sec_mp):
                sec_mp[s_idx] = post_mp
                flow["battle_secondary_mp"] = sec_mp
            flow["battle_staff_charges"] = max(0, int(action.get("post_charges", int(flow.get("battle_staff_charges", 0)))))

        player_name = str(flow.get("selected_name", "Player")).strip() or "Player"
        ui._battle_log_enqueue(flow, ui._battle_action_log_lines(action, int(flow.get("battle_stage", 1)), player_name))
        flow["battle_queue_index"] = qidx + 1
        flow["battle_action_t"] = 0.0
        flow["battle_log_lines"] = ui._battle_log_visible_lines(flow)
        return None

    print(world.ANSI_HIDE_CURSOR + world.ANSI_CLEAR, end="", flush=True)
    try:
        last_tick = time.monotonic()
        while True:
            now = time.monotonic()
            dt = max(0.0, min(0.2, now - last_tick))
            last_tick = now
            wipe_progress = min(1.0, max(0.0, (now - wipe_started_at) / wipe_duration))
            for cloud in clouds:
                speed = float(cloud.get("speed", 1.0))
                cloud["x"] = float(cloud.get("x", 0.0)) - (speed * dt)
                w = int(cloud["template"]["width"])
                if cloud["x"] + w < 0:
                    cloud["x"] = world.SCREEN_W + (cloud["x"] + w)

            ui._battle_log_tick(flow, dt)

            camera_current = int(flow.get("camera_position", TITLE_LANDSCAPE_POSITION))
            camera_target = int(flow.get("camera_target", camera_current))
            if camera_current != camera_target:
                camera_accum += dt
                while camera_current != camera_target and camera_accum >= camera_step_seconds:
                    camera_accum -= camera_step_seconds
                    camera_current += 1 if camera_target > camera_current else -1
                flow["camera_position"] = camera_current
                if camera_current == camera_target and flow.get("camera_transition_screen"):
                    flow["screen"] = str(flow.get("camera_transition_screen"))
                    flow["camera_transition_screen"] = None
                    anim_mode = "opening"
                    anim_step = 0
            else:
                camera_accum = 0.0

            battle_transition = None
            if str(flow.get("screen", "root_menu")) == "story_battle_resolve":
                battle_transition = _tick_stage1_battle(dt)
            if str(flow.get("screen", "root_menu")) == "story_lineup_shift":
                position = current_landscape_position(flow)
                zones_for_transition = world.build_scene_zones(sky_rows=world.landscape_sky_rows(position))
                trans = flow.get("lineup_transition")
                if isinstance(trans, dict):
                    trans["t"] = float(trans.get("t", 0.0)) + dt
                    duration = max(0.001, float(trans.get("duration", 1.0)))
                    progress = max(0.0, min(1.0, float(trans.get("t", 0.0)) / duration))
                    start = trans.get("start", {})
                    end = trans.get("end", {})
                    if isinstance(start, dict) and isinstance(end, dict):
                        story_transition_actors = _interpolate_positions(start, end, progress)
                    if progress >= 1.0:
                        flow["lineup_transition"] = None
                        flow["screen"] = "story_battle_cmd_player"
                        anim_mode = "opening"
                        anim_step = 0
                        story_transition_actors = None
                elif story_transition_actors is None:
                    player_sprite_for_shift = player_cards[int(flow.get("player_index", 0)) % len(player_cards)].get("sprite", [])
                    start_pos = _compute_story_formation_positions(zones_for_transition, player_sprite_for_shift, sprite_map["mushy"], sprite_map["baby_crow"], "pre")
                    end_pos = _compute_story_formation_positions(zones_for_transition, player_sprite_for_shift, sprite_map["mushy"], sprite_map["baby_crow"], "post")
                    flow["lineup_transition"] = {"t": 0.0, "duration": 1.0, "start": start_pos, "end": end_pos}
                    story_transition_actors = _interpolate_positions(start_pos, end_pos, 0.0)
            else:
                story_transition_actors = None

            key = world.read_key_nonblocking()
            if key == "q":
                break
            if battle_transition is not None:
                flow["screen"] = battle_transition
                anim_mode = "opening"
                anim_step = 0
            if anim_mode == "open" and flow.get("camera_transition_screen") is None and str(flow.get("screen", "root_menu")) not in ("story_lineup_shift", "story_battle_resolve"):
                target_screen = handle_input(flow, key)
                current_screen = str(flow.get("screen", "root_menu"))
                if target_screen is not None and target_screen != current_screen:
                    if current_screen == "story_6" and target_screen == "story_lineup_shift":
                        flow["screen"] = "story_lineup_shift"
                    else:
                        pending_screen = target_screen
                        anim_mode = "closing"

            position = current_landscape_position(flow)
            zones = world.build_scene_zones(sky_rows=world.landscape_sky_rows(position))
            sky_bottom_anchor = world.sky_bottom_anchor_for_position(position)
            split_label = f"{zones['sky_bg'].height}/{world.landscape_total_ground_visible_from_horizon(position)}"
            screen = str(flow.get("screen", "root_menu"))
            if screen == "story_lineup_shift":
                ui_box = None
            else:
                ui_box = ui._build_screen_spec(flow)
            step_count = ui.ui_box_step_count(ui_box) if isinstance(ui_box, ui.UIBoxSpec) else 1
            ui_ready = wipe_progress >= 1.0
            if anim_mode == "open" or ui_box is None:
                ui_progress = 1.0
            else:
                ui_progress = anim_step / max(1, step_count)
            avatar_overlay = None
            ui_actor_status = None
            if screen == "avatar_select" and anim_mode == "open":
                pidx = int(flow.get("player_index", 0)) % len(player_cards)
                avatar_overlay = {
                    "left_rows": player_cards[0].get("sprite", []),
                    "right_rows": player_cards[1].get("sprite", []),
                    "left_label": player_cards[0].get("label", "Left"),
                    "right_label": player_cards[1].get("label", "Right"),
                    "selected": pidx,
                }

            if screen in ("story_battle_cmd_player", "story_battle_cmd_mushy"):
                sec_hp = [int(v) for v in flow.get("battle_secondary_hp", [20, 10])]
                sec_hp_max = [int(v) for v in flow.get("battle_secondary_hp_max", sec_hp)]
                sec_mp = [int(v) for v in flow.get("battle_secondary_mp", [0, 6])]
                sec_mp_max = [int(v) for v in flow.get("battle_secondary_mp_max", sec_mp)]
                actor_idx = 1 if screen == "story_battle_cmd_mushy" else 0
                if 0 <= actor_idx < len(sec_hp):
                    hp_total = sec_hp_max[actor_idx] if actor_idx < len(sec_hp_max) else max(1, sec_hp[actor_idx])
                    mp_total = sec_mp_max[actor_idx] if actor_idx < len(sec_mp_max) else (sec_mp[actor_idx] if actor_idx < len(sec_mp) else 0)
                    ui_actor_status = {
                        "hp": sec_hp[actor_idx],
                        "hp_total": max(1, hp_total),
                        "mp": sec_mp[actor_idx] if actor_idx < len(sec_mp) else 0,
                        "mp_total": max(1, mp_total),
                    }

            battle_log_screens = {"story_battle_cmd_player", "story_battle_cmd_mushy", "story_battle_resolve", "battle_log", "story_battle_victory"}
            battle_log_lines = ui._battle_log_visible_lines(flow) if screen in battle_log_screens else None
            story_target_primary_index = None
            story_target_primary_blink = bool((int(now * 2.0) % 2) == 0)
            if screen in ("story_battle_cmd_player", "story_battle_cmd_mushy"):
                pri_hp_now = [int(v) for v in flow.get("battle_primary_hp", [10])]
                t = int(flow.get("battle_target_cursor", 0))
                if 0 <= t < len(pri_hp_now) and pri_hp_now[t] > 0:
                    story_target_primary_index = t
            story_spell = None
            story_smash = None
            story_damage_hud = None
            story_primary_hp = list(int(v) for v in flow.get("battle_primary_hp", [10])) if screen in battle_log_screens else None
            story_primary_hp_totals = list(int(v) for v in flow.get("battle_primary_hp_max", story_primary_hp or [10])) if screen in battle_log_screens else None
            if screen == "story_battle_resolve":
                queue = flow.get("battle_queue", [])
                qidx = int(flow.get("battle_queue_index", 0))
                if isinstance(queue, list) and 0 <= qidx < len(queue):
                    action = queue[qidx]
                    kind = str(action.get("kind", "physical"))
                    duration = 1.2 if kind in ("spell", "summon", "mushroom_tea", "healing_touch_single", "healing_touch_team", "concentric", "birdcall", "flee") else 0.9
                    if kind == "summon":
                        duration = 2.4
                    prog = min(1.0, float(flow.get("battle_action_t", 0.0)) / max(0.001, duration))
                    if kind in ("spell", "physical"):
                        hits = action.get("hits", [])
                        if isinstance(hits, list) and hits:
                            story_damage_hud = {
                                "progress": prog,
                                "target_huds": [
                                    {
                                        "target_index": int(hit.get("target_index", 0)),
                                        "progress": prog,
                                        "pre_hp": int(hit.get("pre_hp", 0)),
                                        "post_hp": int(hit.get("post_hp", 0)),
                                        "total": int(hit.get("total", story_primary_hp_totals[0] if story_primary_hp_totals else 10)),
                                        "damage": int(hit.get("damage", 0)),
                                    }
                                    for hit in hits
                                    if isinstance(hit, dict)
                                ],
                            }
                        else:
                            story_damage_hud = {
                                "target_index": int(action.get("target_index", 0)),
                                "progress": prog,
                                "pre_hp": int(action.get("pre_hp", 0)),
                                "post_hp": int(action.get("post_hp", 0)),
                                "total": int(action.get("total", story_primary_hp_totals[0] if story_primary_hp_totals else 10)),
                                "damage": int(action.get("damage", 0)),
                            }
                    if kind in ("spell", "summon", "mushroom_tea", "healing_touch_single", "healing_touch_team", "concentric", "birdcall"):
                        story_spell = {
                            "source_side": str(action.get("source_side", "secondary")),
                            "source_index": int(action.get("source_index", 0)),
                            "target_side": str(action.get("target_side", "primary")),
                            "target_index": int(action.get("target_index", 0)),
                            "progress": prog,
                        }
                    elif kind == "physical":
                        story_smash = {
                            "source_side": str(action.get("source_side", "secondary")),
                            "source_index": int(action.get("source_index", 0)),
                            "target_side": str(action.get("target_side", "primary")),
                            "target_index": int(action.get("target_index", 0)),
                            "progress": prog,
                        }

            frame = render(
                clouds=clouds,
                ground_rows=ground_rows,
                zones=zones,
                sky_bottom_anchor=sky_bottom_anchor,
                foreground_split_label=split_label,
                landscape_position=position,
                world_treeline_sprites=world_treeline_sprites,
                border_treeline_sprites=border_treeline_sprites,
                crossroad_house_sprites=crossroad_house_sprites,
                primary_actor_sprites=actor_sprites_from_keys(sprite_map, current_primary_keys(flow)),
                secondary_actor_sprites=actor_sprites_from_keys(sprite_map, current_secondary_keys(flow)),
                ui_active_box=(ui_box if (ui_ready and isinstance(ui_box, ui.UIBoxSpec)) else None),
                beat_label=screen,
                address_label=current_address_label(flow),
                blink_on=bool((int(now * 2.0) % 2) == 0),
                title_logo=title_logo,
                show_title=show_title_logo(flow),
                ui_box_progress=(ui_progress if ui_ready else 0.0),
                ui_avatar_overlay=(avatar_overlay if ui_ready else None),
                ui_actor_status=(ui_actor_status if ui_ready else None),
                wipe_progress=wipe_progress,
                story_transition_actors=story_transition_actors,
                story_target_primary_index=story_target_primary_index,
                story_target_primary_blink=story_target_primary_blink,
                story_spell=story_spell,
                story_smash=story_smash,
                story_primary_hp=story_primary_hp,
                story_primary_hp_totals=story_primary_hp_totals,
                story_damage_hud=story_damage_hud,
                battle_log_lines=battle_log_lines,
            )
            print(world.ANSI_HOME + frame, end="", flush=True)

            if ui_ready:
                if anim_mode == "opening":
                    anim_step = min(step_count, anim_step + 4)
                    if anim_step >= step_count:
                        anim_mode = "open"
                elif anim_mode == "closing":
                    anim_step = max(0, anim_step - 4)
                    if anim_step <= 0:
                        flow["screen"] = str(pending_screen or flow.get("screen", "root_menu"))
                        pending_screen = None
                        anim_mode = "opening"
                        anim_step = 0
                else:
                    anim_step = step_count

            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        print(world.ANSI_SHOW_CURSOR + world.ANSI_RESET)


if __name__ == "__main__":
    main()
