import copy
import os
import time
from typing import Dict, List

import cottage_v04 as world
import ui_v08 as ui


ADDRESS_LANDSCAPE_POSITIONS = {
    "#1 Ave A": 50,
}
TRAVEL_STEP_SECONDS = 0.03
TRAVEL_SETTLE_SECONDS = 0.35


def build_stage1_flow(player_name: str) -> dict:
    return {
        "screen": "story_1",
        "avatar_label": player_name,
        "selected_name": player_name,
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
        "battle_player_action": "Magic Spark",
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
    }


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
    body_lines = list(lines[:5])
    return ui.UIBoxSpec(
        role="battle_log",
        border_style="heavy",
        title="Battle Log",
        body_text="\n".join(body_lines),
        center_x=50,
        center_y=17,
        max_body_width=58,
        body_align="left",
        wrap_mode="normal",
        actions=["[ A / Continue ]", "[ Left/Right / Step ]"],
        preserve_body_whitespace=True,
    )


def build_steps(flow: dict, battle_log_lines: List[str]) -> List[dict]:
    steps: List[dict] = [
        {
            "kind": "travel",
            "label": "travel",
            "caption": "Traveling down Main Street to #1 Ave A...",
            "secondary_keys": ["player"],
            "primary_keys": [],
        },
        {
            "kind": "ui",
            "label": "story_1",
            "screen": "story_1",
            "secondary_keys": ["player"],
            "primary_keys": ["baby_crow", "mushy"],
        },
        {
            "kind": "ui",
            "label": "story_4",
            "screen": "story_4",
            "secondary_keys": ["player"],
            "primary_keys": ["baby_crow", "mushy"],
        },
        {
            "kind": "ui",
            "label": "story_5",
            "screen": "story_5",
            "secondary_keys": ["player"],
            "primary_keys": ["baby_crow", "mushy"],
        },
        {
            "kind": "ui",
            "label": "story_6",
            "screen": "story_6",
            "secondary_keys": ["player"],
            "primary_keys": ["baby_crow", "mushy"],
        },
        {
            "kind": "ui",
            "label": "story_battle_cmd_player",
            "screen": "story_battle_cmd_player",
            "secondary_keys": ["player", "mushy"],
            "primary_keys": ["baby_crow"],
        },
        {
            "kind": "ui",
            "label": "story_battle_cmd_mushy",
            "screen": "story_battle_cmd_mushy",
            "secondary_keys": ["player", "mushy"],
            "primary_keys": ["baby_crow"],
        },
        {
            "kind": "battle_log",
            "label": "battle_log",
            "spec": build_battle_log_spec(battle_log_lines),
            "secondary_keys": ["player", "mushy"],
            "primary_keys": ["baby_crow"],
        },
        {
            "kind": "ui",
            "label": "story_battle_victory",
            "screen": "story_battle_victory",
            "secondary_keys": ["player", "mushy"],
            "primary_keys": [],
        },
    ]
    return steps


