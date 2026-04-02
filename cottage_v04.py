import os
import random
import re
import time
import textwrap
from dataclasses import dataclass
from typing import Dict, List

from battle_scene import (
    ANSI_CLEAR,
    ANSI_HIDE_CURSOR,
    ANSI_HOME,
    ANSI_RESET,
    ANSI_SHOW_CURSOR,
    SCREEN_H,
    SCREEN_W,
    ansi_line_to_cells,
    cloud_templates,
    load_json,
    read_key_nonblocking as base_read_key_nonblocking,
)


LAYER_BACKGROUND = 0
LAYER_WORLD = 4
LAYER_FOREGROUND = 8
LAYER_UI = 12
LANDSCAPE_STEP_ROWS = 5
LANDSCAPE_MIN_SKY_ROWS = 5
LANDSCAPE_MAX_SKY_ROWS = 25
LANDSCAPE_VISIBLE_GROUND_ROWS = 25
LANDSCAPE_TOTAL_GROUND_ROWS = 200
LANDSCAPE_STATE_COUNT = LANDSCAPE_TOTAL_GROUND_ROWS // LANDSCAPE_STEP_ROWS
SKY_LAYER_HEIGHT = 124
SKY_LAYER_BASE_BOTTOM = 24
ROAD_BASE_WIDTH = 7
ROAD_EXPAND_ROWS = 15
CROSSROAD_INTERVAL_ROWS = 30
CROSSROAD_DIRT_ROWS = 5
MAIN_STREET_NAME = "Main Street"
TREELINE_ROWS = 3
DEFAULT_LANDSCAPE_POSITION = 15
UI_DEMO_TEXT = "Eenie, Meenie, Miney, Mo.\nWho here dares to be our foe!?"
UI_DIALOG_TEXT = "So what do you say... Are you ready to challenge them?"
WORLD_SCENE_VARIANTS = [
    ("cottage", "house_02"),
    ("fairy_castle", "fairy_castle"),
    ("bridge", "bridge"),
    ("mushroom_house", "mushroom_house"),
]


@dataclass(frozen=True)
class LayoutZone:
    name: str
    x: int
    y: int
    width: int
    height: int
    layer: int

    @property
    def x1(self) -> int:
        return self.x + max(0, self.width) - 1

    @property
    def y1(self) -> int:
        return self.y + max(0, self.height) - 1


def read_key_nonblocking() -> str | None:
    if os.name == "nt":
        import msvcrt

        if not msvcrt.kbhit():
            return None
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            ext = msvcrt.getch()
            if ext == b"H":
                return "up"
            if ext == b"P":
                return "down"
            if ext == b"K":
                return "left"
            if ext == b"M":
                return "right"
            return None
        try:
            return ch.decode("utf-8").lower()
        except UnicodeDecodeError:
            return None
    return base_read_key_nonblocking()


def _make_zone(name: str, x: int, y: int, width: int, height: int, layer: int) -> LayoutZone:
    x = max(0, min(SCREEN_W, x))
    y = max(0, min(SCREEN_H, y))
    width = max(0, min(width, SCREEN_W - x))
    height = max(0, min(height, SCREEN_H - y))
    return LayoutZone(name=name, x=x, y=y, width=width, height=height, layer=layer)


