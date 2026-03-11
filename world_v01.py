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
    if screen in ("story_battle_cmd_player", "story_battle_cmd_mushy", "battle_log"):
        return ["baby_crow"]
    return []


def current_secondary_keys(flow: dict) -> List[str]:
    if isinstance(flow.get("lineup_transition"), dict):
        return []
    screen = str(flow.get("screen", "root_menu"))
    if screen in ("story_4", "story_5", "story_6"):
        return ["player"]
    if screen in ("story_battle_cmd_player", "story_battle_cmd_mushy", "battle_log", "story_battle_victory"):
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
        options = _battle_options(flow, "player")
        cursor = int(flow.get("battle_player_cmd_idx", 0)) % max(1, len(options))
        if key == "up":
            flow["battle_player_cmd_idx"] = (cursor - 1) % len(options)
        elif key == "down":
            flow["battle_player_cmd_idx"] = (cursor + 1) % len(options)
        elif confirm:
            flow["battle_player_action"] = options[cursor]
            return "story_battle_cmd_mushy"
        elif back:
            return "story_6"
        return None

    if screen == "story_battle_cmd_mushy":
        options = _battle_options(flow, "mushy")
        cursor = int(flow.get("battle_mushy_cmd_idx", 0)) % max(1, len(options))
        if key == "up":
            flow["battle_mushy_cmd_idx"] = (cursor - 1) % len(options)
        elif key == "down":
            flow["battle_mushy_cmd_idx"] = (cursor + 1) % len(options)
        elif confirm:
            flow["battle_mushy_action"] = options[cursor]
            flow["battle_log_lines"] = build_stage1_battle_log(flow)
            return "battle_log"
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
    story_transition_actors: List[dict] | None = None,
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

    if isinstance(story_transition_actors, list) and story_transition_actors:
        for actor in story_transition_actors:
            rows = actor.get("rows", [])
            if not isinstance(rows, list):
                continue
            _draw_actor_rows(int(actor.get("x", 0)), int(actor.get("y", 0)), rows)
    else:
        if secondary_actor_sprites:
            for actor in world.layout_actor_strip(secondary_zone, secondary_actor_sprites, spacing=1, stagger_rows=1, reverse_stagger=True):
                _draw_actor_rows(int(actor.get("x", 0)), int(actor.get("y", 0)), actor.get("rows", []))
        if primary_actor_sprites:
            for actor in world.layout_actor_strip(primary_zone, primary_actor_sprites, spacing=1, stagger_rows=1):
                _draw_actor_rows(int(actor.get("x", 0)), int(actor.get("y", 0)), actor.get("rows", []))

    if show_title and isinstance(title_logo, dict):
        ui._overlay_title_logo(canvas, title_logo)
    if ui_active_box is not None:
        progress = max(0.0, min(1.0, float(ui_box_progress)))
        if progress < 1.0:
            ui.draw_ui_box_animated(canvas, ui_active_box, progress, blink_on=blink_on)
        else:
            ui.draw_ui_box(canvas, ui_active_box, blink_on=blink_on)
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
    camera_step_seconds = 0.03
    camera_accum = 0.0
    story_transition_actors = None

    print(world.ANSI_HIDE_CURSOR + world.ANSI_CLEAR, end="", flush=True)
    try:
        last_tick = time.monotonic()
        while True:
            now = time.monotonic()
            dt = max(0.0, min(0.2, now - last_tick))
            last_tick = now
            for cloud in clouds:
                speed = float(cloud.get("speed", 1.0))
                cloud["x"] = float(cloud.get("x", 0.0)) - (speed * dt)
                w = int(cloud["template"]["width"])
                if cloud["x"] + w < 0:
                    cloud["x"] = world.SCREEN_W + (cloud["x"] + w)

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
            if anim_mode == "open" and flow.get("camera_transition_screen") is None and str(flow.get("screen", "root_menu")) != "story_lineup_shift":
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
            if screen == "battle_log":
                ui_box = build_battle_log_spec([str(line) for line in flow.get("battle_log_lines", [])])
            elif screen == "story_lineup_shift":
                ui_box = None
            else:
                ui_box = ui._build_screen_spec(flow)
            step_count = ui.ui_box_step_count(ui_box) if isinstance(ui_box, ui.UIBoxSpec) else 1
            if anim_mode == "open" or ui_box is None:
                ui_progress = 1.0
            else:
                ui_progress = anim_step / max(1, step_count)
            avatar_overlay = None
            if screen == "avatar_select" and anim_mode == "open":
                pidx = int(flow.get("player_index", 0)) % len(player_cards)
                avatar_overlay = {
                    "left_rows": player_cards[0].get("sprite", []),
                    "right_rows": player_cards[1].get("sprite", []),
                    "left_label": player_cards[0].get("label", "Left"),
                    "right_label": player_cards[1].get("label", "Right"),
                    "selected": pidx,
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
                ui_active_box=ui_box if isinstance(ui_box, ui.UIBoxSpec) else None,
                beat_label=screen,
                address_label=current_address_label(flow),
                blink_on=bool((int(now * 2.0) % 2) == 0),
                title_logo=title_logo,
                show_title=show_title_logo(flow),
                ui_box_progress=ui_progress,
                ui_avatar_overlay=avatar_overlay,
                story_transition_actors=story_transition_actors,
            )
            print(world.ANSI_HOME + frame, end="", flush=True)

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
