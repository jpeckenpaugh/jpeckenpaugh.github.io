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
SIDE_STEP_SECONDS = 0.01
SIDE_TARGET_COLUMNS = 2
SIDE_STEP_COLUMNS = 1
TRAVEL_WORLD_WIDTH = 1100
WORLD_MODELS = list(world.WORLD_SCENE_VARIANTS)
AVE_A_MUSHROOM_HOUSE_LABELS = [f"[#{house_number} Ave A]" for house_number in range(1, 11)]
AVE_A_FAIRY_HOUSE_LABELS = [f"[#{house_number} Ave A]" for house_number in range(11, 21)]
HOUSE_10_VIAL_LABEL = "[#10 Ave A]"
FAIRY_FLAP_SEQUENCE = ["primary", "a", "b", "a", "primary"]
FAIRY_FLAP_STEP_SECONDS = 0.12
MUSHROOM_STEP_POSE_SECONDS = 0.18
WALKING_MUSHROOM_SEQUENCE = ["a", "primary", "b", "primary"]
WALKING_MUSHROOM_STEP_SECONDS = 0.20
WALKING_MUSHROOM_SPEED = 4.0
WALKING_MUSHROOM_BURROW_STEP_SECONDS = 0.14
WALKING_MUSHROOM_FROWN_SECONDS = 1.0
WALKING_MUSHROOM_BURROW_BLINK_SECONDS = 1.0
WALKING_MUSHROOM_HIDE_SECONDS = 5.0
WALKING_MUSHROOM_EMERGE_HOLD_SECONDS = 1.0
WALKING_MUSHROOM_EMERGE_BLINK_SECONDS = 1.0
WALKING_FAIRY_SEQUENCE = ["primary", "a", "b", "a", "primary"]
WALKING_FAIRY_STEP_SECONDS = 0.12
WALKING_FAIRY_SPEED = 8.0
WALKING_FAIRY_SCARED_SPEED = 32.0
WALKING_FAIRY_FROWN_SECONDS = 1.0
BLINK_INTERVAL_MIN_SECONDS = 4.0
BLINK_INTERVAL_MAX_SECONDS = 6.0
BLINK_STEP_SECONDS = 0.08
CROW_FLY_SEQUENCE = ["a", "b", "c", "b"]
CROW_FLY_STEP_SECONDS = 0.10
CROW_FLY_SPEED = 52.0
CROW_FLY_VERTICAL_COMPENSATION = 2
CROW_RELOCATE_MIN_SECONDS = 10.0
CROW_RELOCATE_MAX_SECONDS = 15.0
CROW_HIT_HIDE_SECONDS = 60.0
CROW_MAX_HITS_BEFORE_HIDE = 3
CROW_MIN_HIT_RELOCATE_DISTANCE = 10
WALK_FRAME_SEQUENCE = ["idle", "step_a", "idle", "step_b"]
WALK_FRAME_STEP_SECONDS = 0.5
WALK_RESET_IDLE_SECONDS = 0.5
COLLECTIBLE_PEBBLE_DENSITY = 0.035
THROWN_PEBBLE_SPEED_X = 56.0
THROWN_PEBBLE_SPEED_Y = 28.0
THROW_COOLDOWN_SECONDS = 1.0
THROW_POSE_SECONDS = 0.18
DARK_GOLD_PEBBLE_COLORS = [
    "\x1b[38;2;224;186;72m",
    "\x1b[38;2;198;156;48m",
]


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
    bounds = all_window_component_bounds(mask_rows)
    return bounds[0] if bounds else None


def all_window_component_bounds(mask_rows: List[str]) -> List[tuple[int, int, int, int]]:
    coords: List[tuple[int, int]] = []
    for y, row in enumerate(mask_rows):
        for x, ch in enumerate(str(row)):
            if ch == "?":
                coords.append((x, y))
    if not coords:
        return []
    coord_set = set(coords)
    out: List[tuple[int, int, int, int]] = []
    while coord_set:
        seed = min(coord_set, key=lambda item: (item[0], item[1]))
        stack = [seed]
        component: List[tuple[int, int]] = []
        coord_set.remove(seed)
        while stack:
            x, y = stack.pop()
            component.append((x, y))
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if (nx, ny) in coord_set:
                    coord_set.remove((nx, ny))
                    stack.append((nx, ny))
        min_x = min(x for x, _ in component)
        max_x = max(x for x, _ in component)
        min_y = min(y for _, y in component)
        max_y = max(y for _, y in component)
        out.append((min_x, max_x, min_y, max_y))
    out.sort(key=lambda item: (item[0], item[2]))
    return out


def all_window_bounds(mask_rows: List[str]) -> tuple[int, int, int, int] | None:
    bounds = all_window_component_bounds(mask_rows)
    if not bounds:
        return None
    min_x = min(bound[0] for bound in bounds)
    max_x = max(bound[1] for bound in bounds)
    min_y = min(bound[2] for bound in bounds)
    max_y = max(bound[3] for bound in bounds)
    return (min_x, max_x, min_y, max_y)