def _anchored_x_with_overflow_guard(center_x: int, width: int) -> int:
    # Keep centered intent, but if overflow would occur, shift inward until fully visible.
    x = int(center_x) - (max(0, int(width)) // 2)
    max_x = max(0, SCREEN_W - max(0, int(width)))
    return max(0, min(max_x, x))


def build_scene_zones(sky_rows: int) -> Dict[str, LayoutZone]:
    sky_height = max(1, min(SCREEN_H - 1, int(sky_rows)))
    ground_height = SCREEN_H - sky_height
    return {
        "sky_bg": _make_zone("sky_bg", 0, 0, SCREEN_W, sky_height, LAYER_BACKGROUND),
        "ground_bg": _make_zone("ground_bg", 0, sky_height, SCREEN_W, ground_height, LAYER_BACKGROUND),
    }


def landscape_total_ground_visible_from_horizon(position: int) -> int:
    total_ground = int(round(float(position)))
    return max(LANDSCAPE_STEP_ROWS, min(LANDSCAPE_TOTAL_GROUND_ROWS, total_ground))


def landscape_sky_rows(position: int) -> int:
    sky_rows = LANDSCAPE_MAX_SKY_ROWS - (landscape_total_ground_visible_from_horizon(position) - LANDSCAPE_STEP_ROWS)
    return max(LANDSCAPE_MIN_SKY_ROWS, sky_rows)


def landscape_visible_ground_rows(position: int) -> int:
    return min(LANDSCAPE_VISIBLE_GROUND_ROWS, landscape_total_ground_visible_from_horizon(position))


def landscape_ground_window_start(position: int) -> int:
    total_ground = landscape_total_ground_visible_from_horizon(position)
    return max(0, total_ground - landscape_visible_ground_rows(position))


def landscape_ground_window_end(position: int) -> int:
    return min(LANDSCAPE_TOTAL_GROUND_ROWS, landscape_ground_window_start(position) + landscape_visible_ground_rows(position))


def landscape_hidden_ground_rows(position: int) -> int:
    return max(0, landscape_total_ground_visible_from_horizon(position) - landscape_visible_ground_rows(position))


def landscape_is_backside(position: int) -> bool:
    return landscape_hidden_ground_rows(position) > 0


def horizon_depth_state(depth_index: int, hidden_ground_rows: int, ground_top_y: int) -> tuple[bool, int]:
    depth = max(0, int(depth_index))
    hidden = max(0, int(hidden_ground_rows))
    if hidden <= depth:
        return (False, ground_top_y + (depth - hidden))
    return (True, ground_top_y + ((hidden - depth) // 2))


def road_width_for_horizon_distance(distance_from_horizon: int) -> int:
    distance = max(0, int(distance_from_horizon))
    perspective_row = min(distance, max(0, ROAD_EXPAND_ROWS - 1))
    expand_steps = perspective_row // 2
    return min(SCREEN_W, ROAD_BASE_WIDTH + (expand_steps * 2))


def road_geometry_for_horizon_distance(distance_from_horizon: int) -> dict:
    road_width = road_width_for_horizon_distance(distance_from_horizon)
    road_half = road_width // 2
    road_center = (SCREEN_W - 1) // 2
    road_start = max(0, road_center - road_half)
    road_end = min(SCREEN_W - 1, road_start + road_width - 1)
    left_push = road_width // 2
    right_push = road_width - left_push
    return {
        "width": road_width,
        "start": road_start,
        "end": road_end,
        "left_push": left_push,
        "right_push": right_push,
    }


def build_road_pushed_row(base_cells: List[str], road_width: int, row_seed: int, crossroad_phase: str | None = None) -> List[str]:
    cells = list(base_cells[:SCREEN_W])
    if len(cells) < SCREEN_W:
        cells.extend([" "] * (SCREEN_W - len(cells)))
    road_width = max(1, min(SCREEN_W, int(road_width)))
    road_half = road_width // 2
    road_center = (SCREEN_W - 1) // 2
    road_start = max(0, road_center - road_half)
    road_end = min(SCREEN_W - 1, road_start + road_width - 1)
    left_push = road_width // 2
    right_push = road_width - left_push
    road_rng = random.Random(row_seed)
    road_chars = [".", ",", "'", "`"]
    road_color = "[38;2;170;170;170m"
    stone_glyphs = ["o", "O"]
    stone_colors = [
        "[38;2;185;185;185m",
        "[38;2;140;140;140m",
    ]
    out = [" " for _ in range(SCREEN_W)]

    for x in range(road_start):
        src_x = min(SCREEN_W - 1, x + left_push)
        out[x] = cells[src_x]
    for x in range(road_end + 1, SCREEN_W):
        src_x = max(0, x - right_push)
        out[x] = cells[src_x]
    for x in range(road_start, road_end + 1):
        out[x] = f"{road_color}{road_rng.choice(road_chars)}{ANSI_RESET}"
    if road_start - 1 >= 0:
        if crossroad_phase is None:
            left_idx = road_rng.randrange(len(stone_glyphs))
            out[road_start - 1] = f"{stone_colors[left_idx]}{stone_glyphs[left_idx]}{ANSI_RESET}"
        else:
            out[road_start - 1] = f"{road_color}{road_rng.choice(road_chars)}{ANSI_RESET}"
    if road_end + 1 < SCREEN_W:
        if crossroad_phase is None:
            right_idx = road_rng.randrange(len(stone_glyphs))
            out[road_end + 1] = f"{stone_colors[right_idx]}{stone_glyphs[right_idx]}{ANSI_RESET}"
        else:
            out[road_end + 1] = f"{road_color}{road_rng.choice(road_chars)}{ANSI_RESET}"
    return out


def crossroad_row_phase(world_row: int) -> str | None:
    row = int(world_row)
    if row < CROSSROAD_INTERVAL_ROWS:
        return None
    offset = row % CROSSROAD_INTERVAL_ROWS
    if offset == 0 or offset == CROSSROAD_DIRT_ROWS + 1:
        return "stone"
    if 1 <= offset <= CROSSROAD_DIRT_ROWS:
        return "dirt"
    return None


def overlay_crossroad_row(base_cells: List[str], world_row: int, row_seed: int) -> List[str]:
    phase = crossroad_row_phase(world_row)
    if phase is None:
        return list(base_cells)
    out = list(base_cells[:SCREEN_W])
    if len(out) < SCREEN_W:
        out.extend([" "] * (SCREEN_W - len(out)))
    rng = random.Random(row_seed)
    if phase == "stone":
        stone_glyphs = ["o", "O"]
        stone_colors = [
            "[38;2;185;185;185m",
            "[38;2;140;140;140m",
        ]
        for x in range(SCREEN_W):
            idx = rng.randrange(len(stone_glyphs))
            out[x] = f"{stone_colors[idx]}{stone_glyphs[idx]}{ANSI_RESET}"
        return out
    dirt_chars = [".", ",", "'", "`"]
    dirt_color = "[38;2;170;170;170m"
    for x in range(SCREEN_W):
        out[x] = f"{dirt_color}{rng.choice(dirt_chars)}{ANSI_RESET}"
    return out


def _colorize_glyph(glyph: str, key: str, color_codes: Dict[str, str]) -> str:
    code = color_codes.get(key, "")
    return f"{code}{glyph}{ANSI_RESET}" if code else glyph


def build_ground_rows(
    row_count: int,
    objects_data: object,
    color_codes: Dict[str, str],
    pebble_density: float = 0.07,
) -> List[str]:
    rng = random.Random(9051701)
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
    base_road_width = 7
    road_expand_rows = 15
    # Match centered object parity so road aligns with centered house anchor.
    road_center = (SCREEN_W - 1) // 2
    road_chars = [".", ",", "'", "`"]
    road_color = "\x1b[38;2;170;170;170m"

    for row_idx in range(max(0, row_count)):
        # Perspective widens only through the near 15 rows, then holds at max width.
        perspective_row = min(row_idx, max(0, road_expand_rows - 1))
        expand_steps = perspective_row // 2
        road_width = min(SCREEN_W, base_road_width + (expand_steps * 2))
        road_half = road_width // 2
        road_start = max(0, road_center - road_half)
        road_end = min(SCREEN_W - 1, road_start + road_width - 1)
        row: List[str] = []
        for x in range(SCREEN_W):
            base_glyph = grass_pattern[x % max(1, len(grass_pattern))]
            base_key = grass_mask[x % max(1, len(grass_mask))]
            cell = _colorize_glyph(base_glyph, base_key, color_codes)
            if rng.random() < density:
                glyph = rng.choice(pebble_glyphs)
                key = rng.choice(pebble_keys)
                cell = _colorize_glyph(glyph, key, color_codes)
            row.append(cell)
        rows.append("".join(row))
    return rows


def _cloud_speed(size: str, y: int, field_height: int, rng: random.Random) -> float:
    size_weight = {"large": 0.72, "medium": 1.0, "small": 1.28}.get(size, 1.0)
    y_norm = max(0.0, min(1.0, y / max(1, field_height - 1)))
    height_weight = 0.72 + (0.62 * y_norm)
    variance = 1.0 + (rng.random() * 3.0)
    return 0.25 * size_weight * height_weight * variance


def spawn_clouds_full_canvas(templates: List[dict]) -> List[dict]:
    rng = random.Random(14113)
    clouds: List[dict] = []
    if not templates:
        return clouds
    count = max(20, min(72, int(round((SCREEN_W * SKY_LAYER_HEIGHT) / 240.0))))
    for _ in range(count):
        template = templates[rng.randrange(len(templates))]
        w = int(template["width"])
        h = int(template["height"])
        y_max = max(0, SKY_LAYER_HEIGHT - h)
        y = rng.randint(0, y_max) if y_max > 0 else 0
        x = rng.randint(-max(1, w // 2), SCREEN_W - 1)
        speed = _cloud_speed(str(template.get("size", "medium")), y, SKY_LAYER_HEIGHT, rng)
        clouds.append({"template": template, "x": float(x), "y": float(y), "speed": speed})
    return clouds


def sky_bottom_anchor_for_position(landscape_position: int) -> int:
    total_ground = landscape_total_ground_visible_from_horizon(landscape_position)
    ground_rise = max(0, total_ground - LANDSCAPE_STEP_ROWS)
    anchor = SKY_LAYER_BASE_BOTTOM + (ground_rise // 2)
    return max(0, min(SKY_LAYER_HEIGHT - 1, anchor))


def _hex_to_rgb(hex_value: str) -> tuple[int, int, int]:
    value = hex_value.strip().lstrip("#")
    if len(value) != 6:
        return (255, 255, 255)
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _build_color_codes(colors_data: object) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not isinstance(colors_data, dict):
        return out
    for key, payload in colors_data.items():
        if not isinstance(key, str) or len(key) != 1 or not isinstance(payload, dict):
            continue
        hex_value = payload.get("hex")
        if not isinstance(hex_value, str):
            continue
        r, g, b = _hex_to_rgb(hex_value)
        out[key] = f"\x1b[38;2;{r};{g};{b}m"
    return out


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _colorize_object_rows(art_rows: object, mask_rows: object, color_codes: Dict[str, str]) -> List[List[str]]:
    if not isinstance(art_rows, list) or not art_rows:
        return []
    if not isinstance(mask_rows, list):
        mask_rows = []
    width = max((len(str(line)) for line in art_rows), default=0)
    out: List[List[str]] = []
    opaque_space = f"\x1b[37m {ANSI_RESET}"
    for y, raw in enumerate(art_rows):
        art = str(raw).ljust(width)
        mask = str(mask_rows[y]) if y < len(mask_rows) else ""
        row: List[str] = []
        for x, ch in enumerate(art):
            key = mask[x] if x < len(mask) else ""
            if key == "!":
                row.append(opaque_space)
                continue
            if ch == " ":
                row.append(" ")
                continue
            code = color_codes.get(key, "")
            row.append(f"{code}{ch}{ANSI_RESET}" if code else ch)
        out.append(row)
    return out


HOUSE_ACCENT_PALETTES: List[tuple[tuple[int, int, int], tuple[int, int, int]]] = [
    ((250, 95, 95), (209, 46, 46)),
    ((250, 132, 95), (214, 82, 40)),
    ((250, 170, 95), (214, 116, 36)),
    ((250, 208, 95), (206, 152, 32)),
    ((242, 250, 95), (201, 209, 46)),
    ((186, 242, 95), (141, 194, 44)),
    ((128, 240, 88), (83, 191, 40)),
    ((95, 250, 151), (46, 209, 105)),
    ((95, 242, 190), (45, 190, 144)),
    ((95, 238, 228), (44, 187, 176)),
    ((95, 228, 250), (42, 178, 201)),
    ((95, 196, 250), (44, 146, 204)),
    ((95, 146, 250), (46, 100, 209)),
    ((118, 118, 250), (68, 68, 210)),
    ((156, 110, 250), (108, 62, 208)),
    ((198, 108, 250), (149, 58, 206)),
    ((247, 95, 250), (206, 46, 209)),
    ((250, 95, 192), (210, 46, 149)),
    ((250, 110, 148), (209, 58, 106)),
    ((245, 186, 92), (201, 143, 44)),
]
HOUSE_ACCENT_PERMUTATION: List[int] = [0, 10, 5, 15, 2, 12, 7, 17, 4, 14, 9, 19, 1, 11, 6, 16, 3, 13, 8, 18]


def _ansi_color_code(r: int, g: int, b: int) -> str:
    return f"\x1b[38;2;{max(0, min(255, int(r)))};{max(0, min(255, int(g)))};{max(0, min(255, int(b)))}m"


def _house_accent_color_codes(base_color_codes: Dict[str, str], house_number: int) -> Dict[str, str]:
    updated = dict(base_color_codes)
    house_index = max(0, min(19, int(house_number) - 1))
    palette_index = HOUSE_ACCENT_PERMUTATION[house_index]
    bright_rgb, base_rgb = HOUSE_ACCENT_PALETTES[palette_index]
    updated["B"] = _ansi_color_code(*bright_rgb)
    updated["b"] = _ansi_color_code(*base_rgb)
    return updated


def house_palette_index(house_number: int) -> int:
    house_index = max(0, min(19, int(house_number) - 1))
    return HOUSE_ACCENT_PERMUTATION[house_index]


def mushroom_palette_indices_for_house(house_number: int) -> tuple[int, int]:
    house_index = max(0, min(19, int(house_number) - 1))
    accent_index = HOUSE_ACCENT_PERMUTATION[(house_index + 7) % len(HOUSE_ACCENT_PERMUTATION)]
    eye_index = HOUSE_ACCENT_PERMUTATION[(house_index + 13) % len(HOUSE_ACCENT_PERMUTATION)]
    return accent_index, eye_index


def fairy_palette_indices_for_house(house_number: int) -> tuple[int, int]:
    house_index = max(0, min(19, int(house_number) - 1))
    wing_index = HOUSE_ACCENT_PERMUTATION[(house_index + 5) % len(HOUSE_ACCENT_PERMUTATION)]
    eye_index = HOUSE_ACCENT_PERMUTATION[(house_index + 11) % len(HOUSE_ACCENT_PERMUTATION)]
    return wing_index, eye_index


def _with_color_overrides(color_codes: Dict[str, str], overrides: Dict[str, str]) -> Dict[str, str]:
    updated = dict(color_codes)
    updated.update(overrides)
    return updated


def build_world_object_sprite(objects_data: object, colors_data: object, object_id: str) -> dict | None:
    if not isinstance(objects_data, dict):
        return None
    payload = objects_data.get(object_id, {})
    if not isinstance(payload, dict):
        return None
    color_codes = _build_color_codes(colors_data)
    art = payload.get("art", [])
    mask = payload.get("color_mask", [])
    rows = _colorize_object_rows(art, mask, color_codes)
    if not rows:
        return None
    width = len(rows[0])
    return {
        "width": width,
        "height": len(rows),
        "rows": rows,
    }


def avenue_name(index: int) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    value = max(0, int(index))
    if value < len(alphabet):
        return f"Ave {alphabet[value]}"
    return f"Ave {alphabet[value % len(alphabet)]}{(value // len(alphabet)) + 1}"


def build_crossroad_house_sprites(objects_data: object, colors_data: object) -> List[dict]:
    if not isinstance(objects_data, dict):
        return []
    house_payload = objects_data.get("house_02", {})
    if not isinstance(house_payload, dict):
        return []
    base_house = build_world_object_sprite(objects_data, colors_data, "house_02")
    if base_house is None:
        return []
    sprites: List[dict] = []
    street_index = 0
    house_width = int(base_house.get("width", 0))
    house_art = house_payload.get("art", [])
    house_mask = house_payload.get("color_mask", [])
    color_codes = _build_color_codes(colors_data)
    tree_ids = [obj_id for obj_id in ["tree_large", "tree_large_2", "tree_large_3"] if isinstance(objects_data.get(obj_id), dict)]
    tree_rng = random.Random(88241)

    def build_tree_sprite(obj_id: str) -> dict | None:
        payload = objects_data.get(obj_id, {})
        if not isinstance(payload, dict):
            return None
        art = payload.get("art", [])
        mask = payload.get("color_mask", [])
        rows = _colorize_object_rows(art, mask, color_codes)
        if not rows:
            return None
        return {
            "width": len(rows[0]),
            "height": len(rows),
            "rows": rows,
        }

    def add_house(side: str, horizon_depth: int, label: str, house_number: int, side_slot: int, lateral_offset: int = 0) -> None:
        accent_codes = _house_accent_color_codes(color_codes, house_number)
        rows = _colorize_object_rows(house_art, house_mask, accent_codes)
        sprites.append({
            "side": side,
            "side_slot": max(0, int(side_slot)),
            "side_offset": int(lateral_offset),
            "horizon_depth": max(0, min(LANDSCAPE_TOTAL_GROUND_ROWS - 1, int(horizon_depth))),
            "street_name": street_name,
            "main_street": MAIN_STREET_NAME,
            "label": label,
            "width": house_width,
            "height": len(rows) if rows else int(base_house.get("height", 0)),
            "rows": rows if rows else base_house.get("rows", []),
            "art": list(house_art) if isinstance(house_art, list) else [],
            "mask_rows": list(house_mask) if isinstance(house_mask, list) else [],
        })

    def house_left_offset(side: str, side_slot: int, lateral_offset: int) -> int:
        side_gap = house_width + 12
        if side == "left":
            return -house_width - 8 - (side_slot * side_gap) + lateral_offset
        return 8 + (side_slot * side_gap) + lateral_offset

    def add_interhouse_tree(side: str, horizon_depth: int, left_house_number: int, left_slot: int, left_offset: int, right_slot: int, right_offset: int) -> None:
        if not tree_ids:
            return
        tree_id = tree_ids[tree_rng.randrange(len(tree_ids))]
        tree_sprite = build_tree_sprite(tree_id)
        if tree_sprite is None:
            return
        tree_width = int(tree_sprite.get("width", 0))
        left_x = house_left_offset(side, left_slot, left_offset)
        right_x = house_left_offset(side, right_slot, right_offset)
        gap_start = left_x + house_width
        gap_width = max(0, right_x - gap_start)
        tree_x = gap_start + max(0, (gap_width - tree_width) // 2)
        sprites.append({
            "side": side,
            "road_anchor": "start" if side == "left" else "end",
            "road_offset": int(tree_x),
            "horizon_depth": max(0, min(LANDSCAPE_TOTAL_GROUND_ROWS - 1, int(horizon_depth))),
            "street_name": street_name,
            "main_street": MAIN_STREET_NAME,
            "width": tree_width,
            "height": int(tree_sprite.get("height", 0)),
            "rows": tree_sprite.get("rows", []),
        })

    for crossroad_start in range(CROSSROAD_INTERVAL_ROWS, LANDSCAPE_TOTAL_GROUND_ROWS, CROSSROAD_INTERVAL_ROWS):
        street_name = avenue_name(street_index)
        above_depth = crossroad_start - 3
        if above_depth >= 0:
            # Keep all avenue houses on the north side instead of splitting by parity.
            for house_number in range(1, 11):
                slot = 10 - house_number
                lateral_offset = -18 + ((house_number - 1) * 2)
                add_house("left", above_depth, f"[#{house_number} {street_name}]", house_number, slot, lateral_offset=lateral_offset)
                if house_number < 10:
                    next_slot = 10 - (house_number + 1)
                    next_offset = -18 + (house_number * 2)
                    add_interhouse_tree("left", above_depth, house_number, slot, lateral_offset, next_slot, next_offset)
            for house_number in range(11, 21):
                slot = house_number - 11
                lateral_offset = (house_number - 11) * 2
                add_house("right", above_depth, f"[#{house_number} {street_name}]", house_number, slot, lateral_offset=lateral_offset)
                if house_number < 20:
                    next_slot = (house_number + 1) - 11
                    next_offset = (house_number + 1 - 11) * 2
                    add_interhouse_tree("right", above_depth, house_number, slot, lateral_offset, next_slot, next_offset)
        street_index += 1
    return sprites


def build_world_treeline_sprites(
    objects_data: object,
    colors_data: object,
    center_object_id: str = "house_02",
) -> List[dict]:
    if not isinstance(objects_data, dict):
        return []
    color_codes = _build_color_codes(colors_data)
    tree_ids = [obj_id for obj_id in ["tree_large", "tree_large_2", "tree_large_3"] if isinstance(objects_data.get(obj_id), dict)]
    center_obj = objects_data.get(center_object_id, {})
    if not tree_ids or not isinstance(center_obj, dict):
        return []
    rng = random.Random(6611)
    sprites: List[dict] = []

    def make_sprite(obj_id: str, x: int, anchor_offset: int = 0) -> dict | None:
        payload = objects_data.get(obj_id, {})
        if not isinstance(payload, dict):
            return None
        art = payload.get("art", [])
        mask = payload.get("color_mask", [])
        rows = _colorize_object_rows(art, mask, color_codes)
        if not rows:
            return None
        width = len(rows[0])
        return {
            "x": x,
            "width": width,
            "height": len(rows),
            "rows": rows,
            "anchor_offset": max(0, min(TREELINE_ROWS - 1, int(anchor_offset))),
        }

    # Centered focal world object (cottage/castle/bridge/mushroom house).
    center_sprite = make_sprite(center_object_id, 0, anchor_offset=0)
    if center_sprite is None:
        return []
    center_w = int(center_sprite.get("width", 0))
    center_x = (SCREEN_W - center_w) // 2
    center_sprite["x"] = center_x
    sprites.append(center_sprite)

    # Trees on left and right sides of the centered focal object.
    left_cursor = center_x - 3
    right_cursor = center_x + center_w + 2
    side_tree_count = 3

    for _ in range(side_tree_count):
        tree_id = tree_ids[rng.randrange(len(tree_ids))]
        probe = make_sprite(tree_id, 0, anchor_offset=rng.randint(0, TREELINE_ROWS - 1))
        if probe is None:
            continue
        tw = int(probe.get("width", 0))
        left_x = left_cursor - tw
        probe["x"] = left_x
        if left_x + tw > 0:
            sprites.append(probe)
        left_cursor = left_x - rng.randint(1, 4)

    for _ in range(side_tree_count):
        tree_id = tree_ids[rng.randrange(len(tree_ids))]
        probe = make_sprite(tree_id, right_cursor, anchor_offset=rng.randint(0, TREELINE_ROWS - 1))
        if probe is None:
            continue
        if int(probe.get("x", 0)) < SCREEN_W:
            sprites.append(probe)
        right_cursor = int(probe.get("x", 0)) + int(probe.get("width", 0)) + rng.randint(1, 4)

    # Draw from left to right for deterministic overdraw.
    sprites.sort(key=lambda s: int(s.get("x", 0)))
    return sprites


def build_border_treeline_sprites(objects_data: object, colors_data: object) -> List[dict]:
    if not isinstance(objects_data, dict):
        return []
    color_codes = _build_color_codes(colors_data)
    tree_ids = [obj_id for obj_id in ["tree_large", "tree_large_2", "tree_large_3"] if isinstance(objects_data.get(obj_id), dict)]
    if not tree_ids:
        return []
    rng = random.Random(77421)
    sprites: List[dict] = []

    def make_tree(obj_id: str, side: str, column_band: int, horizon_depth: int, column_jitter: int) -> dict | None:
        payload = objects_data.get(obj_id, {})
        if not isinstance(payload, dict):
            return None
        art = payload.get("art", [])
        mask = payload.get("color_mask", [])
        rows = _colorize_object_rows(art, mask, color_codes)
        if not rows:
            return None
        width = len(rows[0])
        return {
            "side": side,
            "side_column": max(0, min(2, int(column_band))),
            "side_jitter": max(-1, min(1, int(column_jitter))),
            "horizon_depth": max(0, int(horizon_depth)),
            "width": width,
            "height": len(rows),
            "rows": rows,
        }

    for side in ("left", "right"):
        depth = rng.randint(5, 7)
        while depth < LANDSCAPE_TOTAL_GROUND_ROWS:
            tree_id = tree_ids[rng.randrange(len(tree_ids))]
            sprite = make_tree(tree_id, side, rng.randint(0, 2), depth, rng.randint(-1, 1))
            if sprite is not None:
                sprites.append(sprite)
            depth += rng.randint(5, 7)
    return sprites


def build_mushy_sprite(opponents_data: object, color_codes: Dict[str, str]) -> List[List[str]]:
    if not isinstance(opponents_data, dict):
        return []
    base_opponents = opponents_data.get("base_opponents", {})
    if not isinstance(base_opponents, dict):
        return []
    mushy = base_opponents.get("mushroom_baby", {})
    if not isinstance(mushy, dict):
        return []
    art = mushy.get("art", [])
    mask = mushy.get("color_map", [])
    if not isinstance(art, list) or not art:
        return []
    if not isinstance(mask, list):
        mask = []
    width = max((len(str(line)) for line in art), default=0)
    out: List[List[str]] = []
    for y, raw in enumerate(art):
        line = str(raw).ljust(width)
        mask_line = str(mask[y]) if y < len(mask) else ""
        row: List[str] = []
        for x, ch in enumerate(line):
            if ch == " ":
                row.append(" ")
                continue
            key = mask_line[x] if x < len(mask_line) else ""
            if key == "!":
                row.append(ch)
                continue
            code = color_codes.get(key, "")
            row.append(f"{code}{ch}{ANSI_RESET}" if code else ch)
        out.append(row)
    return out


def build_opponent_sprite(opponents_data: object, opponent_id: str, color_codes: Dict[str, str]) -> List[List[str]]:
    if not isinstance(opponents_data, dict):
        return []
    base_opponents = opponents_data.get("base_opponents", {})
    if not isinstance(base_opponents, dict):
        return []
    opponent = base_opponents.get(opponent_id, {})
    if not isinstance(opponent, dict):
        return []
    art = opponent.get("art", [])
    mask = opponent.get("color_map", [])
    return _colorize_object_rows(art, mask, color_codes)


def build_opponent_art_variations(
    opponents_data: object,
    opponent_id: str,
    color_codes: Dict[str, str],
) -> Dict[str, List[List[str]]]:
    if not isinstance(opponents_data, dict):
        return {}
    base_opponents = opponents_data.get("base_opponents", {})
    if not isinstance(base_opponents, dict):
        return {}
    opponent = base_opponents.get(opponent_id, {})
    if not isinstance(opponent, dict):
        return {}
    variations = opponent.get("art_variations", [])
    if not isinstance(variations, list):
        return {}
    out: Dict[str, List[List[str]]] = {}
    for entry in variations:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label", "")).strip()
        if not label:
            continue
        rows = _colorize_object_rows(entry.get("art", []), entry.get("color_map", []), color_codes)
        if rows:
            out[label] = rows
    return out


def build_house_mushroom_sprite(
    opponents_data: object,
    color_codes: Dict[str, str],
    house_number: int,
) -> List[List[str]]:
    accent_index, eye_index = mushroom_palette_indices_for_house(house_number)
    accent_bright, accent_base = HOUSE_ACCENT_PALETTES[accent_index]
    eye_bright, eye_base = HOUSE_ACCENT_PALETTES[eye_index]
    overrides = {
        "G": _ansi_color_code(*accent_bright),
        "g": _ansi_color_code(*accent_base),
        "B": _ansi_color_code(*eye_bright),
        "b": _ansi_color_code(*eye_base),
    }
    return build_opponent_sprite(opponents_data, "mushroom_baby", _with_color_overrides(color_codes, overrides))


def build_house_fairy_sprite(
    opponents_data: object,
    color_codes: Dict[str, str],
    house_number: int,
) -> List[List[str]]:
    wing_index, eye_index = fairy_palette_indices_for_house(house_number)
    wing_bright, wing_base = HOUSE_ACCENT_PALETTES[wing_index]
    eye_bright, eye_base = HOUSE_ACCENT_PALETTES[eye_index]
    overrides = {
        "C": _ansi_color_code(*wing_bright),
        "c": _ansi_color_code(*wing_base),
        "B": _ansi_color_code(*eye_bright),
        "b": _ansi_color_code(*eye_base),
    }
    return build_opponent_sprite(opponents_data, "fairy_baby", _with_color_overrides(color_codes, overrides))


def build_house_fairy_frames(
    opponents_data: object,
    color_codes: Dict[str, str],
    house_number: int,
) -> Dict[str, List[List[str]]]:
    wing_index, eye_index = fairy_palette_indices_for_house(house_number)
    wing_bright, wing_base = HOUSE_ACCENT_PALETTES[wing_index]
    eye_bright, eye_base = HOUSE_ACCENT_PALETTES[eye_index]
    overrides = {
        "C": _ansi_color_code(*wing_bright),
        "c": _ansi_color_code(*wing_base),
        "B": _ansi_color_code(*eye_bright),
        "b": _ansi_color_code(*eye_base),
    }
    varied_codes = _with_color_overrides(color_codes, overrides)
    frames = build_opponent_art_variations(opponents_data, "fairy_baby", varied_codes)
    if "primary" not in frames:
        frames["primary"] = build_opponent_sprite(opponents_data, "fairy_baby", varied_codes)
    return frames


def build_player_sprite(players_data: object, player_id: str, color_codes: Dict[str, str]) -> List[List[str]]:
    if not isinstance(players_data, dict):
        return []
    player = players_data.get(player_id, {})
    if not isinstance(player, dict):
        return []
    art = player.get("art", [])
    mask = player.get("color_map", [])
    if not isinstance(art, list) or not art:
        return []
    if not isinstance(mask, list):
        mask = []
    width = max((len(str(line)) for line in art), default=0)
    out: List[List[str]] = []
    opaque_space = f"\x1b[37m {ANSI_RESET}"
    for y, raw in enumerate(art):
        line = str(raw).ljust(width)
        mask_line = str(mask[y]) if y < len(mask) else ""
        row: List[str] = []
        for x, ch in enumerate(line):
            key = mask_line[x] if x < len(mask_line) else ""
            if key == "!":
                # Blocking cell: render opaque space to hide layers behind.
                row.append(opaque_space)
                continue
            if ch == " ":
                row.append(" ")
                continue
            code = color_codes.get(key, "")
            row.append(f"{code}{ch}{ANSI_RESET}" if code else ch)
        out.append(row)
    return out


def build_player_frame(
    players_data: object,
    player_id: str,
    color_codes: Dict[str, str],
    facing: str = "front",
    phase: str = "idle",
) -> List[List[str]]:
    if not isinstance(players_data, dict):
        return []
    player = players_data.get(player_id, {})
    if not isinstance(player, dict):
        return []
    facing_sets = player.get("facing_sets", {})
    if isinstance(facing_sets, dict):
        facing_payload = facing_sets.get(str(facing), {})
        if isinstance(facing_payload, dict):
            frame_payload = facing_payload.get(str(phase), {})
            if isinstance(frame_payload, dict):
                art = frame_payload.get("art", [])
                mask = frame_payload.get("color_map", [])
                rows = _colorize_object_rows(art, mask, color_codes)
                if rows:
                    return rows
    return build_player_sprite(players_data, player_id, color_codes)


def _sprite_size(rows: List[List[str]]) -> tuple[int, int]:
    if not rows:
        return (0, 0)
    width = max((len(row) for row in rows), default=0)
    return (width, len(rows))


def layout_actor_strip(
    area: LayoutZone,
    sprites: List[List[List[str]]],
    spacing: int = 1,
    stagger_rows: int = 0,
    reverse_stagger: bool = False,
) -> List[dict]:
    active = [rows for rows in sprites if isinstance(rows, list) and rows]
    if not active:
        return []
    sizes = [_sprite_size(rows) for rows in active]
    widths = [w for w, _h in sizes]
    total_width = sum(widths) + (max(0, len(active) - 1) * max(0, spacing))
    start_x = area.x + ((area.width - total_width) // 2)
    placements: List[dict] = []
    x = start_x
    count = len(active)
    for idx, (rows, (w, h)) in enumerate(zip(active, sizes)):
        step = (count - 1 - idx) if reverse_stagger else idx
        if reverse_stagger:
            y = area.y1 - max(0, h - 1) - (step * max(0, int(stagger_rows)))
        else:
            y = area.y1 - max(0, h - 1) + (step * max(0, int(stagger_rows)))
        y = max(0, min(SCREEN_H - h, y))
        placements.append({"x": x, "y": y, "rows": rows})
        x += w + max(0, spacing)
    # Rule 1: render left-to-right.
    placements.sort(key=lambda item: int(item.get("x", 0)))
    return placements


def _overlay_zone_guides(canvas: List[List[str]], zones: Dict[str, LayoutZone]) -> None:
    colors = [
        "\x1b[38;2;255;230;120m",
        "\x1b[38;2;135;210;255m",
    ]
    for idx, zone in enumerate(zones.values()):
        if zone.width <= 0 or zone.height <= 0:
            continue
        color = colors[idx % len(colors)]
        x0, y0 = zone.x, zone.y
        x1, y1 = zone.x1, zone.y1
        top_left = f"+-[{zone.name}:z{zone.layer}]-"
        top_right = "-+"
        bottom_left = "+-"
        bottom_right = "-+"

        for i, ch in enumerate(top_left):
            x = x0 + i
            if x > x1:
                break
            canvas[y0][x] = f"{color}{ch}{ANSI_RESET}"
        for i, ch in enumerate(top_right):
            x = x1 - (len(top_right) - 1) + i
            if x < x0 or x > x1:
                continue
            canvas[y0][x] = f"{color}{ch}{ANSI_RESET}"

        for i, ch in enumerate(bottom_left):
            x = x0 + i
            if x > x1:
                break
            canvas[y1][x] = f"{color}{ch}{ANSI_RESET}"
        for i, ch in enumerate(bottom_right):
            x = x1 - (len(bottom_right) - 1) + i
            if x < x0 or x > x1:
                continue
            canvas[y1][x] = f"{color}{ch}{ANSI_RESET}"

        # Light vertical corner hints near top/bottom only (not full box edges).
        if y1 - y0 >= 2:
            canvas[y0 + 1][x0] = f"{color}|{ANSI_RESET}"
            canvas[y0 + 1][x1] = f"{color}|{ANSI_RESET}"
        if y1 - y0 >= 3:
            canvas[y1 - 1][x0] = f"{color}|{ANSI_RESET}"
            canvas[y1 - 1][x1] = f"{color}|{ANSI_RESET}"


def _guide_zones_for_render(
    zones: Dict[str, LayoutZone],
    world_layer_level: int,
    world_treeline_sprites: List[dict] | None,
    world_anchor_stagger: int,
) -> Dict[str, LayoutZone]:
    if world_layer_level <= 0:
        return zones
    if world_layer_level >= 4:
        return {}
    if world_layer_level >= 3:
        secondary_zone = build_secondary_zone()
        ground_zone = zones.get("ground_bg")
        if isinstance(ground_zone, LayoutZone):
            lowest_tree_row = _treeline_lowest_row(ground_zone.y, world_anchor_stagger)
            return {
                "primary": build_primary_zone(lowest_tree_row + 1),
                "secondary": secondary_zone,
            }
        return {"primary": build_primary_zone(SCREEN_H - 1), "secondary": secondary_zone}
    if world_layer_level >= 2:
        ground_zone = zones.get("ground_bg")
        if isinstance(ground_zone, LayoutZone):
            lowest_tree_row = _treeline_lowest_row(ground_zone.y, world_anchor_stagger)
            return {"primary": build_primary_zone(lowest_tree_row + 1)}
        return {"primary": build_primary_zone(SCREEN_H - 1)}
    if not world_treeline_sprites:
        return {}
    ground_zone = zones.get("ground_bg")
    if not isinstance(ground_zone, LayoutZone):
        return {}
    max_tree_h = 1
    for sprite in world_treeline_sprites:
        h = int(sprite.get("height", 0)) if isinstance(sprite, dict) else 0
        max_tree_h = max(max_tree_h, h)
    stagger = TREELINE_ROWS
    top = ground_zone.y - max(0, max_tree_h - 1)
    bottom = ground_zone.y + max(0, stagger - 1)
    return {
        "treeline": _make_zone(
            "treeline",
            0,
            top,
            SCREEN_W,
            (bottom - top + 1),
            LAYER_WORLD,
        ),
    }


def build_primary_zone(anchor_bottom_y: int) -> LayoutZone:
    width = 20
    height = 12
    x_center = 75
    x = _anchored_x_with_overflow_guard(x_center, width)
    y = anchor_bottom_y - height + 1
    return _make_zone("primary", x, y, width, height, LAYER_FOREGROUND)


def build_secondary_zone() -> LayoutZone:
    # Bottom-left quadrant secondary slot:
    # - bottom-left corner anchor position = 1 row above screen bottom
    width = 20
    height = 12
    x_center = SCREEN_W // 4
    x = _anchored_x_with_overflow_guard(x_center, width)
    bottom_anchor_position = 1
    bottom_y = (SCREEN_H - 1) - bottom_anchor_position
    y = bottom_y - height + 1
    return _make_zone("secondary", x, y, width, height, LAYER_WORLD)


def _treeline_lowest_row(ground_top_y: int, world_anchor_stagger: int) -> int:
    return ground_top_y + max(0, TREELINE_ROWS - 1)


def ui_border_gradient_code(x: int, y: int, width: int, height: int) -> str:
    # Match the standard white -> blue -> grey panel gradient.
    if width <= 1 and height <= 1:
        return "\x1b[38;2;192;192;192m"
    t = ((x / max(1, width - 1)) + (y / max(1, height - 1))) / 2.0
    if t <= 0.5:
        tt = t / 0.5
        start = (192, 192, 192)
        end = (77, 77, 255)
    else:
        tt = (t - 0.5) / 0.5
        start = (77, 77, 255)
        end = (96, 96, 96)
    r = int(start[0] + (end[0] - start[0]) * tt)
    g = int(start[1] + (end[1] - start[1]) * tt)
    b = int(start[2] + (end[2] - start[2]) * tt)
    return f"\x1b[38;2;{r};{g};{b}m"


def _draw_ui_text_box(canvas: List[List[str]], text: str, primary_zone: LayoutZone, secondary_zone: LayoutZone) -> None:
    text = str(text).strip()
    if not text:
        return
    padding_x = 1
    padding_y = 1
    max_text_w = min(50, max(16, SCREEN_W - 10 - (padding_x * 2)))
    wrapped: List[str] = []
    for para in text.splitlines():
        line = para.strip()
        if not line:
            wrapped.append("")
            continue
        wrapped.extend(
            textwrap.wrap(
                line,
                width=max_text_w,
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    if not wrapped:
        wrapped = [text[:max_text_w]]
    text_w = max(len(line) for line in wrapped)
    inner_w = text_w + (padding_x * 2)
    box_w = inner_w + 2
    box_h = len(wrapped) + (padding_y * 2) + 2

    p_cx = primary_zone.x + (primary_zone.width // 2)
    p_cy = primary_zone.y + (primary_zone.height // 2)
    s_cx = secondary_zone.x + (secondary_zone.width // 2)
    s_cy = secondary_zone.y + (secondary_zone.height // 2)
    mid_x = int(round((p_cx + s_cx) / 2.0))
    mid_y = int(round((p_cy + s_cy) / 2.0))

    x0 = max(0, min(SCREEN_W - box_w, mid_x - (box_w // 2)))
    y0 = max(0, min(SCREEN_H - box_h, mid_y - (box_h // 2)))

    top = "o" + ("-" * inner_w) + "o"
    bottom = top
    lines: List[str] = [top]
    for _ in range(padding_y):
        lines.append("|" + (" " * inner_w) + "|")
    for line in wrapped:
        text_line = (" " * padding_x) + line.center(text_w) + (" " * padding_x)
        lines.append("|" + text_line + "|")
    for _ in range(padding_y):
        lines.append("|" + (" " * inner_w) + "|")
    lines.append(bottom)

    text_color = "\x1b[38;2;245;245;245m"
    for dy, raw in enumerate(lines):
        y = y0 + dy
        if y < 0 or y >= SCREEN_H:
            continue
        cells = ansi_line_to_cells(raw, len(raw))
        for dx, cell in enumerate(cells):
            x = x0 + dx
            if x < 0 or x >= SCREEN_W:
                continue
            ch = _strip_ansi(cell)
            is_border = dy == 0 or dy == box_h - 1 or dx == 0 or dx == box_w - 1
            if is_border and ch != " ":
                g = ui_border_gradient_code(dx, dy, box_w, box_h)
                canvas[y][x] = f"{g}{ch}{ANSI_RESET}"
            elif ch != " ":
                canvas[y][x] = f"{text_color}{ch}{ANSI_RESET}"
            else:
                canvas[y][x] = " "


def _draw_ui_dialogue_box(
    canvas: List[List[str]],
    speaker: str,
    text: str,
    primary_zone: LayoutZone,
    secondary_zone: LayoutZone,
) -> None:
    def _balanced_wrap(content: str, width: int) -> List[str]:
        lines = textwrap.wrap(content, width=width, break_long_words=False, break_on_hyphens=False)
        if len(lines) < 2:
            return lines or [content[:width]]
        # Rebalance to avoid a tiny orphan tail line when possible.
        while len(lines) >= 2:
            last_words = lines[-1].split()
            prev_words = lines[-2].split()
            if len(last_words) > 2 or len(prev_words) <= 2:
                break
            move = prev_words[-1]
            candidate_last = f"{move} {lines[-1]}".strip()
            candidate_prev = " ".join(prev_words[:-1]).strip()
            if not candidate_prev or len(candidate_last) > width:
                break
            lines[-2] = candidate_prev
            lines[-1] = candidate_last
        return lines

    speaker_title = f"{{ {speaker} }}"
    button_text = "[ A / Confirm ]--[ S / Cancel ]"
    wrapped = _balanced_wrap(str(text).strip(), width=52)
    if not wrapped:
        wrapped = [""]
    inner_w = max(len(line) for line in wrapped)
    inner_w = max(inner_w + 2, len(speaker_title) + 8, len(button_text) + 8)
    box_w = inner_w + 2
    box_h = len(wrapped) + 5  # top + top margin + text + bottom margin + bottom

    p_cx = primary_zone.x + (primary_zone.width // 2)
    p_cy = primary_zone.y + (primary_zone.height // 2)
    s_cx = secondary_zone.x + (secondary_zone.width // 2)
    s_cy = secondary_zone.y + (secondary_zone.height // 2)
    mid_x = int(round((p_cx + s_cx) / 2.0))
    mid_y = int(round((p_cy + s_cy) / 2.0))

    x0 = max(0, min(SCREEN_W - box_w, mid_x - (box_w // 2)))
    y0 = max(0, min(SCREEN_H - box_h, mid_y - (box_h // 2)))

    title_left = max(0, (inner_w - len(speaker_title)) // 2)
    title_right = max(0, inner_w - len(speaker_title) - title_left)
    top = "o" + ("-" * title_left) + speaker_title + ("-" * title_right) + "o"
    title_start_dx = 1 + title_left
    title_end_dx = title_start_dx + len(speaker_title)

    button_left = max(0, (inner_w - len(button_text)) // 2)
    button_right = max(0, inner_w - len(button_text) - button_left)
    bottom = "o" + ("-" * button_left) + button_text + ("-" * button_right) + "o"

    lines: List[str] = [top]
    lines.append("|" + (" " * inner_w) + "|")  # top internal margin
    for line in wrapped:
        lines.append("|" + line.center(inner_w) + "|")
    lines.append("|" + (" " * inner_w) + "|")  # bottom internal margin
    lines.append(bottom)
    box_h = len(lines)

    text_color = "\x1b[38;2;245;245;245m"
    green_key = "\x1b[38;2;56;186;72m"
    red_key = "\x1b[38;2;220;70;70m"
    white_title = "\x1b[38;2;245;245;245m"
    for dy, raw in enumerate(lines):
        y = y0 + dy
        if y < 0 or y >= SCREEN_H:
            continue
        cells = ansi_line_to_cells(raw, len(raw))
        for dx, cell in enumerate(cells):
            x = x0 + dx
            if x < 0 or x >= SCREEN_W:
                continue
            ch = _strip_ansi(cell)
            is_border = dy == 0 or dy == box_h - 1 or dx == 0 or dx == box_w - 1
            if dy == 0 and title_start_dx <= dx < title_end_dx and ch != " ":
                canvas[y][x] = f"{white_title}{ch}{ANSI_RESET}"
            elif dy == box_h - 1 and ch == "A":
                canvas[y][x] = f"{green_key}A{ANSI_RESET}"
            elif dy == box_h - 1 and ch == "S":
                canvas[y][x] = f"{red_key}S{ANSI_RESET}"
            elif is_border and ch != " ":
                g = ui_border_gradient_code(dx, dy, box_w, box_h)
                canvas[y][x] = f"{g}{ch}{ANSI_RESET}"
            elif ch != " ":
                canvas[y][x] = f"{text_color}{ch}{ANSI_RESET}"
            else:
                canvas[y][x] = " "


def _draw_spell_throw(
    canvas: List[List[str]],
    source: tuple[int, int],
    target: tuple[int, int],
    spell_phase: float,
) -> None:
    progress = max(0.0, min(1.0, float(spell_phase)))
    sx, sy = source
    tx, ty = target
    travel_portion = 0.62
    if progress < travel_portion:
        travel_t = progress / max(0.001, travel_portion)
        x = int(round(sx + ((tx - sx) * travel_t)))
        y = int(round(sy + ((ty - sy) * travel_t)))
        stage_idx = min(2, int(travel_t * 3.0))
    else:
        # Hold at destination and cycle through all three stages before loop reset.
        x, y = tx, ty
        impact_t = (progress - travel_portion) / max(0.001, 1.0 - travel_portion)
        cycles = 2.0
        stage_idx = int((impact_t * cycles * 3.0)) % 3

    # Gold -> white gradient spectrum for per-spark variation.
    start = (255, 215, 90)
    end = (255, 255, 255)
    steps = 10
    palette: List[str] = []
    for i in range(steps):
        t = i / max(1, steps - 1)
        r = int(start[0] + ((end[0] - start[0]) * t))
        g = int(start[1] + ((end[1] - start[1]) * t))
        b = int(start[2] + ((end[2] - start[2]) * t))
        palette.append(f"\x1b[38;2;{r};{g};{b}m")
    if stage_idx == 0:
        pattern = ["*"]
    elif stage_idx == 1:
        pattern = [
            " * ",
            "* *",
            " * ",
        ]
    else:
        pattern = [
            "  *  ",
            " * * ",
            "*   *",
            " * * ",
            "  *  ",
        ]
    h = len(pattern)
    w = max((len(row) for row in pattern), default=1)
    x0 = x - (w // 2)
    y0 = y - (h // 2)
    for dy, row in enumerate(pattern):
        for dx, ch in enumerate(row):
            if ch != "*":
                continue
            gx = x0 + dx
            gy = y0 + dy
            if 0 <= gx < SCREEN_W and 0 <= gy < SCREEN_H:
                # Deterministic per-cell/per-phase random color pick from gold-white spectrum.
                seed = (gx * 73856093) ^ (gy * 19349663) ^ int(progress * 1000)
                rng = random.Random(seed)
                color = palette[rng.randrange(len(palette))]
                canvas[gy][gx] = f"{color}*{ANSI_RESET}"


def _draw_spell_barrage(
    canvas: List[List[str]],
    source: tuple[int, int],
    targets: List[tuple[int, int]],
    spell_clock: float,
) -> None:
    if not targets:
        return
    # 50% overlap: each next cast starts when previous reaches half progress.
    start_interval = 0.5
    cast_duration = 1.0
    total_span = cast_duration + (start_interval * max(0, len(targets) - 1))
    t = float(spell_clock) % total_span
    for idx, target in enumerate(targets):
        local = t - (idx * start_interval)
        if local < 0:
            local += total_span
        if 0.0 <= local < cast_duration:
            _draw_spell_throw(canvas, source, target, local / cast_duration)


def load_smash_frames(path: str) -> List[List[str]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        raw_lines = handle.read().splitlines()
    frames: List[List[str]] = []
    current: List[str] = []
    for line in raw_lines:
        if line.strip() == "":
            if current:
                frames.append(current)
                current = []
            continue
        current.append(line.rstrip("\n"))
    if current:
        frames.append(current)
    return frames


def _physical_hit_state(clock: float) -> tuple[bool, bool, int]:
    # (hide_attacker, show_impact, frame_index_hint)
    # One cycle: blink twice, then play smash frames 1..5 once (no intra-hit looping).
    phase = float(clock) % 1.0
    blink_window = 0.50
    impact_window = 0.50
    if phase < blink_window:
        step = int((phase / max(0.001, blink_window)) * 4.0)  # two blinks
        blink_visible = (step % 2) == 0
        return (not blink_visible, False, 0)
    if phase < (blink_window + impact_window):
        impact_t = (phase - blink_window) / max(0.001, impact_window)
        frame_idx = min(4, int(impact_t * 5.0))
        return (False, True, frame_idx)
    return (False, False, 0)


def _draw_smash_frame(canvas: List[List[str]], frame: List[str], center: tuple[int, int]) -> None:
    if not frame:
        return
    h = len(frame)
    w = max((len(line) for line in frame), default=0)
    cx, cy = center
    x0 = cx - (w // 2)
    y0 = cy - (h // 2)
    color = "\x1b[38;2;255;245;245m"
    for dy, line in enumerate(frame):
        y = y0 + dy
        if y < 0 or y >= SCREEN_H:
            continue
        for dx, ch in enumerate(line):
            if ch == " ":
                continue
            x = x0 + dx
            if 0 <= x < SCREEN_W:
                canvas[y][x] = f"{color}{ch}{ANSI_RESET}"


def _draw_health_bar(canvas: List[List[str]], center_x: int, top_y: int, filled: int, total: int = 6) -> None:
    total = max(1, int(total))
    filled = max(0, min(total, int(filled)))
    empty = total - filled
    hp_color = "\x1b[38;2;56;186;72m"
    miss_color = "\x1b[38;2;18;18;18m"
    frame_color = "\x1b[38;2;210;210;210m"
    cells: List[str] = [f"{frame_color}[{ANSI_RESET}"]
    cells.extend([f"{hp_color}#{ANSI_RESET}" for _ in range(filled)])
    cells.extend([f"{miss_color}_{ANSI_RESET}" for _ in range(empty)])
    cells.append(f"{frame_color}]{ANSI_RESET}")
    width = len(cells)
    x0 = max(0, min(SCREEN_W - width, int(center_x) - (width // 2)))
    y = int(top_y)
    if y < 0 or y >= SCREEN_H:
        return
    for i, cell in enumerate(cells):
        x = x0 + i
        if 0 <= x < SCREEN_W:
            canvas[y][x] = cell


def _draw_actor_health_bars(canvas: List[List[str]], placements: List[dict], mixed: bool = True) -> None:
    for idx, actor in enumerate(placements):
        rows = actor.get("rows", [])
        if not isinstance(rows, list) or not rows:
            continue
        w = max((len(row) for row in rows), default=0)
        x0 = int(actor.get("x", 0))
        y0 = int(actor.get("y", 0))
        center_x = x0 + (w // 2)
        bar_y = y0 - 1
        filled = 6 if (not mixed or idx % 2 == 0) else 3
        _draw_health_bar(canvas, center_x, bar_y, filled, total=6)


def render(
    clouds: List[dict],
    ground_rows: List[str],
    zones: Dict[str, LayoutZone],
    sky_bottom_anchor: int,
    foreground_split_label: str,
    world_layer_level: int = 0,
    world_anchor_stagger: int = TREELINE_ROWS,
    world_treeline_sprites: List[dict] | None = None,
    border_treeline_sprites: List[dict] | None = None,
    crossroad_house_sprites: List[dict] | None = None,
    primary_actor_sprites: List[List[List[str]]] | None = None,
    primary_actor_stagger: int = 0,
    secondary_actor_sprites: List[List[List[str]]] | None = None,
    secondary_actor_stagger: int = 0,
    secondary_actor_reverse_stagger: bool = False,
    guy_sprite: List[List[str]] | None = None,
    mushy_sprite: List[List[str]] | None = None,
    spell_phase: float = 0.0,
    spell_clock: float = 0.0,
    smash_frames: List[List[str]] | None = None,
    wipe_progress: float = 1.0,
    show_zone_guides: bool = False,
    world_scene_label: str = "cottage",
    landscape_position: int = DEFAULT_LANDSCAPE_POSITION,
) -> str:
    canvas = [[" " for _ in range(SCREEN_W)] for _ in range(SCREEN_H)]

    sky_zone = zones["sky_bg"]
    ground_zone = zones["ground_bg"]
    secondary_zone = build_secondary_zone()
    primary_zone = None
    if world_layer_level >= 2:
        lowest_tree_row = _treeline_lowest_row(ground_zone.y, world_anchor_stagger)
        primary_zone = build_primary_zone(lowest_tree_row + 1)
    sky_layer_bottom = int(sky_bottom_anchor)
    sky_layer_top = sky_layer_bottom - (SKY_LAYER_HEIGHT - 1)
    current_backside = landscape_is_backside(landscape_position)
    hidden_ground_rows = landscape_hidden_ground_rows(landscape_position)
    total_ground_rows = landscape_total_ground_visible_from_horizon(landscape_position)
    ground_slice_start = landscape_ground_window_start(landscape_position)

    def draw_world_scene_sprites(draw_backside: bool) -> None:
        if world_layer_level < 1:
            return
        if world_treeline_sprites:
            for sprite in world_treeline_sprites:
                rows = sprite.get("rows", [])
                if not isinstance(rows, list):
                    continue
                x0 = int(sprite.get("x", 0))
                height = int(sprite.get("height", len(rows)))
                offset = min(TREELINE_ROWS - 1, max(0, int(sprite.get("anchor_offset", 0))))
                sprite_is_backside, y_base = horizon_depth_state(offset, hidden_ground_rows, ground_zone.y)
                if sprite_is_backside != draw_backside:
                    continue
                y_base = max(ground_zone.y, y_base)
                y0 = y_base - max(0, height - 1)
                for dy, row in enumerate(rows):
                    y = y0 + dy
                    if y < 0 or y >= SCREEN_H or not isinstance(row, list):
                        continue
                    for dx, cell in enumerate(row):
                        x = x0 + dx
                        if 0 <= x < SCREEN_W and cell != " ":
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
                if crossroad_row_phase(horizon_depth) is not None:
                    continue
                sprite_is_backside, y_base = horizon_depth_state(horizon_depth, hidden_ground_rows, ground_zone.y)
                if sprite_is_backside != draw_backside:
                    continue
                y_base = max(ground_zone.y, y_base)
                distance_from_horizon = max(0, y_base - ground_zone.y)
                road = road_geometry_for_horizon_distance(distance_from_horizon)
                column_band = max(0, min(2, int(sprite.get("side_column", 0))))
                column_jitter = max(-1, min(1, int(sprite.get("side_jitter", 0))))
                if side == "left":
                    x0 = (column_band * 3) + column_jitter - int(road.get("left_push", 0))
                else:
                    x0 = (SCREEN_W - max(1, width) - (column_band * 3) + column_jitter) + int(road.get("right_push", 0))
                y0 = y_base - max(0, height - 1)
                for dy, row in enumerate(rows):
                    y = y0 + dy
                    if y < 0 or y >= SCREEN_H or not isinstance(row, list):
                        continue
                    for dx, cell in enumerate(row):
                        x = x0 + dx
                        if 0 <= x < SCREEN_W and cell != " ":
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
                sprite_is_backside, y_base = horizon_depth_state(horizon_depth, hidden_ground_rows, ground_zone.y)
                if sprite_is_backside != draw_backside:
                    continue
                y_base = max(ground_zone.y, y_base)
                distance_from_horizon = max(0, y_base - ground_zone.y)
                road = road_geometry_for_horizon_distance(distance_from_horizon)
                if side == "left":
                    x0 = int(road.get("start", 0)) - width - 8
                else:
                    x0 = int(road.get("end", SCREEN_W - 1)) + 8
                y0 = y_base - max(0, height - 1)
                for dy, row in enumerate(rows):
                    y = y0 + dy
                    if y < 0 or y >= SCREEN_H or not isinstance(row, list):
                        continue
                    for dx, cell in enumerate(row):
                        x = x0 + dx
                        if 0 <= x < SCREEN_W and cell != " ":
                            canvas[y][x] = cell
                label = str(sprite.get("label", "")).strip()
                if label:
                    plaque_y = y0 + max(0, min(max(0, height - 1), 5) - 3)
                    plaque_x = x0 + max(0, (width - len(label)) // 2)
                    plaque_color = "[38;2;245;245;245m"
                    for idx, ch in enumerate(label):
                        x = plaque_x + idx
                        if 0 <= x < SCREEN_W and 0 <= plaque_y < SCREEN_H:
                            canvas[plaque_y][x] = f"{plaque_color}{ch}{ANSI_RESET}"

    # Background sky pass: drifting cloud sprites placed inside a 100-row sky layer.
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
                if 0 <= x < SCREEN_W and cell != " ":
                    canvas[y][x] = cell

    # Backside world pass: draw first so the ground can occlude it at the horizon.
    draw_world_scene_sprites(draw_backside=True)

    # Background ground pass: draw a moving slice through a taller world ground buffer.
    for i in range(ground_zone.height):
        y = ground_zone.y + i
        src_index = ground_slice_start + i
        src = ground_rows[src_index] if 0 <= src_index < len(ground_rows) else ""
        cells = ansi_line_to_cells(src, SCREEN_W)
        road_width = road_width_for_horizon_distance(i)
        crossroad_phase = crossroad_row_phase(src_index)
        row_cells = overlay_crossroad_row(cells, src_index, 12051701 + src_index)
        row_cells = build_road_pushed_row(row_cells, road_width, 9051701 + src_index, crossroad_phase=crossroad_phase)
        for x, cell in enumerate(row_cells):
            if cell != " ":
                canvas[y][x] = cell

    # Frontside world pass: draw after the ground so the scene sits in front of the landscape.
    draw_world_scene_sprites(draw_backside=False)

    hide_attacker = False
    show_hit_impact = False
    impact_frame_hint = 0
    if world_layer_level == 7:
        hide_attacker, show_hit_impact, impact_frame_hint = _physical_hit_state(spell_clock)

    # World pane actor pass (secondary): centered collective, bottom-anchored individuals.
    secondary_placements: List[dict] = []
    if world_layer_level >= 3:
        sec_sprites = secondary_actor_sprites if secondary_actor_sprites is not None else ([guy_sprite] if guy_sprite else [])
        secondary_placements = layout_actor_strip(
            secondary_zone,
            sec_sprites,
            spacing=1,
            stagger_rows=secondary_actor_stagger,
            reverse_stagger=secondary_actor_reverse_stagger,
        )
        for idx, actor in enumerate(secondary_placements):
            if hide_attacker and idx == 0:
                continue
            x0 = int(actor.get("x", 0))
            y0 = int(actor.get("y", 0))
            rows = actor.get("rows", [])
            if not isinstance(rows, list):
                continue
            for dy, row in enumerate(rows):
                y = y0 + dy
                if y < 0 or y >= SCREEN_H:
                    continue
                for dx, cell in enumerate(row):
                    x = x0 + dx
                    if 0 <= x < SCREEN_W and cell != " ":
                        canvas[y][x] = cell

    # Foreground primary pass (primary pane): centered collective, bottom-anchored individuals.
    primary_placements: List[dict] = []
    if world_layer_level >= 2 and primary_zone is not None:
        pri_sprites = primary_actor_sprites if primary_actor_sprites is not None else ([mushy_sprite] if mushy_sprite else [])
        primary_placements = layout_actor_strip(primary_zone, pri_sprites, spacing=1, stagger_rows=primary_actor_stagger)
        for actor in primary_placements:
            x0 = int(actor.get("x", 0))
            y0 = int(actor.get("y", 0))
            rows = actor.get("rows", [])
            if not isinstance(rows, list):
                continue
            for dy, row in enumerate(rows):
                y = y0 + dy
                if y < 0 or y >= SCREEN_H:
                    continue
                for dx, cell in enumerate(row):
                    x = x0 + dx
                    if 0 <= x < SCREEN_W and cell != " ":
                        canvas[y][x] = cell

    if world_layer_level == 4 and primary_zone is not None:
        _draw_ui_text_box(canvas, UI_DEMO_TEXT, primary_zone, secondary_zone)

    if world_layer_level == 5 and secondary_placements and primary_placements:
        src = secondary_placements[0]
        dst = primary_placements[0]
        src_rows = src.get("rows", [])
        dst_rows = dst.get("rows", [])
        src_w = max((len(row) for row in src_rows), default=0) if isinstance(src_rows, list) else 0
        src_h = len(src_rows) if isinstance(src_rows, list) else 0
        dst_w = max((len(row) for row in dst_rows), default=0) if isinstance(dst_rows, list) else 0
        dst_h = len(dst_rows) if isinstance(dst_rows, list) else 0
        source = (int(src.get("x", 0)) + (src_w // 2), int(src.get("y", 0)) + (src_h // 2))
        target = (int(dst.get("x", 0)) + (dst_w // 2), int(dst.get("y", 0)) + (dst_h // 2))
        _draw_spell_throw(canvas, source, target, spell_phase)
    if world_layer_level == 6 and secondary_placements and primary_placements:
        src = secondary_placements[0]
        src_rows = src.get("rows", [])
        src_w = max((len(row) for row in src_rows), default=0) if isinstance(src_rows, list) else 0
        src_h = len(src_rows) if isinstance(src_rows, list) else 0
        source = (int(src.get("x", 0)) + (src_w // 2), int(src.get("y", 0)) + (src_h // 2))
        targets: List[tuple[int, int]] = []
        for dst in primary_placements[:4]:
            dst_rows = dst.get("rows", [])
            dst_w = max((len(row) for row in dst_rows), default=0) if isinstance(dst_rows, list) else 0
            dst_h = len(dst_rows) if isinstance(dst_rows, list) else 0
            targets.append((int(dst.get("x", 0)) + (dst_w // 2), int(dst.get("y", 0)) + (dst_h // 2)))
        _draw_spell_barrage(canvas, source, targets, spell_clock)
    if world_layer_level == 7 and primary_placements and show_hit_impact and smash_frames:
        dst = primary_placements[0]
        dst_rows = dst.get("rows", [])
        dst_w = max((len(row) for row in dst_rows), default=0) if isinstance(dst_rows, list) else 0
        dst_h = len(dst_rows) if isinstance(dst_rows, list) else 0
        target = (int(dst.get("x", 0)) + (dst_w // 2), int(dst.get("y", 0)) + (dst_h // 2))
        frame_idx = min(max(0, impact_frame_hint), len(smash_frames) - 1)
        _draw_smash_frame(canvas, smash_frames[frame_idx], target)
    if world_layer_level == 8:
        _draw_actor_health_bars(canvas, primary_placements, mixed=True)
        _draw_actor_health_bars(canvas, secondary_placements, mixed=True)
    if world_layer_level == 9 and primary_zone is not None:
        _draw_ui_dialogue_box(canvas, "Beba", UI_DIALOG_TEXT, primary_zone, secondary_zone)

    progress = max(0.0, min(1.0, wipe_progress))
    if progress < 1.0:
        visible_rows = int(round(SCREEN_H * progress))
        top_hidden_rows = max(0, SCREEN_H - visible_rows)
        for y in range(top_hidden_rows):
            for x in range(SCREEN_W):
                canvas[y][x] = " "

    if show_zone_guides:
        guide_zones = _guide_zones_for_render(
            zones=zones,
            world_layer_level=world_layer_level,
            world_treeline_sprites=world_treeline_sprites,
            world_anchor_stagger=TREELINE_ROWS,
        )
        _overlay_zone_guides(canvas, guide_zones)

    footer = f"[background][{foreground_split_label}]"
    if world_layer_level >= 1:
        side_label = "back" if current_backside else "front"
        footer += f"[world][{TREELINE_ROWS}][horizon:{side_label}:{hidden_ground_rows}]"
        footer += f"[scene:{world_scene_label}]"
    if world_layer_level >= 2:
        footer += "[foreground]"
    if world_layer_level == 4:
        footer += "[ui]"
    if world_layer_level >= 5:
        footer += "[effect]"
    if world_layer_level >= 6:
        footer += "[barrage]"
    if world_layer_level >= 7:
        footer += "[physical]"
    if world_layer_level >= 8:
        footer += "[health]"
    if world_layer_level >= 9:
        footer += "[dialogue]"
    if len(footer) <= SCREEN_W:
        x0 = (SCREEN_W - len(footer)) // 2
        y = SCREEN_H - 1
        for i, ch in enumerate(footer):
            canvas[y][x0 + i] = ch

    return "\n".join("".join(row) for row in canvas)


def main() -> None:
    base = os.getcwd()
    objects_path = os.path.join(base, "legacy", "data", "objects.json")
    colors_path = os.path.join(base, "legacy", "data", "colors.json")
    opponents_path = os.path.join(base, "legacy", "data", "opponents.json")
    players_path = os.path.join(base, "legacy", "data", "players.json")
    objects = load_json(objects_path)
    colors = load_json(colors_path)
    opponents = load_json(opponents_path)
    players = load_json(players_path)
    if not isinstance(objects, dict):
        raise RuntimeError("objects.json is not a JSON object")
    if not isinstance(colors, dict):
        raise RuntimeError("colors.json is not a JSON object")
    if not isinstance(opponents, dict):
        raise RuntimeError("opponents.json is not a JSON object")
    if not isinstance(players, dict):
        raise RuntimeError("players.json is not a JSON object")
    color_codes = _build_color_codes(colors)

    templates = cloud_templates(objects)
    if not templates:
        raise RuntimeError("No cloud_* objects found in objects.json")

    current_landscape_position = DEFAULT_LANDSCAPE_POSITION
    target_landscape_position = current_landscape_position
    zones = build_scene_zones(sky_rows=landscape_sky_rows(current_landscape_position))
    sky_bottom_anchor = sky_bottom_anchor_for_position(current_landscape_position)
    clouds = spawn_clouds_full_canvas(templates)
    ground_rows = build_ground_rows(
        row_count=LANDSCAPE_TOTAL_GROUND_ROWS,
        objects_data=objects,
        color_codes=color_codes,
        pebble_density=0.07,
    )
    wipe_duration = 1.0
    wipe_started_at = time.monotonic()
    show_zone_guides = False
    world_layer_level = 0
    world_mode_count = 10
    world_anchor_stagger = TREELINE_ROWS
    world_scene_index = 0
    world_scene_label, world_center_object_id = WORLD_SCENE_VARIANTS[world_scene_index]
    world_treeline_sprites = build_world_treeline_sprites(objects, colors, world_center_object_id)
    border_treeline_sprites = build_border_treeline_sprites(objects, colors)
    crossroad_house_sprites = build_crossroad_house_sprites(objects, colors)
    guy_sprite = build_player_sprite(players, "player_01", color_codes)
    chase_sprite = build_opponent_sprite(opponents, "wolf_pup", color_codes)
    mushy_sprite = build_opponent_sprite(opponents, "mushroom_baby", color_codes)
    baby_fairy_sprite = build_opponent_sprite(opponents, "fairy_baby", color_codes)
    beba_rexa_sprite = build_opponent_sprite(opponents, "fairy_teen", color_codes)
    if not beba_rexa_sprite:
        beba_rexa_sprite = baby_fairy_sprite
    smash_frames = load_smash_frames(os.path.join(base, "smash.txt"))
    transition_accum = 0.0
    transition_step_seconds = 0.03

    print(ANSI_HIDE_CURSOR + ANSI_CLEAR, end="", flush=True)
    try:
        last_tick = time.monotonic()
        while True:
            now = time.monotonic()
            dt = max(0.0, min(0.2, now - last_tick))
            last_tick = now
            wipe_progress = min(1.0, max(0.0, (now - wipe_started_at) / wipe_duration))

            if current_landscape_position != target_landscape_position:
                transition_accum += dt
                while current_landscape_position != target_landscape_position and transition_accum >= transition_step_seconds:
                    transition_accum -= transition_step_seconds
                    direction = 1 if target_landscape_position > current_landscape_position else -1
                    current_landscape_position += direction
                    zones = build_scene_zones(sky_rows=landscape_sky_rows(current_landscape_position))
                    sky_bottom_anchor = sky_bottom_anchor_for_position(current_landscape_position)
            else:
                transition_accum = 0.0

            for cloud in clouds:
                speed = float(cloud.get("speed", 1.0))
                cloud["x"] = float(cloud.get("x", 0.0)) - (speed * dt)
                w = int(cloud["template"]["width"])
                if cloud["x"] + w < 0:
                    cloud["x"] = SCREEN_W + (cloud["x"] + w)

            key = read_key_nonblocking()
            if key == "q":
                break
            if key == "z":
                show_zone_guides = not show_zone_guides
            if key == "c":
                world_scene_index = (world_scene_index + 1) % len(WORLD_SCENE_VARIANTS)
                world_scene_label, world_center_object_id = WORLD_SCENE_VARIANTS[world_scene_index]
                world_treeline_sprites = build_world_treeline_sprites(objects, colors, world_center_object_id)
                border_treeline_sprites = build_border_treeline_sprites(objects, colors)
                crossroad_house_sprites = build_crossroad_house_sprites(objects, colors)
            if key == "up":
                target_landscape_position -= 1
                if target_landscape_position < LANDSCAPE_STEP_ROWS:
                    target_landscape_position = LANDSCAPE_TOTAL_GROUND_ROWS
            if key == "down":
                target_landscape_position += 1
                if target_landscape_position > LANDSCAPE_TOTAL_GROUND_ROWS:
                    target_landscape_position = LANDSCAPE_STEP_ROWS
            if key == "right":
                world_layer_level = (world_layer_level + 1) % world_mode_count
            if key == "left":
                world_layer_level = (world_layer_level - 1) % world_mode_count

            split_label = f"{landscape_sky_rows(current_landscape_position)}/{landscape_total_ground_visible_from_horizon(current_landscape_position)}"
            spell_clock = now * 0.75
            spell_phase = spell_clock % 1.0

            frame = render(
                clouds=clouds,
                ground_rows=ground_rows,
                zones=zones,
                sky_bottom_anchor=sky_bottom_anchor,
                foreground_split_label=split_label,
                world_layer_level=world_layer_level,
                world_anchor_stagger=world_anchor_stagger,
                world_treeline_sprites=world_treeline_sprites,
                border_treeline_sprites=border_treeline_sprites,
                crossroad_house_sprites=crossroad_house_sprites,
                primary_actor_sprites=[
                    baby_fairy_sprite,
                    baby_fairy_sprite,
                    baby_fairy_sprite,
                    baby_fairy_sprite,
                ],
                primary_actor_stagger=1,
                secondary_actor_sprites=[guy_sprite, mushy_sprite, chase_sprite, beba_rexa_sprite],
                secondary_actor_stagger=1,
                secondary_actor_reverse_stagger=True,
                guy_sprite=guy_sprite,
                mushy_sprite=mushy_sprite,
                spell_phase=spell_phase,
                spell_clock=spell_clock,
                smash_frames=smash_frames,
                wipe_progress=wipe_progress,
                show_zone_guides=show_zone_guides,
                world_scene_label=world_scene_label,
                landscape_position=current_landscape_position,
            )
            print(ANSI_HOME + frame, end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        print(ANSI_SHOW_CURSOR + ANSI_RESET)


if __name__ == "__main__":
    main()