def actor_sprites_from_keys(sprite_map: Dict[str, List[List[str]]], keys: List[str]) -> List[List[List[str]]]:
    sprites: List[List[List[str]]] = []
    for key in keys:
        rows = sprite_map.get(key, [])
        if isinstance(rows, list) and rows:
            sprites.append(rows)
    return sprites


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

    secondary_placements = world.layout_actor_strip(
        secondary_zone,
        secondary_actor_sprites,
        spacing=1,
        stagger_rows=1,
        reverse_stagger=True,
    )
    for actor in secondary_placements:
        x0 = int(actor.get("x", 0))
        y0 = int(actor.get("y", 0))
        rows = actor.get("rows", [])
        if not isinstance(rows, list):
            continue
        for dy, row in enumerate(rows):
            y = y0 + dy
            if y < 0 or y >= world.SCREEN_H:
                continue
            for dx, cell in enumerate(row):
                x = x0 + dx
                if 0 <= x < world.SCREEN_W and cell != " ":
                    canvas[y][x] = cell

    primary_placements = world.layout_actor_strip(primary_zone, primary_actor_sprites, spacing=1, stagger_rows=1)
    for actor in primary_placements:
        x0 = int(actor.get("x", 0))
        y0 = int(actor.get("y", 0))
        rows = actor.get("rows", [])
        if not isinstance(rows, list):
            continue
        for dy, row in enumerate(rows):
            y = y0 + dy
            if y < 0 or y >= world.SCREEN_H:
                continue
            for dx, cell in enumerate(row):
                x = x0 + dx
                if 0 <= x < world.SCREEN_W and cell != " ":
                    canvas[y][x] = cell

    if ui_active_box is not None:
        ui.draw_ui_box(canvas, ui_active_box, blink_on=blink_on)

    footer = f"[background][{foreground_split_label}][address:{address_label}][beat:{beat_label}]"
    if len(footer) <= world.SCREEN_W:
        x0 = (world.SCREEN_W - len(footer)) // 2
        y = world.SCREEN_H - 1
        for idx, ch in enumerate(footer):
            canvas[y][x0 + idx] = ch

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
    templates = world.cloud_templates(objects)
    if not templates:
        raise RuntimeError("No cloud templates available")

    player_name = "Guy"
    flow = build_stage1_flow(player_name)
    battle_log_lines = build_stage1_battle_log(flow)
    steps = build_steps(flow, battle_log_lines)

    sprite_map = {
        "player": world.build_player_sprite(players, "player_01", color_codes),
        "mushy": world.build_opponent_sprite(opponents, "mushroom_baby", color_codes),
        "baby_crow": world.build_opponent_sprite(opponents, "baby_crow", color_codes),
    }

    clouds = world.spawn_clouds_full_canvas(templates)
    ground_rows = world.build_ground_rows(
        row_count=world.LANDSCAPE_TOTAL_GROUND_ROWS,
        objects_data=objects,
        color_codes=color_codes,
        pebble_density=0.07,
    )
    world_treeline_sprites = world.build_world_treeline_sprites(objects, colors, "house")
    border_treeline_sprites = world.build_border_treeline_sprites(objects, colors)
    crossroad_house_sprites = world.build_crossroad_house_sprites(objects, colors)

    current_landscape_position = world.DEFAULT_LANDSCAPE_POSITION
    target_landscape_position = ADDRESS_LANDSCAPE_POSITIONS["#1 Ave A"]
    current_step = 0
    travel_arrived_at = None
    transition_accum = 0.0

    print(world.ANSI_HIDE_CURSOR + world.ANSI_CLEAR, end="", flush=True)
    try:
        last_tick = time.monotonic()
        while True:
            now = time.monotonic()
            dt = max(0.0, min(0.2, now - last_tick))
            last_tick = now

            if current_step == 0:
                if current_landscape_position != target_landscape_position:
                    transition_accum += dt
                    while current_landscape_position != target_landscape_position and transition_accum >= TRAVEL_STEP_SECONDS:
                        transition_accum -= TRAVEL_STEP_SECONDS
                        current_landscape_position += 1 if target_landscape_position > current_landscape_position else -1
                elif travel_arrived_at is None:
                    travel_arrived_at = now
                elif now - travel_arrived_at >= TRAVEL_SETTLE_SECONDS:
                    current_step = 1
            else:
                current_landscape_position = target_landscape_position
                transition_accum = 0.0

            for cloud in clouds:
                speed = float(cloud.get("speed", 1.0))
                cloud["x"] = float(cloud.get("x", 0.0)) - (speed * dt)
                w = int(cloud["template"]["width"])
                if cloud["x"] + w < 0:
                    cloud["x"] = world.SCREEN_W + (cloud["x"] + w)

            key = world.read_key_nonblocking()
            if key == "q":
                break
            if key in ("\r", "\n", "d", "right"):
                current_step = min(len(steps) - 1, current_step + 1)
            elif key in ("a", "left"):
                current_step = max(0, current_step - 1)
                if current_step == 0 and current_landscape_position != target_landscape_position:
                    travel_arrived_at = None

            zones = world.build_scene_zones(sky_rows=world.landscape_sky_rows(current_landscape_position))
            sky_bottom_anchor = world.sky_bottom_anchor_for_position(current_landscape_position)
            split_label = f"{zones['sky_bg'].height}/{world.landscape_total_ground_visible_from_horizon(current_landscape_position)}"
            step = steps[current_step]

            if step.get("kind") == "travel":
                ui_box = ui.UIBoxSpec(
                    role="story",
                    border_style="heavy",
                    title="Main Street",
                    body_text=str(step.get("caption", "")),
                    center_x=50,
                    center_y=17,
                    max_body_width=48,
                    wrap_mode="balanced",
                    body_align="left",
                    actions=["[ Auto Travel ]", "[ Left/Right / Step ]"],
                )
            elif step.get("kind") == "battle_log":
                ui_box = step.get("spec")
            else:
                step_flow = copy.deepcopy(flow)
                step_flow["screen"] = str(step.get("screen", "story_1"))
                ui_box = ui._build_screen_spec(step_flow)

            frame = render(
                clouds=clouds,
                ground_rows=ground_rows,
                zones=zones,
                sky_bottom_anchor=sky_bottom_anchor,
                foreground_split_label=split_label,
                landscape_position=current_landscape_position,
                world_treeline_sprites=world_treeline_sprites,
                border_treeline_sprites=border_treeline_sprites,
                crossroad_house_sprites=crossroad_house_sprites,
                primary_actor_sprites=actor_sprites_from_keys(sprite_map, list(step.get("primary_keys", []))),
                secondary_actor_sprites=actor_sprites_from_keys(sprite_map, list(step.get("secondary_keys", []))),
                ui_active_box=ui_box if isinstance(ui_box, ui.UIBoxSpec) else None,
                beat_label=str(step.get("label", "scene")),
                address_label="#1 Ave A",
                blink_on=bool((int(now * 2.0) % 2) == 0),
            )
            print(world.ANSI_HOME + frame, end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        print(world.ANSI_SHOW_CURSOR + world.ANSI_RESET)


if __name__ == "__main__":
    main()