def centered_window_object_pose(mask_rows: List[str], object_rows: List[List[str]], window_index: int = 0) -> dict | None:
    bounds = all_window_component_bounds(mask_rows)
    if window_index < 0 or window_index >= len(bounds):
        return None
    min_x, max_x, _min_y, max_y = bounds[window_index]
    obj_h = len(object_rows)
    obj_w = max((len(row) for row in object_rows), default=0)
    return {
        "x0": min_x + max(0, ((max_x - min_x + 1) - obj_w) // 2),
        "y0": max_y - max(0, obj_h - 1),
    }


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
    distance = rng.randint(1, 3)
    if direction == "left":
        updated["x0"] = int(updated.get("x0", 0)) - distance
    elif direction == "right":
        updated["x0"] = int(updated.get("x0", 0)) + distance
    elif direction == "up":
        updated["floor_offset"] = int(updated.get("floor_offset", 0)) + distance
    else:
        updated["floor_offset"] = int(updated.get("floor_offset", 0)) - distance
    updated = clamp_house_occupant_pose(art_rows, mask_rows, occupant_rows, updated)
    return updated if can_place_house_occupant_pose(art_rows, occupant_rows, updated) else pose


def draw_house_sprite(
    canvas: List[List[str]],
    drawable: dict,
    occupant_rows: List[List[str]] | None = None,
    occupant_pose: dict | None = None,
    window_objects: List[dict] | None = None,
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
    if isinstance(window_objects, list):
        for item in window_objects:
            item_rows = item.get("rows", [])
            if isinstance(item_rows, list):
                draw_sprite(
                    canvas,
                    item_rows,
                    x0 + int(item.get("x0", 0)),
                    y0 + int(item.get("y0", 0)),
                )


def mushroom_frame_label_for_facing(facing: str, phase: str) -> str:
    normalized = str(facing).strip().lower()
    if normalized == "back":
        return "back_primary" if phase == "primary" else f"back_{phase}"
    return phase


def make_blink_state(seed: int, open_choices: List[str]) -> dict:
    rng = random.Random(seed)
    choices = [str(choice)[:1] for choice in open_choices if str(choice)]
    if not choices:
        choices = ["◉"]
    return {
        "rng": rng,
        "open_eye": choices[rng.randrange(len(choices))],
        "phase": "open",
        "phase_timer": 0.0,
        "blinks_remaining": 0,
        "next_blink": rng.uniform(BLINK_INTERVAL_MIN_SECONDS, BLINK_INTERVAL_MAX_SECONDS),
    }


def update_blink_state(state: dict, dt: float) -> dict:
    updated = dict(state)
    rng = updated.get("rng")
    if not isinstance(rng, random.Random):
        rng = random.Random(0)
        updated["rng"] = rng
    phase = str(updated.get("phase", "open"))
    if phase == "open" and int(updated.get("blinks_remaining", 0)) <= 0:
        updated["next_blink"] = float(updated.get("next_blink", BLINK_INTERVAL_MIN_SECONDS)) - dt
        if float(updated.get("next_blink", 0.0)) <= 0.0:
            updated["blinks_remaining"] = rng.choice([1, 2])
            updated["phase"] = "half_1"
            updated["phase_timer"] = BLINK_STEP_SECONDS
        return updated

    updated["phase_timer"] = float(updated.get("phase_timer", 0.0)) - dt
    if float(updated.get("phase_timer", 0.0)) > 0.0:
        return updated
    phase = str(updated.get("phase", "open"))
    if phase == "half_1":
        updated["phase"] = "closed"
        updated["phase_timer"] = BLINK_STEP_SECONDS
    elif phase == "closed":
        updated["phase"] = "half_2"
        updated["phase_timer"] = BLINK_STEP_SECONDS
    elif phase == "half_2":
        remaining = max(0, int(updated.get("blinks_remaining", 1)) - 1)
        updated["blinks_remaining"] = remaining
        if remaining > 0:
            updated["phase"] = "half_1"
            updated["phase_timer"] = BLINK_STEP_SECONDS
        else:
            updated["phase"] = "open"
            updated["phase_timer"] = 0.0
            updated["next_blink"] = rng.uniform(BLINK_INTERVAL_MIN_SECONDS, BLINK_INTERVAL_MAX_SECONDS)
    else:
        updated["phase"] = "open"
        updated["phase_timer"] = 0.0
        updated["blinks_remaining"] = 0
        updated["next_blink"] = rng.uniform(BLINK_INTERVAL_MIN_SECONDS, BLINK_INTERVAL_MAX_SECONDS)
    return updated


def _visible_cell_glyph(cell: str) -> str:
    text = str(cell)
    idx = 0
    while idx < len(text):
        if text[idx] == "\x1b":
            end = text.find("m", idx)
            if end == -1:
                break
            idx = end + 1
            continue
        return text[idx]
    return ""


def _replace_visible_cell_glyph(cell: str, glyph: str) -> str:
    text = str(cell)
    idx = 0
    while idx < len(text):
        if text[idx] == "\x1b":
            end = text.find("m", idx)
            if end == -1:
                return text
            idx = end + 1
            continue
        return text[:idx] + str(glyph)[:1] + text[idx + 1:]
    return text


def apply_blink_to_rows(rows: List[List[str]], blink_state: dict | None) -> List[List[str]]:
    if not isinstance(rows, list) or not rows or not isinstance(blink_state, dict):
        return rows
    phase = str(blink_state.get("phase", "open"))
    if phase == "open":
        target = str(blink_state.get("open_eye", "◉"))[:1] or "◉"
    elif phase in {"half_1", "half_2"}:
        target = "◓"
    elif phase == "closed":
        target = "●"
    else:
        target = str(blink_state.get("open_eye", "◉"))[:1] or "◉"
    out: List[List[str]] = []
    for row in rows:
        new_row: List[str] = []
        for cell in row:
            glyph = _visible_cell_glyph(cell)
            if glyph in {"◎", "◉", "◓", "●"}:
                new_row.append(_replace_visible_cell_glyph(cell, target))
            else:
                new_row.append(cell)
        out.append(new_row)
    return out


def apply_eye_glyph_to_rows(rows: List[List[str]], target: str) -> List[List[str]]:
    if not isinstance(rows, list) or not rows:
        return rows
    glyph_target = str(target)[:1] or "◓"
    out: List[List[str]] = []
    for row in rows:
        new_row: List[str] = []
        for cell in row:
            glyph = _visible_cell_glyph(cell)
            if glyph in {"◎", "◉", "◓", "●"}:
                new_row.append(_replace_visible_cell_glyph(cell, glyph_target))
            else:
                new_row.append(cell)
        out.append(new_row)
    return out


def apply_forced_double_blink_rows(rows: List[List[str]], total_seconds: float, remaining_seconds: float) -> List[List[str]]:
    if not isinstance(rows, list) or not rows:
        return rows
    total = max(0.001, float(total_seconds))
    remaining = max(0.0, min(total, float(remaining_seconds)))
    progress = 1.0 - (remaining / total)
    phase_index = min(4, max(0, int(progress * 5.0)))
    target = ["◓", "●", "◓", "●", "◓"][phase_index]
    return apply_eye_glyph_to_rows(rows, target)


def make_crow_blink_state(seed: int) -> dict:
    rng = random.Random(seed)
    return {
        "rng": rng,
        "phase": "open",
        "phase_timer": 0.0,
        "blinks_remaining": 0,
        "next_blink": rng.uniform(BLINK_INTERVAL_MIN_SECONDS, BLINK_INTERVAL_MAX_SECONDS),
    }


def update_crow_blink_state(state: dict, dt: float) -> dict:
    updated = dict(state)
    rng = updated.get("rng")
    if not isinstance(rng, random.Random):
        rng = random.Random(0)
        updated["rng"] = rng
    phase = str(updated.get("phase", "open"))
    if phase == "open" and int(updated.get("blinks_remaining", 0)) <= 0:
        updated["next_blink"] = float(updated.get("next_blink", BLINK_INTERVAL_MIN_SECONDS)) - dt
        if float(updated.get("next_blink", 0.0)) <= 0.0:
            updated["blinks_remaining"] = rng.choice([1, 2])
            updated["phase"] = "closed"
            updated["phase_timer"] = BLINK_STEP_SECONDS
        return updated
    updated["phase_timer"] = float(updated.get("phase_timer", 0.0)) - dt
    if float(updated.get("phase_timer", 0.0)) > 0.0:
        return updated
    phase = str(updated.get("phase", "open"))
    if phase == "closed":
        remaining = max(0, int(updated.get("blinks_remaining", 1)) - 1)
        updated["blinks_remaining"] = remaining
        if remaining > 0:
            updated["phase"] = "open_between"
            updated["phase_timer"] = BLINK_STEP_SECONDS
        else:
            updated["phase"] = "open"
            updated["phase_timer"] = 0.0
            updated["next_blink"] = rng.uniform(BLINK_INTERVAL_MIN_SECONDS, BLINK_INTERVAL_MAX_SECONDS)
    elif phase == "open_between":
        updated["phase"] = "closed"
        updated["phase_timer"] = BLINK_STEP_SECONDS
    else:
        updated["phase"] = "open"
        updated["phase_timer"] = 0.0
        updated["blinks_remaining"] = 0
        updated["next_blink"] = rng.uniform(BLINK_INTERVAL_MIN_SECONDS, BLINK_INTERVAL_MAX_SECONDS)
    return updated


def apply_crow_blink_to_rows(rows: List[List[str]], blink_state: dict | None) -> List[List[str]]:
    if not isinstance(rows, list) or not rows or not isinstance(blink_state, dict):
        return rows
    target = "^" if str(blink_state.get("phase", "open")) == "closed" else "\""
    out: List[List[str]] = []
    for row in rows:
        new_row: List[str] = []
        for cell in row:
            glyph = _visible_cell_glyph(cell)
            if glyph in {"\"", "^"}:
                new_row.append(_replace_visible_cell_glyph(cell, target))
            else:
                new_row.append(cell)
        out.append(new_row)
    return out


def sprite_projection_for_scene(
    sprite: dict,
    camera_x: int,
    hidden_ground_rows: int,
    ground_zone: world.LayoutZone,
    center_object_id: str,
) -> tuple[int, int, bool] | None:
    rows = sprite.get("rows", [])
    if not isinstance(rows, list):
        return None
    width = int(sprite.get("width", len(rows[0]) if rows else 0))
    height = int(sprite.get("height", len(rows)))
    if "anchor_offset" in sprite:
        offset = min(world.TREELINE_ROWS - 1, max(0, int(sprite.get("anchor_offset", 0))))
        sprite_is_backside, y_base = world.horizon_depth_state(offset, hidden_ground_rows, ground_zone.y)
        y_base = max(ground_zone.y, y_base)
        y_offset = 1 if center_object_id in {"house", "house_02"} else 0
        x0 = int(sprite.get("x", 0)) - camera_x
        y0 = y_base - max(0, height - 1) + y_offset
        return x0, y0, sprite_is_backside
    horizon_depth = max(0, int(sprite.get("horizon_depth", 0)))
    if world.crossroad_row_phase(horizon_depth) is not None:
        return None
    sprite_is_backside, y_base = world.horizon_depth_state(horizon_depth, hidden_ground_rows, ground_zone.y)
    y_base = max(ground_zone.y, y_base)
    road = road_geometry_for_horizon_distance(max(0, y_base - ground_zone.y))
    road_anchor = str(sprite.get("road_anchor", "")).strip()
    if road_anchor == "start":
        x0 = int(road.get("start", 0)) + int(sprite.get("road_offset", 0)) - camera_x
    elif road_anchor == "end":
        x0 = int(road.get("end", TRAVEL_WORLD_WIDTH - 1)) + int(sprite.get("road_offset", 0)) - camera_x
    elif "side" in sprite:
        side = str(sprite.get("side", "left"))
        side_slot = max(0, int(sprite.get("side_slot", 0)))
        side_offset = int(sprite.get("side_offset", 0))
        side_gap = width + 12
        if side == "left":
            x0 = int(road.get("start", 0)) - width - 8 - (side_slot * side_gap) + side_offset - camera_x
        else:
            x0 = int(road.get("end", TRAVEL_WORLD_WIDTH - 1)) + 8 + (side_slot * side_gap) + side_offset - camera_x
    else:
        x0 = int(sprite.get("x", 0)) - camera_x
    y0 = y_base - max(0, height - 1)
    if str(sprite.get("label", "")).strip():
        y0 += 1
    return x0, y0, sprite_is_backside


def sprite_top_left_for_scene(
    sprite: dict,
    camera_x: int,
    hidden_ground_rows: int,
    ground_zone: world.LayoutZone,
    center_object_id: str,
) -> tuple[int, int] | None:
    projection = sprite_projection_for_scene(sprite, camera_x, hidden_ground_rows, ground_zone, center_object_id)
    if projection is None:
        return None
    x0, y0, backside = projection
    if backside:
        return None
    return x0, y0


def visible_crow_perches(
    world_treeline_sprites: List[dict],
    border_treeline_sprites: List[dict],
    crossroad_house_sprites: List[dict],
    zones: Dict[str, world.LayoutZone],
    landscape_position: int,
    center_object_id: str,
    camera_x: int,
    crow_width: int,
    crow_height: int,
) -> List[dict]:
    hidden_ground_rows = world.landscape_hidden_ground_rows(landscape_position)
    ground_zone = zones["ground_bg"]
    out: List[dict] = []
    blocked_tree_lines: set[int] = set()
    for house in crossroad_house_sprites:
        rows = house.get("rows", [])
        if not isinstance(rows, list):
            continue
        label = str(house.get("label", "")).strip()
        if not label:
            continue
        projection = sprite_projection_for_scene(house, camera_x, hidden_ground_rows, ground_zone, center_object_id)
        if projection is None:
            continue
        _x0, y0, backside = projection
        if backside:
            continue
        height = int(house.get("height", len(rows)))
        base_y = y0 + max(0, height - 1)
        blocked_tree_lines.add(base_y)
        blocked_tree_lines.add(base_y + 1)
    roadside_tree_sprites = [
        sprite
        for sprite in crossroad_house_sprites
        if bool(sprite.get("perchable_tree"))
    ]
    tree_perch_sources = [
        sprite
        for sprite in list(world_treeline_sprites) + list(border_treeline_sprites) + roadside_tree_sprites
        if bool(sprite.get("perchable_tree"))
    ]
    for sprite in tree_perch_sources:
        rows = sprite.get("rows", [])
        if not isinstance(rows, list):
            continue
        top_left = sprite_top_left_for_scene(sprite, camera_x, hidden_ground_rows, ground_zone, center_object_id)
        if top_left is None:
            continue
        x0, y0 = top_left
        width = int(sprite.get("width", len(rows[0]) if rows else 0))
        height = int(sprite.get("height", len(rows)))
        base_y = y0 + max(0, height - 1)
        if base_y in blocked_tree_lines:
            continue
        if x0 + width <= 0 or x0 >= world.SCREEN_W:
            continue
        if y0 + height <= 0 or y0 >= world.SCREEN_H:
            continue
        local_x = max(0, (width // 2) - (crow_width // 2))
        local_y = max(0, min(2, height // 4))
        perch_x = x0 + local_x
        perch_y = y0 + local_y
        if perch_x < 0 or perch_x + crow_width > world.SCREEN_W:
            continue
        if perch_y < 0 or perch_y >= world.SCREEN_H:
            continue
        out.append({
            "id": f"tree:{id(sprite)}",
            "kind": "tree",
            "sprite": sprite,
            "local_x": local_x,
            "local_y": local_y,
            "perch_x": perch_x,
            "perch_y": perch_y,
        })
    for house in crossroad_house_sprites:
        rows = house.get("rows", [])
        if not isinstance(rows, list):
            continue
        label = str(house.get("label", "")).strip()
        if not label or not bool(house.get("perchable_house", bool(label))):
            continue
        projection = sprite_projection_for_scene(house, camera_x, hidden_ground_rows, ground_zone, center_object_id)
        if projection is None:
            continue
        x0, y0, backside = projection
        if backside:
            continue
        width = int(house.get("width", len(rows[0]) if rows else 0))
        height = int(house.get("height", len(rows)))
        if x0 + width <= 0 or x0 >= world.SCREEN_W:
            continue
        if y0 + height <= 0 or y0 >= world.SCREEN_H:
            continue
        foot_row_targets = [row for row in (0, 1) if row < height]
        for foot_row in foot_row_targets:
            local_y = foot_row - max(0, crow_height - 1)
            for local_x in range(0, max(1, width - crow_width + 1), max(2, crow_width)):
                perch_x = x0 + local_x
                perch_y = y0 + local_y
                if perch_x < 0 or perch_x + crow_width > world.SCREEN_W:
                    continue
                if perch_y < 0 or perch_y >= world.SCREEN_H:
                    continue
                out.append({
                    "id": f"house:{label}:{local_x}:{local_y}",
                    "kind": "house",
                    "sprite": house,
                    "local_x": local_x,
                    "local_y": local_y,
                    "perch_x": perch_x,
                    "perch_y": perch_y,
                })
    return out


def occupied_perch_ids(crow_states: List[dict], exclude_index: int | None = None) -> set[str]:
    occupied: set[str] = set()
    for idx, crow in enumerate(crow_states):
        if exclude_index is not None and idx == exclude_index:
            continue
        if str(crow.get("mode", "")) == "hidden":
            continue
        perch = crow.get("perch", {})
        perch_id = str(perch.get("id", "")).strip() if isinstance(perch, dict) else ""
        if perch_id:
            occupied.add(perch_id)
    return occupied


def perch_screen_position(
    perch: dict,
    zones: Dict[str, world.LayoutZone],
    landscape_position: int,
    center_object_id: str,
    camera_x: int,
) -> tuple[float, float] | None:
    sprite = perch.get("sprite")
    if not isinstance(sprite, dict):
        return None
    hidden_ground_rows = world.landscape_hidden_ground_rows(landscape_position)
    ground_zone = zones["ground_bg"]
    projection = sprite_projection_for_scene(sprite, camera_x, hidden_ground_rows, ground_zone, center_object_id)
    if projection is None:
        return None
    x0, y0, backside = projection
    return (
        float(x0 + int(perch.get("local_x", 0))),
        float(y0 + int(perch.get("local_y", 0))),
    )


def spawn_intro_crows(
    perches: List[dict],
    crow_frames: Dict[str, List[List[str]]],
) -> List[dict]:
    resting_rows = crow_frames.get("resting", [])
    if not resting_rows or not perches:
        return []
    crow_width = max((len(row) for row in resting_rows), default=0)
    states: List[dict] = []
    left_perches = [p for p in perches if float(p.get("perch_x", 0)) < (world.SCREEN_W / 2)]
    right_perches = [p for p in perches if float(p.get("perch_x", 0)) >= (world.SCREEN_W / 2)]
    rng_left = random.Random(7317)
    rng_right = random.Random(7318)
    if left_perches:
        perch = left_perches[rng_left.randrange(len(left_perches))]
        start_x = float(-crow_width - 4)
        start_y = float(max(0, int(perch["perch_y"]) - 4))
        facing = resolve_crow_facing(start_x, start_y, float(perch.get("perch_x", start_x)), float(perch.get("perch_y", start_y)), {})
        states.append({
            "x": start_x,
            "y": start_y,
            "perch": perch,
            "mode": "flying",
            "anim_index": 0,
            "anim_accum": 0.0,
            "launch_delay": 0.0,
            "move_cooldown": CROW_RELOCATE_MIN_SECONDS,
            "hit_count": 0,
            "hide_cooldown": 0.0,
            "blink_state": make_crow_blink_state(7319),
            "depth_facing": str(facing.get("depth_facing", "front")),
            "lateral_facing": str(facing.get("lateral_facing", "right")),
        })
    if right_perches:
        occupied = occupied_perch_ids(states)
        available_right = [p for p in right_perches if str(p.get("id", "")) not in occupied]
        perch_pool = available_right if available_right else right_perches
        perch = perch_pool[rng_right.randrange(len(perch_pool))]
        start_x = float(world.SCREEN_W + 4)
        start_y = float(max(0, int(perch["perch_y"]) - 5))
        facing = resolve_crow_facing(start_x, start_y, float(perch.get("perch_x", start_x)), float(perch.get("perch_y", start_y)), {})
        states.append({
            "x": start_x,
            "y": start_y,
            "perch": perch,
            "mode": "waiting",
            "anim_index": 1 % len(CROW_FLY_SEQUENCE),
            "anim_accum": 0.0,
            "launch_delay": 1.0,
            "move_cooldown": CROW_RELOCATE_MIN_SECONDS,
            "hit_count": 0,
            "hide_cooldown": 0.0,
            "blink_state": make_crow_blink_state(7320),
            "depth_facing": str(facing.get("depth_facing", "front")),
            "lateral_facing": str(facing.get("lateral_facing", "right")),
        })
    return states


def resolve_crow_facing(origin_x: float, origin_y: float, target_x: float, target_y: float, current_crow: dict | None = None) -> dict:
    facing = dict(current_crow) if isinstance(current_crow, dict) else {}
    if target_y < origin_y:
        facing["depth_facing"] = "back"
    elif target_y > origin_y:
        facing["depth_facing"] = "front"
    if target_x < origin_x:
        facing["lateral_facing"] = "left"
    elif target_x > origin_x:
        facing["lateral_facing"] = "right"
    return facing


def launch_crow_to_perch(perch: dict, crow_frames: Dict[str, List[List[str]]]) -> dict:
    resting_rows = crow_frames.get("resting", [])
    crow_width = max((len(row) for row in resting_rows), default=0)
    perch_x = float(perch.get("perch_x", 0.0))
    perch_y = float(perch.get("perch_y", 0.0))
    start_x = float(-crow_width - 4) if perch_x < (world.SCREEN_W / 2) else float(world.SCREEN_W + 4)
    start_y = float(max(0, int(perch_y) - (4 if perch_x < (world.SCREEN_W / 2) else 5)))
    facing = resolve_crow_facing(start_x, start_y, perch_x, perch_y, {})
    return {
        "x": start_x,
        "y": start_y,
        "perch": perch,
        "mode": "flying",
        "anim_index": 0 if perch_x < (world.SCREEN_W / 2) else (1 % len(CROW_FLY_SEQUENCE)),
        "anim_accum": 0.0,
        "launch_delay": 0.0,
        "move_cooldown": CROW_RELOCATE_MIN_SECONDS,
        "depth_facing": str(facing.get("depth_facing", "front")),
        "lateral_facing": str(facing.get("lateral_facing", "right")),
    }


def crow_rest_label(crow: dict) -> str:
    depth = str(crow.get("depth_facing", "front"))
    lateral = str(crow.get("lateral_facing", "right"))
    if depth == "back":
        return "back_left" if lateral == "left" else "back_right"
    return "front_left" if lateral == "left" else "front_right"


def crow_fly_label(crow: dict, phase_label: str) -> str:
    depth = str(crow.get("depth_facing", "front"))
    lateral = str(crow.get("lateral_facing", "right"))
    if depth == "back":
        return f"back_{phase_label}"
    side = "left" if lateral == "left" else "right"
    return f"front_{side}_{phase_label}"


def redirect_crow_to_perch(crow: dict, perch: dict) -> dict:
    updated = dict(crow)
    origin_x = float(updated.get("x", 0.0))
    origin_y = float(updated.get("y", 0.0))
    target_x = float(perch.get("perch_x", origin_x))
    target_y = float(perch.get("perch_y", origin_y))
    updated.update(resolve_crow_facing(origin_x, origin_y, target_x, target_y, updated))
    updated["perch"] = perch
    updated["mode"] = "flying"
    updated["anim_index"] = 0
    updated["anim_accum"] = 0.0
    updated["launch_delay"] = 0.0
    updated["move_cooldown"] = CROW_RELOCATE_MIN_SECONDS
    return updated


def crow_exit_target(crow: dict, crow_frames: Dict[str, List[List[str]]]) -> tuple[float, float]:
    rows = crow_rows_for_state(crow, crow_frames)
    crow_width = max((len(row) for row in rows), default=0)
    x = float(crow.get("x", 0.0))
    y = float(crow.get("y", 0.0))
    if x < (world.SCREEN_W / 2):
        return float(-crow_width - 4), y
    return float(world.SCREEN_W + 4), y


def crow_rows_for_state(crow: dict, crow_frames: Dict[str, List[List[str]]]) -> List[List[str]]:
    if str(crow.get("mode", "resting")) == "resting":
        label = crow_rest_label(crow)
        return crow_frames.get(label, crow_frames.get("resting", []))
    frame_label = CROW_FLY_SEQUENCE[int(crow.get("anim_index", 0)) % len(CROW_FLY_SEQUENCE)]
    label = crow_fly_label(crow, frame_label)
    return crow_frames.get(label, crow_frames.get(frame_label, crow_frames.get("resting", [])))


def crow_screen_position(
    crow: dict,
    zones: Dict[str, world.LayoutZone],
    landscape_position: int,
    center_object_id: str,
    camera_x: int,
) -> tuple[float, float] | None:
    if str(crow.get("mode", "")) == "hidden":
        return None
    if str(crow.get("mode", "resting")) == "resting":
        return perch_screen_position(crow.get("perch", {}), zones, landscape_position, center_object_id, camera_x)
    return float(crow.get("x", 0.0)), float(crow.get("y", 0.0))


def handle_crow_hits(
    crow_states: List[dict],
    crow_frames: Dict[str, List[List[str]]],
    thrown_pebbles: List[dict],
    zones: Dict[str, world.LayoutZone],
    landscape_position: int,
    center_object_id: str,
    camera_x: int,
    visible_perches: List[dict],
    rng: random.Random,
) -> tuple[List[dict], List[dict]]:
    if not crow_states or not thrown_pebbles:
        return crow_states, thrown_pebbles
    boxes: List[tuple[int, int, int, int] | None] = []
    for crow in crow_states:
        pos = crow_screen_position(crow, zones, landscape_position, center_object_id, camera_x)
        rows = crow_rows_for_state(crow, crow_frames)
        if pos is None or not rows:
            boxes.append(None)
            continue
        x0 = int(round(pos[0]))
        y0 = int(round(pos[1]))
        width = max((len(row) for row in rows), default=0)
        boxes.append((x0, y0, x0 + max(0, width - 1), y0 + max(0, len(rows) - 1)))

    ground_start = world.landscape_ground_window_start(landscape_position)
    updated_crows = [dict(crow) for crow in crow_states]
    surviving_projectiles: List[dict] = []
    for projectile in thrown_pebbles:
        screen_x = int(round(float(projectile.get("world_x", 0.0)))) - int(camera_x)
        world_row = int(round(float(projectile.get("world_row", 0.0))))
        screen_y = int(zones["ground_bg"].y) + (world_row - ground_start)
        hit_index = None
        for idx, box in enumerate(boxes):
            if box is None:
                continue
            x0, y0, x1, y1 = box
            if x0 <= screen_x <= x1 and y0 <= screen_y <= y1:
                hit_index = idx
                break
        if hit_index is None:
            surviving_projectiles.append(projectile)
            continue
        crow = updated_crows[hit_index]
        crow["hit_count"] = int(crow.get("hit_count", 0)) + 1
        if int(crow.get("hit_count", 0)) >= CROW_MAX_HITS_BEFORE_HIDE:
            exit_x, exit_y = crow_exit_target(crow, crow_frames)
            crow.update(resolve_crow_facing(float(crow.get("x", 0.0)), float(crow.get("y", 0.0)), exit_x, exit_y, crow))
            crow["mode"] = "escaping"
            crow["exit_x"] = exit_x
            crow["exit_y"] = exit_y
            crow["hide_cooldown"] = 0.0
            crow["perch"] = {}
            crow["launch_delay"] = 0.0
            crow["anim_accum"] = 0.0
        else:
            occupied = occupied_perch_ids(updated_crows, exclude_index=hit_index)
            current_pos = crow_screen_position(crow, zones, landscape_position, center_object_id, camera_x)
            choices = []
            for perch in visible_perches:
                if str(perch.get("id", "")) in occupied:
                    continue
                if current_pos is not None:
                    dx = float(perch.get("perch_x", 0.0)) - float(current_pos[0])
                    dy = float(perch.get("perch_y", 0.0)) - float(current_pos[1])
                    if (dx * dx + dy * dy) ** 0.5 < CROW_MIN_HIT_RELOCATE_DISTANCE:
                        continue
                choices.append(perch)
            if not choices:
                choices = [perch for perch in visible_perches if str(perch.get("id", "")) not in occupied]
            if choices:
                next_perch = choices[rng.randrange(len(choices))]
                crow.update(redirect_crow_to_perch(crow, next_perch))
                crow["hide_cooldown"] = 0.0
        updated_crows[hit_index] = crow
        boxes[hit_index] = None
    return updated_crows, surviving_projectiles


def update_intro_crows(
    crow_states: List[dict],
    crow_frames: Dict[str, List[List[str]]],
    dt: float,
    zones: Dict[str, world.LayoutZone],
    landscape_position: int,
    center_object_id: str,
    camera_x: int,
    visible_perches: List[dict],
    rng: random.Random,
) -> List[dict]:
    updated: List[dict] = []
    for crow_index, crow in enumerate(crow_states):
        item = dict(crow)
        item["blink_state"] = update_crow_blink_state(item.get("blink_state", make_crow_blink_state(7400 + crow_index)), dt)
        if str(item.get("mode", "")) == "hidden":
            item["hide_cooldown"] = max(0.0, float(item.get("hide_cooldown", 0.0)) - dt)
            if float(item.get("hide_cooldown", 0.0)) <= 0.0 and visible_perches:
                occupied = occupied_perch_ids(crow_states, exclude_index=crow_index)
                choices = [perch for perch in visible_perches if str(perch.get("id", "")) not in occupied]
                if choices:
                    next_perch = choices[rng.randrange(len(choices))]
                    item.update(launch_crow_to_perch(next_perch, crow_frames))
                    item["hit_count"] = 0
                    item["hide_cooldown"] = 0.0
            updated.append(item)
            continue
        if str(item.get("mode", "")) == "escaping":
            item["anim_accum"] = float(item.get("anim_accum", 0.0)) + dt
            while float(item.get("anim_accum", 0.0)) >= CROW_FLY_STEP_SECONDS:
                item["anim_accum"] = float(item.get("anim_accum", 0.0)) - CROW_FLY_STEP_SECONDS
                item["anim_index"] = (int(item.get("anim_index", 0)) + 1) % len(CROW_FLY_SEQUENCE)
            target_x = float(item.get("exit_x", item.get("x", 0.0)))
            target_y = float(item.get("exit_y", item.get("y", 0.0)))
            dx = target_x - float(item.get("x", 0.0))
            dy = target_y - float(item.get("y", 0.0))
            compensated_dy = dy * CROW_FLY_VERTICAL_COMPENSATION
            distance = (dx * dx + compensated_dy * compensated_dy) ** 0.5
            step = CROW_FLY_SPEED * dt
            if distance <= max(1.0, step):
                item["x"] = target_x
                item["y"] = target_y
                item["mode"] = "hidden"
                item["hide_cooldown"] = CROW_HIT_HIDE_SECONDS
                item["exit_x"] = target_x
                item["exit_y"] = target_y
            elif distance > 0:
                item["x"] = float(item.get("x", 0.0)) + (dx / distance) * step
                item["y"] = float(item.get("y", 0.0)) + (compensated_dy / distance) * step
            updated.append(item)
            continue
        target_pos = perch_screen_position(item.get("perch", {}), zones, landscape_position, center_object_id, camera_x)
        mode = str(item.get("mode", "flying"))
        if mode == "waiting":
            item["launch_delay"] = max(0.0, float(item.get("launch_delay", 0.0)) - dt)
            if float(item.get("launch_delay", 0.0)) <= 0.0:
                item["mode"] = "flying"
        if str(item.get("mode", "flying")) == "flying":
            item["anim_accum"] = float(item.get("anim_accum", 0.0)) + dt
            while float(item.get("anim_accum", 0.0)) >= CROW_FLY_STEP_SECONDS:
                item["anim_accum"] = float(item.get("anim_accum", 0.0)) - CROW_FLY_STEP_SECONDS
                item["anim_index"] = (int(item.get("anim_index", 0)) + 1) % len(CROW_FLY_SEQUENCE)
            target_x, target_y = target_pos if target_pos is not None else (float(item.get("x", 0.0)), float(item.get("y", 0.0)))
            dx = target_x - float(item.get("x", 0.0))
            dy = target_y - float(item.get("y", 0.0))
            compensated_dy = dy * CROW_FLY_VERTICAL_COMPENSATION
            distance = (dx * dx + compensated_dy * compensated_dy) ** 0.5
            step = CROW_FLY_SPEED * dt
            if distance <= max(1.0, step):
                item["x"] = target_x
                item["y"] = target_y
                item["mode"] = "resting"
                item["anim_index"] = 0
                item["anim_accum"] = 0.0
            elif distance > 0:
                item["x"] = float(item.get("x", 0.0)) + (dx / distance) * step
                item["y"] = float(item.get("y", 0.0)) + (compensated_dy / distance) * step
        elif str(item.get("mode", "resting")) == "resting" and target_pos is not None:
            item["x"], item["y"] = target_pos
            item["move_cooldown"] = float(item.get("move_cooldown", CROW_RELOCATE_MIN_SECONDS)) - dt
            if float(item.get("move_cooldown", 0.0)) <= 0.0 and visible_perches:
                current_perch = item.get("perch", {})
                occupied = occupied_perch_ids(crow_states, exclude_index=crow_index)
                choices = [
                    perch
                    for perch in visible_perches
                    if str(perch.get("id", "")) != str(current_perch.get("id", ""))
                    and str(perch.get("id", "")) not in occupied
                ]
                if choices:
                    next_perch = choices[rng.randrange(len(choices))]
                    item = redirect_crow_to_perch(item, next_perch)
                item["move_cooldown"] = rng.uniform(CROW_RELOCATE_MIN_SECONDS, CROW_RELOCATE_MAX_SECONDS)
        updated.append(item)
    return updated


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


def _pebble_palette(objects_data: object) -> tuple[List[str], List[str]]:
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
    return pebble_glyphs, pebble_keys


def _dark_gold_pebble_cell(glyph: str, variant: int = 0) -> str:
    color = DARK_GOLD_PEBBLE_COLORS[max(0, int(variant)) % len(DARK_GOLD_PEBBLE_COLORS)]
    return f"{color}{(str(glyph)[:1] or 'o')}{world.ANSI_RESET}"


def build_collectible_road_pebbles(
    row_count: int,
    objects_data: object,
    color_codes: Dict[str, str],
    density: float = COLLECTIBLE_PEBBLE_DENSITY,
) -> Dict[int, Dict[int, str]]:
    rng = __import__("random").Random(9051702)
    glyphs, keys = _pebble_palette(objects_data)
    density = max(0.0, min(0.2, float(density)))
    pebbles: Dict[int, Dict[int, str]] = {}
    for world_row in range(max(0, row_count)):
        crossroad_phase = world.crossroad_row_phase(world_row)
        if crossroad_phase is None:
            road = road_geometry_for_horizon_distance(world_row)
            x_start = int(road.get("start", 0))
            x_end = int(road.get("end", TRAVEL_WORLD_WIDTH - 1))
        else:
            x_start = 0
            x_end = TRAVEL_WORLD_WIDTH - 1
        row_pebbles: Dict[int, str] = {}
        for world_x in range(x_start, x_end + 1):
            if rng.random() >= density:
                continue
            glyph = rng.choice(glyphs)
            row_pebbles[world_x] = _dark_gold_pebble_cell(glyph, rng.randrange(len(DARK_GOLD_PEBBLE_COLORS)))
        if row_pebbles:
            pebbles[world_row] = row_pebbles
    return pebbles


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


def collect_overlapping_pebbles(
    collectible_pebbles: Dict[int, Dict[int, str]],
    avatar_rows: List[List[str]],
    camera_x: int,
    zones: Dict[str, world.LayoutZone],
    landscape_position: int,
) -> int:
    if not collectible_pebbles:
        return 0
    avatar = build_avatar_placement(avatar_rows)
    ground_zone = zones["ground_bg"]
    ground_start = world.landscape_ground_window_start(landscape_position)
    covered: set[tuple[int, int]] = set()
    for dy, row in enumerate(avatar_rows):
        screen_y = int(avatar["y"]) + dy
        if screen_y < int(ground_zone.y) or screen_y > int(ground_zone.y1):
            continue
        world_row = ground_start + (screen_y - int(ground_zone.y))
        for dx, cell in enumerate(row):
            if cell == " ":
                continue
            world_x = int(camera_x) + int(avatar["x"]) + dx
            covered.add((world_row, world_x))
    collected = 0
    for world_row, world_x in covered:
        row_pebbles = collectible_pebbles.get(world_row)
        if not row_pebbles or world_x not in row_pebbles:
            continue
        del row_pebbles[world_x]
        collected += 1
        if not row_pebbles:
            collectible_pebbles.pop(world_row, None)
    return collected


def spawn_thrown_pebble(
    avatar_rows: List[List[str]],
    camera_x: int,
    zones: Dict[str, world.LayoutZone],
    landscape_position: int,
    facing: str,
) -> dict:
    avatar = build_avatar_placement(avatar_rows)
    hand_offsets = {
        "front": (1, 4),
        "back": (5, 4),
        "left": (1, 4),
        "right": (4, 4),
    }
    hand_x, hand_y = hand_offsets.get(facing, hand_offsets["front"])
    hand_x = max(0, min(max(0, int(avatar["width"]) - 1), hand_x))
    hand_y = max(0, min(max(0, int(avatar["height"]) - 1), hand_y))
    ground_start = world.landscape_ground_window_start(landscape_position)
    world_x = int(camera_x) + int(avatar["x"]) + hand_x
    screen_y = int(avatar["y"]) + hand_y
    world_row = ground_start + max(0, screen_y - int(zones["ground_bg"].y))
    dx = 0.0
    dy = 0.0
    if facing == "left":
        dx = -THROWN_PEBBLE_SPEED_X
    elif facing == "right":
        dx = THROWN_PEBBLE_SPEED_X
    elif facing == "back":
        dy = -THROWN_PEBBLE_SPEED_Y
    else:
        dy = THROWN_PEBBLE_SPEED_Y
    return {
        "world_x": float(world_x),
        "world_row": float(world_row),
        "vx": dx,
        "vy": dy,
        "cell": _dark_gold_pebble_cell("o", 0),
    }


def throw_pose_for_facing(facing: str) -> str:
    if facing in {"front", "back"}:
        return "step_a"
    return "step_b"


def update_thrown_pebbles(projectiles: List[dict], dt: float) -> List[dict]:
    updated: List[dict] = []
    max_row = max(0, world.LANDSCAPE_TOTAL_GROUND_ROWS - 1)
    for item in projectiles:
        world_x = float(item.get("world_x", 0.0)) + (float(item.get("vx", 0.0)) * dt)
        world_row = float(item.get("world_row", 0.0)) + (float(item.get("vy", 0.0)) * dt)
        if world_x < 0 or world_x >= TRAVEL_WORLD_WIDTH:
            continue
        if world_row < 0 or world_row > max_row:
            continue
        updated.append({
            "world_x": world_x,
            "world_row": world_row,
            "vx": float(item.get("vx", 0.0)),
            "vy": float(item.get("vy", 0.0)),
            "cell": str(item.get("cell", "o")),
        })
    return updated


def update_walking_mushroom(mushroom: dict, dt: float) -> dict:
    updated = dict(mushroom)
    total_rows = max(0, int(updated.get("total_rows", 0)))
    if bool(updated.get("frowning", False)):
        frown_accum = max(0.0, float(updated.get("frown_accum", 0.0)) - dt)
        updated["frown_accum"] = frown_accum
        if frown_accum <= 0.0:
            updated["frowning"] = False
            updated["burrow_blinking"] = True
            updated["burrow_blink_accum"] = WALKING_MUSHROOM_BURROW_BLINK_SECONDS
            updated["visible_rows"] = max(0, total_rows - 1)
        return updated
    if bool(updated.get("burrow_blinking", False)):
        burrow_blink_accum = max(0.0, float(updated.get("burrow_blink_accum", 0.0)) - dt)
        updated["burrow_blink_accum"] = burrow_blink_accum
        if burrow_blink_accum <= 0.0:
            updated["burrow_blinking"] = False
            updated["burrowing"] = True
            updated["burrow_accum"] = 0.0
        return updated
    if bool(updated.get("burrowing", False)):
        burrow_accum = float(updated.get("burrow_accum", 0.0)) + dt
        visible_rows = int(updated.get("visible_rows", total_rows))
        while burrow_accum >= WALKING_MUSHROOM_BURROW_STEP_SECONDS and visible_rows > 0:
            burrow_accum -= WALKING_MUSHROOM_BURROW_STEP_SECONDS
            visible_rows -= 1
        updated["burrow_accum"] = burrow_accum
        updated["visible_rows"] = visible_rows
        if visible_rows <= 0:
            updated["burrowing"] = False
            updated["burrow_accum"] = 0.0
            updated["world_x"] = float(updated.get("home_world_x", updated.get("world_x", 0.0)))
            updated["visible_rows"] = 0
            updated["hidden_wait"] = True
            updated["hidden_wait_accum"] = WALKING_MUSHROOM_HIDE_SECONDS
        return updated
    if bool(updated.get("hidden_wait", False)):
        hidden_wait_accum = max(0.0, float(updated.get("hidden_wait_accum", 0.0)) - dt)
        updated["hidden_wait_accum"] = hidden_wait_accum
        updated["visible_rows"] = 0
        updated["world_x"] = float(updated.get("home_world_x", updated.get("world_x", 0.0)))
        if hidden_wait_accum <= 0.0:
            updated["hidden_wait"] = False
            updated["visible_rows"] = max(0, min(3, total_rows))
            updated["emerging_hold"] = True
            updated["emerge_hold_accum"] = WALKING_MUSHROOM_EMERGE_HOLD_SECONDS
        return updated
    if bool(updated.get("emerging_hold", False)):
        emerge_hold_accum = max(0.0, float(updated.get("emerge_hold_accum", 0.0)) - dt)
        updated["emerge_hold_accum"] = emerge_hold_accum
        updated["visible_rows"] = max(0, min(3, total_rows))
        updated["world_x"] = float(updated.get("home_world_x", updated.get("world_x", 0.0)))
        if emerge_hold_accum <= 0.0:
            updated["emerging_hold"] = False
            updated["emerging_blink"] = True
            updated["emerge_blink_accum"] = WALKING_MUSHROOM_EMERGE_BLINK_SECONDS
        return updated
    if bool(updated.get("emerging_blink", False)):
        emerge_blink_accum = max(0.0, float(updated.get("emerge_blink_accum", 0.0)) - dt)
        updated["emerge_blink_accum"] = emerge_blink_accum
        updated["visible_rows"] = total_rows
        updated["world_x"] = float(updated.get("home_world_x", updated.get("world_x", 0.0)))
        if emerge_blink_accum <= 0.0:
            updated["emerging_blink"] = False
            updated["visible_rows"] = total_rows
        return updated
    world_x = float(updated.get("world_x", 0.0)) + (WALKING_MUSHROOM_SPEED * dt)
    width = max(1, int(updated.get("width", 1)))
    if world_x > TRAVEL_WORLD_WIDTH:
        world_x = 0.0 - max(0, width - 1)
    updated["world_x"] = world_x
    accum = float(updated.get("anim_accum", 0.0)) + dt
    phase_index = int(updated.get("phase_index", 0))
    while accum >= WALKING_MUSHROOM_STEP_SECONDS:
        accum -= WALKING_MUSHROOM_STEP_SECONDS
        phase_index = (phase_index + 1) % len(WALKING_MUSHROOM_SEQUENCE)
    updated["anim_accum"] = accum
    updated["phase_index"] = phase_index
    return updated


def update_walking_fairy(fairy: dict, dt: float) -> dict:
    updated = dict(fairy)
    if bool(updated.get("frowning", False)):
        frown_accum = max(0.0, float(updated.get("frown_accum", 0.0)) - dt)
        updated["frown_accum"] = frown_accum
        if frown_accum <= 0.0:
            updated["frowning"] = False
            updated["scared"] = True
        return updated
    scared = bool(updated.get("scared", False))
    speed = WALKING_FAIRY_SCARED_SPEED if scared else WALKING_FAIRY_SPEED
    direction = int(updated.get("scared_direction", -1)) if scared else -1
    world_x = float(updated.get("world_x", 0.0)) + (direction * speed * dt)
    width = max(1, int(updated.get("width", 1)))
    if direction < 0 and world_x + width - 1 < 0:
        world_x = float(TRAVEL_WORLD_WIDTH - 1)
        updated["scared"] = False
        updated["scared_direction"] = -1
    elif direction > 0 and world_x > TRAVEL_WORLD_WIDTH:
        world_x = 0.0 - max(0, width - 1)
        updated["scared"] = False
        updated["scared_direction"] = -1
    updated["world_x"] = world_x
    accum = float(updated.get("anim_accum", 0.0)) + dt
    phase_index = int(updated.get("phase_index", 0))
    while accum >= WALKING_FAIRY_STEP_SECONDS:
        accum -= WALKING_FAIRY_STEP_SECONDS
        phase_index = (phase_index + 1) % len(WALKING_FAIRY_SEQUENCE)
    updated["anim_accum"] = accum
    updated["phase_index"] = phase_index
    return updated


def walking_fairy_rows(
    walking_fairy: dict,
    walking_fairy_frames: Dict[str, List[List[str]]],
) -> List[List[str]]:
    rows = walking_fairy_frames.get(
        WALKING_FAIRY_SEQUENCE[int(walking_fairy.get("phase_index", 0)) % len(WALKING_FAIRY_SEQUENCE)],
        walking_fairy_frames.get("primary", []),
    )
    if not isinstance(rows, list) or not rows:
        return []
    if bool(walking_fairy.get("frowning", False)) or bool(walking_fairy.get("scared", False)):
        out: List[List[str]] = []
        for row in rows:
            new_row = []
            for cell in row:
                text = str(cell)
                new_row.append(text.replace("◡", "◠"))
            out.append(new_row)
        return out
    return rows


def walking_mushroom_rows(
    walking_mushroom: dict,
    walking_mushroom_frames: Dict[str, List[List[str]]],
) -> List[List[str]]:
    rows = walking_mushroom_frames.get(
        WALKING_MUSHROOM_SEQUENCE[int(walking_mushroom.get("phase_index", 0)) % len(WALKING_MUSHROOM_SEQUENCE)],
        walking_mushroom_frames.get("primary", []),
    )
    if not isinstance(rows, list) or not rows:
        return []
    draw_rows = list(rows[:max(0, int(walking_mushroom.get("visible_rows", len(rows))))])
    if bool(walking_mushroom.get("frowning", False)) or bool(walking_mushroom.get("burrow_blinking", False)):
        out: List[List[str]] = []
        for row in draw_rows:
            new_row = []
            for cell in row:
                text = str(cell)
                new_row.append(text.replace("◡", "◠"))
            out.append(new_row)
        return out
    return draw_rows


def handle_walking_fairy_hits(
    walking_fairy: dict,
    walking_fairy_frames: Dict[str, List[List[str]]],
    thrown_pebbles: List[dict],
    zones: Dict[str, world.LayoutZone],
    landscape_position: int,
    camera_x: int,
    player_world_x: int,
) -> tuple[dict, List[dict]]:
    fairy_rows = walking_fairy_rows(walking_fairy, walking_fairy_frames)
    if not fairy_rows or not thrown_pebbles:
        return walking_fairy, thrown_pebbles
    ground_start = world.landscape_ground_window_start(landscape_position)
    fairy_world_row = int(walking_fairy.get("world_row", 0))
    fairy_screen_y = int(zones["ground_bg"].y) + (fairy_world_row - ground_start) - max(0, len(fairy_rows) - 1)
    fairy_screen_x = int(round(float(walking_fairy.get("world_x", 0.0)))) - int(camera_x)
    fairy_width = max((len(row) for row in fairy_rows), default=0)
    fairy_box = (
        fairy_screen_x,
        fairy_screen_y,
        fairy_screen_x + max(0, fairy_width - 1),
        fairy_screen_y + max(0, len(fairy_rows) - 1),
    )
    surviving: List[dict] = []
    updated = dict(walking_fairy)
    hit = False
    for projectile in thrown_pebbles:
        screen_x = int(round(float(projectile.get("world_x", 0.0)))) - int(camera_x)
        world_row = int(round(float(projectile.get("world_row", 0.0))))
        screen_y = int(zones["ground_bg"].y) + (world_row - ground_start)
        if fairy_box[0] <= screen_x <= fairy_box[2] and fairy_box[1] <= screen_y <= fairy_box[3] and not hit:
            hit = True
            if not bool(updated.get("frowning", False)) and not bool(updated.get("scared", False)):
                updated["frowning"] = True
                updated["frown_accum"] = WALKING_FAIRY_FROWN_SECONDS
                updated["scared_direction"] = 1 if float(updated.get("world_x", 0.0)) >= float(player_world_x) else -1
            continue
        surviving.append(projectile)
    return updated, surviving


def handle_walking_mushroom_hits(
    walking_mushroom: dict,
    walking_mushroom_frames: Dict[str, List[List[str]]],
    thrown_pebbles: List[dict],
    zones: Dict[str, world.LayoutZone],
    landscape_position: int,
    camera_x: int,
) -> tuple[dict, List[dict]]:
    mushroom_rows = walking_mushroom_rows(walking_mushroom, walking_mushroom_frames)
    if not mushroom_rows or not thrown_pebbles:
        return walking_mushroom, thrown_pebbles
    ground_start = world.landscape_ground_window_start(landscape_position)
    mushroom_world_row = int(walking_mushroom.get("world_row", 0))
    mushroom_screen_y = int(zones["ground_bg"].y) + (mushroom_world_row - ground_start) - max(0, len(mushroom_rows) - 1)
    mushroom_screen_x = int(round(float(walking_mushroom.get("world_x", 0.0)))) - int(camera_x)
    mushroom_width = max((len(row) for row in mushroom_rows), default=0)
    mushroom_box = (
        mushroom_screen_x,
        mushroom_screen_y,
        mushroom_screen_x + max(0, mushroom_width - 1),
        mushroom_screen_y + max(0, len(mushroom_rows) - 1),
    )
    surviving: List[dict] = []
    updated = dict(walking_mushroom)
    hit = False
    for projectile in thrown_pebbles:
        screen_x = int(round(float(projectile.get("world_x", 0.0)))) - int(camera_x)
        world_row = int(round(float(projectile.get("world_row", 0.0))))
        screen_y = int(zones["ground_bg"].y) + (world_row - ground_start)
        if mushroom_box[0] <= screen_x <= mushroom_box[2] and mushroom_box[1] <= screen_y <= mushroom_box[3] and not hit:
            hit = True
            if (
                not bool(updated.get("frowning", False))
                and not bool(updated.get("burrow_blinking", False))
                and not bool(updated.get("burrowing", False))
                and not bool(updated.get("hidden_wait", False))
                and not bool(updated.get("emerging_hold", False))
                and not bool(updated.get("emerging_blink", False))
            ):
                updated["frowning"] = True
                updated["frown_accum"] = WALKING_MUSHROOM_FROWN_SECONDS
                updated["home_world_x"] = float(updated.get("world_x", 0.0))
            continue
        surviving.append(projectile)
    return updated, surviving


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
    avatar_facing: str,
    house_occupants: Dict[str, List[List[str]]],
    house_blink_states: Dict[str, dict],
    house_occupant_poses: Dict[str, dict],
    house_window_objects: Dict[str, List[dict]],
    walking_mushroom_frames: Dict[str, List[List[str]]],
    walking_mushroom: dict,
    walking_mushroom_blink: dict,
    walking_fairy_frames: Dict[str, List[List[str]]],
    walking_fairy: dict,
    walking_fairy_blink: dict,
    collectible_pebbles: Dict[int, Dict[int, str]],
    thrown_pebbles: List[dict],
    pebble_count: int,
    throw_cooldown: float,
    game_time_seconds: float,
    address_label: str,
    scene_label: str,
    center_object_id: str,
    camera_x: int,
    avatar_blink: dict,
    crow_frames: Dict[str, List[List[str]]],
    crow_states: List[dict],
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
            width = int(sprite.get("width", len(rows[0]) if rows else 0))
            height = int(sprite.get("height", len(rows)))
            horizon_depth = max(0, int(sprite.get("horizon_depth", 0)))
            sprite_is_backside, y_base = world.horizon_depth_state(horizon_depth, hidden_ground_rows, ground_zone.y)
            if sprite_is_backside != draw_backside:
                continue
            y_base = max(ground_zone.y, y_base)
            distance_from_horizon = max(0, y_base - ground_zone.y)
            road = road_geometry_for_horizon_distance(distance_from_horizon)
            road_anchor = str(sprite.get("road_anchor", "")).strip()
            if road_anchor == "start":
                x0 = int(road.get("start", 0)) + int(sprite.get("road_offset", 0)) - camera_x
            elif road_anchor == "end":
                x0 = int(road.get("end", TRAVEL_WORLD_WIDTH - 1)) + int(sprite.get("road_offset", 0)) - camera_x
            else:
                side = str(sprite.get("side", "left"))
                side_slot = max(0, int(sprite.get("side_slot", 0)))
                side_offset = int(sprite.get("side_offset", 0))
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

        for crow in crow_states:
            if str(crow.get("mode", "resting")) != "resting":
                continue
            perch = crow.get("perch", {})
            if not isinstance(perch, dict):
                continue
            sprite = perch.get("sprite", {})
            if not isinstance(sprite, dict):
                continue
            projection = sprite_projection_for_scene(sprite, camera_x, hidden_ground_rows, ground_zone, center_object_id)
            if projection is None:
                continue
            perch_x, perch_y = perch_screen_position(perch, zones, landscape_position, center_object_id, camera_x) or (None, None)
            if perch_x is None or perch_y is None:
                continue
            _x0, _y0, sprite_is_backside = projection
            if sprite_is_backside != draw_backside:
                continue
            rows = apply_crow_blink_to_rows(crow_rows_for_state(crow, crow_frames), crow.get("blink_state"))
            if not isinstance(rows, list) or not rows:
                continue
            tree_rows = sprite.get("rows", [])
            tree_height = int(sprite.get("height", len(tree_rows) if isinstance(tree_rows, list) else 0))
            tree_base_y = int(_y0) + max(0, tree_height - 1)
            target.append({
                "x": int(round(perch_x)),
                "y": int(round(perch_y)),
                "rows": rows,
                "base_y": tree_base_y,
                "horizon_depth": int(sprite.get("horizon_depth", sprite.get("anchor_offset", 0))),
                "z_bias": 25,
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
            label = str(drawable.get("label", "")).strip()
            occupant_rows = apply_blink_to_rows(house_occupants.get(label, []), house_blink_states.get(label))
            occupant_pose = house_occupant_poses.get(label) if occupant_rows else None
            draw_house_sprite(
                canvas,
                drawable,
                occupant_rows=occupant_rows,
                occupant_pose=occupant_pose,
                window_objects=house_window_objects.get(label, []),
            )
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
        row_pebbles = collectible_pebbles.get(src_index, {})
        for world_x, cell in row_pebbles.items():
            screen_x = int(world_x) - int(camera_x)
            if 0 <= screen_x < world.SCREEN_W:
                canvas[y][screen_x] = cell

    draw_world_scene_sprites(draw_backside=False)

    avatar_display_rows = apply_blink_to_rows(avatar_rows, avatar_blink)
    avatar = build_avatar_placement(avatar_display_rows)
    walker_draw_rows = walking_mushroom_rows(walking_mushroom, walking_mushroom_frames)
    if bool(walking_mushroom.get("frowning", False)):
        walker_draw_rows = apply_forced_double_blink_rows(
            walker_draw_rows,
            WALKING_MUSHROOM_FROWN_SECONDS,
            float(walking_mushroom.get("frown_accum", 0.0)),
        )
    elif bool(walking_mushroom.get("burrow_blinking", False)):
        walker_draw_rows = apply_forced_double_blink_rows(
            walker_draw_rows,
            WALKING_MUSHROOM_BURROW_BLINK_SECONDS,
            float(walking_mushroom.get("burrow_blink_accum", 0.0)),
        )
    elif bool(walking_mushroom.get("emerging_hold", False)):
        walker_draw_rows = apply_forced_double_blink_rows(
            walker_draw_rows,
            WALKING_MUSHROOM_EMERGE_HOLD_SECONDS,
            float(walking_mushroom.get("emerge_hold_accum", 0.0)),
        )
    elif bool(walking_mushroom.get("emerging_blink", False)):
        walker_draw_rows = apply_forced_double_blink_rows(
            walker_draw_rows,
            WALKING_MUSHROOM_EMERGE_BLINK_SECONDS,
            float(walking_mushroom.get("emerge_blink_accum", 0.0)),
        )
    else:
        walker_draw_rows = apply_blink_to_rows(walker_draw_rows, walking_mushroom_blink)
    if isinstance(walker_draw_rows, list) and walker_draw_rows:
        ground_start = world.landscape_ground_window_start(landscape_position)
        walker_world_row = int(walking_mushroom.get("world_row", 0))
        walker_screen_y = int(ground_zone.y) + (walker_world_row - ground_start) - max(0, len(walker_draw_rows) - 1)
        walker_screen_x = int(round(float(walking_mushroom.get("world_x", 0.0)))) - int(camera_x)
        if (
            walker_screen_x + max((len(row) for row in walker_draw_rows), default=0) > 0
            and walker_screen_x < world.SCREEN_W
            and walker_screen_y + len(walker_draw_rows) > int(ground_zone.y)
            and walker_screen_y <= int(ground_zone.y1)
        ):
            foreground_drawables.append({
                "x": walker_screen_x,
                "y": walker_screen_y,
                "rows": walker_draw_rows,
                "base_y": walker_screen_y + max(0, len(walker_draw_rows) - 1),
                "z_bias": 12,
            })
    fairy_rows = walking_fairy_rows(walking_fairy, walking_fairy_frames)
    if bool(walking_fairy.get("frowning", False)):
        fairy_rows = apply_forced_double_blink_rows(
            fairy_rows,
            WALKING_FAIRY_FROWN_SECONDS,
            float(walking_fairy.get("frown_accum", 0.0)),
        )
    else:
        fairy_rows = apply_blink_to_rows(fairy_rows, walking_fairy_blink)
    if isinstance(fairy_rows, list) and fairy_rows:
        ground_start = world.landscape_ground_window_start(landscape_position)
        fairy_world_row = int(walking_fairy.get("world_row", 0))
        fairy_screen_y = int(ground_zone.y) + (fairy_world_row - ground_start) - max(0, len(fairy_rows) - 1)
        fairy_screen_x = int(round(float(walking_fairy.get("world_x", 0.0)))) - int(camera_x)
        if (
            fairy_screen_x + max((len(row) for row in fairy_rows), default=0) > 0
            and fairy_screen_x < world.SCREEN_W
            and fairy_screen_y + len(fairy_rows) > int(ground_zone.y)
            and fairy_screen_y <= int(ground_zone.y1)
        ):
            foreground_drawables.append({
                "x": fairy_screen_x,
                "y": fairy_screen_y,
                "rows": fairy_rows,
                "base_y": fairy_screen_y + max(0, len(fairy_rows) - 1),
                "z_bias": 13,
            })
    foreground_drawables.append({
        "x": int(avatar["x"]),
        "y": int(avatar["y"]),
        "rows": avatar_display_rows,
        "base_y": int(avatar["y"]) + max(0, int(avatar["height"]) - 1),
        "z_bias": 15,
    })

    foreground_drawables.sort(key=lambda item: (int(item.get("base_y", 0)), int(item.get("z_bias", 0)), int(item.get("y", 0)), int(item.get("x", 0))))
    for drawable in foreground_drawables:
        rows = drawable.get("rows", [])
        if isinstance(rows, list) and drawable.get("house_sprite"):
            label = str(drawable.get("label", "")).strip()
            occupant_rows = apply_blink_to_rows(house_occupants.get(label, []), house_blink_states.get(label))
            occupant_pose = house_occupant_poses.get(label) if occupant_rows else None
            draw_house_sprite(
                canvas,
                drawable,
                occupant_rows=occupant_rows,
                occupant_pose=occupant_pose,
                window_objects=house_window_objects.get(label, []),
            )
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
    for crow in crow_states:
        if str(crow.get("mode", "")) in {"resting", "hidden"}:
            continue
        rows = apply_crow_blink_to_rows(crow_rows_for_state(crow, crow_frames), crow.get("blink_state"))
        if isinstance(rows, list) and rows:
            draw_sprite(
                canvas,
                rows,
                int(round(float(crow.get("x", 0.0)))),
                int(round(float(crow.get("y", 0.0)))),
            )

    ground_start = world.landscape_ground_window_start(landscape_position)
    for projectile in thrown_pebbles:
        screen_x = int(round(float(projectile.get("world_x", 0.0)))) - int(camera_x)
        world_row = int(round(float(projectile.get("world_row", 0.0))))
        screen_y = int(ground_zone.y) + (world_row - ground_start)
        if 0 <= screen_x < world.SCREEN_W and int(ground_zone.y) <= screen_y <= int(ground_zone.y1):
            canvas[screen_y][screen_x] = str(projectile.get("cell", "o"))
    if avatar_facing == "back":
        draw_sprite(canvas, avatar_display_rows, int(avatar["x"]), int(avatar["y"]))

    header = f"[travel][scene:{scene_label}][address:{address_label}]"
    controls = "[up/down travel][left/right strafe][t throw][a avatar][c scene][q quit]"
    pebble_label = f"Pebbles: {max(0, int(pebble_count))}"
    throw_label = "Throw: ready" if throw_cooldown <= 0 else f"Throw: {throw_cooldown:.1f}s"
    total_seconds = max(0, int(game_time_seconds))
    game_time_label = f"Time: {total_seconds // 60:02d}:{total_seconds % 60:02d}"
    if len(header) <= world.SCREEN_W:
        draw_label(canvas, header, max(0, (world.SCREEN_W - len(header)) // 2), 0)
    if len(pebble_label) <= world.SCREEN_W:
        draw_label(canvas, pebble_label, max(0, world.SCREEN_W - len(pebble_label) - 1), 1, color="\x1b[38;2;235;220;170m")
    if len(throw_label) <= world.SCREEN_W:
        draw_label(canvas, throw_label, max(0, world.SCREEN_W - len(throw_label) - 1), 2, color="\x1b[38;2;205;205;255m")
    if len(game_time_label) <= world.SCREEN_W:
        draw_label(canvas, game_time_label, max(0, world.SCREEN_W - len(game_time_label) - 1), 3, color="\x1b[38;2;200;235;200m")
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
    avatar_forward_facing = "front"
    walk_frame_index = 0
    walk_frame_accum = 0.0
    idle_reset_accum = WALK_RESET_IDLE_SECONDS
    last_walk_step_phase = "step_b"
    was_avatar_moving = False
    avatar_rows = world.build_player_frame(players, avatar_ids[avatar_index], color_codes, avatar_facing, "idle")
    camera_x = clamp_camera_to_road(starting_camera_x(), avatar_rows, zones, landscape_position)
    target_camera_x = camera_x
    clouds = spawn_clouds_wide(templates)
    ground_rows = build_ground_rows_wide(
        row_count=world.LANDSCAPE_TOTAL_GROUND_ROWS,
        objects_data=objects,
        color_codes=color_codes,
        pebble_density=0.07,
    )
    collectible_pebbles = build_collectible_road_pebbles(
        row_count=world.LANDSCAPE_TOTAL_GROUND_ROWS,
        objects_data=objects,
        color_codes=color_codes,
    )
    pebble_count = 0
    thrown_pebbles: List[dict] = []
    throw_cooldown = 0.0
    game_time_seconds = 0.0
    throw_pose_accum = 0.0
    scene_index = 0
    scene_label, center_object_id = WORLD_MODELS[scene_index]
    world_treeline_sprites = [recenter_sprite_x(sprite) for sprite in world.build_world_treeline_sprites(objects, colors, center_object_id)]
    border_treeline_sprites = [recenter_border_sprite_x(sprite) for sprite in world.build_border_treeline_sprites(objects, colors)]
    crossroad_house_sprites = world.build_crossroad_house_sprites(objects, colors)
    crow_frames = world.build_opponent_art_variations(opponents, "baby_crow", color_codes)
    if "resting" not in crow_frames:
        crow_frames["resting"] = world.build_opponent_sprite(opponents, "baby_crow", color_codes)
    house_sprite_by_label = {
        str(sprite.get("label", "")).strip(): sprite
        for sprite in crossroad_house_sprites
        if str(sprite.get("label", "")).strip()
    }
    vials_sprite = world.build_world_object_sprite(objects, colors, "vials")
    house_mushroom_frames = {
        label: world.build_house_mushroom_frames(opponents, color_codes, house_number)
        for house_number, label in enumerate(AVE_A_MUSHROOM_HOUSE_LABELS, start=1)
    }
    house_occupants = {
        label: frames.get("primary", [])
        for label, frames in house_mushroom_frames.items()
    }
    house_fairy_frames = {
        label: world.build_house_fairy_frames(opponents, color_codes, house_number)
        for house_number, label in enumerate(AVE_A_FAIRY_HOUSE_LABELS, start=11)
    }
    house_occupants.update({
        label: frames.get("primary", [])
        for label, frames in house_fairy_frames.items()
    })
    house_fairy_flap_states = {
        label: {"active": False, "sequence_index": 0, "accum": 0.0}
        for label in AVE_A_FAIRY_HOUSE_LABELS
    }
    house_blink_states = {
        label: make_blink_state(8100 + idx, ["◎", "◉"])
        for idx, label in enumerate(AVE_A_MUSHROOM_HOUSE_LABELS + AVE_A_FAIRY_HOUSE_LABELS)
    }
    house_mushroom_step_states = {
        label: {"active": False, "accum": 0.0, "next_variant": "a", "facing": "front"}
        for label in AVE_A_MUSHROOM_HOUSE_LABELS
    }
    house_window_objects: Dict[str, List[dict]] = {}
    vial_house = house_sprite_by_label.get(HOUSE_10_VIAL_LABEL)
    vial_rows = vials_sprite.get("rows", []) if isinstance(vials_sprite, dict) else []
    vial_mask_rows = vial_house.get("mask_rows", []) if isinstance(vial_house, dict) else []
    vial_pose = centered_window_object_pose(vial_mask_rows, vial_rows, window_index=1) if isinstance(vial_mask_rows, list) else None
    if isinstance(vial_pose, dict) and isinstance(vial_rows, list) and vial_rows:
        house_window_objects[HOUSE_10_VIAL_LABEL] = [{"rows": vial_rows, "x0": int(vial_pose["x0"]), "y0": int(vial_pose["y0"])}]
    walking_mushroom_frames = world.build_house_mushroom_frames(opponents, color_codes, 14, band_pattern="╺◇╸")
    walking_mushroom_house = house_sprite_by_label.get("[#9 Ave A]")
    walking_mushroom = {
        "world_x": 0.0,
        "world_row": 30,
        "home_world_x": 0.0,
        "phase_index": 0,
        "anim_accum": 0.0,
        "width": max((len(row) for row in walking_mushroom_frames.get("primary", [])), default=0),
        "total_rows": len(walking_mushroom_frames.get("primary", [])),
        "visible_rows": len(walking_mushroom_frames.get("primary", [])),
        "burrowing": False,
        "burrow_accum": 0.0,
        "burrow_blinking": False,
        "burrow_blink_accum": 0.0,
        "hidden_wait": False,
        "hidden_wait_accum": 0.0,
        "emerging_hold": False,
        "emerge_hold_accum": 0.0,
        "emerging_blink": False,
        "emerge_blink_accum": 0.0,
        "frowning": False,
        "frown_accum": 0.0,
    }
    walking_mushroom_blink = make_blink_state(9001, ["◎", "◉"])
    if isinstance(walking_mushroom_house, dict):
        house_x0, _house_y0, _backside = sprite_projection_for_scene(
            walking_mushroom_house,
            0,
            world.landscape_hidden_ground_rows(START_TRAVEL_POSITION),
            world.build_scene_zones(sky_rows=world.landscape_sky_rows(START_TRAVEL_POSITION))["ground_bg"],
            center_object_id,
        ) or (0, 0, False)
        house_width = int(walking_mushroom_house.get("width", 0))
        walking_mushroom["world_x"] = float(max(0, house_x0 + max(0, (house_width // 2) - 3)))
        walking_mushroom["home_world_x"] = float(walking_mushroom["world_x"])
        walking_mushroom["world_row"] = max(0, int(walking_mushroom_house.get("horizon_depth", 27)) + 8)
    walking_fairy_frames = world.build_house_fairy_frames(opponents, color_codes, 16)
    walking_fairy_house = house_sprite_by_label.get("[#12 Ave A]")
    walking_fairy = {
        "world_x": float(TRAVEL_WORLD_WIDTH - 1),
        "world_row": 29,
        "phase_index": 0,
        "anim_accum": 0.0,
        "width": max((len(row) for row in walking_fairy_frames.get("primary", [])), default=0),
        "scared": False,
        "scared_direction": -1,
        "frowning": False,
        "frown_accum": 0.0,
    }
    walking_fairy_blink = make_blink_state(9002, ["◎", "◉"])
    avatar_blink = make_blink_state(9003, ["◎"])
    if isinstance(walking_fairy_house, dict):
        house_x0, _house_y0, _backside = sprite_projection_for_scene(
            walking_fairy_house,
            0,
            world.landscape_hidden_ground_rows(START_TRAVEL_POSITION),
            world.build_scene_zones(sky_rows=world.landscape_sky_rows(START_TRAVEL_POSITION))["ground_bg"],
            center_object_id,
        ) or (0, 0, False)
        house_width = int(walking_fairy_house.get("width", 0))
        walking_fairy["world_x"] = float(max(0, house_x0 + max(0, (house_width // 2) - 2)))
        walking_fairy["world_row"] = max(0, int(walking_fairy_house.get("horizon_depth", 27)) + 4)
    crow_resting_rows = crow_frames.get("resting", [])
    crow_width = max((len(row) for row in crow_resting_rows), default=0)
    crow_states = spawn_intro_crows(
        visible_crow_perches(
            world_treeline_sprites,
            border_treeline_sprites,
            crossroad_house_sprites,
            zones,
            landscape_position,
            center_object_id,
            camera_x,
            crow_width,
            len(crow_resting_rows),
        ),
        crow_frames,
    )
    house_occupant_poses = {}
    for label, occupant_rows in house_occupants.items():
        target_house = house_sprite_by_label.get(label)
        target_art_rows = target_house.get("art", []) if isinstance(target_house, dict) else []
        target_mask_rows = target_house.get("mask_rows", []) if isinstance(target_house, dict) else []
        house_occupant_poses[label] = (
            default_house_occupant_pose(target_art_rows, target_mask_rows, occupant_rows)
            if isinstance(target_art_rows, list) and isinstance(target_mask_rows, list)
            else {"x0": 0, "floor_offset": 1}
        )
    mushroom_motion_rng = random.Random()
    crow_motion_rng = random.Random(9471)
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
        strafe_accum = 0.0
        while True:
            now = time.monotonic()
            dt = max(0.0, min(0.2, now - last_tick))
            last_tick = now
            game_time_seconds += dt
            throw_cooldown = max(0.0, throw_cooldown - dt)
            throw_pose_accum = max(0.0, throw_pose_accum - dt)
            thrown_pebbles = update_thrown_pebbles(thrown_pebbles, dt)
            for label, state in list(house_blink_states.items()):
                house_blink_states[label] = update_blink_state(state, dt)
            walking_mushroom_blink = update_blink_state(walking_mushroom_blink, dt)
            walking_fairy_blink = update_blink_state(walking_fairy_blink, dt)
            avatar_blink = update_blink_state(avatar_blink, dt)
            walking_mushroom = update_walking_mushroom(walking_mushroom, dt)
            walking_fairy = update_walking_fairy(walking_fairy, dt)
            for label, frames in house_fairy_frames.items():
                state = house_fairy_flap_states.get(label, {"active": False, "sequence_index": 0, "accum": 0.0})
                if state.get("active"):
                    state["accum"] = float(state.get("accum", 0.0)) + dt
                    while float(state.get("accum", 0.0)) >= FAIRY_FLAP_STEP_SECONDS and state.get("active"):
                        state["accum"] = float(state.get("accum", 0.0)) - FAIRY_FLAP_STEP_SECONDS
                        next_index = int(state.get("sequence_index", 0)) + 1
                        if next_index >= len(FAIRY_FLAP_SEQUENCE):
                            state["active"] = False
                            state["sequence_index"] = 0
                            state["accum"] = 0.0
                            break
                        state["sequence_index"] = next_index
                    house_fairy_flap_states[label] = state
                phase = FAIRY_FLAP_SEQUENCE[int(state.get("sequence_index", 0))]
                house_occupants[label] = frames.get(phase, frames.get("primary", []))
            for label, frames in house_mushroom_frames.items():
                state = house_mushroom_step_states.get(label, {"active": False, "accum": 0.0, "next_variant": "a", "facing": "front"})
                if state.get("active"):
                    state["accum"] = max(0.0, float(state.get("accum", 0.0)) - dt)
                    if float(state.get("accum", 0.0)) <= 0.0:
                        state["active"] = False
                        idle_label = mushroom_frame_label_for_facing(state.get("facing", "front"), "primary")
                        house_occupants[label] = frames.get(idle_label, frames.get("primary", []))
                house_mushroom_step_states[label] = state

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
                strafe_accum += dt
                while camera_x != target_camera_x and strafe_accum >= SIDE_STEP_SECONDS:
                    strafe_accum -= SIDE_STEP_SECONDS
                    direction = 1 if target_camera_x > camera_x else -1
                    camera_x += direction * min(SIDE_STEP_COLUMNS, abs(target_camera_x - camera_x))
            else:
                strafe_accum = 0.0
            current_visible_perches = visible_crow_perches(
                world_treeline_sprites,
                border_treeline_sprites,
                crossroad_house_sprites,
                zones,
                landscape_position,
                center_object_id,
                camera_x,
                crow_width,
                len(crow_resting_rows),
            )
            crow_states = update_intro_crows(
                crow_states,
                crow_frames,
                dt,
                zones,
                landscape_position,
                center_object_id,
                camera_x,
                current_visible_perches,
                crow_motion_rng,
            )
            crow_states, thrown_pebbles = handle_crow_hits(
                crow_states,
                crow_frames,
                thrown_pebbles,
                zones,
                landscape_position,
                center_object_id,
                camera_x,
                current_visible_perches,
                crow_motion_rng,
            )
            walking_mushroom, thrown_pebbles = handle_walking_mushroom_hits(
                walking_mushroom,
                walking_mushroom_frames,
                thrown_pebbles,
                zones,
                landscape_position,
                camera_x,
            )
            walking_fairy, thrown_pebbles = handle_walking_fairy_hits(
                walking_fairy,
                walking_fairy_frames,
                thrown_pebbles,
                zones,
                landscape_position,
                camera_x,
                avatar_feet_world_x(avatar_rows, camera_x),
            )
            mushroom_motion_accum += dt
            while mushroom_motion_accum >= 1.0:
                mushroom_motion_accum -= 1.0
                for label, occupant_rows in house_occupants.items():
                    target_house = house_sprite_by_label.get(label)
                    target_art_rows = target_house.get("art", []) if isinstance(target_house, dict) else []
                    target_mask_rows = target_house.get("mask_rows", []) if isinstance(target_house, dict) else []
                    if isinstance(target_art_rows, list) and isinstance(target_mask_rows, list) and target_art_rows and target_mask_rows:
                        prior_pose = house_occupant_poses.get(label, {"x0": 0, "floor_offset": 1})
                        updated_pose = step_house_occupant_pose(
                            target_art_rows,
                            target_mask_rows,
                            occupant_rows,
                            prior_pose,
                            mushroom_motion_rng,
                        )
                        house_occupant_poses[label] = updated_pose
                        if label in house_mushroom_frames and updated_pose != prior_pose:
                            state = house_mushroom_step_states.get(label, {"active": False, "accum": 0.0, "next_variant": "a", "facing": "front"})
                            prior_floor = int(prior_pose.get("floor_offset", 1))
                            updated_floor = int(updated_pose.get("floor_offset", 1))
                            if updated_floor > prior_floor:
                                state["facing"] = "back"
                            elif updated_floor < prior_floor:
                                state["facing"] = "front"
                            variant = str(state.get("next_variant", "a"))
                            frames = house_mushroom_frames[label]
                            variant_label = mushroom_frame_label_for_facing(state.get("facing", "front"), variant)
                            house_occupants[label] = frames.get(variant_label, frames.get(variant, frames.get("primary", [])))
                            state["active"] = True
                            state["accum"] = MUSHROOM_STEP_POSE_SECONDS
                            state["next_variant"] = "b" if variant == "a" else "a"
                            house_mushroom_step_states[label] = state
                        if label in house_fairy_frames and updated_pose != prior_pose:
                            house_fairy_flap_states[label] = {"active": True, "sequence_index": 0, "accum": 0.0}
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
                avatar_forward_facing = "back"
                candidate = target_landscape_position - 1
                if candidate < world.LANDSCAPE_STEP_ROWS:
                    candidate = world.LANDSCAPE_TOTAL_GROUND_ROWS
                candidate_zones = world.build_scene_zones(sky_rows=world.landscape_sky_rows(candidate))
                if is_camera_on_walkable_surface(camera_x, avatar_rows, candidate_zones, candidate):
                    target_landscape_position = candidate
            if key == "down":
                avatar_facing = "front"
                avatar_forward_facing = "front"
                candidate = target_landscape_position + 1
                if candidate > world.LANDSCAPE_TOTAL_GROUND_ROWS:
                    candidate = world.LANDSCAPE_STEP_ROWS
                candidate_zones = world.build_scene_zones(sky_rows=world.landscape_sky_rows(candidate))
                if is_camera_on_walkable_surface(camera_x, avatar_rows, candidate_zones, candidate):
                    target_landscape_position = candidate
            if key == "left":
                avatar_facing = "left"
                candidate = max(0, target_camera_x - SIDE_TARGET_COLUMNS)
                if is_camera_on_walkable_surface(candidate, avatar_rows, zones, landscape_position):
                    target_camera_x = candidate
            if key == "right":
                avatar_facing = "right"
                candidate = min(TRAVEL_WORLD_WIDTH - world.SCREEN_W, target_camera_x + SIDE_TARGET_COLUMNS)
                if is_camera_on_walkable_surface(candidate, avatar_rows, zones, landscape_position):
                    target_camera_x = candidate
            if key == "a":
                avatar_index = (avatar_index + 1) % len(avatar_ids)
                avatar_rows = world.build_player_frame(players, avatar_ids[avatar_index], color_codes, avatar_facing, "idle")
                target_camera_x = clamp_camera_to_road(target_camera_x, avatar_rows, zones, landscape_position)
                camera_x = clamp_camera_to_road(camera_x, avatar_rows, zones, landscape_position)
                walk_frame_index = 0
                walk_frame_accum = 0.0
                idle_reset_accum = WALK_RESET_IDLE_SECONDS
                was_avatar_moving = False
            if key == "c":
                scene_index = (scene_index + 1) % len(WORLD_MODELS)
                scene_label, center_object_id = WORLD_MODELS[scene_index]
                world_treeline_sprites = [recenter_sprite_x(sprite) for sprite in world.build_world_treeline_sprites(objects, colors, center_object_id)]
                border_treeline_sprites = [recenter_border_sprite_x(sprite) for sprite in world.build_border_treeline_sprites(objects, colors)]
                crossroad_house_sprites = world.build_crossroad_house_sprites(objects, colors)
                house_sprite_by_label = {
                    str(sprite.get("label", "")).strip(): sprite
                    for sprite in crossroad_house_sprites
                    if str(sprite.get("label", "")).strip()
                }
                for label, occupant_rows in house_occupants.items():
                    target_house = house_sprite_by_label.get(label)
                    target_art_rows = target_house.get("art", []) if isinstance(target_house, dict) else []
                    target_mask_rows = target_house.get("mask_rows", []) if isinstance(target_house, dict) else []
                    if isinstance(target_art_rows, list) and isinstance(target_mask_rows, list) and target_art_rows and target_mask_rows:
                        house_occupant_poses[label] = clamp_house_occupant_pose(
                            target_art_rows,
                            target_mask_rows,
                            occupant_rows,
                            house_occupant_poses.get(label, {"x0": 0, "floor_offset": 1}),
                        )
                crow_states = []
            if key == "t" and pebble_count > 0 and throw_cooldown <= 0.0:
                throw_phase = throw_pose_for_facing(avatar_facing)
                throw_rows = world.build_player_frame(players, avatar_ids[avatar_index], color_codes, avatar_facing, throw_phase)
                thrown_pebbles.append(
                    spawn_thrown_pebble(
                        throw_rows,
                        camera_x,
                        zones,
                        landscape_position,
                        avatar_facing,
                    )
                )
                pebble_count -= 1
                throw_cooldown = THROW_COOLDOWN_SECONDS
                throw_pose_accum = THROW_POSE_SECONDS
            avatar_is_moving = (camera_x != target_camera_x) or (landscape_position != target_landscape_position)
            if avatar_is_moving:
                if not was_avatar_moving:
                    walk_frame_index = 3 if last_walk_step_phase == "step_a" else 1
                    walk_frame_accum = 0.0
                idle_reset_accum = 0.0
                walk_frame_accum += dt
                while walk_frame_accum >= WALK_FRAME_STEP_SECONDS:
                    walk_frame_accum -= WALK_FRAME_STEP_SECONDS
                    walk_frame_index = (walk_frame_index + 1) % len(WALK_FRAME_SEQUENCE)
            else:
                if was_avatar_moving and WALK_FRAME_SEQUENCE[walk_frame_index] in {"step_a", "step_b"}:
                    last_walk_step_phase = WALK_FRAME_SEQUENCE[walk_frame_index]
                idle_reset_accum += dt
                if idle_reset_accum >= WALK_RESET_IDLE_SECONDS:
                    walk_frame_index = 0
                    walk_frame_accum = 0.0
            avatar_phase = WALK_FRAME_SEQUENCE[walk_frame_index]
            if throw_pose_accum > 0.0:
                avatar_phase = throw_pose_for_facing(avatar_facing)
            if avatar_phase in {"step_a", "step_b"}:
                last_walk_step_phase = avatar_phase
            was_avatar_moving = avatar_is_moving
            avatar_rows = world.build_player_frame(players, avatar_ids[avatar_index], color_codes, avatar_facing, avatar_phase)
            pebble_count += collect_overlapping_pebbles(
                collectible_pebbles,
                avatar_rows,
                camera_x,
                zones,
                landscape_position,
            )

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
                avatar_facing=avatar_facing,
                house_occupants=house_occupants,
                house_blink_states=house_blink_states,
                house_occupant_poses=house_occupant_poses,
                house_window_objects=house_window_objects,
                walking_mushroom_frames=walking_mushroom_frames,
                walking_mushroom=walking_mushroom,
                walking_mushroom_blink=walking_mushroom_blink,
                walking_fairy_frames=walking_fairy_frames,
                walking_fairy=walking_fairy,
                walking_fairy_blink=walking_fairy_blink,
                collectible_pebbles=collectible_pebbles,
                thrown_pebbles=thrown_pebbles,
                pebble_count=pebble_count,
                throw_cooldown=throw_cooldown,
                game_time_seconds=game_time_seconds,
                address_label=current_address_label(landscape_position),
                scene_label=scene_label,
                center_object_id=center_object_id,
                camera_x=camera_x,
                avatar_blink=avatar_blink,
                crow_frames=crow_frames,
                crow_states=crow_states,
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
