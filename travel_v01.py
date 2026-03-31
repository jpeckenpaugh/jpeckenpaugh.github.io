import os
import random
import sys
import time
from typing import Dict, List

import cottage_v04 as world


TITLE_LANDSCAPE_POSITION = 5
START_TRAVEL_POSITION = 15
ADDRESS_LANDSCAPE_POSITIONS = {
    "#1 Ave A": 50,
}
CAMERA_STEP_SECONDS = 0.02
SIDE_STEP_COLUMNS = 2
TRAVEL_WORLD_WIDTH = 320
WORLD_MODELS = list(world.WORLD_SCENE_VARIANTS)
MUSHROOM_HOUSE_LABEL = "[#10 Ave A]"
WALK_FRAME_SEQUENCE = ["idle", "step_a", "idle", "step_b"]
WALK_FRAME_STEP_SECONDS = 0.5
WALK_RESET_IDLE_SECONDS = 1.0


def current_address_label(position: int) -> str:
    return "#1 Ave A" if int(position) >= ADDRESS_LANDSCAPE_POSITIONS["#1 Ave A"] else "Main Street"


def world_center_x() -> int:
    return (TRAVEL_WORLD_WIDTH - 1) // 2


def starting_camera_x() -> int:
    return max(0, min(TRAVEL_WORLD_WIDTH - world.SCREEN_W, (TRAVEL_WORLD_WIDTH - world.SCREEN_W) // 2))


def draw_sprite(canvas: List[List[str]], rows: List[List[str]], x0: int, y0: int) -> None:
    for dy, row in enumerate(rows):
        y = y0 + dy
        if y < 0 or y >= world.SCREEN_H or not isinstance(row, list):
            continue
        for dx, cell in enumerate(row):
            x = x0 + dx
            if 0 <= x < world.SCREEN_W and cell != " ":
                canvas[y][x] = cell


def draw_label(canvas: List[List[str]], text: str, x0: int, y0: int, color: str = "") -> None:
    if y0 < 0 or y0 >= world.SCREEN_H:
        return
    for idx, ch in enumerate(text):
        x = x0 + idx
        if 0 <= x < world.SCREEN_W:
            canvas[y0][x] = f"{color}{ch}{world.ANSI_RESET}" if color else ch


def first_window_bounds(mask_rows: List[str]) -> tuple[int, int, int, int] | None:
    coords: List[tuple[int, int]] = []
    for y, row in enumerate(mask_rows):
        for x, ch in enumerate(str(row)):
            if ch == "?":
                coords.append((x, y))
    if not coords:
        return None
    coord_set = set(coords)
    seed = min(coords, key=lambda item: (item[0], item[1]))
    stack = [seed]
    visited = {seed}
    component: List[tuple[int, int]] = []
    while stack:
        x, y = stack.pop()
        component.append((x, y))
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (nx, ny) in coord_set and (nx, ny) not in visited:
                visited.add((nx, ny))
                stack.append((nx, ny))
    min_x = min(x for x, _ in component)
    max_x = max(x for x, _ in component)
    min_y = min(y for _, y in component)
    max_y = max(y for _, y in component)
    return (min_x, max_x, min_y, max_y)


def all_window_bounds(mask_rows: List[str]) -> tuple[int, int, int, int] | None:
    coords: List[tuple[int, int]] = []
    for y, row in enumerate(mask_rows):
        for x, ch in enumerate(str(row)):
            if ch == "?":
                coords.append((x, y))
    if not coords:
        return None
    min_x = min(x for x, _ in coords)
    max_x = max(x for x, _ in coords)
    min_y = min(y for _, y in coords)
    max_y = max(y for _, y in coords)
    return (min_x, max_x, min_y, max_y)


def house_row_spans(art_rows: List[str]) -> List[tuple[int, int] | None]:
    spans: List[tuple[int, int] | None] = []
    for row in art_rows:
        line = str(row)
        filled = [idx for idx, ch in enumerate(line) if ch != " "]
        spans.append((filled[0], filled[-1]) if filled else None)
    return spans


def can_place_house_occupant_pose(art_rows: List[str], occupant_rows: List[List[str]], pose: dict) -> bool:
    spans = house_row_spans(art_rows)
    occ_h = len(occupant_rows)
    occ_x0 = int(pose.get("x0", 0))
    occ_y0 = max(0, len(art_rows) - occ_h - int(pose.get("floor_offset", 1)))
    for local_y, occ_row in enumerate(occupant_rows):
        house_y = occ_y0 + local_y
        if house_y < 0 or house_y >= len(spans):
            return False
        span = spans[house_y]
        if span is None:
            return False
        min_x, max_x = span
        for local_x, cell in enumerate(occ_row):
            if cell == " ":
                continue
            house_x = occ_x0 + local_x
            if house_x < min_x or house_x > max_x:
                return False
    return True


def default_house_occupant_pose(art_rows: List[str], mask_rows: List[str], occupant_rows: List[List[str]]) -> dict:
    occ_h = len(occupant_rows)
    occ_w = max((len(row) for row in occupant_rows), default=0)
    first_bounds = first_window_bounds(mask_rows)
    occ_x0 = 0
    if first_bounds is not None:
        min_x, max_x, _min_y, _max_y = first_bounds
        occ_x0 = ((min_x + max_x) // 2) - (occ_w // 2)
    pose = {"x0": occ_x0, "floor_offset": 1, "height": occ_h, "width": occ_w}
    return clamp_house_occupant_pose(art_rows, mask_rows, occupant_rows, pose)


def clamp_house_occupant_pose(art_rows: List[str], mask_rows: List[str], occupant_rows: List[List[str]], pose: dict) -> dict:
    bounds = all_window_bounds(mask_rows)
    occ_h = len(occupant_rows)
    occ_w = max((len(row) for row in occupant_rows), default=0)
    x0 = int(pose.get("x0", 0))
    floor_offset = max(1, min(3, int(pose.get("floor_offset", 1))))
    if bounds is not None and occ_w > 0:
        min_x, max_x, _min_y, _max_y = bounds
        x0 = max(min_x - occ_w + 1, min(max_x, x0))
    candidate = {"x0": x0, "floor_offset": floor_offset, "height": occ_h, "width": occ_w}
    if can_place_house_occupant_pose(art_rows, occupant_rows, candidate):
        return candidate
    for test_floor in range(floor_offset, 0, -1):
        test_candidate = {"x0": x0, "floor_offset": test_floor, "height": occ_h, "width": occ_w}
        if can_place_house_occupant_pose(art_rows, occupant_rows, test_candidate):
            return test_candidate
    for delta in range(1, max(1, occ_w) + 8):
        for test_x0 in (x0 - delta, x0 + delta):
            test_candidate = {"x0": test_x0, "floor_offset": floor_offset, "height": occ_h, "width": occ_w}
            if can_place_house_occupant_pose(art_rows, occupant_rows, test_candidate):
                return clamp_house_occupant_pose(art_rows, mask_rows, occupant_rows, test_candidate)
    return candidate


def step_house_occupant_pose(art_rows: List[str], mask_rows: List[str], occupant_rows: List[List[str]], pose: dict, rng: random.Random) -> dict:
    if rng.random() >= 0.5:
        return clamp_house_occupant_pose(art_rows, mask_rows, occupant_rows, pose)
    updated = dict(pose)
    direction = rng.choice(["left", "right", "up", "down"])
    if direction == "left":
        updated["x0"] = int(updated.get("x0", 0)) - 1
    elif direction == "right":
        updated["x0"] = int(updated.get("x0", 0)) + 1
    elif direction == "up":
        updated["floor_offset"] = int(updated.get("floor_offset", 0)) + 1
    else:
        updated["floor_offset"] = int(updated.get("floor_offset", 0)) - 1
    updated = clamp_house_occupant_pose(art_rows, mask_rows, occupant_rows, updated)
    return updated if can_place_house_occupant_pose(art_rows, occupant_rows, updated) else pose


def draw_house_sprite(
    canvas: List[List[str]],
    drawable: dict,
    occupant_rows: List[List[str]] | None = None,
    occupant_pose: dict | None = None,
) -> None:
    rows = drawable.get("rows", [])
    if not isinstance(rows, list):
        return
    x0 = int(drawable.get("x", 0))
    y0 = int(drawable.get("y", 0))
    mask_rows = drawable.get("mask_rows", [])
    if not isinstance(mask_rows, list) or not mask_rows:
        draw_sprite(canvas, rows, x0, y0)
        return

    opaque_space = f"\x1b[37m {world.ANSI_RESET}"
    occ_rows = occupant_rows if isinstance(occupant_rows, list) else []
    occ_h = len(occ_rows)
    occ_x0 = 0
    occ_y0 = 0
    if occ_rows:
        art_rows = drawable.get("art_rows", [])
        if not isinstance(art_rows, list):
            art_rows = []
        pose = clamp_house_occupant_pose(
            [str(row) for row in art_rows],
            [str(row) for row in mask_rows],
            occ_rows,
            occupant_pose or default_house_occupant_pose([str(row) for row in art_rows], [str(row) for row in mask_rows], occ_rows),
        )
        occ_x0 = int(pose.get("x0", 0))
        occ_y0 = max(0, len(rows) - occ_h - int(pose.get("floor_offset", 0)))

    for dy, row in enumerate(rows):
        screen_y = y0 + dy
        if screen_y < 0 or screen_y >= world.SCREEN_H or not isinstance(row, list):
            continue
        mask_line = str(mask_rows[dy]) if dy < len(mask_rows) else ""
        for dx, cell in enumerate(row):
            screen_x = x0 + dx
            if screen_x < 0 or screen_x >= world.SCREEN_W:
                continue
            key = mask_line[dx] if dx < len(mask_line) else ""
            if key == "?":
                occ_cell = " "
                local_x = dx - occ_x0
                local_y = dy - occ_y0
                if 0 <= local_y < occ_h:
                    occ_row = occ_rows[local_y]
                    if 0 <= local_x < len(occ_row):
                        occ_cell = occ_row[local_x]
                canvas[screen_y][screen_x] = occ_cell if occ_cell != " " else opaque_space
                continue
            if cell != " ":
                canvas[screen_y][screen_x] = cell


def build_avatar_placement(rows: List[List[str]]) -> dict:
    width = max((len(row) for row in rows), default=0) if isinstance(rows, list) else 0
    height = len(rows) if isinstance(rows, list) else 0
    x = max(0, min(world.SCREEN_W - max(1, width), (world.SCREEN_W // 2) - (width // 2)))
    y = max(0, min(world.SCREEN_H - max(1, height), world.SCREEN_H - height - 6))
    return {"x": x, "y": y, "width": width, "height": height, "rows": rows}


def avatar_feet_world_x(avatar_rows: List[List[str]], camera_x: int) -> int:
    avatar = build_avatar_placement(avatar_rows)
    return int(camera_x) + int(avatar["x"]) + max(0, (int(avatar["width"]) // 2))


def avatar_feet_distance_from_horizon(avatar_rows: List[List[str]], zones: Dict[str, world.LayoutZone]) -> int:
    ground_zone = zones["ground_bg"]
    avatar = build_avatar_placement(avatar_rows)
    foot_y = int(avatar["y"]) + max(0, int(avatar["height"]) - 1)
    return max(0, foot_y - int(ground_zone.y))


def is_camera_on_walkable_surface(
    camera_x: int,
    avatar_rows: List[List[str]],
    zones: Dict[str, world.LayoutZone],
    landscape_position: int,
) -> bool:
    distance_from_horizon = avatar_feet_distance_from_horizon(avatar_rows, zones)
    world_row = world.landscape_ground_window_start(landscape_position) + distance_from_horizon
    if world.crossroad_row_phase(world_row) is not None:
        return True
    road = road_geometry_for_horizon_distance(distance_from_horizon)
    foot_world_x = avatar_feet_world_x(avatar_rows, camera_x)
    return int(road.get("start", 0)) <= foot_world_x <= int(road.get("end", TRAVEL_WORLD_WIDTH - 1))


def clamp_camera_to_road(
    camera_x: int,
    avatar_rows: List[List[str]],
    zones: Dict[str, world.LayoutZone],
    landscape_position: int,
) -> int:
    distance_from_horizon = avatar_feet_distance_from_horizon(avatar_rows, zones)
    world_row = world.landscape_ground_window_start(landscape_position) + distance_from_horizon
    min_bound = 0
    max_bound = max(0, TRAVEL_WORLD_WIDTH - world.SCREEN_W)
    if world.crossroad_row_phase(world_row) is not None:
        return max(min_bound, min(max_bound, int(camera_x)))
    road = road_geometry_for_horizon_distance(distance_from_horizon)
    avatar = build_avatar_placement(avatar_rows)
    foot_screen_x = int(avatar["x"]) + max(0, (int(avatar["width"]) // 2))
    min_camera_x = int(road.get("start", 0)) - foot_screen_x
    max_camera_x = int(road.get("end", TRAVEL_WORLD_WIDTH - 1)) - foot_screen_x
    return max(min_bound, min(max_bound, max(min_camera_x, min(max_camera_x, int(camera_x)))))


def recenter_sprite_x(sprite: dict) -> dict:
    updated = dict(sprite)
    updated["x"] = int(sprite.get("x", 0)) + starting_camera_x()
    return updated


def spawn_clouds_wide(templates: List[dict]) -> List[dict]:
    rng = __import__("random").Random(14113)
    clouds: List[dict] = []
    if not templates:
        return clouds
    count = max(20, min(96, int(round((TRAVEL_WORLD_WIDTH * world.SKY_LAYER_HEIGHT) / 240.0))))
    for _ in range(count):
        template = templates[rng.randrange(len(templates))]
        width = int(template["width"])
        height = int(template["height"])
        y_max = max(0, world.SKY_LAYER_HEIGHT - height)
        y = rng.randint(0, y_max) if y_max > 0 else 0
        x = rng.randint(-max(1, width // 2), TRAVEL_WORLD_WIDTH - 1)
        speed = world._cloud_speed(str(template.get("size", "medium")), y, world.SKY_LAYER_HEIGHT, rng)
        clouds.append({"template": template, "x": float(x), "y": float(y), "speed": speed})
    return clouds


def build_ground_rows_wide(
    row_count: int,
    objects_data: object,
    color_codes: Dict[str, str],
    pebble_density: float = 0.07,
) -> List[str]:
    rng = __import__("random").Random(9051701)
    rows: List[str] = []
    grass_pattern = "~"
    grass_mask = "g"
    if isinstance(objects_data, dict):
        grass_obj = objects_data.get("grass", {})
        if isinstance(grass_obj, dict):
            art = grass_obj.get("art", [])
            mask = grass_obj.get("color_mask", [])
            if isinstance(art, list) and art:
                grass_pattern = str(art[0]) or "~"
            if isinstance(mask, list) and mask:
                grass_mask = str(mask[0]) or "g"

    pebble_glyphs: List[str] = ["o", "O"]
    pebble_keys: List[str] = ["Z", "z", "X", "x", "L", "l"]
    if isinstance(objects_data, dict):
        scatter_obj = objects_data.get("battle_ground", {}) or objects_data.get("pebble", {})
        dynamic = scatter_obj.get("dynamic", {}) if isinstance(scatter_obj, dict) else {}
        dyn_glyphs = dynamic.get("glyphs", []) if isinstance(dynamic, dict) else []
        dyn_keys = dynamic.get("color_keys", []) if isinstance(dynamic, dict) else []
        if isinstance(dyn_glyphs, list) and dyn_glyphs:
            pebble_glyphs = [str(g)[:1] or "o" for g in dyn_glyphs]
        if isinstance(dyn_keys, list) and dyn_keys:
            pebble_keys = [str(k)[:1] or "Z" for k in dyn_keys]

    density = max(0.0, min(0.4, pebble_density))
    for _row_idx in range(max(0, row_count)):
        row: List[str] = []
        for x in range(TRAVEL_WORLD_WIDTH):
            base_glyph = grass_pattern[x % max(1, len(grass_pattern))]
            base_key = grass_mask[x % max(1, len(grass_mask))]
            cell = world._colorize_glyph(base_glyph, base_key, color_codes)
            if rng.random() < density:
                glyph = rng.choice(pebble_glyphs)
                key = rng.choice(pebble_keys)
                cell = world._colorize_glyph(glyph, key, color_codes)
            row.append(cell)
        rows.append("".join(row))
    return rows


def road_geometry_for_horizon_distance(distance_from_horizon: int) -> dict:
    road_width = world.road_width_for_horizon_distance(distance_from_horizon)
    road_half = road_width // 2
    road_center = world_center_x()
    road_start = max(0, road_center - road_half)
    road_end = min(TRAVEL_WORLD_WIDTH - 1, road_start + road_width - 1)
    left_push = road_width // 2
    right_push = road_width - left_push
    return {
        "width": road_width,
        "start": road_start,
        "end": road_end,
        "left_push": left_push,
        "right_push": right_push,
    }


def border_tree_screen_x(side: str, width: int, column_band: int, column_jitter: int) -> int:
    band = max(0, min(2, int(column_band)))
    jitter = max(-1, min(1, int(column_jitter)))
    if side == "left":
        return (band * 3) + jitter
    return world.SCREEN_W - max(1, width) - (band * 3) + jitter


def recenter_border_sprite_x(sprite: dict) -> dict:
    updated = dict(sprite)
    side = str(sprite.get("side", "left"))
    width = int(sprite.get("width", 0))
    column_band = int(sprite.get("side_column", 0))
    column_jitter = int(sprite.get("side_jitter", 0))
    updated["x"] = border_tree_screen_x(side, width, column_band, column_jitter) + starting_camera_x()
    return updated


def overlay_crossroad_row(base_cells: List[str], world_row: int, row_seed: int) -> List[str]:
    phase = world.crossroad_row_phase(world_row)
    if phase is None:
        return list(base_cells)
    out = list(base_cells[:TRAVEL_WORLD_WIDTH])
    if len(out) < TRAVEL_WORLD_WIDTH:
        out.extend([" "] * (TRAVEL_WORLD_WIDTH - len(out)))
    rng = __import__("random").Random(row_seed)
    if phase == "stone":
        stone_glyphs = ["o", "O"]
        stone_colors = [
            "\x1b[38;2;185;185;185m",
            "\x1b[38;2;140;140;140m",
        ]
        for x in range(TRAVEL_WORLD_WIDTH):
            idx = rng.randrange(len(stone_glyphs))
            out[x] = f"{stone_colors[idx]}{stone_glyphs[idx]}{world.ANSI_RESET}"
        return out
    dirt_chars = [".", ",", "'", "`"]
    dirt_color = "\x1b[38;2;170;170;170m"
    for x in range(TRAVEL_WORLD_WIDTH):
        out[x] = f"{dirt_color}{rng.choice(dirt_chars)}{world.ANSI_RESET}"
    return out


def build_road_pushed_row(base_cells: List[str], road_width: int, row_seed: int, crossroad_phase: str | None = None) -> List[str]:
    cells = list(base_cells[:TRAVEL_WORLD_WIDTH])
    if len(cells) < TRAVEL_WORLD_WIDTH:
        cells.extend([" "] * (TRAVEL_WORLD_WIDTH - len(cells)))
    road_width = max(1, min(TRAVEL_WORLD_WIDTH, int(road_width)))
    road_half = road_width // 2
    road_center = world_center_x()
    road_start = max(0, road_center - road_half)
    road_end = min(TRAVEL_WORLD_WIDTH - 1, road_start + road_width - 1)
    left_push = road_width // 2
    right_push = road_width - left_push
    road_rng = __import__("random").Random(row_seed)
    road_chars = [".", ",", "'", "`"]
    road_color = "\x1b[38;2;170;170;170m"
    stone_glyphs = ["o", "O"]
    stone_colors = [
        "\x1b[38;2;185;185;185m",
        "\x1b[38;2;140;140;140m",
    ]
    out = [" " for _ in range(TRAVEL_WORLD_WIDTH)]

    for x in range(road_start):
        src_x = min(TRAVEL_WORLD_WIDTH - 1, x + left_push)
        out[x] = cells[src_x]
    for x in range(road_end + 1, TRAVEL_WORLD_WIDTH):
        src_x = max(0, x - right_push)
        out[x] = cells[src_x]
    for x in range(road_start, road_end + 1):
        out[x] = f"{road_color}{road_rng.choice(road_chars)}{world.ANSI_RESET}"
    if road_start - 1 >= 0:
        if crossroad_phase is None:
            left_idx = road_rng.randrange(len(stone_glyphs))
            out[road_start - 1] = f"{stone_colors[left_idx]}{stone_glyphs[left_idx]}{world.ANSI_RESET}"
        else:
            out[road_start - 1] = f"{road_color}{road_rng.choice(road_chars)}{world.ANSI_RESET}"
    if road_end + 1 < TRAVEL_WORLD_WIDTH:
        if crossroad_phase is None:
            right_idx = road_rng.randrange(len(stone_glyphs))
            out[road_end + 1] = f"{stone_colors[right_idx]}{stone_glyphs[right_idx]}{world.ANSI_RESET}"
        else:
            out[road_end + 1] = f"{road_color}{road_rng.choice(road_chars)}{world.ANSI_RESET}"
    return out


def render(
    clouds: List[dict],
    ground_rows: List[str],
    zones: Dict[str, world.LayoutZone],
    sky_bottom_anchor: int,
    landscape_position: int,
    world_treeline_sprites: List[dict],
    border_treeline_sprites: List[dict],
    crossroad_house_sprites: List[dict],
    avatar_rows: List[List[str]],
    mushroom_rows: List[List[str]],
    mushroom_pose: dict,
    address_label: str,
    scene_label: str,
    center_object_id: str,
    camera_x: int,
) -> str:
    canvas = [[" " for _ in range(world.SCREEN_W)] for _ in range(world.SCREEN_H)]
    sky_zone = zones["sky_bg"]
    ground_zone = zones["ground_bg"]
    sky_layer_bottom = int(sky_bottom_anchor)
    sky_layer_top = sky_layer_bottom - (world.SKY_LAYER_HEIGHT - 1)
    hidden_ground_rows = world.landscape_hidden_ground_rows(landscape_position)
    ground_slice_start = world.landscape_ground_window_start(landscape_position)
    backside_drawables: List[dict] = []
    foreground_drawables: List[dict] = []

    def draw_world_scene_sprites(draw_backside: bool) -> None:
        target = backside_drawables if draw_backside else foreground_drawables
        blocked_border_tree_lines: set[int] = set()

        for sprite in crossroad_house_sprites:
            horizon_depth = max(0, int(sprite.get("horizon_depth", 0)))
            sprite_is_backside, house_y_base = world.horizon_depth_state(horizon_depth, hidden_ground_rows, ground_zone.y)
            if sprite_is_backside != draw_backside:
                continue
            house_y_base = max(ground_zone.y, house_y_base)
            blocked_border_tree_lines.add(house_y_base)
            blocked_border_tree_lines.add(house_y_base + 1)

        for sprite in world_treeline_sprites:
            rows = sprite.get("rows", [])
            if not isinstance(rows, list):
                continue
            x0 = int(sprite.get("x", 0)) - camera_x
            height = int(sprite.get("height", len(rows)))
            offset = min(world.TREELINE_ROWS - 1, max(0, int(sprite.get("anchor_offset", 0))))
            sprite_is_backside, y_base = world.horizon_depth_state(offset, hidden_ground_rows, ground_zone.y)
            if sprite_is_backside != draw_backside:
                continue
            y_base = max(ground_zone.y, y_base)
            y_offset = 1 if center_object_id in {"house", "house_02"} else 0
            y0 = y_base - max(0, height - 1) + y_offset
            target.append({
                "x": x0,
                "y": y0,
                "rows": rows,
                "base_y": y_base,
                "horizon_depth": offset,
                "z_bias": 10,
            })

        for sprite in border_treeline_sprites:
            rows = sprite.get("rows", [])
            if not isinstance(rows, list):
                continue
            width = int(sprite.get("width", len(rows[0]) if rows else 0))
            height = int(sprite.get("height", len(rows)))
            horizon_depth = max(0, int(sprite.get("horizon_depth", 0)))
            if world.crossroad_row_phase(horizon_depth) is not None:
                continue
            sprite_is_backside, y_base = world.horizon_depth_state(horizon_depth, hidden_ground_rows, ground_zone.y)
            if sprite_is_backside != draw_backside:
                continue
            y_base = max(ground_zone.y, y_base)
            if y_base in blocked_border_tree_lines:
                continue
            x0 = int(sprite.get("x", 0)) - camera_x
            y0 = y_base - max(0, height - 1)
            target.append({
                "x": x0,
                "y": y0,
                "rows": rows,
                "base_y": y_base,
                "horizon_depth": horizon_depth,
                "z_bias": 20,
            })

        for sprite in crossroad_house_sprites:
            rows = sprite.get("rows", [])
            if not isinstance(rows, list):
                continue
            side = str(sprite.get("side", "left"))
            side_slot = max(0, int(sprite.get("side_slot", 0)))
            side_offset = int(sprite.get("side_offset", 0))
            width = int(sprite.get("width", len(rows[0]) if rows else 0))
            height = int(sprite.get("height", len(rows)))
            horizon_depth = max(0, int(sprite.get("horizon_depth", 0)))
            sprite_is_backside, y_base = world.horizon_depth_state(horizon_depth, hidden_ground_rows, ground_zone.y)
            if sprite_is_backside != draw_backside:
                continue
            y_base = max(ground_zone.y, y_base)
            distance_from_horizon = max(0, y_base - ground_zone.y)
            road = road_geometry_for_horizon_distance(distance_from_horizon)
            side_gap = width + 12
            if side == "left":
                x0 = int(road.get("start", 0)) - width - 8 - (side_slot * side_gap) + side_offset - camera_x
            else:
                x0 = int(road.get("end", TRAVEL_WORLD_WIDTH - 1)) + 8 + (side_slot * side_gap) + side_offset - camera_x
            y0 = y_base - max(0, height - 1) + 1
            label = str(sprite.get("label", "")).strip()
            target.append({
                "x": x0,
                "y": y0,
                "rows": rows,
                "art_rows": sprite.get("art", []),
                "mask_rows": sprite.get("mask_rows", []),
                "house_sprite": True,
                "base_y": y_base,
                "horizon_depth": horizon_depth,
                "z_bias": 0,
                "label": label,
                "label_y": y0 + max(0, min(max(0, height - 1), 5) - 3) + 1,
                "label_x": (x0 + max(0, (width - len(label)) // 2) - 1) if label else x0,
            })

    for cloud in clouds:
        template = cloud["template"]
        x0 = int(cloud["x"]) - camera_x
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
    # Once objects pass the horizon, projected screen Y compresses and can invert
    # their relative near/far order. Use true world depth for the backside pass.
    backside_drawables.sort(key=lambda item: (int(item.get("horizon_depth", 0)), int(item.get("z_bias", 0))))
    for drawable in backside_drawables:
        rows = drawable.get("rows", [])
        if isinstance(rows, list) and drawable.get("house_sprite"):
            occupant_rows = mushroom_rows if str(drawable.get("label", "")).strip() == MUSHROOM_HOUSE_LABEL else []
            occupant_pose = mushroom_pose if occupant_rows else None
            draw_house_sprite(canvas, drawable, occupant_rows=occupant_rows, occupant_pose=occupant_pose)
        elif isinstance(rows, list):
            draw_sprite(canvas, rows, int(drawable.get("x", 0)), int(drawable.get("y", 0)))
        label = str(drawable.get("label", "")).strip()
        if label:
            draw_label(
                canvas,
                label,
                int(drawable.get("label_x", 0)),
                int(drawable.get("label_y", 0)),
                color="\x1b[38;2;245;245;245m",
            )

    for i in range(ground_zone.height):
        y = ground_zone.y + i
        src_index = ground_slice_start + i
        src = ground_rows[src_index] if 0 <= src_index < len(ground_rows) else ""
        cells = world.ansi_line_to_cells(src, TRAVEL_WORLD_WIDTH)
        road_width = world.road_width_for_horizon_distance(i)
        crossroad_phase = world.crossroad_row_phase(src_index)
        row_cells = overlay_crossroad_row(cells, src_index, 12051701 + src_index)
        row_cells = build_road_pushed_row(row_cells, road_width, 9051701 + src_index, crossroad_phase=crossroad_phase)
        viewport_cells = row_cells[camera_x:camera_x + world.SCREEN_W]
        for x, cell in enumerate(viewport_cells):
            if cell != " ":
                canvas[y][x] = cell

    draw_world_scene_sprites(draw_backside=False)

    avatar = build_avatar_placement(avatar_rows)
    foreground_drawables.append({
        "x": int(avatar["x"]),
        "y": int(avatar["y"]),
        "rows": avatar_rows,
        "base_y": int(avatar["y"]) + max(0, int(avatar["height"]) - 1),
        "z_bias": 15,
    })

    foreground_drawables.sort(key=lambda item: (int(item.get("base_y", 0)), int(item.get("z_bias", 0)), int(item.get("y", 0)), int(item.get("x", 0))))
    for drawable in foreground_drawables:
        rows = drawable.get("rows", [])
        if isinstance(rows, list) and drawable.get("house_sprite"):
            occupant_rows = mushroom_rows if str(drawable.get("label", "")).strip() == MUSHROOM_HOUSE_LABEL else []
            occupant_pose = mushroom_pose if occupant_rows else None
            draw_house_sprite(canvas, drawable, occupant_rows=occupant_rows, occupant_pose=occupant_pose)
        elif isinstance(rows, list):
            draw_sprite(canvas, rows, int(drawable.get("x", 0)), int(drawable.get("y", 0)))
        label = str(drawable.get("label", "")).strip()
        if label:
            draw_label(
                canvas,
                label,
                int(drawable.get("label_x", 0)),
                int(drawable.get("label_y", 0)),
                color="\x1b[38;2;245;245;245m",
            )

    header = f"[travel][scene:{scene_label}][address:{address_label}]"
    controls = "[up/down travel][left/right strafe][a avatar][c scene][q quit]"
    if len(header) <= world.SCREEN_W:
        draw_label(canvas, header, max(0, (world.SCREEN_W - len(header)) // 2), 0)
    if len(controls) <= world.SCREEN_W:
        draw_label(canvas, controls, max(0, (world.SCREEN_W - len(controls)) // 2), world.SCREEN_H - 1)

    return "\n".join("".join(row) for row in canvas)


def main() -> None:
    base = os.getcwd()
    objects = world.load_json(os.path.join(base, "legacy", "data", "objects.json"))
    colors = world.load_json(os.path.join(base, "legacy", "data", "colors.json"))
    opponents = world.load_json(os.path.join(base, "legacy", "data", "opponents.json"))
    players = world.load_json(os.path.join(base, "legacy", "data", "players.json"))
    if not isinstance(objects, dict):
        raise RuntimeError("objects.json is not a JSON object")
    if not isinstance(colors, dict):
        raise RuntimeError("colors.json is not a JSON object")
    if not isinstance(opponents, dict):
        raise RuntimeError("opponents.json is not a JSON object")
    if not isinstance(players, dict):
        raise RuntimeError("players.json is not a JSON object")

    color_codes = world._build_color_codes(colors)
    templates = world.cloud_templates(objects)
    if not templates:
        raise RuntimeError("No cloud_* objects found in objects.json")

    avatar_ids = [pid for pid in ("player_01", "player_02") if isinstance(players.get(pid), dict)]
    if not avatar_ids:
        avatar_ids = [pid for pid, entry in players.items() if isinstance(entry, dict)]
    if not avatar_ids:
        raise RuntimeError("No playable avatars found in players.json")

    avatar_index = 0
    landscape_position = START_TRAVEL_POSITION
    target_landscape_position = landscape_position
    zones = world.build_scene_zones(sky_rows=world.landscape_sky_rows(landscape_position))
    sky_bottom_anchor = world.sky_bottom_anchor_for_position(landscape_position)
    avatar_facing = "front"
    walk_frame_index = 0
    walk_frame_accum = 0.0
    idle_reset_accum = 0.0
    was_avatar_moving = False
    avatar_rows = world.build_player_frame(players, avatar_ids[avatar_index], color_codes, avatar_facing, "idle")
    mushroom_rows = world.build_opponent_sprite(opponents, "mushroom_baby", color_codes)
    camera_x = clamp_camera_to_road(starting_camera_x(), avatar_rows, zones, landscape_position)
    target_camera_x = camera_x
    clouds = spawn_clouds_wide(templates)
    ground_rows = build_ground_rows_wide(
        row_count=world.LANDSCAPE_TOTAL_GROUND_ROWS,
        objects_data=objects,
        color_codes=color_codes,
        pebble_density=0.07,
    )
    scene_index = 0
    scene_label, center_object_id = WORLD_MODELS[scene_index]
    world_treeline_sprites = [recenter_sprite_x(sprite) for sprite in world.build_world_treeline_sprites(objects, colors, center_object_id)]
    border_treeline_sprites = [recenter_border_sprite_x(sprite) for sprite in world.build_border_treeline_sprites(objects, colors)]
    crossroad_house_sprites = world.build_crossroad_house_sprites(objects, colors)
    target_house = next((sprite for sprite in crossroad_house_sprites if str(sprite.get("label", "")).strip() == MUSHROOM_HOUSE_LABEL), None)
    target_art_rows = target_house.get("art", []) if isinstance(target_house, dict) else []
    target_mask_rows = target_house.get("mask_rows", []) if isinstance(target_house, dict) else []
    mushroom_pose = (
        default_house_occupant_pose(target_art_rows, target_mask_rows, mushroom_rows)
        if isinstance(target_art_rows, list) and isinstance(target_mask_rows, list)
        else {"x0": 0, "floor_offset": 1}
    )
    mushroom_motion_rng = random.Random()
    mushroom_motion_accum = 0.0

    posix_stdin_restore: tuple[int, list] | None = None
    if os.name != "nt" and sys.stdin.isatty():
        try:
            import termios
            import tty

            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            raw = termios.tcgetattr(fd)
            raw[3] &= ~termios.ECHO
            termios.tcsetattr(fd, termios.TCSADRAIN, raw)
            posix_stdin_restore = (fd, old)
        except Exception:
            posix_stdin_restore = None

    print(world.ANSI_HIDE_CURSOR + world.ANSI_CLEAR, end="", flush=True)
    try:
        last_tick = time.monotonic()
        camera_accum = 0.0
        while True:
            now = time.monotonic()
            dt = max(0.0, min(0.2, now - last_tick))
            last_tick = now

            if landscape_position != target_landscape_position:
                camera_accum += dt
                while landscape_position != target_landscape_position and camera_accum >= CAMERA_STEP_SECONDS:
                    camera_accum -= CAMERA_STEP_SECONDS
                    direction = 1 if target_landscape_position > landscape_position else -1
                    landscape_position += direction
                    if landscape_position < world.LANDSCAPE_STEP_ROWS:
                        landscape_position = world.LANDSCAPE_TOTAL_GROUND_ROWS
                    if landscape_position > world.LANDSCAPE_TOTAL_GROUND_ROWS:
                        landscape_position = world.LANDSCAPE_STEP_ROWS
                    zones = world.build_scene_zones(sky_rows=world.landscape_sky_rows(landscape_position))
                    sky_bottom_anchor = world.sky_bottom_anchor_for_position(landscape_position)
            else:
                camera_accum = 0.0

            if camera_x != target_camera_x:
                direction = 1 if target_camera_x > camera_x else -1
                camera_x += direction * min(SIDE_STEP_COLUMNS, abs(target_camera_x - camera_x))
            mushroom_motion_accum += dt
            while mushroom_motion_accum >= 1.0:
                mushroom_motion_accum -= 1.0
                if isinstance(target_art_rows, list) and isinstance(target_mask_rows, list) and target_art_rows and target_mask_rows:
                    mushroom_pose = step_house_occupant_pose(target_art_rows, target_mask_rows, mushroom_rows, mushroom_pose, mushroom_motion_rng)
            for cloud in clouds:
                speed = float(cloud.get("speed", 1.0))
                cloud["x"] = float(cloud.get("x", 0.0)) - (speed * dt)
                width = int(cloud["template"]["width"])
                if cloud["x"] + width < 0:
                    cloud["x"] = TRAVEL_WORLD_WIDTH + (cloud["x"] + width)

            key = world.read_key_nonblocking()
            if key == "q":
                break
            if key == "up":
                avatar_facing = "back"
                candidate = target_landscape_position - 1
                if candidate < world.LANDSCAPE_STEP_ROWS:
                    candidate = world.LANDSCAPE_TOTAL_GROUND_ROWS
                candidate_zones = world.build_scene_zones(sky_rows=world.landscape_sky_rows(candidate))
                if is_camera_on_walkable_surface(camera_x, avatar_rows, candidate_zones, candidate):
                    target_landscape_position = candidate
            if key == "down":
                avatar_facing = "front"
                candidate = target_landscape_position + 1
                if candidate > world.LANDSCAPE_TOTAL_GROUND_ROWS:
                    candidate = world.LANDSCAPE_STEP_ROWS
                candidate_zones = world.build_scene_zones(sky_rows=world.landscape_sky_rows(candidate))
                if is_camera_on_walkable_surface(camera_x, avatar_rows, candidate_zones, candidate):
                    target_landscape_position = candidate
            if key == "left":
                candidate = max(0, target_camera_x - SIDE_STEP_COLUMNS)
                if is_camera_on_walkable_surface(candidate, avatar_rows, zones, landscape_position):
                    target_camera_x = candidate
            if key == "right":
                candidate = min(TRAVEL_WORLD_WIDTH - world.SCREEN_W, target_camera_x + SIDE_STEP_COLUMNS)
                if is_camera_on_walkable_surface(candidate, avatar_rows, zones, landscape_position):
                    target_camera_x = candidate
            if key == "a":
                avatar_index = (avatar_index + 1) % len(avatar_ids)
                avatar_rows = world.build_player_frame(players, avatar_ids[avatar_index], color_codes, avatar_facing, "idle")
                target_camera_x = clamp_camera_to_road(target_camera_x, avatar_rows, zones, landscape_position)
                camera_x = clamp_camera_to_road(camera_x, avatar_rows, zones, landscape_position)
                walk_frame_index = 0
                walk_frame_accum = 0.0
                idle_reset_accum = 0.0
                was_avatar_moving = False
            if key == "c":
                scene_index = (scene_index + 1) % len(WORLD_MODELS)
                scene_label, center_object_id = WORLD_MODELS[scene_index]
                world_treeline_sprites = [recenter_sprite_x(sprite) for sprite in world.build_world_treeline_sprites(objects, colors, center_object_id)]
                border_treeline_sprites = [recenter_border_sprite_x(sprite) for sprite in world.build_border_treeline_sprites(objects, colors)]
                crossroad_house_sprites = world.build_crossroad_house_sprites(objects, colors)
                target_house = next((sprite for sprite in crossroad_house_sprites if str(sprite.get("label", "")).strip() == MUSHROOM_HOUSE_LABEL), None)
                target_art_rows = target_house.get("art", []) if isinstance(target_house, dict) else []
                target_mask_rows = target_house.get("mask_rows", []) if isinstance(target_house, dict) else []
                if isinstance(target_art_rows, list) and isinstance(target_mask_rows, list) and target_art_rows and target_mask_rows:
                    mushroom_pose = clamp_house_occupant_pose(target_art_rows, target_mask_rows, mushroom_rows, mushroom_pose)
            avatar_is_moving = (camera_x != target_camera_x) or (landscape_position != target_landscape_position)
            if avatar_is_moving:
                if not was_avatar_moving:
                    walk_frame_index = 1
                    walk_frame_accum = 0.0
                idle_reset_accum = 0.0
                walk_frame_accum += dt
                while walk_frame_accum >= WALK_FRAME_STEP_SECONDS:
                    walk_frame_accum -= WALK_FRAME_STEP_SECONDS
                    walk_frame_index = (walk_frame_index + 1) % len(WALK_FRAME_SEQUENCE)
            else:
                walk_frame_accum = 0.0
                idle_reset_accum += dt
                if idle_reset_accum >= WALK_RESET_IDLE_SECONDS:
                    walk_frame_index = 0
            avatar_phase = WALK_FRAME_SEQUENCE[walk_frame_index]
            was_avatar_moving = avatar_is_moving
            avatar_rows = world.build_player_frame(players, avatar_ids[avatar_index], color_codes, avatar_facing, avatar_phase)

            frame = render(
                clouds=clouds,
                ground_rows=ground_rows,
                zones=zones,
                sky_bottom_anchor=sky_bottom_anchor,
                landscape_position=landscape_position,
                world_treeline_sprites=world_treeline_sprites,
                border_treeline_sprites=border_treeline_sprites,
                crossroad_house_sprites=crossroad_house_sprites,
                avatar_rows=avatar_rows,
                mushroom_rows=mushroom_rows,
                mushroom_pose=mushroom_pose,
                address_label=current_address_label(landscape_position),
                scene_label=scene_label,
                center_object_id=center_object_id,
                camera_x=camera_x,
            )
            print(world.ANSI_HOME + frame, end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        if posix_stdin_restore is not None:
            try:
                import termios

                fd, old = posix_stdin_restore
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except Exception:
                pass
        print(world.ANSI_SHOW_CURSOR + world.ANSI_RESET)


if __name__ == "__main__":
    main()
