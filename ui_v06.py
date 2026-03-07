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
SKY_ROWS_OPTIONS = [5, 10, 15, 20, 25]
DEFAULT_SKY_ROWS = 15
UI_DEMO_TEXT = "Eenie, Meenie, Miney, Mo.\nWho here dares to be our foe!?"
UI_DIALOG_TEXT = "So what do you say... Are you ready to challenge them?"
DEMO_BATTLE_LOG_LINES = [
    "Mushy casts Magic Spark on 4 Fairy Warriors.",
    "Beba casts Magic Spark on 4 Fairy Warriors.",
    "Fairy Warrior has been defeated.",
    "Fairy Warrior has been defeated.",
    "Fairy 1 casts Healing Light on Fairy 3.",
]
WORLD_SCENE_VARIANTS = [
    ("cottage", "house"),
    ("fairy_castle", "fairy_castle"),
    ("bridge", "bridge"),
    ("mushroom_house", "mushroom_house"),
]
FLIGHTED_ACTOR_TAGS = {"crow", "crow1", "crow2", "baby_crow", "hawk"}


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


@dataclass(frozen=True)
class UIBoxBorderGlyphs:
    tl: str
    tr: str
    bl: str
    br: str
    h: str
    v: str


@dataclass
class UIBoxSpec:
    role: str
    border_style: str
    body_text: str
    title: str = ""
    actions: List[str] | None = None
    center_x: int | None = None
    center_y: int | None = None
    x: int | None = None
    y: int | None = None
    max_body_width: int = 40
    padding_x: int = 1
    padding_y: int = 1
    body_align: str = "left"
    wrap_mode: str = "normal"
    border_gradient: bool = True
    anchor: str = "center"
    preserve_body_whitespace: bool = False
    blink_body_rows: List[int] | None = None


@dataclass(frozen=True)
class UIBoxLayout:
    spec: UIBoxSpec
    lines: List[str]
    x0: int
    y0: int
    box_w: int
    box_h: int
    title_start: int
    title_end: int
    action_row_index: int
    blink_line_indices: set[int]


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
    # Match centered object parity so road aligns with centered house anchor.
    road_center = (SCREEN_W - 1) // 2
    road_chars = [".", ",", "'", "`"]
    road_color = "\x1b[38;2;170;170;170m"

    for row_idx in range(max(0, row_count)):
        # Perspective: widen by 1 column on each side every 2 rows downward.
        expand_steps = row_idx // 2
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
            if road_start <= x <= road_end:
                dirt = rng.choice(road_chars)
                cell = f"{road_color}{dirt}{ANSI_RESET}"
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
    count = max(8, min(24, int(round((SCREEN_W * SCREEN_H) / 150.0))))
    for _ in range(count):
        template = templates[rng.randrange(len(templates))]
        w = int(template["width"])
        h = int(template["height"])
        y_max = max(0, SCREEN_H - h)
        y = rng.randint(0, y_max) if y_max > 0 else 0
        x = rng.randint(-max(1, w // 2), SCREEN_W - 1)
        speed = _cloud_speed(str(template.get("size", "medium")), y, SCREEN_H, rng)
        clouds.append({"template": template, "x": float(x), "y": float(y), "speed": speed})
    return clouds


def sky_bottom_anchor_for_rows(sky_rows: int) -> int:
    # Parallax: move sky-bottom anchor 1 row for every 2 rows of sky change.
    half_shift = max(0, int(sky_rows) // 2)
    anchor = SCREEN_H - half_shift
    return max(0, min(SCREEN_H, anchor))


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


def build_world_treeline_sprites(
    objects_data: object,
    colors_data: object,
    center_object_id: str = "house",
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
            "anchor_offset": max(0, min(2, int(anchor_offset))),
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
        probe = make_sprite(tree_id, 0, anchor_offset=rng.randint(0, 2))
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
        probe = make_sprite(tree_id, right_cursor, anchor_offset=rng.randint(0, 2))
        if probe is None:
            continue
        if int(probe.get("x", 0)) < SCREEN_W:
            sprites.append(probe)
        right_cursor = int(probe.get("x", 0)) + int(probe.get("width", 0)) + rng.randint(1, 4)

    # Draw from left to right for deterministic overdraw.
    sprites.sort(key=lambda s: int(s.get("x", 0)))
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


def build_mushroom_variant_sprite(opponents_data: object, color_codes: Dict[str, str], hat_key: str) -> List[List[str]]:
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
    hat = (str(hat_key)[:1] or "i")
    for y, raw in enumerate(art):
        line = str(raw).ljust(width)
        mask_line = str(mask[y]) if y < len(mask) else ""
        row: List[str] = []
        for x, ch in enumerate(line):
            if ch == " ":
                row.append(" ")
                continue
            key = mask_line[x] if x < len(mask_line) else ""
            if key == "q":
                key = hat
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
    if total_width <= SCREEN_W:
        # Keep whole strip on-screen; shift left/right as needed.
        start_x = max(0, min(SCREEN_W - total_width, start_x))
    else:
        # Strip wider than viewport: anchor to left edge and allow clipping.
        start_x = 0
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
    stagger = max(1, min(3, int(world_anchor_stagger)))
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
    stagger = max(1, min(3, int(world_anchor_stagger)))
    return ground_top_y + max(0, stagger - 1)


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


def battle_log_border_gradient_code(x: int, y: int, width: int, height: int) -> str:
    # Battle log style: white -> dark grey -> light grey.
    if width <= 1 and height <= 1:
        return "\x1b[38;2;128;128;128m"
    t = ((x / max(1, width - 1)) + (y / max(1, height - 1))) / 2.0
    if t <= 0.5:
        tt = t / 0.5
        start = (245, 245, 245)
        end = (56, 56, 56)
    else:
        tt = (t - 0.5) / 0.5
        start = (56, 56, 56)
        end = (176, 176, 176)
    r = int(start[0] + (end[0] - start[0]) * tt)
    g = int(start[1] + (end[1] - start[1]) * tt)
    b = int(start[2] + (end[2] - start[2]) * tt)
    return f"\x1b[38;2;{r};{g};{b}m"


def battle_log_text_gradient_code(x: int, y: int, width: int, height: int) -> str:
    # Text gradient direction: bottom-left -> top-right.
    if width <= 1 and height <= 1:
        return "\x1b[38;2;176;176;176m"
    t = ((x / max(1, width - 1)) + ((max(0, height - 1) - y) / max(1, height - 1))) / 2.0
    if t <= 0.5:
        tt = t / 0.5
        start = (245, 245, 245)
        end = (56, 56, 56)
    else:
        tt = (t - 0.5) / 0.5
        start = (56, 56, 56)
        end = (176, 176, 176)
    r = int(start[0] + (end[0] - start[0]) * tt)
    g = int(start[1] + (end[1] - start[1]) * tt)
    b = int(start[2] + (end[2] - start[2]) * tt)
    return f"\x1b[38;2;{r};{g};{b}m"


def _ui_border_glyphs(style: str) -> UIBoxBorderGlyphs:
    key = str(style).strip().lower()
    if key == "double":
        return UIBoxBorderGlyphs(tl="\u2554", tr="\u2557", bl="\u255a", br="\u255d", h="\u2550", v="\u2551")
    if key == "heavy":
        return UIBoxBorderGlyphs(tl="\u250f", tr="\u2513", bl="\u2517", br="\u251b", h="\u2501", v="\u2503")
    return UIBoxBorderGlyphs(tl="\u250c", tr="\u2510", bl="\u2514", br="\u2518", h="\u2500", v="\u2502")


def _balanced_wrap_lines(text: str, width: int) -> List[str]:
    lines = textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)
    if len(lines) < 2:
        return lines or [text[:width]]
    while len(lines) >= 2:
        tail_words = lines[-1].split()
        prev_words = lines[-2].split()
        if len(tail_words) > 2 or len(prev_words) <= 2:
            break
        moved = prev_words[-1]
        cand_tail = f"{moved} {lines[-1]}".strip()
        cand_prev = " ".join(prev_words[:-1]).strip()
        if not cand_prev or len(cand_tail) > width:
            break
        lines[-2] = cand_prev
        lines[-1] = cand_tail
    return lines


def _wrap_ui_body(text: str, width: int, mode: str, preserve_whitespace: bool = False) -> List[str]:
    out: List[str] = []
    wrap_mode = str(mode).strip().lower()
    for para in str(text).splitlines():
        line = str(para).rstrip("\n")
        test_line = line if preserve_whitespace else line.strip()
        if not preserve_whitespace:
            line = test_line
        if not test_line:
            out.append("")
            continue
        if wrap_mode == "balanced":
            out.extend(_balanced_wrap_lines(line, width))
        else:
            out.extend(textwrap.wrap(line, width=width, break_long_words=False, break_on_hyphens=False))
    return out or [""]


def _format_ui_body_line(text: str, width: int, align: str) -> str:
    mode = str(align).strip().lower()
    if mode == "center":
        return text.center(width)
    if mode == "right":
        return text.rjust(width)
    return text.ljust(width)


def _format_select_lines(options: List[str], selected_index: int) -> List[str]:
    clean = [str(opt) for opt in options]
    max_len = max((len(opt) for opt in clean), default=0)
    out: List[str] = []
    for idx, opt in enumerate(clean):
        core = opt.ljust(max_len)
        if idx == selected_index:
            out.append(f"[ {core} ]")
        else:
            out.append(f"  {core}  ")
    return out


def _resolve_ui_box_origin(box_w: int, box_h: int, spec: UIBoxSpec) -> tuple[int, int]:
    if spec.x is not None and spec.y is not None:
        x0 = max(0, min(SCREEN_W - box_w, int(spec.x)))
        y0 = max(0, min(SCREEN_H - box_h, int(spec.y)))
        return (x0, y0)

    cx = SCREEN_W // 2 if spec.center_x is None else int(spec.center_x)
    cy = SCREEN_H // 2 if spec.center_y is None else int(spec.center_y)
    anchor = str(spec.anchor).strip().lower()
    if anchor == "left":
        x0 = cx
        y0 = cy - (box_h // 2)
    elif anchor == "right":
        x0 = cx - box_w
        y0 = cy - (box_h // 2)
    elif anchor == "top":
        x0 = cx - (box_w // 2)
        y0 = cy
    elif anchor == "bottom":
        x0 = cx - (box_w // 2)
        y0 = cy - box_h
    else:
        x0 = cx - (box_w // 2)
        y0 = cy - (box_h // 2)
    x0 = max(0, min(SCREEN_W - box_w, x0))
    y0 = max(0, min(SCREEN_H - box_h, y0))
    return (x0, y0)


def _build_ui_box_layout(spec: UIBoxSpec) -> UIBoxLayout:
    glyphs = _ui_border_glyphs(spec.border_style)
    max_w = max(8, min(SCREEN_W - 4, int(spec.max_body_width)))
    wrapped = _wrap_ui_body(spec.body_text, max_w, spec.wrap_mode, preserve_whitespace=bool(spec.preserve_body_whitespace))
    body_w = max((len(line) for line in wrapped), default=0)

    actions = spec.actions if isinstance(spec.actions, list) else []
    action_row = "  ".join([str(item).strip() for item in actions if str(item).strip()])

    title = str(spec.title).strip()
    title_token = f"[ {title} ]" if title else ""
    inner_w = body_w + (max(0, int(spec.padding_x)) * 2)
    if title_token:
        inner_w = max(inner_w, len(title_token) + 4)
    if action_row:
        inner_w = max(inner_w, len(action_row) + 4)

    lines: List[str] = []
    title_left = max(0, (inner_w - len(title_token)) // 2) if title_token else 0
    title_right = max(0, inner_w - len(title_token) - title_left) if title_token else 0
    if title_token:
        top = glyphs.tl + (glyphs.h * title_left) + title_token + (glyphs.h * title_right) + glyphs.tr
    else:
        top = glyphs.tl + (glyphs.h * inner_w) + glyphs.tr
    lines.append(top)

    for _ in range(max(0, int(spec.padding_y))):
        lines.append(glyphs.v + (" " * inner_w) + glyphs.v)

    for line in wrapped:
        body = _format_ui_body_line(line, body_w, spec.body_align)
        content = (" " * max(0, int(spec.padding_x))) + body + (" " * max(0, int(spec.padding_x)))
        lines.append(glyphs.v + content.ljust(inner_w)[:inner_w] + glyphs.v)

    for _ in range(max(0, int(spec.padding_y))):
        lines.append(glyphs.v + (" " * inner_w) + glyphs.v)

    action_row_index = -1
    if action_row:
        action_row_index = len(lines)
        lines.append(glyphs.v + action_row.center(inner_w)[:inner_w] + glyphs.v)

    lines.append(glyphs.bl + (glyphs.h * inner_w) + glyphs.br)

    box_w = inner_w + 2
    box_h = len(lines)
    x0, y0 = _resolve_ui_box_origin(box_w, box_h, spec)
    title_start = 1 + title_left
    title_end = title_start + len(title_token)
    blink_line_indices: set[int] = set()
    if isinstance(spec.blink_body_rows, list):
        body_start = 1 + max(0, int(spec.padding_y))
        for row in spec.blink_body_rows:
            try:
                r = int(row)
            except Exception:
                continue
            line_idx = body_start + r
            if 0 <= line_idx < box_h:
                blink_line_indices.add(line_idx)
    return UIBoxLayout(
        spec=spec,
        lines=lines,
        x0=x0,
        y0=y0,
        box_w=box_w,
        box_h=box_h,
        title_start=title_start,
        title_end=title_end,
        action_row_index=action_row_index,
        blink_line_indices=blink_line_indices,
    )


def _draw_ui_box_layout(
    canvas: List[List[str]],
    layout: UIBoxLayout,
    visible_w: int | None = None,
    visible_h: int | None = None,
    blink_on: bool = True,
) -> None:
    spec = layout.spec
    text_color = "\x1b[38;2;245;245;245m"
    title_color = "\x1b[38;2;255;255;255m"
    key_green = "\x1b[38;2;56;186;72m"
    key_red = "\x1b[38;2;220;70;70m"
    dim_text = "\x1b[38;2;150;150;150m"
    border_flat = "\x1b[38;2;210;210;210m"

    vw = layout.box_w if visible_w is None else max(2, min(layout.box_w, int(visible_w)))
    vh = layout.box_h if visible_h is None else max(2, min(layout.box_h, int(visible_h)))
    clip_x0 = (layout.box_w - vw) // 2
    clip_y0 = (layout.box_h - vh) // 2
    clip_x1 = clip_x0 + vw - 1
    clip_y1 = clip_y0 + vh - 1

    for dy, raw in enumerate(layout.lines):
        if dy < clip_y0 or dy > clip_y1:
            continue
        y = layout.y0 + dy
        if y < 0 or y >= SCREEN_H:
            continue
        for dx, ch in enumerate(raw):
            if dx < clip_x0 or dx > clip_x1:
                continue
            x = layout.x0 + dx
            if x < 0 or x >= SCREEN_W:
                continue
            is_border = dy == 0 or dy == (layout.box_h - 1) or dx == 0 or dx == (layout.box_w - 1)
            if is_border and ch != " ":
                border_code = ui_border_gradient_code(dx, dy, layout.box_w, layout.box_h) if spec.border_gradient else border_flat
                if dy == 0 and layout.title_end > layout.title_start and layout.title_start <= dx < layout.title_end:
                    canvas[y][x] = f"{title_color}{ch}{ANSI_RESET}"
                else:
                    canvas[y][x] = f"{border_code}{ch}{ANSI_RESET}"
                continue
            if ch == " ":
                canvas[y][x] = " "
                continue
            if dy == layout.action_row_index and ch == "A":
                canvas[y][x] = f"{key_green}A{ANSI_RESET}"
            elif dy == layout.action_row_index and ch == "S":
                canvas[y][x] = f"{key_red}S{ANSI_RESET}"
            else:
                use_color = dim_text if (dy in layout.blink_line_indices and not blink_on) else text_color
                canvas[y][x] = f"{use_color}{ch}{ANSI_RESET}"


def _build_meter_cells(value: int, total: int, width: int, fill_color: str, empty_color: str) -> List[str]:
    total = max(1, int(total))
    width = max(1, int(width))
    value = max(0, min(total, int(value)))
    fill_count = int(round((value / float(total)) * width))
    fill_count = max(0, min(width, fill_count))
    cells: List[str] = []
    for i in range(width):
        if i < fill_count:
            cells.append(f"{fill_color}\u2588{ANSI_RESET}")
        else:
            cells.append(f"{empty_color}\u2588{ANSI_RESET}")
    return cells


def _draw_actor_cmd_status_overlay(
    canvas: List[List[str]],
    spec: UIBoxSpec,
    hp: int,
    hp_total: int,
    mp: int,
    mp_total: int,
    progress: float = 1.0,
) -> None:
    layout = _build_ui_box_layout(spec)
    inner_w = max(1, layout.box_w - 2)
    y = layout.y0 + 2
    if y < 0 or y >= SCREEN_H:
        return
    hp_ratio = (max(0, hp) / max(1, hp_total))
    if hp_ratio >= 0.5:
        hp_fill = "\x1b[38;2;56;186;72m"
    elif hp_ratio >= 0.25:
        hp_fill = "\x1b[38;2;236;201;58m"
    else:
        hp_fill = "\x1b[38;2;220;70;70m"
    mp_fill = "\x1b[38;2;80;150;255m"
    empty = "\x1b[38;2;30;30;30m"
    label = "\x1b[38;2;245;245;245m"
    hp_cells = _build_meter_cells(hp, hp_total, 8, hp_fill, empty)
    mp_cells = _build_meter_cells(mp, mp_total, 8, mp_fill, empty)
    cells: List[str] = [f"{label}H{ANSI_RESET}", f"{label}P{ANSI_RESET}", f"{label}:{ANSI_RESET}", " "]
    cells.extend(hp_cells)
    cells.extend([" ", f"{label}M{ANSI_RESET}", f"{label}P{ANSI_RESET}", f"{label}:{ANSI_RESET}", " "])
    cells.extend(mp_cells)
    if len(cells) > inner_w:
        cells = cells[:inner_w]

    x = layout.x0 + 1 + max(0, (inner_w - len(cells)) // 2)

    # Match box open/close clipping so this strip reveals with the box.
    p = max(0.0, min(1.0, float(progress)))
    h_steps = max(0, layout.box_h - 2)
    w_steps = max(0, layout.box_w - 2)
    h_ticks = max(0, (h_steps + 1) // 2)
    w_ticks = max(0, (w_steps + 1) // 2)
    total_ticks = max(1, h_ticks + w_ticks)
    tick = int(round(total_ticks * p))
    tick = max(0, min(total_ticks, tick))
    if tick <= h_ticks:
        vh = 2 + min(h_steps, tick * 2)
        vw = 2
    else:
        vh = layout.box_h
        width_tick = tick - h_ticks
        vw = 2 + min(w_steps, width_tick * 2)
    vw = max(2, min(layout.box_w, int(vw)))
    vh = max(2, min(layout.box_h, int(vh)))
    ax0 = layout.x0 + ((layout.box_w - vw) // 2)
    ay0 = layout.y0 + ((layout.box_h - vh) // 2)
    ax1 = ax0 + vw - 1
    ay1 = ay0 + vh - 1
    if y <= ay0 or y >= ay1:
        return

    for i, cell in enumerate(cells):
        xx = x + i
        if 0 <= xx < SCREEN_W and (ax0 < xx < ax1):
            canvas[y][xx] = cell


def draw_ui_box(canvas: List[List[str]], spec: UIBoxSpec, blink_on: bool = True) -> None:
    layout = _build_ui_box_layout(spec)
    _draw_ui_box_layout(canvas, layout, blink_on=blink_on)


def draw_ui_box_animated(
    canvas: List[List[str]],
    spec: UIBoxSpec,
    progress: float,
    blink_on: bool = True,
) -> None:
    layout = _build_ui_box_layout(spec)
    p = max(0.0, min(1.0, float(progress)))
    h_steps = max(0, layout.box_h - 2)
    w_steps = max(0, layout.box_w - 2)
    h_ticks = max(0, (h_steps + 1) // 2)
    w_ticks = max(0, (w_steps + 1) // 2)
    total_ticks = max(1, h_ticks + w_ticks)
    tick = int(round(total_ticks * p))
    tick = max(0, min(total_ticks, tick))

    if tick <= h_ticks:
        # Phase 1: grow vertically first while keeping width at 2.
        vh = 2 + min(h_steps, tick * 2)
        vw = 2
        width_phase = False
    else:
        # Phase 2: then grow horizontally while height stays full.
        vh = layout.box_h
        width_tick = tick - h_ticks
        vw = 2 + min(w_steps, width_tick * 2)
        width_phase = True

    vw = max(2, min(layout.box_w, int(vw)))
    vh = max(2, min(layout.box_h, int(vh)))

    ax0 = layout.x0 + ((layout.box_w - vw) // 2)
    ay0 = layout.y0 + ((layout.box_h - vh) // 2)
    ax1 = ax0 + vw - 1
    ay1 = ay0 + vh - 1

    glyphs = _ui_border_glyphs(spec.border_style)
    border_flat = "\x1b[38;2;210;210;210m"
    text_color = "\x1b[38;2;245;245;245m"
    key_green = "\x1b[38;2;56;186;72m"
    key_red = "\x1b[38;2;220;70;70m"
    dim_text = "\x1b[38;2;150;150;150m"

    # Title behavior: during width-phase, reveal "[ Title ]" progressively on top border.
    top_row_override: List[str] | None = None
    title_text = str(spec.title).strip()
    if width_phase and title_text and vw >= 4:
        inner_w = vw - 2
        body_w = max(0, inner_w - 4)
        if body_w <= 0:
            title_token = "[]"
        else:
            # Reveal centered core title while keeping braces compact.
            reveal = min(len(title_text), body_w)
            if reveal <= 0:
                core = ""
            else:
                start = max(0, (len(title_text) - reveal) // 2)
                core = title_text[start : start + reveal]
            if core:
                title_token = f"[ {core} ]"
            else:
                title_token = "[]"
            if len(title_token) > inner_w:
                title_token = title_token[:inner_w]
        left = max(0, (inner_w - len(title_token)) // 2)
        right = max(0, inner_w - len(title_token) - left)
        top_row_override = [glyphs.tl] + ([glyphs.h] * left) + list(title_token) + ([glyphs.h] * right) + [glyphs.tr]
        if len(top_row_override) < vw:
            top_row_override.extend([glyphs.h] * (vw - len(top_row_override)))
            top_row_override[-1] = glyphs.tr
        elif len(top_row_override) > vw:
            top_row_override = top_row_override[:vw]
            top_row_override[0] = glyphs.tl
            top_row_override[-1] = glyphs.tr

    # Draw animated frame geometry (actual growing/shrinking box).
    for dy in range(vh):
        y = ay0 + dy
        if y < 0 or y >= SCREEN_H:
            continue
        for dx in range(vw):
            x = ax0 + dx
            if x < 0 or x >= SCREEN_W:
                continue
            border = dy == 0 or dy == (vh - 1) or dx == 0 or dx == (vw - 1)
            if border:
                if dy == 0 and top_row_override is not None:
                    ch = top_row_override[dx]
                elif dy == 0 and dx == 0:
                    ch = glyphs.tl
                elif dy == 0 and dx == (vw - 1):
                    ch = glyphs.tr
                elif dy == (vh - 1) and dx == 0:
                    ch = glyphs.bl
                elif dy == (vh - 1) and dx == (vw - 1):
                    ch = glyphs.br
                elif dy == 0 or dy == (vh - 1):
                    ch = glyphs.h
                else:
                    ch = glyphs.v
                border_code = ui_border_gradient_code(dx, dy, vw, vh) if spec.border_gradient else border_flat
                canvas[y][x] = f"{border_code}{ch}{ANSI_RESET}"
            else:
                canvas[y][x] = " "

    # Reveal pre-positioned final content only where animated box currently covers.
    for dy, raw in enumerate(layout.lines):
        y = layout.y0 + dy
        if y < ay0 or y > ay1 or y < 0 or y >= SCREEN_H:
            continue
        for dx, ch in enumerate(raw):
            x = layout.x0 + dx
            if x < ax0 or x > ax1 or x < 0 or x >= SCREEN_W:
                continue
            on_anim_border = y == ay0 or y == ay1 or x == ax0 or x == ax1
            if on_anim_border:
                continue
            if ch == " ":
                continue
            final_border = dy == 0 or dy == (layout.box_h - 1) or dx == 0 or dx == (layout.box_w - 1)
            if final_border:
                continue
            if dy == layout.action_row_index and ch == "A":
                canvas[y][x] = f"{key_green}A{ANSI_RESET}"
            elif dy == layout.action_row_index and ch == "S":
                canvas[y][x] = f"{key_red}S{ANSI_RESET}"
            else:
                use_color = dim_text if (dy in layout.blink_line_indices and not blink_on) else text_color
                canvas[y][x] = f"{use_color}{ch}{ANSI_RESET}"


def build_ui_demo_specs(variant: int) -> List[UIBoxSpec]:
    mode = max(0, int(variant) % 3)
    if mode == 1:
        return [
            UIBoxSpec(
                role="notification",
                border_style="double",
                title="Notification",
                body_text="Status effects resolved. Turn order updated.",
                x=2,
                y=12,
                max_body_width=44,
                body_align="left",
            ),
            UIBoxSpec(
                role="prompt",
                border_style="double",
                title="Beba",
                body_text="So what do you say... Are you ready to challenge them?",
                center_x=54,
                center_y=18,
                max_body_width=54,
                wrap_mode="balanced",
                body_align="center",
                actions=["[ A / Confirm ]", "[ S / Cancel ]"],
            ),
            UIBoxSpec(
                role="history",
                border_style="heavy",
                title="Battle Log",
                body_text="\n".join(DEMO_BATTLE_LOG_LINES[-3:]),
                x=58,
                y=18,
                max_body_width=40,
            ),
        ]
    if mode == 2:
        return [
            UIBoxSpec(
                role="notification",
                border_style="heavy",
                title="Notice",
                body_text="Magic Spark is now attuned to Water affinity.",
                x=3,
                y=13,
                max_body_width=42,
                body_align="center",
            ),
            UIBoxSpec(
                role="prompt",
                border_style="light",
                title="Action Prompt",
                body_text="Use current loadout for the next encounter?",
                center_x=50,
                center_y=18,
                max_body_width=46,
                wrap_mode="balanced",
                body_align="center",
                actions=["[ A / Yes ]", "[ S / No ]"],
            ),
            UIBoxSpec(
                role="history",
                border_style="double",
                title="Console",
                body_text="\n".join(DEMO_BATTLE_LOG_LINES),
                x=56,
                y=17,
                max_body_width=42,
            ),
        ]
    return [
        UIBoxSpec(
            role="notification",
            border_style="light",
            title="Notification",
            body_text="Quest progress updated: 2 objectives remaining.",
            x=2,
            y=12,
            max_body_width=44,
        ),
        UIBoxSpec(
            role="prompt",
            border_style="heavy",
            title="Beba",
            body_text="So what do you say... Are you ready to challenge them?",
            center_x=50,
            center_y=18,
            max_body_width=52,
            wrap_mode="balanced",
            body_align="center",
            actions=["[ A / Confirm ]", "[ S / Cancel ]"],
        ),
        UIBoxSpec(
            role="history",
            border_style="double",
            title="Battle Log",
            body_text="\n".join(DEMO_BATTLE_LOG_LINES),
            x=58,
            y=17,
            max_body_width=40,
        ),
    ]


def build_ui_animation_specs() -> List[UIBoxSpec]:
    return [
        UIBoxSpec(
            role="notification",
            border_style="light",
            title="Notification",
            body_text="Quest progress updated.",
            center_x=17,
            center_y=17,
            max_body_width=22,
            body_align="center",
            wrap_mode="balanced",
            anchor="center",
        ),
        UIBoxSpec(
            role="prompt",
            border_style="heavy",
            title="Prompt",
            body_text="Engage this battle now?",
            center_x=50,
            center_y=17,
            max_body_width=24,
            body_align="center",
            wrap_mode="balanced",
            actions=["[ A / Confirm ]", "[ S / Cancel ]"],
            anchor="center",
        ),
        UIBoxSpec(
            role="history",
            border_style="double",
            title="History",
            body_text="Mushy casts Magic Spark.\nFairy Warrior is defeated.",
            center_x=83,
            center_y=17,
            max_body_width=22,
            body_align="left",
            wrap_mode="normal",
            anchor="center",
        ),
    ]


def build_new_game_workflow_specs() -> List[UIBoxSpec]:
    return [
        UIBoxSpec(
            role="menu",
            border_style="heavy",
            title="Title Menu",
            body_text=(
                "[ New Game ]\n"
                "  Saved Game\n"
                "  Asset Explorer\n"
                "\n"
                "Use Up/Down to choose."
            ),
            center_x=50,
            center_y=17,
            max_body_width=36,
            body_align="left",
            wrap_mode="normal",
            actions=["[ A / Confirm ]", "[ S / Back ]"],
            anchor="center",
        ),
        UIBoxSpec(
            role="avatar_select",
            border_style="double",
            title="Choose Adventurer",
            body_text=(
                "Slot 1\n"
                "\n"
                "[ GUY ]                 GAL\n"
                "  O                    .-.\n"
                " /|\\                  (o o)\n"
                " / \\                   /|\\\n"
                "\n"
                "Use Left/Right to toggle avatar."
            ),
            center_x=50,
            center_y=17,
            max_body_width=58,
            body_align="left",
            wrap_mode="normal",
            actions=["[ A / Confirm ]", "[ S / Back ]"],
            anchor="center",
        ),
        UIBoxSpec(
            role="name_toggle",
            border_style="heavy",
            title="Say Your Name",
            body_text=(
                "Preset Name:\n"
                "< MUSHY >\n"
                "\n"
                "Use Left/Right to cycle preset names,\n"
                "or choose Custom..."
            ),
            center_x=50,
            center_y=17,
            max_body_width=48,
            body_align="center",
            wrap_mode="balanced",
            actions=["[ A / Confirm ]", "[ S / Back ]"],
            anchor="center",
        ),
        UIBoxSpec(
            role="name_custom",
            border_style="double",
            title="Custom Name",
            body_text=(
                "Name: MUSHY_\n"
                "\n"
                "1 2 3 4 5 6 7 8 9 0\n"
                "A B C D E F G H I J\n"
                "K L M N O P Q R S T\n"
                "U V W X Y Z - ' SPACE DEL\n"
                "SHIFT  DONE  CANCEL\n"
                "\n"
                "Arrows move. A selects. S cancels."
            ),
            center_x=50,
            center_y=17,
            max_body_width=62,
            body_align="left",
            wrap_mode="normal",
            actions=["[ A / Key ]", "[ S / Cancel ]"],
            anchor="center",
        ),
        UIBoxSpec(
            role="start_confirm",
            border_style="heavy",
            title="Begin Adventure",
            body_text=(
                "Avatar: Guy\n"
                "Name: MUSHY\n"
                "Fortune: Well-Off (100 GP)\n"
                "\n"
                "Start new game with these settings?"
            ),
            center_x=50,
            center_y=17,
            max_body_width=52,
            body_align="left",
            wrap_mode="balanced",
            actions=["[ A / Start ]", "[ S / Back ]"],
            anchor="center",
        ),
    ]


def ui_box_step_count(spec: UIBoxSpec) -> int:
    layout = _build_ui_box_layout(spec)
    h_ticks = max(0, ((layout.box_h - 2) + 1) // 2)
    w_ticks = max(0, ((layout.box_w - 2) + 1) // 2)
    return max(1, h_ticks + w_ticks)


NAME_KEYBOARD = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
    ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
    ["K", "L", "M", "N", "O", "P", "Q", "R", "S", "T"],
    ["U", "V", "W", "X", "Y", "Z", "-", "'", "SPACE", "DEL"],
    ["SHIFT", "DONE", "CANCEL"],
]


def _display_keyboard_rows(shift: bool) -> List[List[str]]:
    out: List[List[str]] = []
    for row in NAME_KEYBOARD:
        drow: List[str] = []
        for token in row:
            if len(token) == 1 and token.isalpha():
                drow.append(token.upper() if shift else token.lower())
            else:
                drow.append(token)
        out.append(drow)
    return out


def _apply_name_key(name: str, key_token: str, shift: bool) -> tuple[str, bool, bool, bool]:
    # Returns: (updated_name, updated_shift, done, cancel)
    token = str(key_token)
    if token == "SHIFT":
        return (name, not shift, False, False)
    if token == "DEL":
        return (name[:-1], shift, False, False)
    if token == "SPACE":
        if len(name) < 16:
            return (name + " ", shift, False, False)
        return (name, shift, False, False)
    if token == "DONE":
        if name.strip():
            return (name, shift, True, False)
        return (name, shift, False, False)
    if token == "CANCEL":
        return (name, shift, False, True)
    if len(token) == 1 and len(name) < 16:
        return (name + token, shift, False, False)
    return (name, shift, False, False)


def _draw_text(canvas: List[List[str]], x0: int, y: int, text: str, color: str) -> None:
    if y < 0 or y >= SCREEN_H:
        return
    for i, ch in enumerate(str(text)):
        x = x0 + i
        if 0 <= x < SCREEN_W:
            if ch == " ":
                canvas[y][x] = " "
            else:
                canvas[y][x] = f"{color}{ch}{ANSI_RESET}"


def _draw_sprite(canvas: List[List[str]], rows: List[List[str]], x0: int, y0: int) -> None:
    for dy, row in enumerate(rows):
        y = y0 + dy
        if y < 0 or y >= SCREEN_H or not isinstance(row, list):
            continue
        for dx, cell in enumerate(row):
            x = x0 + dx
            if 0 <= x < SCREEN_W and cell != " ":
                canvas[y][x] = cell


def _draw_avatar_overlay(
    canvas: List[List[str]],
    spec: UIBoxSpec,
    left_sprite: List[List[str]],
    right_sprite: List[List[str]],
    left_label: str,
    right_label: str,
    selected: int,
    blink_selected_on: bool = True,
) -> None:
    layout = _build_ui_box_layout(spec)
    center_x = layout.x0 + (layout.box_w // 2)
    left_w, left_h = _sprite_size(left_sprite)
    right_w, right_h = _sprite_size(right_sprite)
    top_y = layout.y0 + 6

    left_cx = center_x - 16
    right_cx = center_x + 16
    left_x = left_cx - (left_w // 2)
    right_x = right_cx - (right_w // 2)
    if selected == 0:
        if blink_selected_on:
            _draw_sprite(canvas, left_sprite, left_x, top_y)
        _draw_sprite(canvas, right_sprite, right_x, top_y)
    elif selected == 1:
        _draw_sprite(canvas, left_sprite, left_x, top_y)
        if blink_selected_on:
            _draw_sprite(canvas, right_sprite, right_x, top_y)
    else:
        _draw_sprite(canvas, left_sprite, left_x, top_y)
        _draw_sprite(canvas, right_sprite, right_x, top_y)

    label_y = top_y + max(left_h, right_h) + 1
    dim = "\x1b[38;2;210;210;210m"
    bright = "\x1b[38;2;245;245;245m"
    left_text = f"[ {left_label} ]" if selected == 0 else f"  {left_label}  "
    right_text = f"[ {right_label} ]" if selected == 1 else f"  {right_label}  "
    _draw_text(canvas, left_cx - (len(left_text) // 2), label_y, left_text, bright if selected == 0 else dim)
    _draw_text(canvas, right_cx - (len(right_text) // 2), label_y, right_text, bright if selected == 1 else dim)


def _actor_action_options(actor_key: str) -> List[str]:
    key = str(actor_key).strip().lower()
    if key == "player":
        return ["Attack", "Magic Spark", "Defend"]
    if key == "mushy":
        return ["Attack", "Mushroom Tea", "Defend"]
    if key == "sharoom":
        return ["Attack", "Healing Touch", "Defend"]
    if key == "roomy":
        return ["Attack", "Concentric", "Defend"]
    return ["Attack", "Defend"]


def _action_label(flow: dict, actor_key: str) -> str:
    options = _actor_action_options(actor_key)
    idx_key = f"battle_{actor_key}_cmd_idx"
    idx = int(flow.get(idx_key, 0))
    if not options:
        return "Attack"
    return options[idx % len(options)]


def _spell_targeting_meta(actor_key: str, action: str) -> dict | None:
    a = str(actor_key).strip().lower()
    act = str(action).strip()
    if a == "mushy" and act == "Mushroom Tea":
        return {
            "side": "ally",
            "supports_all": False,
            "default_mode": "single",
            "desc": "Mushroom Tea (2 MP): +3 Attack and +3 Defense. Stacks. Decays by 1 each turn.",
        }
    if a == "sharoom" and act == "Healing Touch":
        return {
            "side": "ally",
            "supports_all": True,
            "default_mode": "single",
            "desc": "Healing Touch (2 MP): single target heals up to 5 HP, or ALL allies heal up to 2 HP each.",
        }
    if a == "roomy" and act == "Concentric":
        return {
            "side": "ally",
            "supports_all": False,
            "default_mode": "all",
            "desc": "Concentric (2 MP): restore +1 MP to each ally except caster.",
        }
    return None


def _alive_secondary_target_indices(flow: dict, actor_key: str, action: str, stage: int) -> List[int]:
    sec_hp = [int(v) for v in flow.get("battle_secondary_hp", [20, 10])]
    alive = [idx for idx, hp in enumerate(sec_hp) if hp > 0]
    if not alive:
        return []
    a = str(actor_key).strip().lower()
    act = str(action).strip()
    caster_idx = 1 if int(stage) >= 3 and a == "player" else (2 if int(stage) >= 3 and a == "mushy" else (0 if int(stage) >= 3 and a == "sharoom" else (0 if a == "player" else 1)))
    if a == "mushy" and act == "Mushroom Tea":
        team_only = [i for i in alive if i != caster_idx]
        return team_only or alive
    return alive


def _reset_battle_command_picks(flow: dict, stage: int) -> None:
    flow["battle_player_cmd_idx"] = 0
    flow["battle_player_action"] = _actor_action_options("player")[0]
    flow["battle_mushy_cmd_idx"] = 0
    flow["battle_mushy_action"] = _actor_action_options("mushy")[0]
    if int(stage) >= 3:
        flow["battle_sharoom_cmd_idx"] = 0
        flow["battle_sharoom_action"] = _actor_action_options("sharoom")[0]


def _build_screen_spec(flow: dict) -> UIBoxSpec | None:
    screen = str(flow.get("screen", "root_menu"))
    if screen == "root_menu":
        options = ["New Game", "Saved Game", "Asset Explorer"]
        cursor = int(flow.get("menu_cursor", 0)) % len(options)
        lines = _format_select_lines(options, cursor)
        return UIBoxSpec(
            role="menu",
            border_style="heavy",
            title="Title Menu",
            body_text="\n".join(lines + ["", "Use Up/Down and A/S."]),
            center_x=50,
            center_y=17,
            max_body_width=34,
            actions=["[ A / Confirm ]", "[ S / Back ]"],
            body_align="left",
            preserve_body_whitespace=True,
            blink_body_rows=[cursor],
        )

    if screen == "avatar_select":
        label = str(flow.get("avatar_label", "Adventurer"))
        return UIBoxSpec(
            role="avatar_select",
            border_style="double",
            title="Choose Adventurer",
            body_text=f"Slot 1  Avatar: {label}\n\nUse Left/Right to toggle.",
            center_x=50,
            center_y=17,
            max_body_width=62,
            actions=["[ A / Confirm ]", "[ S / Back ]"],
            body_align="left",
        )

    if screen == "name_select":
        names = flow.get("name_choices", ["WARRIOR"])
        idx = int(flow.get("name_choice_index", 0)) % max(1, len(names))
        name = str(names[idx])
        focus = int(flow.get("name_focus", 0))
        select_lines = _format_select_lines([f"< {name} >", "Custom..."], focus)
        preset_line, custom_line = select_lines[0], select_lines[1]
        return UIBoxSpec(
            role="name_select",
            border_style="heavy",
            title="Say Your Name",
            body_text=(
                f"{preset_line}\n"
                f"{custom_line}\n\n"
                "Left/Right cycles preset names."
            ),
            center_x=50,
            center_y=17,
            max_body_width=46,
            body_align="center",
            wrap_mode="balanced",
            actions=["[ A / Confirm ]", "[ S / Back ]"],
            preserve_body_whitespace=True,
            blink_body_rows=[focus],
        )

    if screen == "name_input":
        typed = str(flow.get("typed_name", ""))[:16]
        shift = bool(flow.get("name_shift", True))
        key_rows = _display_keyboard_rows(shift)
        cur_row = int(flow.get("key_row", 0))
        cur_col = int(flow.get("key_col", 0))
        lines = [f"Name: {typed}_", ""]
        for r, row in enumerate(key_rows):
            parts: List[str] = []
            for c, token in enumerate(row):
                t = token
                if r == cur_row and c == cur_col:
                    parts.append(f"[{t}]")
                else:
                    parts.append(f" {t} ")
            lines.append(" ".join(parts))
        return UIBoxSpec(
            role="name_input",
            border_style="double",
            title="Custom Name",
            body_text="\n".join(lines + ["", "Arrows move. A selects key."]),
            center_x=50,
            center_y=17,
            max_body_width=72,
            body_align="left",
            actions=["[ A / Key ]", "[ S / Cancel ]"],
            preserve_body_whitespace=True,
        )

    if screen == "fortune_select":
        options = ["Poor (10 GP)", "Well-Off (100 GP)", "Royalty (1000 GP)"]
        cursor = int(flow.get("fortune_cursor", 1)) % len(options)
        lines = _format_select_lines(options, cursor)
        return UIBoxSpec(
            role="fortune_select",
            border_style="heavy",
            title="Choose Fortune",
            body_text="\n".join(lines + ["", "Select your starting gold."]),
            center_x=50,
            center_y=17,
            max_body_width=42,
            body_align="left",
            actions=["[ A / Confirm ]", "[ S / Back ]"],
            preserve_body_whitespace=True,
            blink_body_rows=[cursor],
        )

    if screen == "start_confirm":
        return UIBoxSpec(
            role="start_confirm",
            border_style="heavy",
            title="Begin Adventure",
            body_text=(
                f"Avatar: {flow.get('avatar_label', 'Adventurer')}\n"
                f"Name: {flow.get('selected_name', 'WARRIOR')}\n"
                f"Fortune: {flow.get('fortune_choice', 'Well-Off (100 GP)')}\n\n"
                "Start this new game setup?"
            ),
            center_x=50,
            center_y=17,
            max_body_width=52,
            body_align="left",
            wrap_mode="balanced",
            actions=["[ A / Start ]", "[ S / Back ]"],
        )

    if screen == "story_1":
        return UIBoxSpec(
            role="story",
            border_style="heavy",
            title="Story",
            body_text=(
                "One day as you are walking home you hear a commotion. "
                "You stumble upon a small magic mushroom and a crow who appear to be fighting."
            ),
            center_x=50,
            center_y=17,
            max_body_width=52,
            wrap_mode="balanced",
            body_align="left",
            actions=["[ A / Continue ]"],
        )

    if screen == "story_4":
        return UIBoxSpec(
            role="story",
            border_style="heavy",
            title="Mushy",
            body_text="Hey you! You seem like a nice person. Would you come help me deal with this pesky crow?",
            center_x=50,
            center_y=17,
            max_body_width=42,
            wrap_mode="balanced",
            body_align="left",
            actions=["[ A / Continue ]"],
        )

    if screen == "story_5":
        return UIBoxSpec(
            role="story",
            border_style="double",
            title="Mushy",
            body_text=(
                "I have a Magic Staff embued with the Magic Spark spell. "
                "If you can figure out how to use it, we can get rid of this crow together."
            ),
            center_x=50,
            center_y=17,
            max_body_width=44,
            wrap_mode="balanced",
            body_align="left",
            actions=["[ A / Accept Mycostaff ]"],
        )

    if screen == "story_6":
        return UIBoxSpec(
            role="story",
            border_style="heavy",
            title="Mushy",
            body_text="Great! Now let's show this crow who is boss around here.",
            center_x=50,
            center_y=17,
            max_body_width=40,
            wrap_mode="balanced",
            body_align="left",
            actions=["[ A / Continue ]"],
        )

    if screen == "story_battle_cmd_player":
        options = _actor_action_options("player")
        cursor = int(flow.get("battle_player_cmd_idx", 0)) % len(options)
        lines = _format_select_lines(options, cursor)
        return UIBoxSpec(
            role="battle_select",
            border_style="double",
            title=str(flow.get("selected_name", flow.get("avatar_label", "Player"))),
            body_text="\n" + "\n".join(lines),
            center_x=50,
            center_y=17,
            max_body_width=32,
            body_align="left",
            actions=["[ A / Confirm ]", "[ S / Back ]"],
            blink_body_rows=[1 + cursor],
            preserve_body_whitespace=True,
        )

    if screen == "story_battle_cmd_mushy":
        options = _actor_action_options("mushy")
        cursor = int(flow.get("battle_mushy_cmd_idx", 0)) % len(options)
        lines = _format_select_lines(options, cursor)
        return UIBoxSpec(
            role="battle_select",
            border_style="double",
            title="Mushy",
            body_text="\n" + "\n".join(lines),
            center_x=50,
            center_y=17,
            max_body_width=32,
            body_align="left",
            actions=["[ A / Confirm ]", "[ S / Back ]"],
            blink_body_rows=[1 + cursor],
            preserve_body_whitespace=True,
        )

    if screen == "story_battle_cmd_sharoom":
        options = _actor_action_options("sharoom")
        cursor = int(flow.get("battle_sharoom_cmd_idx", 0)) % len(options)
        lines = _format_select_lines(options, cursor)
        return UIBoxSpec(
            role="battle_select",
            border_style="double",
            title="Sharoom",
            body_text="\n" + "\n".join(lines),
            center_x=50,
            center_y=17,
            max_body_width=34,
            body_align="left",
            actions=["[ A / Confirm ]", "[ S / Back ]"],
            blink_body_rows=[1 + cursor],
            preserve_body_whitespace=True,
        )

    if screen == "story_battle_ally_target":
        actor_key = str(flow.get("battle_ally_select_actor", "mushy")).strip().lower()
        action = str(flow.get("battle_ally_action", "Mushroom Tea"))
        supports_all = bool(flow.get("battle_ally_supports_all", False))
        mode = str(flow.get("battle_ally_target_mode", "single"))
        desc = str(flow.get("battle_ally_desc", "")).strip()
        who = "Mushy" if actor_key == "mushy" else ("Sharoom" if actor_key == "sharoom" else actor_key.title())
        mode_line = f"Mode: {'ALL' if mode == 'all' else 'Single'}"
        hint = "Left/Right: target"
        if supports_all:
            hint += "  Up/Down: Single/All"
        return UIBoxSpec(
            role="battle_select",
            border_style="double",
            title=f"{who} - {action}",
            body_text=f"\n{desc}\n\n{mode_line}\n{hint}",
            center_x=50,
            center_y=17,
            max_body_width=56,
            body_align="left",
            actions=["[ A / Confirm ]", "[ S / Back ]"],
            preserve_body_whitespace=True,
        )

    if screen == "story_battle_victory":
        return UIBoxSpec(
            role="story",
            border_style="heavy",
            title="Mushy",
            body_text="Next we should seek out Roomie. I think he is looking for a place to stay...",
            center_x=50,
            center_y=17,
            max_body_width=44,
            wrap_mode="balanced",
            body_align="left",
            actions=["[ A / Continue ]"],
        )

    if screen == "story_sharoom_1":
        return UIBoxSpec(
            role="story",
            border_style="heavy",
            title="Mushy",
            body_text="We should seek out my friend Sharoom. She is a powerful magic user, who can give us a boost.",
            center_x=50,
            center_y=17,
            max_body_width=44,
            wrap_mode="balanced",
            body_align="left",
            actions=["[ A / Continue ]"],
        )

    if screen == "story_sharoom_3":
        return UIBoxSpec(
            role="story",
            border_style="heavy",
            title="Mushy",
            body_text="Sharoom, the time has come! Crow war is on. Come join our fight...",
            center_x=50,
            center_y=17,
            max_body_width=44,
            wrap_mode="balanced",
            body_align="left",
            actions=["[ A / Continue ]"],
        )

    if screen == "story_sharoom_4":
        return UIBoxSpec(
            role="story",
            border_style="double",
            title="Sharoom",
            body_text="Let's do this!",
            center_x=50,
            center_y=17,
            max_body_width=28,
            wrap_mode="balanced",
            body_align="left",
            actions=["[ A / Continue ]"],
        )

    if screen == "story_more_crows":
        return UIBoxSpec(
            role="story",
            border_style="heavy",
            title="Mushy",
            body_text="Uh oh, more crows. Let's take them together!",
            center_x=50,
            center_y=17,
            max_body_width=40,
            wrap_mode="balanced",
            body_align="left",
            actions=["[ A / Continue ]"],
        )

    if screen in (
        "story_2",
        "story_actor_entrance",
        "story_sharoom_entrance",
        "story_sharoom_lineup_shift",
        "story_battle2_entrance",
        "story_battle3_entrance",
        "story_battle_resolve",
        "story_battle3_resolve",
        "story_lineup_shift",
    ):
        return None

    message = str(flow.get("message_text", ""))
    return UIBoxSpec(
        role="info",
        border_style="light",
        title="Notice",
        body_text=message or "Demo placeholder.",
        center_x=50,
        center_y=17,
        max_body_width=50,
        body_align="center",
        wrap_mode="balanced",
        actions=["[ A / OK ]", "[ S / Back ]"],
    )


def _anchor_box_next_to_actor(spec: UIBoxSpec, actor: dict, prefer: str = "auto") -> UIBoxSpec:
    rows = actor.get("rows", [])
    if not isinstance(rows, list) or not rows:
        return spec
    w = max((len(r) for r in rows), default=0)
    h = len(rows)
    ax0 = int(actor.get("x", 0))
    ay0 = int(actor.get("y", 0))
    actor_cx = ax0 + (w // 2)
    actor_cy = ay0 + (h // 2)
    side = str(prefer).strip().lower()
    if side not in ("left", "right"):
        side = "left" if actor_cx > (SCREEN_W // 2) else "right"

    spec.x = None
    spec.y = None
    spec.center_y = max(2, min(SCREEN_H - 3, actor_cy))
    if side == "right":
        # Render box to the right of actor.
        spec.anchor = "left"
        spec.center_x = min(SCREEN_W - 2, ax0 + w + 2)
    else:
        # Render box to the left of actor.
        spec.anchor = "right"
        spec.center_x = max(1, ax0 - 2)
    return spec


def _position_screen_box_for_actors(
    screen: str,
    spec: UIBoxSpec | None,
    primary_placements: List[dict],
    secondary_placements: List[dict],
) -> UIBoxSpec | None:
    if not isinstance(spec, UIBoxSpec):
        return spec
    if screen in ("story_4", "story_5", "story_6", "story_11") and primary_placements:
        idx = 1 if len(primary_placements) >= 2 else 0
        return _anchor_box_next_to_actor(spec, primary_placements[idx], prefer="left")
    if screen in ("story_sharoom_1", "story_more_crows") and len(secondary_placements) >= 2:
        return _anchor_box_next_to_actor(spec, secondary_placements[1], prefer="right")
    if screen == "story_sharoom_3" and len(secondary_placements) >= 2:
        return _anchor_box_next_to_actor(spec, secondary_placements[1], prefer="right")
    if screen == "story_sharoom_4" and primary_placements:
        return _anchor_box_next_to_actor(spec, primary_placements[0], prefer="left")
    if screen in ("story_7", "story_9", "story_battle_cmd_player") and secondary_placements:
        idx = 1 if len(secondary_placements) >= 3 else 0
        return _anchor_box_next_to_actor(spec, secondary_placements[idx], prefer="right")
    if screen == "story_battle_cmd_mushy" and len(secondary_placements) >= 2:
        idx = 2 if len(secondary_placements) >= 3 else 1
        return _anchor_box_next_to_actor(spec, secondary_placements[idx], prefer="right")
    if screen == "story_battle_cmd_sharoom" and secondary_placements:
        return _anchor_box_next_to_actor(spec, secondary_placements[0], prefer="right")
    if screen == "story_battle_ally_target" and secondary_placements:
        actor_key = str(spec.title or "").lower()
        idx = 1 if len(secondary_placements) >= 3 else 0
        if "sharoom" in actor_key:
            idx = 0
        elif "mushy" in actor_key:
            idx = 2 if len(secondary_placements) >= 3 else 1
        return _anchor_box_next_to_actor(spec, secondary_placements[idx], prefer="right")
    if screen in ("story_battle_victory", "story_more_crows") and len(secondary_placements) >= 2:
        return _anchor_box_next_to_actor(spec, secondary_placements[1], prefer="right")
    return spec


def _alive_indices(hp_values: List[int]) -> List[int]:
    return [idx for idx, hp in enumerate(hp_values) if int(hp) > 0]


def _first_alive(hp_values: List[int], fallback: int = 0) -> int:
    alive = _alive_indices(hp_values)
    return alive[0] if alive else fallback


def _next_alive_index(hp_values: List[int], current: int, step: int) -> int:
    alive = _alive_indices(hp_values)
    if not alive:
        return 0
    if current not in alive:
        return alive[0]
    pos = alive.index(current)
    return alive[(pos + step) % len(alive)]


# v06 combat notes (physical attacks):
# 1) Per-hit luck roll for attacker and defender.
# 2) luck roll is uniform integer in [0, Luck].
# 3) attack_total = base_atk + attacker_luck_roll.
# 4) defense_total = base_def + defender_luck_roll.
# 5) damage = max(0, attack_total - defense_total).
def _roll_physical_damage(
    rng: random.Random,
    attacker_atk: int,
    attacker_luck: int,
    defender_def: int,
    defender_luck: int,
) -> int:
    atk_roll = rng.randint(0, max(0, int(attacker_luck)))
    def_roll = rng.randint(0, max(0, int(defender_luck)))
    atk_total = int(attacker_atk) + atk_roll
    def_total = int(defender_def) + def_roll
    return max(0, atk_total - def_total)


def _build_battle_round_actions(flow: dict) -> List[dict]:
    rng = random.Random(time.monotonic_ns())
    pri_hp = [int(v) for v in flow.get("battle_primary_hp", [10, 10])]
    sec_hp = [int(v) for v in flow.get("battle_secondary_hp", [20, 10])]
    sec_mp = [int(v) for v in flow.get("battle_secondary_mp", [0, 6])]
    sec_hp_max = [int(v) for v in flow.get("battle_secondary_hp_max", sec_hp)]
    sec_mp_max = [int(v) for v in flow.get("battle_secondary_mp_max", sec_mp)]
    staff_charges = max(0, int(flow.get("battle_staff_charges", 3)))
    stage = int(flow.get("battle_stage", 1))
    player_idx = 1 if stage >= 3 else 0
    mushy_idx = 2 if stage >= 3 else 1
    sharoom_idx = 0 if stage >= 3 else -1
    sec_base_atk = [2 for _ in sec_hp]
    sec_base_def = [2 for _ in sec_hp]
    sec_base_luck = [2 for _ in sec_hp]
    if 0 <= player_idx < len(sec_hp):
        sec_base_atk[player_idx] = 1
        sec_base_def[player_idx] = 1
        sec_base_luck[player_idx] = 2
    sec_boost_atk = [max(0, int(v)) for v in flow.get("battle_secondary_boost_atk", [0 for _ in sec_hp])]
    sec_boost_def = [max(0, int(v)) for v in flow.get("battle_secondary_boost_def", [0 for _ in sec_hp])]
    if len(sec_boost_atk) < len(sec_hp):
        sec_boost_atk.extend([0] * (len(sec_hp) - len(sec_boost_atk)))
    if len(sec_boost_def) < len(sec_hp):
        sec_boost_def.extend([0] * (len(sec_hp) - len(sec_boost_def)))
    pri_base_atk = [3 for _ in pri_hp]
    pri_base_def = [0 for _ in pri_hp]
    pri_base_luck = [2 for _ in pri_hp]
    queue: List[dict] = []
    defending: set[int] = set()
    defended_was_attacked: set[int] = set()

    def _valid_enemy_target(raw_target: int) -> int:
        target = int(raw_target)
        if target < 0 or target >= len(pri_hp):
            target = _first_alive(pri_hp, 0)
        if 0 <= target < len(pri_hp) and pri_hp[target] <= 0:
            target = _first_alive(pri_hp, target)
        return target

    def _enqueue_physical_from_secondary(actor_idx: int, flow_target_key: str) -> bool:
        if not _alive_indices(pri_hp) or actor_idx < 0 or actor_idx >= len(sec_hp) or sec_hp[actor_idx] <= 0:
            return False
        target = _valid_enemy_target(int(flow.get(flow_target_key, 0)))
        atk_val = sec_base_atk[actor_idx] + sec_boost_atk[actor_idx]
        dmg = _roll_physical_damage(
            rng,
            attacker_atk=atk_val,
            attacker_luck=sec_base_luck[actor_idx],
            defender_def=pri_base_def[target],
            defender_luck=pri_base_luck[target],
        )
        pre_hp = pri_hp[target]
        post_hp = max(0, pre_hp - dmg)
        queue.append(
            {
                "kind": "physical",
                "source_side": "secondary",
                "source_index": actor_idx,
                "target_side": "primary",
                "target_index": target,
                "damage": dmg,
                "pre_hp": pre_hp,
                "post_hp": post_hp,
            }
        )
        pri_hp[target] = post_hp
        return True

    turn_order: List[tuple[str, int, str]] = []
    if stage >= 3 and 0 <= sharoom_idx < len(sec_hp):
        turn_order.append(("sharoom", sharoom_idx, "battle_sharoom_target"))
    if 0 <= player_idx < len(sec_hp):
        turn_order.append(("player", player_idx, "battle_player_target"))
    if 0 <= mushy_idx < len(sec_hp):
        turn_order.append(("mushy", mushy_idx, "battle_mushy_target"))

    for actor_key, actor_idx, target_key in turn_order:
        if actor_idx < 0 or actor_idx >= len(sec_hp) or sec_hp[actor_idx] <= 0:
            continue
        action = str(flow.get(f"battle_{actor_key}_action", "Attack")).strip()
        if action == "Defend":
            defending.add(actor_idx)
            queue.append(
                {
                    "kind": "defend",
                    "source_side": "secondary",
                    "source_index": actor_idx,
                }
            )
            continue
        if action == "Attack":
            _enqueue_physical_from_secondary(actor_idx, target_key)
            continue
        if actor_key == "player" and action == "Magic Spark":
            can_cast = _alive_indices(pri_hp) and (staff_charges > 0 or (actor_idx < len(sec_mp) and sec_mp[actor_idx] >= 2))
            if not can_cast:
                _enqueue_physical_from_secondary(actor_idx, target_key)
                continue
            target = _valid_enemy_target(int(flow.get(target_key, 0)))
            dmg = rng.randint(5, 8)
            pre_hp = pri_hp[target]
            post_hp = max(0, pre_hp - dmg)
            uses_charge = staff_charges > 0
            uses_mp = not uses_charge
            pre_mp = sec_mp[actor_idx]
            post_mp = max(0, sec_mp[actor_idx] - 2) if uses_mp else sec_mp[actor_idx]
            pre_charges = staff_charges
            post_charges = max(0, staff_charges - 1) if uses_charge else staff_charges
            queue.append(
                {
                    "kind": "spell",
                    "spell_name": "Magic Spark",
                    "source_side": "secondary",
                    "source_index": actor_idx,
                    "target_side": "primary",
                    "target_index": target,
                    "damage": dmg,
                    "pre_hp": pre_hp,
                    "post_hp": post_hp,
                    "pre_mp": pre_mp,
                    "post_mp": post_mp,
                    "mp_cost": 2 if uses_mp else 0,
                    "uses_mp": uses_mp,
                    "pre_charges": pre_charges,
                    "post_charges": post_charges,
                }
            )
            pri_hp[target] = post_hp
            sec_mp[actor_idx] = post_mp
            staff_charges = post_charges
            continue
        if actor_key == "mushy" and action == "Mushroom Tea":
            if actor_idx >= len(sec_mp) or sec_mp[actor_idx] < 2:
                _enqueue_physical_from_secondary(actor_idx, target_key)
                continue
            allies = _alive_secondary_target_indices(flow, "mushy", "Mushroom Tea", stage)
            if not allies:
                allies = [actor_idx]
            raw_t = int(flow.get("battle_mushy_spell_target", allies[0]))
            target_ally = raw_t if raw_t in allies else allies[0]
            pre_mp = sec_mp[actor_idx]
            post_mp = max(0, pre_mp - 2)
            pre_atk = sec_boost_atk[target_ally]
            pre_def = sec_boost_def[target_ally]
            post_atk = pre_atk + 3
            post_def = pre_def + 3
            sec_mp[actor_idx] = post_mp
            sec_boost_atk[target_ally] = post_atk
            sec_boost_def[target_ally] = post_def
            queue.append(
                {
                    "kind": "mushroom_tea",
                    "source_side": "secondary",
                    "source_index": actor_idx,
                    "target_side": "secondary",
                    "target_index": target_ally,
                    "pre_mp": pre_mp,
                    "post_mp": post_mp,
                    "mp_cost": 2,
                    "effects": [
                        {"type": "set_secondary_mp", "index": actor_idx, "value": post_mp},
                        {"type": "set_secondary_boost_atk", "index": target_ally, "value": post_atk},
                        {"type": "set_secondary_boost_def", "index": target_ally, "value": post_def},
                    ],
                }
            )
            continue
        if actor_key == "sharoom" and action == "Healing Touch":
            if actor_idx >= len(sec_mp) or sec_mp[actor_idx] < 2:
                _enqueue_physical_from_secondary(actor_idx, target_key)
                continue
            mode = str(flow.get("battle_sharoom_spell_target_mode", "single")).strip().lower()
            valid_targets = _alive_secondary_target_indices(flow, "sharoom", "Healing Touch", stage)
            pre_mp = sec_mp[actor_idx]
            post_mp = max(0, pre_mp - 2)
            sec_mp[actor_idx] = post_mp
            effects = [{"type": "set_secondary_mp", "index": actor_idx, "value": post_mp}]
            if mode == "all":
                heals: List[dict] = []
                for i in valid_targets:
                    pre = sec_hp[i]
                    post = min(sec_hp_max[i], pre + 2)
                    sec_hp[i] = post
                    heals.append({"index": i, "pre_hp": pre, "post_hp": post, "amount": max(0, post - pre)})
                    effects.append({"type": "set_secondary_hp", "index": i, "value": post})
                queue.append(
                    {
                        "kind": "healing_touch_team",
                        "source_side": "secondary",
                        "source_index": actor_idx,
                        "pre_mp": pre_mp,
                        "post_mp": post_mp,
                        "mp_cost": 2,
                        "heals": heals,
                        "effects": effects,
                    }
                )
            else:
                raw_t = int(flow.get("battle_sharoom_spell_target", actor_idx))
                target_ally = raw_t if raw_t in valid_targets else (valid_targets[0] if valid_targets else actor_idx)
                pre = sec_hp[target_ally]
                post = min(sec_hp_max[target_ally], pre + 5)
                sec_hp[target_ally] = post
                effects.append({"type": "set_secondary_hp", "index": target_ally, "value": post})
                queue.append(
                    {
                        "kind": "healing_touch_single",
                        "source_side": "secondary",
                        "source_index": actor_idx,
                        "target_side": "secondary",
                        "target_index": target_ally,
                        "pre_mp": pre_mp,
                        "post_mp": post_mp,
                        "mp_cost": 2,
                        "heal_amount": max(0, post - pre),
                        "pre_hp": pre,
                        "post_hp": post,
                        "effects": effects,
                    }
                )
            continue
        if actor_key == "roomy" and action == "Concentric":
            if actor_idx >= len(sec_mp) or sec_mp[actor_idx] < 2:
                _enqueue_physical_from_secondary(actor_idx, target_key)
                continue
            pre_mp = sec_mp[actor_idx]
            post_mp = max(0, pre_mp - 2)
            sec_mp[actor_idx] = post_mp
            restores: List[dict] = []
            effects = [{"type": "set_secondary_mp", "index": actor_idx, "value": post_mp}]
            for i in range(len(sec_mp)):
                if i == actor_idx or sec_hp[i] <= 0:
                    continue
                pre = sec_mp[i]
                post = min(sec_mp_max[i], pre + 1)
                sec_mp[i] = post
                restores.append({"index": i, "pre_mp": pre, "post_mp": post, "amount": max(0, post - pre)})
                effects.append({"type": "set_secondary_mp", "index": i, "value": post})
            queue.append(
                {
                    "kind": "concentric",
                    "source_side": "secondary",
                    "source_index": actor_idx,
                    "pre_mp": pre_mp,
                    "post_mp": post_mp,
                    "mp_cost": 2,
                    "restores": restores,
                    "effects": effects,
                }
            )
            continue
        _enqueue_physical_from_secondary(actor_idx, target_key)

    for crow_idx in _alive_indices(pri_hp):
        alive_sec = _alive_indices(sec_hp)
        if not alive_sec:
            break
        target = alive_sec[rng.randrange(len(alive_sec))]
        def_luck = sec_base_luck[target] * (3 if target in defending else 1)
        if target in defending:
            defended_was_attacked.add(target)
        def_val = sec_base_def[target] + sec_boost_def[target]
        dmg = _roll_physical_damage(
            rng,
            attacker_atk=pri_base_atk[crow_idx],
            attacker_luck=pri_base_luck[crow_idx],
            defender_def=def_val,
            defender_luck=def_luck,
        )
        pre_hp = sec_hp[target]
        post_hp = max(0, pre_hp - dmg)
        queue.append(
            {
                "kind": "physical",
                "source_side": "primary",
                "source_index": crow_idx,
                "target_side": "secondary",
                "target_index": target,
                "damage": dmg,
                "pre_hp": pre_hp,
                "post_hp": post_hp,
            }
        )
        sec_hp[target] = post_hp

    for idx in sorted(defending):
        if idx in defended_was_attacked or idx < 0 or idx >= len(sec_hp) or sec_hp[idx] <= 0:
            continue
        if idx < len(sec_mp_max) and sec_mp_max[idx] > 0 and sec_mp[idx] < sec_mp_max[idx]:
            pre = sec_mp[idx]
            post = min(sec_mp_max[idx], pre + 1)
            sec_mp[idx] = post
            queue.append(
                {
                    "kind": "defend_convert",
                    "source_side": "secondary",
                    "source_index": idx,
                    "convert_stat": "MP",
                    "pre_value": pre,
                    "post_value": post,
                    "effects": [{"type": "set_secondary_mp", "index": idx, "value": post}],
                }
            )
        elif idx < len(sec_hp_max) and sec_hp[idx] < sec_hp_max[idx]:
            pre = sec_hp[idx]
            post = min(sec_hp_max[idx], pre + 1)
            sec_hp[idx] = post
            queue.append(
                {
                    "kind": "defend_convert",
                    "source_side": "secondary",
                    "source_index": idx,
                    "convert_stat": "HP",
                    "pre_value": pre,
                    "post_value": post,
                    "effects": [{"type": "set_secondary_hp", "index": idx, "value": post}],
                }
            )

    flow["battle_secondary_boost_atk"] = [max(0, int(v) - 1) for v in sec_boost_atk[: len(sec_hp)]]
    flow["battle_secondary_boost_def"] = [max(0, int(v) - 1) for v in sec_boost_def[: len(sec_hp)]]
    return queue


def _battle_actor_name(side: str, idx: int, stage: int, player_name: str) -> str:
    side_key = str(side).strip().lower()
    i = int(idx)
    if side_key == "primary":
        return "Baby Crow"
    if stage >= 3:
        if i == 0:
            return "Sharoom"
        if i == 1:
            return player_name
        if i == 2:
            return "Mushy"
        return f"Ally {i + 1}"
    if i == 0:
        return player_name
    if i == 1:
        return "Mushy"
    return f"Ally {i + 1}"


def _battle_action_log_lines(action: dict, stage: int, player_name: str) -> List[str]:
    if not isinstance(action, dict):
        return []
    kind = str(action.get("kind", "physical"))
    source_side = str(action.get("source_side", "secondary"))
    source_idx = int(action.get("source_index", 0))
    target_side = str(action.get("target_side", "primary"))
    target_idx = int(action.get("target_index", 0))
    damage = max(0, int(action.get("damage", 0)))
    pre_hp = max(0, int(action.get("pre_hp", 0)))
    post_hp = max(0, int(action.get("post_hp", 0)))
    src = _battle_actor_name(source_side, source_idx, stage, player_name)
    dst = _battle_actor_name(target_side, target_idx, stage, player_name)
    if kind == "spell":
        lines = [f"{src} casts Magic Spark on {dst} for {damage} damage."]
    elif kind == "physical":
        lines = [f"{src} attacks {dst} for {damage} damage."]
    elif kind == "defend":
        lines = [f"{src} takes a defensive stance."]
    elif kind == "defend_convert":
        stat = str(action.get("convert_stat", "HP"))
        lines = [f"{src} converts defend into +1 {stat}."]
    elif kind == "mushroom_tea":
        lines = [f"{src} uses Mushroom Tea on {dst}, boosting Attack and Defense."]
    elif kind == "healing_touch_single":
        heal_amount = max(0, int(action.get("heal_amount", 0)))
        lines = [f"{src} uses Healing Touch on {dst}, restoring {heal_amount} HP."]
    elif kind == "healing_touch_team":
        lines = [f"{src} uses Healing Touch on the whole team."]
    elif kind == "concentric":
        lines = [f"{src} uses Concentric to restore team MP."]
    else:
        lines = [f"{src} acts."]
    if pre_hp > 0 and post_hp <= 0:
        lines.append(f"{dst} has been defeated.")
    return lines


def _battle_log_start(flow: dict, stage: int) -> None:
    flow["battle_log_committed"] = []
    flow["battle_log_pending"] = []
    flow["battle_log_active"] = None
    flow["battle_log_active_chars"] = 0
    if int(stage) >= 3:
        opener = "Battle begins: Sharoom, Player, and Mushy vs 3 Baby Crows."
    elif int(stage) == 2:
        opener = "Battle begins: Player and Mushy vs 2 Baby Crows."
    else:
        opener = "Battle begins: Player and Mushy vs Baby Crow."
    flow["battle_log_pending"] = [opener]


def _battle_log_enqueue(flow: dict, lines: List[str]) -> None:
    if not isinstance(lines, list):
        return
    pending = flow.get("battle_log_pending")
    if not isinstance(pending, list):
        pending = []
    for line in lines:
        text = str(line).strip()
        if text:
            pending.append(text)
    flow["battle_log_pending"] = pending


def _battle_log_tick(flow: dict, dt: float) -> None:
    cps = 38.0
    pending = flow.get("battle_log_pending")
    if not isinstance(pending, list):
        pending = []
    active = flow.get("battle_log_active")
    if not isinstance(active, str) or active == "":
        if pending:
            active = str(pending.pop(0))
            flow["battle_log_active"] = active
            flow["battle_log_active_chars"] = 0
        else:
            flow["battle_log_active"] = None
            flow["battle_log_active_chars"] = 0
            flow["battle_log_pending"] = pending
            return
    chars = int(flow.get("battle_log_active_chars", 0)) + int(max(0.0, dt) * cps)
    active = str(flow.get("battle_log_active", ""))
    committed = flow.get("battle_log_committed")
    if not isinstance(committed, list):
        committed = []
    if chars >= len(active):
        committed.append(active)
        flow["battle_log_committed"] = committed[-200:]
        flow["battle_log_active"] = None
        flow["battle_log_active_chars"] = 0
    else:
        flow["battle_log_active_chars"] = chars
    flow["battle_log_pending"] = pending


def _battle_log_visible_lines(flow: dict) -> List[str]:
    committed = flow.get("battle_log_committed")
    if not isinstance(committed, list):
        committed = []
    out = [str(line) for line in committed if str(line)]
    active = flow.get("battle_log_active")
    if isinstance(active, str) and active:
        chars = max(0, min(len(active), int(flow.get("battle_log_active_chars", 0))))
        out.append(active[:chars])
    return out


def _draw_battle_log_panel(
    canvas: List[List[str]],
    lines: List[str] | None,
    width: int = 40,
    height: int = 10,
) -> None:
    w = max(8, int(width))
    h = max(5, int(height))
    x0 = max(0, SCREEN_W - w)
    y0 = max(0, SCREEN_H - h)
    tl, tr, bl, br = "\u250c", "\u2510", "\u2514", "\u2518"
    hz, vt = "\u2500", "\u2502"
    for dx in range(w):
        x = x0 + dx
        if 0 <= x < SCREEN_W and 0 <= y0 < SCREEN_H:
            ch = tl if dx == 0 else (tr if dx == w - 1 else hz)
            g = battle_log_border_gradient_code(dx, 0, w, h)
            canvas[y0][x] = f"{g}{ch}{ANSI_RESET}"
    for dy in range(1, h - 1):
        y = y0 + dy
        if not (0 <= y < SCREEN_H):
            continue
        for dx in range(w):
            x = x0 + dx
            if not (0 <= x < SCREEN_W):
                continue
            if dx == 0 or dx == w - 1:
                g = battle_log_border_gradient_code(dx, dy, w, h)
                canvas[y][x] = f"{g}{vt}{ANSI_RESET}"
            else:
                canvas[y][x] = " "
    yb = y0 + h - 1
    for dx in range(w):
        x = x0 + dx
        if 0 <= x < SCREEN_W and 0 <= yb < SCREEN_H:
            ch = bl if dx == 0 else (br if dx == w - 1 else hz)
            g = battle_log_border_gradient_code(dx, h - 1, w, h)
            canvas[yb][x] = f"{g}{ch}{ANSI_RESET}"
    if not lines:
        return
    inner_w = max(1, w - 2)
    inner_h = max(1, h - 2)
    wrapped: List[str] = []
    for line in lines:
        text = str(line).strip()
        if not text:
            wrapped.append("")
            continue
        wrapped.extend(
            textwrap.wrap(
                text,
                width=inner_w,
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    visible = wrapped[-inner_h:]
    start_y = y0 + 1 + max(0, inner_h - len(visible))
    for row_idx, line in enumerate(visible):
        y = start_y + row_idx
        if not (0 <= y < SCREEN_H):
            continue
        for i, ch in enumerate(line[:inner_w]):
            x = x0 + 1 + i
            if 0 <= x < SCREEN_W:
                g = battle_log_text_gradient_code(i, row_idx, inner_w, max(1, len(visible)))
                canvas[y][x] = f"{g}{ch}{ANSI_RESET}"


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


def _mp_fill_color(pct: float) -> str:
    p = max(0.0, min(1.0, float(pct)))
    start = (120, 175, 255)
    end = (40, 120, 255)
    r = int(start[0] + ((end[0] - start[0]) * p))
    g = int(start[1] + ((end[1] - start[1]) * p))
    b = int(start[2] + ((end[2] - start[2]) * p))
    return f"\x1b[38;2;{r};{g};{b}m"


def _draw_health_bar_custom(
    canvas: List[List[str]],
    center_x: int,
    top_y: int,
    filled: int,
    total: int = 10,
    fill_color: str | None = None,
    frame_color: str | None = None,
    overlay_text: str | None = None,
    overlay_color: str = "\x1b[38;2;245;245;245m",
    row_label: str | None = None,
) -> None:
    total = max(1, int(total))
    filled = max(0, min(total, int(filled)))
    empty = total - filled
    pct = filled / float(total)
    if fill_color is None:
        if pct >= 0.5:
            fill_color = "\x1b[38;2;56;186;72m"
        elif pct >= 0.25:
            fill_color = "\x1b[38;2;236;201;58m"
        else:
            fill_color = "\x1b[38;2;220;70;70m"
    miss_color = "\x1b[38;2;26;26;26m"
    frame_color = frame_color or "\x1b[38;2;210;210;210m"

    def _fg_to_bg(code: str) -> str:
        m = re.search(r"\x1b\[38;2;(\d+);(\d+);(\d+)m", str(code))
        if not m:
            return ""
        return f"\x1b[48;2;{m.group(1)};{m.group(2)};{m.group(3)}m"

    inner_w = total
    box_w = inner_w + 2
    x0 = max(0, min(SCREEN_W - box_w, int(center_x) - (box_w // 2)))
    y0 = int(top_y)
    if y0 < 0 or (y0 + 2) >= SCREEN_H:
        return

    tl, tr = "\u250c", "\u2510"
    bl, br = "\u2514", "\u2518"
    hz, vt = "\u2500", "\u2502"
    fill_ch, miss_ch = "\u2588", "\u00b7"

    top_row: List[str] = [f"{frame_color}{tl}{ANSI_RESET}"]
    top_row.extend([f"{frame_color}{hz}{ANSI_RESET}" for _ in range(inner_w)])
    top_row.append(f"{frame_color}{tr}{ANSI_RESET}")

    styles: List[str] = ([fill_color] * filled) + ([miss_color] * empty)
    mid_row: List[str] = [f"{frame_color}{vt}{ANSI_RESET}"]
    for idx, style in enumerate(styles):
        ch = fill_ch if idx < filled else miss_ch
        mid_row.append(f"{style}{ch}{ANSI_RESET}")
    mid_row.append(f"{frame_color}{vt}{ANSI_RESET}")

    label = str(row_label or "").strip()
    if label:
        for i, ch in enumerate(label[:inner_w]):
            style = styles[i] if i < len(styles) else miss_color
            bg = _fg_to_bg(style)
            mid_row[1 + i] = f"\x1b[38;2;245;245;245m{bg}{ch}{ANSI_RESET}" if bg else f"\x1b[38;2;245;245;245m{ch}{ANSI_RESET}"

    if overlay_text:
        text = str(overlay_text)
        start = 1 + max(0, (inner_w - len(text)) // 2)
        for i, ch in enumerate(text):
            x = start + i
            if 1 <= x <= inner_w:
                style_idx = x - 1
                style = styles[style_idx] if 0 <= style_idx < len(styles) else miss_color
                bg = _fg_to_bg(style)
                mid_row[x] = f"{overlay_color}{bg}{ch}{ANSI_RESET}" if bg else f"{overlay_color}{ch}{ANSI_RESET}"

    bot_row: List[str] = [f"{frame_color}{bl}{ANSI_RESET}"]
    bot_row.extend([f"{frame_color}{hz}{ANSI_RESET}" for _ in range(inner_w)])
    bot_row.append(f"{frame_color}{br}{ANSI_RESET}")

    for dy, row in enumerate([top_row, mid_row, bot_row]):
        y = y0 + dy
        if y < 0 or y >= SCREEN_H:
            continue
        for dx, cell in enumerate(row):
            x = x0 + dx
            if 0 <= x < SCREEN_W:
                canvas[y][x] = cell


def _draw_damage_hud_step(
    canvas: List[List[str]],
    target_actor: dict,
    progress: float,
    pre_hp: int,
    post_hp: int,
    total: int,
    damage: int,
) -> None:
    rows = target_actor.get("rows", [])
    if not isinstance(rows, list) or not rows:
        return
    w = max((len(row) for row in rows), default=0)
    x0 = int(target_actor.get("x", 0))
    y0 = int(target_actor.get("y", 0))
    cx = x0 + (w // 2)
    bar_top = y0 - 4
    p = max(0.0, min(1.0, float(progress)))
    if p < 0.50:
        _draw_health_bar_custom(canvas, cx, bar_top, pre_hp, total=total, row_label="HP")
        return
    if p < 0.75:
        flash_on = (int((p - 0.50) / 0.06) % 2) == 0
        _draw_health_bar_custom(
            canvas,
            cx,
            bar_top,
            pre_hp,
            total=total,
            fill_color="\x1b[38;2;255;95;95m" if flash_on else None,
            frame_color="\x1b[38;2;255;170;170m" if flash_on else None,
            overlay_text=f"-{damage}",
            overlay_color="\x1b[38;2;250;250;250m",
            row_label="HP",
        )
        return
    _draw_health_bar_custom(canvas, cx, bar_top, post_hp, total=total, overlay_text=f"-{damage}", row_label="HP")


def _draw_mp_cast_hud_step(
    canvas: List[List[str]],
    caster_actor: dict,
    progress: float,
    pre_mp: int,
    post_mp: int,
    total: int = 10,
    cost: int = 4,
) -> None:
    rows = caster_actor.get("rows", [])
    if not isinstance(rows, list) or not rows:
        return
    w = max((len(row) for row in rows), default=0)
    x0 = int(caster_actor.get("x", 0))
    y0 = int(caster_actor.get("y", 0))
    cx = x0 + (w // 2)
    bar_top = y0 - 4
    p = max(0.0, min(1.0, float(progress)))
    pre_fill = max(0, min(total, int(pre_mp)))
    post_fill = max(0, min(total, int(post_mp)))
    normal = _mp_fill_color(pre_fill / max(1.0, float(total)))
    post = _mp_fill_color(post_fill / max(1.0, float(total)))
    if p < 0.45:
        _draw_health_bar_custom(canvas, cx, bar_top, pre_fill, total=total, fill_color=normal, row_label="MP")
        return
    if p < 0.75:
        flash_on = (int((p - 0.45) / 0.06) % 2) == 0
        _draw_health_bar_custom(
            canvas,
            cx,
            bar_top,
            pre_fill,
            total=total,
            fill_color="\x1b[38;2;120;190;255m" if flash_on else normal,
            frame_color="\x1b[38;2;165;205;255m" if flash_on else None,
            overlay_text=f"-{cost}",
            overlay_color="\x1b[38;2;245;245;255m",
            row_label="MP",
        )
        return
    _draw_health_bar_custom(canvas, cx, bar_top, post_fill, total=total, fill_color=post, overlay_text=f"-{cost}", row_label="MP")


def _grey_cell(cell: str) -> str:
    ch = _strip_ansi(cell)
    if ch == " ":
        return " "
    return f"\x1b[38;2;156;156;156m{ch}{ANSI_RESET}"


def _draw_defeat_dissolve(canvas: List[List[str]], actor: dict, progress: float) -> None:
    rows = actor.get("rows", [])
    if not isinstance(rows, list) or not rows:
        return
    x0 = int(actor.get("x", 0))
    y0 = int(actor.get("y", 0))
    h = len(rows)
    p = max(0.0, min(1.0, float(progress)))

    # Round A (0.0-0.5): top->bottom decolor sweep.
    # Round B (0.5-1.0): top->bottom two-beat drift:
    #   beat1: drift +/-2 and white
    #   beat2: drift +/-2 and black, then disappear
    # Staggering: next row starts beat1 while previous row is in beat2.
    phase_a = min(1.0, p / 0.5) if p < 0.5 else 1.0
    phase_b = 0.0 if p < 0.5 else min(1.0, (p - 0.5) / 0.5)
    a_sweep = phase_a * h
    b_pos = phase_b * (h + 1)
    white = "\x1b[38;2;245;245;245m"
    black = "\x1b[38;2;20;20;20m"

    for dy, row in enumerate(rows):
        if not isinstance(row, list):
            continue
        y = y0 + dy
        if y < 0 or y >= SCREEN_H:
            continue

        is_grey = dy < a_sweep
        shift = 0
        tint = None
        visible = True

        if phase_b > 0.0:
            local = b_pos - dy
            if local < 0.0:
                pass
            elif local < 1.0:
                shift = -2 if (dy % 2 == 0) else 2
                tint = white
            elif local < 2.0:
                shift = -2 if (dy % 2 == 0) else 2
                tint = black
            else:
                visible = False

        if not visible:
            continue
        for dx, cell in enumerate(row):
            x = x0 + dx + shift
            if x < 0 or x >= SCREEN_W:
                continue
            if cell == " ":
                continue
            if tint is not None:
                ch = _strip_ansi(cell)
                out = f"{tint}{ch}{ANSI_RESET}" if ch != " " else " "
            else:
                out = _grey_cell(cell) if is_grey else cell
            canvas[y][x] = out


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


def _logo_gradient_code(x: int, y: int, width: int, height: int) -> str:
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


def _title_subtitle_text() -> str:
    return "*-----<{([  AI World Engine  ])}>-----*"


def _title_subtitle_cells(y: int, start_x: int) -> List[str]:
    text = _title_subtitle_text()
    left = "*-----<{([  "
    mid = "AI World Engine"
    out: List[str] = []
    for i, ch in enumerate(text):
        if ch == " ":
            out.append(" ")
        elif len(left) <= i < len(left) + len(mid):
            out.append(f"\x1b[38;2;255;255;255m{ch}{ANSI_RESET}")
        else:
            out.append(f"{_logo_gradient_code(start_x + i, y, SCREEN_W, SCREEN_H)}{ch}{ANSI_RESET}")
    return out


def _logo_cells_from_objects(objects: Dict[str, object]) -> dict:
    entry = objects.get("lokarta_logo", {})
    if not isinstance(entry, dict):
        return {"width": 0, "height": 0, "rows": []}
    art = entry.get("art", [])
    blocking = str(entry.get("blocking_space", "#"))[:1] or "#"
    if not isinstance(art, list) or not art:
        return {"width": 0, "height": 0, "rows": []}

    lines = [str(line) for line in art]
    width = max((len(line) for line in lines), default=0)
    height = len(lines)
    rows: List[List[str]] = []
    for y, line in enumerate(lines):
        padded = line.ljust(width)
        row: List[str] = []
        for x, ch in enumerate(padded):
            if ch == " ":
                row.append(" ")
            elif ch == blocking:
                # Opaque empty cell that blocks background behind the logo.
                row.append(f"{ANSI_RESET} ")
            else:
                row.append(f"{_logo_gradient_code(x, y, width, height)}{ch}{ANSI_RESET}")
        rows.append(row)
    return {"width": width, "height": height, "rows": rows}


def _overlay_title_logo(canvas: List[List[str]], logo: dict) -> None:
    rows = logo.get("rows", [])
    width = int(logo.get("width", 0))
    height = int(logo.get("height", 0))
    if not isinstance(rows, list) or width <= 0 or height <= 0:
        return
    x0 = max(0, (SCREEN_W - width) // 2)
    # Title behavior: logo stays near the top of the screen.
    y0 = 1
    subtitle_y = min(SCREEN_H - 1, y0 + height)
    for dy, row in enumerate(rows):
        y = y0 + dy
        if y < 0 or y >= SCREEN_H or not isinstance(row, list):
            continue
        for dx, cell in enumerate(row):
            x = x0 + dx
            if 0 <= x < SCREEN_W and cell != " ":
                canvas[y][x] = cell

    if 0 <= subtitle_y < SCREEN_H:
        text = _title_subtitle_text()
        sx = max(0, (SCREEN_W - len(text)) // 2)
        cells = _title_subtitle_cells(subtitle_y, sx)
        for i, cell in enumerate(cells):
            x = sx + i
            if 0 <= x < SCREEN_W and cell != " ":
                canvas[subtitle_y][x] = cell


def render(
    clouds: List[dict],
    ground_rows: List[str],
    zones: Dict[str, LayoutZone],
    sky_bottom_anchor: int,
    foreground_split_label: str,
    world_layer_level: int = 0,
    world_anchor_stagger: int = 1,
    world_treeline_sprites: List[dict] | None = None,
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
    title_logo: dict | None = None,
    show_title_logo: bool = False,
    ui_box_specs: List[UIBoxSpec] | None = None,
    ui_active_box: UIBoxSpec | None = None,
    ui_active_box_progress: float = 1.0,
    ui_actor_status: dict | None = None,
    ui_avatar_overlay: dict | None = None,
    blink_phase: float = 0.0,
    story_target_primary_index: int | None = None,
    story_target_blink: bool = False,
    story_target_secondary_index: int | None = None,
    story_target_secondary_indices: List[int] | None = None,
    story_target_secondary_blink: bool = False,
    story_spell: dict | None = None,
    story_primary_hp: List[int] | None = None,
    story_primary_hp_total: int = 10,
    story_secondary_hp: List[int] | None = None,
    story_secondary_hp_total: List[int] | None = None,
    story_secondary_mp: List[int] | None = None,
    story_secondary_mp_total: List[int] | None = None,
    story_secondary_hud_indices: List[int] | None = None,
    story_damage_hud: dict | None = None,
    story_mp_hud: dict | None = None,
    story_smash: dict | None = None,
    story_melt_primary_index: int | None = None,
    story_melt_progress: float = 0.0,
    story_hidden_primary_indices: List[int] | None = None,
    story_transition_actors: List[dict] | None = None,
    battle_log_lines: List[str] | None = None,
) -> str:
    canvas = [[" " for _ in range(SCREEN_W)] for _ in range(SCREEN_H)]

    sky_zone = zones["sky_bg"]
    ground_zone = zones["ground_bg"]
    secondary_zone = build_secondary_zone()
    primary_zone = None
    if world_layer_level >= 2:
        lowest_tree_row = _treeline_lowest_row(ground_zone.y, world_anchor_stagger)
        primary_zone = build_primary_zone(lowest_tree_row + 1)
    sky_source_bottom = max(0, min(SCREEN_H, int(sky_bottom_anchor)))
    sky_source_top = sky_source_bottom - sky_zone.height

    # Background sky pass: drifting cloud sprites.
    for cloud in clouds:
        template = cloud["template"]
        x0 = int(cloud["x"])
        y0 = int(cloud["y"])
        for dy, row in enumerate(template["rows"]):
            src_y = y0 + dy
            if src_y < sky_source_top or src_y >= sky_source_bottom:
                continue
            y = sky_zone.y + (src_y - sky_source_top)
            for dx, cell in enumerate(row):
                x = x0 + dx
                if 0 <= x < SCREEN_W and cell != " ":
                    canvas[y][x] = cell

    # Background ground pass: 15 rows of grass and pebbles.
    for i in range(ground_zone.height):
        y = ground_zone.y + i
        src = ground_rows[i] if i < len(ground_rows) else ""
        cells = ansi_line_to_cells(src, SCREEN_W)
        for x, cell in enumerate(cells):
            if cell != " ":
                canvas[y][x] = cell

    # World layer pass: tree sprites anchored to top of ground.
    if world_layer_level >= 1 and world_treeline_sprites:
        for sprite in world_treeline_sprites:
            rows = sprite.get("rows", [])
            if not isinstance(rows, list):
                continue
            x0 = int(sprite.get("x", 0))
            height = int(sprite.get("height", len(rows)))
            stagger = max(1, min(3, int(world_anchor_stagger)))
            offset_cap = stagger - 1
            offset = min(offset_cap, max(0, int(sprite.get("anchor_offset", 0))))
            y_base = ground_zone.y + offset
            y0 = y_base - max(0, height - 1)
            for dy, row in enumerate(rows):
                y = y0 + dy
                if y < 0 or y >= SCREEN_H or not isinstance(row, list):
                    continue
                for dx, cell in enumerate(row):
                    x = x0 + dx
                    if 0 <= x < SCREEN_W and cell != " ":
                        canvas[y][x] = cell

    hide_attacker = False
    show_hit_impact = False
    impact_frame_hint = 0
    story_hidden_secondary: set[int] = set()
    story_hidden_primary: set[int] = set()
    if world_layer_level == 7:
        hide_attacker, show_hit_impact, impact_frame_hint = _physical_hit_state(spell_clock)
    if isinstance(story_smash, dict):
        p = max(0.0, min(1.0, float(story_smash.get("progress", 0.0))))
        if p < 0.5:
            step = int((p / 0.5) * 4.0)  # two blinks
            blink_visible = (step % 2) == 0
            if not blink_visible:
                s_side = str(story_smash.get("source_side", "secondary")).strip().lower()
                s_idx = int(story_smash.get("source_index", 0))
                if s_side == "primary":
                    story_hidden_primary.add(s_idx)
                else:
                    story_hidden_secondary.add(s_idx)

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
            if idx in story_hidden_secondary:
                continue
            blink_indices = set(int(i) for i in (story_target_secondary_indices or []))
            if story_target_secondary_index is not None:
                blink_indices.add(int(story_target_secondary_index))
            if blink_indices and idx in blink_indices and not story_target_secondary_blink:
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
        hidden_primary = set(int(i) for i in (story_hidden_primary_indices or []))
        hidden_primary.update(story_hidden_primary)
        for idx, actor in enumerate(primary_placements):
            x0 = int(actor.get("x", 0))
            y0 = int(actor.get("y", 0))
            rows = actor.get("rows", [])
            if not isinstance(rows, list):
                continue
            if story_melt_primary_index is not None and idx == int(story_melt_primary_index):
                _draw_defeat_dissolve(canvas, actor, story_melt_progress)
                continue
            if idx in hidden_primary:
                # Keep slot spacing, but do not render defeated actor artwork.
                continue
            if story_target_primary_index is not None and idx == int(story_target_primary_index) and not story_target_blink:
                # Selection feedback: flash the selected opponent artwork itself.
                continue
            for dy, row in enumerate(rows):
                y = y0 + dy
                if y < 0 or y >= SCREEN_H:
                    continue
                for dx, cell in enumerate(row):
                    x = x0 + dx
                    if 0 <= x < SCREEN_W and cell != " ":
                        canvas[y][x] = cell

    # Optional formation tween actors (used during lineup transitions).
    if isinstance(story_transition_actors, list):
        for actor in story_transition_actors:
            if not isinstance(actor, dict):
                continue
            x0 = int(actor.get("x", 0))
            y0 = int(actor.get("y", 0))
            rows = actor.get("rows", [])
            if not isinstance(rows, list):
                continue
            for dy, row in enumerate(rows):
                y = y0 + dy
                if y < 0 or y >= SCREEN_H or not isinstance(row, list):
                    continue
                for dx, cell in enumerate(row):
                    x = x0 + dx
                    if 0 <= x < SCREEN_W and cell != " ":
                        canvas[y][x] = cell

    # Story battle overlays: targeting, projectile, HP, and defeat cues.
    if primary_placements and secondary_placements:
        def _center_of(actor: dict) -> tuple[int, int]:
            rows = actor.get("rows", [])
            w = max((len(r) for r in rows), default=0) if isinstance(rows, list) else 0
            h = len(rows) if isinstance(rows, list) else 0
            return (int(actor.get("x", 0)) + (w // 2), int(actor.get("y", 0)) + (h // 2))

        def _actor_from_side(side: str, idx: int) -> dict | None:
            side_key = str(side).strip().lower()
            if side_key == "primary":
                return primary_placements[idx] if 0 <= idx < len(primary_placements) else None
            return secondary_placements[idx] if 0 <= idx < len(secondary_placements) else None

        if isinstance(story_spell, dict):
            s_side = str(story_spell.get("source_side", "secondary"))
            t_side = str(story_spell.get("target_side", "primary"))
            s_idx = int(story_spell.get("source_index", story_spell.get("source_secondary_index", 0)))
            t_idx = int(story_spell.get("target_index", story_spell.get("target_primary_index", 0)))
            prog = float(story_spell.get("progress", 0.0))
            src_actor = _actor_from_side(s_side, s_idx)
            dst_actor = _actor_from_side(t_side, t_idx)
            if isinstance(src_actor, dict) and isinstance(dst_actor, dict):
                _draw_spell_throw(canvas, _center_of(src_actor), _center_of(dst_actor), prog)

        if isinstance(story_damage_hud, dict):
            t_side = str(story_damage_hud.get("target_side", "primary"))
            t_idx = int(story_damage_hud.get("target_index", story_damage_hud.get("target_primary_index", 0)))
            actor = _actor_from_side(t_side, t_idx)
            if isinstance(actor, dict):
                _draw_damage_hud_step(
                    canvas,
                    actor,
                    progress=float(story_damage_hud.get("progress", 0.0)),
                    pre_hp=max(0, int(story_damage_hud.get("pre_hp", 0))),
                    post_hp=max(0, int(story_damage_hud.get("post_hp", 0))),
                    total=max(1, int(story_damage_hud.get("total", 10))),
                    damage=max(0, int(story_damage_hud.get("damage", 0))),
                )

        if isinstance(story_mp_hud, dict):
            s_side = str(story_mp_hud.get("source_side", "secondary"))
            s_idx = int(story_mp_hud.get("source_index", story_mp_hud.get("source_secondary_index", 0)))
            actor = _actor_from_side(s_side, s_idx)
            if isinstance(actor, dict):
                _draw_mp_cast_hud_step(
                    canvas,
                    actor,
                    progress=float(story_mp_hud.get("progress", 0.0)),
                    pre_mp=max(0, int(story_mp_hud.get("pre_mp", 0))),
                    post_mp=max(0, int(story_mp_hud.get("post_mp", 0))),
                    total=max(1, int(story_mp_hud.get("total", 10))),
                    cost=max(0, int(story_mp_hud.get("cost", 4))),
                )

        if isinstance(story_smash, dict) and smash_frames:
            t_side = str(story_smash.get("target_side", "primary"))
            t_idx = int(story_smash.get("target_index", 0))
            prog = max(0.0, min(1.0, float(story_smash.get("progress", 0.0))))
            actor = _actor_from_side(t_side, t_idx)
            if isinstance(actor, dict) and prog >= 0.5:
                frame_idx = min(len(smash_frames) - 1, int(((prog - 0.5) / 0.5) * len(smash_frames)))
                _draw_smash_frame(canvas, smash_frames[max(0, frame_idx)], _center_of(actor))

        # Planning-phase HUD: show HP bars above all opponents while selecting targets.
        if isinstance(story_primary_hp, list):
            total = max(1, int(story_primary_hp_total))
            hidden_idx = set(int(i) for i in (story_hidden_primary_indices or []))
            for idx, hp_val in enumerate(story_primary_hp):
                if idx < 0 or idx >= len(primary_placements):
                    continue
                if idx in hidden_idx or int(hp_val) <= 0:
                    continue
                actor = primary_placements[idx]
                rows = actor.get("rows", [])
                w = max((len(r) for r in rows), default=0) if isinstance(rows, list) else 0
                x = int(actor.get("x", 0)) + (w // 2)
                y = int(actor.get("y", 0)) - 1
                _draw_health_bar_custom(
                    canvas,
                    x,
                    y - 2,
                    max(0, int(hp_val)),
                    total=total,
                    row_label="HP",
                )
        if isinstance(story_secondary_hp, list):
            sec_hp_total = story_secondary_hp_total if isinstance(story_secondary_hp_total, list) else [max(1, int(v)) for v in story_secondary_hp]
            sec_mp_vals = story_secondary_mp if isinstance(story_secondary_mp, list) else [0 for _ in story_secondary_hp]
            sec_mp_total = story_secondary_mp_total if isinstance(story_secondary_mp_total, list) else [max(1, int(v)) for v in sec_mp_vals]
            eligible = set(int(i) for i in (story_secondary_hud_indices or []))
            if not eligible:
                eligible = set(range(len(story_secondary_hp)))
            for idx, hp_val in enumerate(story_secondary_hp):
                if idx < 0 or idx >= len(secondary_placements) or idx not in eligible or int(hp_val) <= 0:
                    continue
                actor = secondary_placements[idx]
                rows = actor.get("rows", [])
                w = max((len(r) for r in rows), default=0) if isinstance(rows, list) else 0
                cx = int(actor.get("x", 0)) + (w // 2)
                y = int(actor.get("y", 0))
                hp_total = max(1, int(sec_hp_total[idx] if idx < len(sec_hp_total) else hp_val))
                mp_val = int(sec_mp_vals[idx] if idx < len(sec_mp_vals) else 0)
                mp_tot = max(1, int(sec_mp_total[idx] if idx < len(sec_mp_total) else mp_val))
                _draw_health_bar_custom(canvas, cx, y - 7, max(0, int(hp_val)), total=hp_total, row_label="HP")
                _draw_health_bar_custom(
                    canvas,
                    cx,
                    y - 4,
                    max(0, mp_val),
                    total=mp_tot,
                    fill_color=_mp_fill_color(max(0.0, min(1.0, mp_val / max(1.0, float(mp_tot))))),
                    row_label="MP",
                )

    # UI layer demo: auto-sizing text box centered between primary/secondary centers.
    if world_layer_level == 4 and primary_zone is not None:
        _draw_ui_text_box(canvas, UI_DEMO_TEXT, primary_zone, secondary_zone)

    # Effect layer demo: Guy throws spell at first primary fairy.
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
    # Next demo step: barrage to all 4 primary fairies with 50% overlap.
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
    # Next demo step: physical hit (blink attacker, then smash animation on target).
    if world_layer_level == 7 and primary_placements and show_hit_impact and smash_frames:
        dst = primary_placements[0]
        dst_rows = dst.get("rows", [])
        dst_w = max((len(row) for row in dst_rows), default=0) if isinstance(dst_rows, list) else 0
        dst_h = len(dst_rows) if isinstance(dst_rows, list) else 0
        target = (int(dst.get("x", 0)) + (dst_w // 2), int(dst.get("y", 0)) + (dst_h // 2))
        frame_idx = min(max(0, impact_frame_hint), len(smash_frames) - 1)
        _draw_smash_frame(canvas, smash_frames[frame_idx], target)
    # Next demo step: health bars above all actors in both panes.
    if world_layer_level == 8:
        _draw_actor_health_bars(canvas, primary_placements, mixed=True)
        _draw_actor_health_bars(canvas, secondary_placements, mixed=True)
    if world_layer_level == 9 and primary_zone is not None:
        _draw_ui_dialogue_box(canvas, "Beba", UI_DIALOG_TEXT, primary_zone, secondary_zone)

    if show_title_logo and isinstance(title_logo, dict):
        _overlay_title_logo(canvas, title_logo)

    # Keep battle log below other active UI boxes.
    if isinstance(battle_log_lines, list):
        _draw_battle_log_panel(canvas, battle_log_lines, width=40, height=10)

    if isinstance(ui_box_specs, list):
        for spec in ui_box_specs:
            if isinstance(spec, UIBoxSpec):
                box_blink_on = bool((int(float(blink_phase) * 2.0) % 2) == 0)
                draw_ui_box(canvas, spec, blink_on=box_blink_on)
    if isinstance(ui_active_box, UIBoxSpec):
        box_blink_on = bool((int(float(blink_phase) * 2.0) % 2) == 0)
        draw_ui_box_animated(canvas, ui_active_box, ui_active_box_progress, blink_on=box_blink_on)
        if isinstance(ui_actor_status, dict):
            _draw_actor_cmd_status_overlay(
                canvas,
                ui_active_box,
                hp=max(0, int(ui_actor_status.get("hp", 0))),
                hp_total=max(1, int(ui_actor_status.get("hp_total", 1))),
                mp=max(0, int(ui_actor_status.get("mp", 0))),
                mp_total=max(1, int(ui_actor_status.get("mp_total", 1))),
                progress=ui_active_box_progress,
            )
    if isinstance(ui_avatar_overlay, dict) and isinstance(ui_active_box, UIBoxSpec):
        left_rows = ui_avatar_overlay.get("left_rows", [])
        right_rows = ui_avatar_overlay.get("right_rows", [])
        left_label = str(ui_avatar_overlay.get("left_label", "Left"))
        right_label = str(ui_avatar_overlay.get("right_label", "Right"))
        selected = int(ui_avatar_overlay.get("selected", 0))
        blink_on = bool((int(float(blink_phase) * 2.0) % 2) == 0)
        if isinstance(left_rows, list) and isinstance(right_rows, list):
            _draw_avatar_overlay(
                canvas,
                ui_active_box,
                left_rows,
                right_rows,
                left_label,
                right_label,
                selected,
                blink_selected_on=blink_on,
            )

    # Vertical wipe-in from bottom.
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
            world_anchor_stagger=world_anchor_stagger,
        )
        _overlay_zone_guides(canvas, guide_zones)

    return "\n".join("".join(row) for row in canvas)


def main() -> None:
    base = os.getcwd()
    objects_path = os.path.join(base, "legecay", "data", "objects.json")
    colors_path = os.path.join(base, "legecay", "data", "colors.json")
    players_path = os.path.join(base, "legecay", "data", "players.json")
    opponents_path = os.path.join(base, "legecay", "data", "opponents.json")
    objects = load_json(objects_path)
    colors = load_json(colors_path)
    players = load_json(players_path)
    opponents = load_json(opponents_path)
    if not isinstance(objects, dict):
        raise RuntimeError("objects.json is not a JSON object")
    if not isinstance(colors, dict):
        raise RuntimeError("colors.json is not a JSON object")
    if not isinstance(players, dict):
        raise RuntimeError("players.json is not a JSON object")
    if not isinstance(opponents, dict):
        raise RuntimeError("opponents.json is not a JSON object")
    color_codes = _build_color_codes(colors)

    templates = cloud_templates(objects)
    if not templates:
        raise RuntimeError("No cloud_* objects found in objects.json")
    title_logo = _logo_cells_from_objects(objects)

    # Fixed title scene foundation:
    # [background][25/5][world][3][scene:cottage]
    current_sky_rows = 25
    target_sky_rows = 25
    zones = build_scene_zones(sky_rows=current_sky_rows)
    sky_bottom_anchor = sky_bottom_anchor_for_rows(current_sky_rows)
    clouds = spawn_clouds_full_canvas(templates)
    ground_rows = build_ground_rows(
        row_count=zones["ground_bg"].height,
        objects_data=objects,
        color_codes=color_codes,
        pebble_density=0.07,
    )
    wipe_duration = 1.0
    wipe_started_at = time.monotonic()
    transition_accum = 0.0
    transition_step_seconds = 0.06
    show_zone_guides = False
    world_layer_level = 1
    world_anchor_stagger = 3
    world_scene_label = "cottage"
    world_center_object_id = "house"
    world_treeline_sprites = build_world_treeline_sprites(objects, colors, world_center_object_id)

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
        sprite = build_player_sprite(players, pid, color_codes)
        player_cards.append({"id": pid, "label": label, "names": clean_names, "sprite": sprite})

    mushy_sprite = build_opponent_sprite(opponents, "mushroom_baby", color_codes)
    sharoom_sprite = build_mushroom_variant_sprite(opponents, color_codes, "i")
    roomie_sprite = build_mushroom_variant_sprite(opponents, color_codes, "w")
    crow_sprite = build_opponent_sprite(opponents, "baby_crow", color_codes)

    flow = {
        "screen": "root_menu",
        "next_screen": None,
        "menu_cursor": 0,
        "player_cards": player_cards,
        "player_index": 0,
        "avatar_label": player_cards[0]["label"],
        "name_choices": list(player_cards[0]["names"]),
        "name_choice_index": 0,
        "name_focus": 0,
        "typed_name": "",
        "selected_name": player_cards[0]["names"][0],
        "fortune_cursor": 1,
        "fortune_choice": "Well-Off (100 GP)",
        "name_shift": True,
        "key_row": 0,
        "key_col": 0,
        "message_text": "",
        "story_action": None,
        "story_action_t": 0.0,
        "battle_stage": 1,
        "battle_primary_hp": [10],          # stage 1 starts with one baby crow
        "battle_secondary_hp": [20, 10],    # player, mushy
        "battle_secondary_hp_max": [20, 10],
        "battle_secondary_mp": [0, 6],      # player, mushy
        "battle_secondary_mp_max": [0, 6],
        "battle_staff_charges": 3,          # Mycostaff charges for Magic Spark
        "battle_player_cmd_idx": 0,
        "battle_mushy_cmd_idx": 0,
        "battle_sharoom_cmd_idx": 0,
        "battle_player_action": "Attack",
        "battle_mushy_action": "Attack",
        "battle_sharoom_action": "Attack",
        "battle_secondary_boost_atk": [0, 0],
        "battle_secondary_boost_def": [0, 0],
        "battle_mushy_spell_target": 0,
        "battle_mushy_spell_target_mode": "single",
        "battle_sharoom_spell_target": 0,
        "battle_sharoom_spell_target_mode": "single",
        "battle_ally_select_actor": "",
        "battle_ally_action": "",
        "battle_ally_desc": "",
        "battle_ally_supports_all": False,
        "battle_ally_target_mode": "single",
        "battle_ally_target_cursor": 0,
        "battle_player_target": 0,
        "battle_mushy_target": 0,
        "battle_sharoom_target": 0,
        "battle_target_cursor": 0,
        "battle_queue": [],
        "battle_queue_index": 0,
        "battle_action_t": 0.0,
        "battle_melt_index": None,
        "battle_melt_t": 0.0,
        "battle_log_committed": [],
        "battle_log_pending": [],
        "battle_log_active": None,
        "battle_log_active_chars": 0,
        "lineup_transition": None,
        "actor_entrance": None,
        "battle2_entrance": None,
        "sharoom_entrance": None,
        "battle3_entrance": None,
        "sharoom_lineup_transition": None,
    }
    anim_mode = "opening"  # opening | open | closing
    anim_step = 0

    def begin_transition(target: str) -> None:
        flow["next_screen"] = target
        nonlocal anim_mode
        anim_mode = "closing"

    def _compute_story_formation_positions(player_sprite: List[List[str]], formation: str) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        ground_zone = zones.get("ground_bg")
        if not isinstance(ground_zone, LayoutZone):
            return out
        primary_zone = build_primary_zone(_treeline_lowest_row(ground_zone.y, world_anchor_stagger) + 1)
        secondary_zone = build_secondary_zone()
        if formation == "pre":
            pri = layout_actor_strip(primary_zone, [crow_sprite, mushy_sprite], spacing=1, stagger_rows=1)
            sec = layout_actor_strip(secondary_zone, [player_sprite], spacing=1, stagger_rows=1, reverse_stagger=True)
            if sec:
                out["player"] = {"x": int(sec[0]["x"]), "y": int(sec[0]["y"]), "rows": player_sprite}
            if len(pri) >= 1:
                out["crow1"] = {"x": int(pri[0]["x"]), "y": int(pri[0]["y"]), "rows": crow_sprite}
            if len(pri) >= 2:
                out["mushy"] = {"x": int(pri[1]["x"]), "y": int(pri[1]["y"]), "rows": mushy_sprite}
        else:
            pri = layout_actor_strip(primary_zone, [crow_sprite], spacing=1, stagger_rows=1)
            sec = layout_actor_strip(secondary_zone, [player_sprite, mushy_sprite], spacing=1, stagger_rows=1, reverse_stagger=True)
            if sec:
                out["player"] = {"x": int(sec[0]["x"]), "y": int(sec[0]["y"]), "rows": player_sprite}
            if len(sec) >= 2:
                out["mushy"] = {"x": int(sec[1]["x"]), "y": int(sec[1]["y"]), "rows": mushy_sprite}
            if pri:
                out["crow1"] = {"x": int(pri[0]["x"]), "y": int(pri[0]["y"]), "rows": crow_sprite}
        return out

    def _compute_battle_primary_positions(enemy_count: int) -> List[dict]:
        ground_zone = zones.get("ground_bg")
        if not isinstance(ground_zone, LayoutZone):
            return []
        primary_zone = build_primary_zone(_treeline_lowest_row(ground_zone.y, world_anchor_stagger) + 1)
        sprites = [crow_sprite for _ in range(max(0, int(enemy_count)))]
        return layout_actor_strip(primary_zone, sprites, spacing=1, stagger_rows=1)

    def _compute_sharoom_shift_positions(player_sprite: List[List[str]]) -> tuple[Dict[str, dict], Dict[str, dict]]:
        start: Dict[str, dict] = {}
        end: Dict[str, dict] = {}
        ground_zone = zones.get("ground_bg")
        if not isinstance(ground_zone, LayoutZone):
            return (start, end)
        primary_zone = build_primary_zone(_treeline_lowest_row(ground_zone.y, world_anchor_stagger) + 1)
        secondary_zone = build_secondary_zone()
        start_pri = layout_actor_strip(primary_zone, [sharoom_sprite], spacing=1, stagger_rows=1)
        start_sec = layout_actor_strip(secondary_zone, [player_sprite, mushy_sprite], spacing=1, stagger_rows=1, reverse_stagger=True)
        end_pri = layout_actor_strip(primary_zone, [crow_sprite, crow_sprite, crow_sprite], spacing=1, stagger_rows=1)
        end_sec = layout_actor_strip(secondary_zone, [sharoom_sprite, player_sprite, mushy_sprite], spacing=1, stagger_rows=1, reverse_stagger=True)
        if start_pri:
            start["sharoom"] = {"x": int(start_pri[0]["x"]), "y": int(start_pri[0]["y"]), "rows": sharoom_sprite}
        if len(start_sec) >= 1:
            start["player"] = {"x": int(start_sec[0]["x"]), "y": int(start_sec[0]["y"]), "rows": player_sprite}
        if len(start_sec) >= 2:
            start["mushy"] = {"x": int(start_sec[1]["x"]), "y": int(start_sec[1]["y"]), "rows": mushy_sprite}
        if len(end_sec) >= 1:
            end["sharoom"] = {"x": int(end_sec[0]["x"]), "y": int(end_sec[0]["y"]), "rows": sharoom_sprite}
        if len(end_sec) >= 2:
            end["player"] = {"x": int(end_sec[1]["x"]), "y": int(end_sec[1]["y"]), "rows": player_sprite}
        if len(end_sec) >= 3:
            end["mushy"] = {"x": int(end_sec[2]["x"]), "y": int(end_sec[2]["y"]), "rows": mushy_sprite}
        for idx, crow in enumerate(end_pri):
            cid = f"crow{idx+1}"
            cx = int(crow["x"])
            cy = int(crow["y"])
            rows = crow["rows"]
            h = len(rows) if isinstance(rows, list) else 0
            # Start flighted crows above viewport; end in primary battle slots.
            start[cid] = {"x": cx, "y": -max(2, h + 2 + (idx * 2)), "rows": rows}
            end[cid] = {"x": cx, "y": cy, "rows": rows}
        return (start, end)

    print(ANSI_HIDE_CURSOR + ANSI_CLEAR, end="", flush=True)
    try:
        last_tick = time.monotonic()
        while True:
            now = time.monotonic()
            dt = max(0.0, min(0.2, now - last_tick))
            last_tick = now
            wipe_progress = min(1.0, max(0.0, (now - wipe_started_at) / wipe_duration))
            _battle_log_tick(flow, dt)

            if current_sky_rows != target_sky_rows:
                transition_accum += dt
                while current_sky_rows != target_sky_rows and transition_accum >= transition_step_seconds:
                    transition_accum -= transition_step_seconds
                    if current_sky_rows < target_sky_rows:
                        current_sky_rows += 1
                    else:
                        current_sky_rows -= 1
                    zones = build_scene_zones(sky_rows=current_sky_rows)
                    sky_bottom_anchor = sky_bottom_anchor_for_rows(current_sky_rows)
                    ground_rows = build_ground_rows(
                        row_count=zones["ground_bg"].height,
                        objects_data=objects,
                        color_codes=color_codes,
                        pebble_density=0.07,
                    )

            for cloud in clouds:
                speed = float(cloud.get("speed", 1.0))
                cloud["x"] = float(cloud.get("x", 0.0)) - (speed * dt)
                w = int(cloud["template"]["width"])
                if cloud["x"] + w < 0:
                    cloud["x"] = SCREEN_W + (cloud["x"] + w)

            key = read_key_nonblocking()
            if key == "q":
                break

            screen = str(flow.get("screen", "root_menu"))
            confirm = key in ("a", "\r", "\n")
            back = key == "s"
            player_cards = flow["player_cards"]
            selected_card = player_cards[int(flow.get("player_index", 0)) % len(player_cards)]
            story_action = flow.get("story_action")
            if anim_mode == "open" and screen in ("story_battle_resolve", "story_battle3_resolve"):
                pri_hp = [int(v) for v in flow.get("battle_primary_hp", [10, 10])]
                sec_hp = [int(v) for v in flow.get("battle_secondary_hp", [20, 10])]
                melt_index = flow.get("battle_melt_index")
                if melt_index is not None:
                    flow["battle_melt_t"] = float(flow.get("battle_melt_t", 0.0)) + dt
                    if float(flow.get("battle_melt_t", 0.0)) >= 0.8:
                        flow["battle_melt_index"] = None
                        flow["battle_melt_t"] = 0.0
                else:
                    queue = flow.get("battle_queue", [])
                    qidx = int(flow.get("battle_queue_index", 0))
                    if qidx >= len(queue):
                        if not _alive_indices(pri_hp):
                            # Recharge Mycostaff after each completed battle.
                            flow["battle_staff_charges"] = 3
                            if int(flow.get("battle_stage", 1)) == 1:
                                begin_transition("story_more_crows")
                            elif int(flow.get("battle_stage", 1)) == 2:
                                begin_transition("story_sharoom_1")
                            else:
                                begin_transition("story_battle_victory")
                        else:
                            flow["battle_target_cursor"] = _first_alive(pri_hp, 0)
                            _reset_battle_command_picks(flow, int(flow.get("battle_stage", 1)))
                            begin_transition("story_battle_cmd_player")
                    else:
                        action = queue[qidx]
                        action_t = float(flow.get("battle_action_t", 0.0)) + dt
                        flow["battle_action_t"] = action_t
                        action_kind = str(action.get("kind", "physical"))
                        duration = 1.2 if action_kind == "spell" else 0.9
                        if action_t >= duration:
                            # Apply this action once at completion.
                            has_hp_transition = ("pre_hp" in action) and ("post_hp" in action) and ("target_side" in action) and ("target_index" in action)
                            if has_hp_transition:
                                t_side = str(action.get("target_side", "primary"))
                                t_idx = int(action.get("target_index", 0))
                                post_hp = max(0, int(action.get("post_hp", 0)))
                                pre_hp = max(0, int(action.get("pre_hp", 0)))
                                if t_side == "primary" and 0 <= t_idx < len(pri_hp):
                                    pri_hp[t_idx] = post_hp
                                    flow["battle_primary_hp"] = pri_hp
                                    if pre_hp > 0 and post_hp <= 0:
                                        flow["battle_melt_index"] = t_idx
                                        flow["battle_melt_t"] = 0.0
                                elif t_side == "secondary" and 0 <= t_idx < len(sec_hp):
                                    sec_hp[t_idx] = post_hp
                                    flow["battle_secondary_hp"] = sec_hp
                            if action_kind == "spell":
                                sec_mp = [int(v) for v in flow.get("battle_secondary_mp", [0, 6])]
                                s_idx = int(action.get("source_index", 0))
                                post_mp = max(0, int(action.get("post_mp", 0)))
                                post_charges = max(0, int(action.get("post_charges", int(flow.get("battle_staff_charges", 0)))))
                                if 0 <= s_idx < len(sec_mp):
                                    sec_mp[s_idx] = post_mp
                                    flow["battle_secondary_mp"] = sec_mp
                                flow["battle_staff_charges"] = post_charges
                            effects = action.get("effects", [])
                            if isinstance(effects, list) and effects:
                                sec_mp = [int(v) for v in flow.get("battle_secondary_mp", [0, 6])]
                                sec_boost_atk = [int(v) for v in flow.get("battle_secondary_boost_atk", [0 for _ in sec_hp])]
                                sec_boost_def = [int(v) for v in flow.get("battle_secondary_boost_def", [0 for _ in sec_hp])]
                                if len(sec_boost_atk) < len(sec_hp):
                                    sec_boost_atk.extend([0] * (len(sec_hp) - len(sec_boost_atk)))
                                if len(sec_boost_def) < len(sec_hp):
                                    sec_boost_def.extend([0] * (len(sec_hp) - len(sec_boost_def)))
                                for eff in effects:
                                    if not isinstance(eff, dict):
                                        continue
                                    eff_type = str(eff.get("type", ""))
                                    idx = int(eff.get("index", -1))
                                    val = int(eff.get("value", 0))
                                    if eff_type == "set_secondary_hp" and 0 <= idx < len(sec_hp):
                                        sec_hp[idx] = max(0, val)
                                    elif eff_type == "set_secondary_mp" and 0 <= idx < len(sec_mp):
                                        sec_mp[idx] = max(0, val)
                                    elif eff_type == "set_secondary_boost_atk" and 0 <= idx < len(sec_boost_atk):
                                        sec_boost_atk[idx] = max(0, val)
                                    elif eff_type == "set_secondary_boost_def" and 0 <= idx < len(sec_boost_def):
                                        sec_boost_def[idx] = max(0, val)
                                flow["battle_secondary_hp"] = sec_hp
                                flow["battle_secondary_mp"] = sec_mp
                                flow["battle_secondary_boost_atk"] = sec_boost_atk[: len(sec_hp)]
                                flow["battle_secondary_boost_def"] = sec_boost_def[: len(sec_hp)]
                            stage_now = int(flow.get("battle_stage", 1))
                            player_name = str(flow.get("selected_name", "Player")).strip() or "Player"
                            _battle_log_enqueue(flow, _battle_action_log_lines(action, stage_now, player_name))
                            flow["battle_queue_index"] = qidx + 1
                            flow["battle_action_t"] = 0.0
            elif anim_mode == "open" and screen == "story_lineup_shift":
                trans = flow.get("lineup_transition")
                if isinstance(trans, dict):
                    trans["t"] = float(trans.get("t", 0.0)) + dt
                    if float(trans.get("t", 0.0)) >= float(trans.get("duration", 1.0)):
                        flow["lineup_transition"] = None
                        _battle_log_start(flow, int(flow.get("battle_stage", 1)))
                        _reset_battle_command_picks(flow, int(flow.get("battle_stage", 1)))
                        begin_transition("story_battle_cmd_player")
            elif anim_mode == "open" and screen == "story_actor_entrance":
                ent = flow.get("actor_entrance")
                if isinstance(ent, dict):
                    ent["t"] = float(ent.get("t", 0.0)) + dt
                    if float(ent.get("t", 0.0)) >= float(ent.get("duration", 1.0)):
                        flow["actor_entrance"] = None
                        begin_transition("story_4")
            elif anim_mode == "open" and screen == "story_battle2_entrance":
                ent = flow.get("battle2_entrance")
                if isinstance(ent, dict):
                    ent["t"] = float(ent.get("t", 0.0)) + dt
                    if float(ent.get("t", 0.0)) >= float(ent.get("duration", 1.0)):
                        flow["battle2_entrance"] = None
                        _battle_log_start(flow, int(flow.get("battle_stage", 1)))
                        _reset_battle_command_picks(flow, int(flow.get("battle_stage", 1)))
                        begin_transition("story_battle_cmd_player")
            elif anim_mode == "open" and screen == "story_sharoom_entrance":
                ent = flow.get("sharoom_entrance")
                if isinstance(ent, dict):
                    ent["t"] = float(ent.get("t", 0.0)) + dt
                    if float(ent.get("t", 0.0)) >= float(ent.get("duration", 1.0)):
                        flow["sharoom_entrance"] = None
                        begin_transition("story_sharoom_3")
            elif anim_mode == "open" and screen == "story_battle3_entrance":
                ent = flow.get("battle3_entrance")
                if isinstance(ent, dict):
                    ent["t"] = float(ent.get("t", 0.0)) + dt
                    if float(ent.get("t", 0.0)) >= float(ent.get("duration", 1.0)):
                        flow["battle3_entrance"] = None
                        flow["battle_queue"] = _build_battle_round_actions(flow)
                        flow["battle_queue_index"] = 0
                        flow["battle_action_t"] = 0.0
                        begin_transition("story_battle3_resolve")
            elif anim_mode == "open" and screen == "story_sharoom_lineup_shift":
                trans = flow.get("sharoom_lineup_transition")
                if isinstance(trans, dict):
                    trans["t"] = float(trans.get("t", 0.0)) + dt
                    if float(trans.get("t", 0.0)) >= float(trans.get("duration", 1.0)):
                        flow["sharoom_lineup_transition"] = None
                        pri_hp = [int(v) for v in flow.get("battle_primary_hp", [10, 10, 10])]
                        flow["battle_target_cursor"] = _first_alive(pri_hp, 0)
                        _battle_log_start(flow, int(flow.get("battle_stage", 1)))
                        _reset_battle_command_picks(flow, int(flow.get("battle_stage", 1)))
                        begin_transition("story_battle_cmd_player")

            if anim_mode == "open" and flow.get("story_action") is None:
                if str(flow.get("screen", "root_menu")) == "story_2" and current_sky_rows == target_sky_rows:
                    flow["actor_entrance"] = {"t": 0.0, "duration": 1.0}
                    begin_transition("story_actor_entrance")

            if anim_mode == "open" and key is not None and flow.get("story_action") is None:
                if screen == "root_menu":
                    cursor = int(flow.get("menu_cursor", 0))
                    if key == "up":
                        flow["menu_cursor"] = (cursor - 1) % 3
                    elif key == "down":
                        flow["menu_cursor"] = (cursor + 1) % 3
                    elif confirm:
                        if cursor == 0:
                            flow["player_index"] = 0
                            selected = flow["player_cards"][0]
                            flow["avatar_label"] = selected["label"]
                            flow["name_choices"] = list(selected["names"])
                            flow["name_choice_index"] = 0
                            flow["name_focus"] = 0
                            flow["selected_name"] = selected["names"][0]
                            begin_transition("avatar_select")
                        elif cursor == 1:
                            flow["message_text"] = "Saved Game menu selected. (Demo placeholder)"
                            begin_transition("info")
                        else:
                            flow["message_text"] = "Asset Explorer selected. (Demo placeholder)"
                            begin_transition("info")
                elif screen == "avatar_select":
                    idx = int(flow.get("player_index", 0))
                    if key in ("left", "up"):
                        idx = 1 if idx == 0 else 0
                        flow["player_index"] = idx
                        flow["avatar_label"] = player_cards[idx]["label"]
                        flow["name_choices"] = list(player_cards[idx]["names"])
                        flow["name_choice_index"] = 0
                    elif key in ("right", "down"):
                        idx = 1 if idx == 0 else 0
                        flow["player_index"] = idx
                        flow["avatar_label"] = player_cards[idx]["label"]
                        flow["name_choices"] = list(player_cards[idx]["names"])
                        flow["name_choice_index"] = 0
                    elif confirm:
                        selected = player_cards[idx]
                        flow["avatar_label"] = selected["label"]
                        flow["name_choices"] = list(selected["names"])
                        flow["name_choice_index"] = 0
                        flow["name_focus"] = 0
                        flow["selected_name"] = selected["names"][0]
                        begin_transition("name_select")
                    elif back:
                        begin_transition("root_menu")
                elif screen == "name_select":
                    focus = int(flow.get("name_focus", 0))
                    if key in ("up", "down"):
                        flow["name_focus"] = 1 - focus
                    elif focus == 0 and key == "left":
                        count = max(1, len(flow["name_choices"]))
                        flow["name_choice_index"] = (int(flow.get("name_choice_index", 0)) - 1) % count
                    elif focus == 0 and key == "right":
                        count = max(1, len(flow["name_choices"]))
                        flow["name_choice_index"] = (int(flow.get("name_choice_index", 0)) + 1) % count
                    elif confirm:
                        if focus == 0:
                            idx = int(flow.get("name_choice_index", 0)) % max(1, len(flow["name_choices"]))
                            flow["selected_name"] = str(flow["name_choices"][idx])
                            begin_transition("fortune_select")
                        else:
                            flow["typed_name"] = str(flow.get("selected_name", ""))[:16]
                            flow["name_shift"] = True
                            flow["key_row"] = 0
                            flow["key_col"] = 0
                            begin_transition("name_input")
                    elif back:
                        begin_transition("avatar_select")
                elif screen == "name_input":
                    row = int(flow.get("key_row", 0))
                    col = int(flow.get("key_col", 0))
                    if key == "up":
                        row = (row - 1) % len(NAME_KEYBOARD)
                        col = min(col, len(NAME_KEYBOARD[row]) - 1)
                    elif key == "down":
                        row = (row + 1) % len(NAME_KEYBOARD)
                        col = min(col, len(NAME_KEYBOARD[row]) - 1)
                    elif key == "left":
                        col = (col - 1) % len(NAME_KEYBOARD[row])
                    elif key == "right":
                        col = (col + 1) % len(NAME_KEYBOARD[row])
                    elif confirm:
                        display_rows = _display_keyboard_rows(bool(flow.get("name_shift", True)))
                        token = display_rows[row][col]
                        name, shift, done, cancel = _apply_name_key(
                            str(flow.get("typed_name", "")),
                            token,
                            bool(flow.get("name_shift", True)),
                        )
                        flow["typed_name"] = name[:16]
                        flow["name_shift"] = shift
                        if done:
                            flow["selected_name"] = name[:16]
                            begin_transition("fortune_select")
                        elif cancel:
                            begin_transition("name_select")
                    elif back:
                        begin_transition("name_select")
                    flow["key_row"] = row
                    flow["key_col"] = col
                elif screen == "fortune_select":
                    cursor = int(flow.get("fortune_cursor", 1))
                    if key == "up":
                        flow["fortune_cursor"] = (cursor - 1) % 3
                    elif key == "down":
                        flow["fortune_cursor"] = (cursor + 1) % 3
                    elif confirm:
                        options = ["Poor (10 GP)", "Well-Off (100 GP)", "Royalty (1000 GP)"]
                        pick = options[int(flow.get("fortune_cursor", 1)) % len(options)]
                        flow["fortune_choice"] = pick
                        begin_transition("start_confirm")
                    elif back:
                        begin_transition("name_select")
                elif screen == "start_confirm":
                    if confirm:
                        flow["story_action"] = None
                        flow["story_action_t"] = 0.0
                        flow["battle_stage"] = 1
                        flow["battle_primary_hp"] = [10]
                        flow["battle_secondary_hp"] = [20, 10]
                        flow["battle_secondary_hp_max"] = [20, 10]
                        flow["battle_secondary_mp"] = [0, 6]
                        flow["battle_secondary_mp_max"] = [0, 6]
                        flow["battle_staff_charges"] = 3
                        flow["battle_player_cmd_idx"] = 0
                        flow["battle_mushy_cmd_idx"] = 0
                        flow["battle_sharoom_cmd_idx"] = 0
                        flow["battle_player_action"] = "Attack"
                        flow["battle_mushy_action"] = "Attack"
                        flow["battle_sharoom_action"] = "Attack"
                        flow["battle_secondary_boost_atk"] = [0, 0]
                        flow["battle_secondary_boost_def"] = [0, 0]
                        flow["battle_mushy_spell_target"] = 0
                        flow["battle_mushy_spell_target_mode"] = "single"
                        flow["battle_sharoom_spell_target"] = 0
                        flow["battle_sharoom_spell_target_mode"] = "single"
                        flow["battle_player_target"] = 0
                        flow["battle_mushy_target"] = 0
                        flow["battle_sharoom_target"] = 0
                        flow["battle_target_cursor"] = 0
                        flow["battle_queue"] = []
                        flow["battle_queue_index"] = 0
                        flow["battle_action_t"] = 0.0
                        flow["battle_melt_index"] = None
                        flow["battle_melt_t"] = 0.0
                        flow["battle_log_committed"] = []
                        flow["battle_log_pending"] = []
                        flow["battle_log_active"] = None
                        flow["battle_log_active_chars"] = 0
                        begin_transition("story_1")
                    elif back:
                        begin_transition("fortune_select")
                elif screen == "info":
                    if confirm or back:
                        begin_transition("root_menu")
                elif screen == "story_1":
                    if confirm:
                        target_sky_rows = 10
                        begin_transition("story_2")
                elif screen == "story_4":
                    if confirm:
                        begin_transition("story_5")
                elif screen == "story_5":
                    if confirm:
                        begin_transition("story_6")
                elif screen == "story_6":
                    if confirm:
                        pri_hp = [int(v) for v in flow.get("battle_primary_hp", [10, 10])]
                        flow["battle_target_cursor"] = _first_alive(pri_hp, 0)
                        player_sprite_for_shift = selected_card.get("sprite", [])
                        start_pos = _compute_story_formation_positions(player_sprite_for_shift, "pre")
                        end_pos = _compute_story_formation_positions(player_sprite_for_shift, "post")
                        actor_ids = [aid for aid in ("player", "mushy", "crow1") if aid in start_pos and aid in end_pos]
                        flow["lineup_transition"] = {
                            "t": 0.0,
                            "duration": 1.0,
                            "actors": [
                                {
                                    "id": aid,
                                    "rows": start_pos[aid]["rows"],
                                    "sx": int(start_pos[aid]["x"]),
                                    "sy": int(start_pos[aid]["y"]),
                                    "ex": int(end_pos[aid]["x"]),
                                    "ey": int(end_pos[aid]["y"]),
                                }
                                for aid in actor_ids
                            ],
                        }
                        begin_transition("story_lineup_shift")
                elif screen == "story_battle_cmd_player":
                    pri_hp = [int(v) for v in flow.get("battle_primary_hp", [10, 10])]
                    options = _actor_action_options("player")
                    cmd_idx = int(flow.get("battle_player_cmd_idx", 0)) % len(options)
                    cursor = int(flow.get("battle_target_cursor", 0))
                    if key == "up":
                        cmd_idx = (cmd_idx - 1) % len(options)
                        flow["battle_player_cmd_idx"] = cmd_idx
                    elif key == "down":
                        cmd_idx = (cmd_idx + 1) % len(options)
                        flow["battle_player_cmd_idx"] = cmd_idx
                    elif key == "left" and options[cmd_idx] in ("Attack", "Magic Spark"):
                        flow["battle_target_cursor"] = _next_alive_index(pri_hp, cursor, -1)
                    elif key == "right" and options[cmd_idx] in ("Attack", "Magic Spark"):
                        flow["battle_target_cursor"] = _next_alive_index(pri_hp, cursor, 1)
                    elif confirm:
                        pick = options[cmd_idx]
                        flow["battle_player_action"] = pick
                        if pick in ("Attack", "Magic Spark"):
                            flow["battle_player_target"] = int(flow.get("battle_target_cursor", 0))
                        flow["battle_target_cursor"] = _first_alive(pri_hp, int(flow.get("battle_player_target", 0)))
                        begin_transition("story_battle_cmd_mushy")
                    elif back:
                        begin_transition("story_6")
                elif screen == "story_battle_cmd_mushy":
                    pri_hp = [int(v) for v in flow.get("battle_primary_hp", [10, 10])]
                    options = _actor_action_options("mushy")
                    cmd_idx = int(flow.get("battle_mushy_cmd_idx", 0)) % len(options)
                    cursor = int(flow.get("battle_target_cursor", 0))
                    if key == "up":
                        cmd_idx = (cmd_idx - 1) % len(options)
                        flow["battle_mushy_cmd_idx"] = cmd_idx
                    elif key == "down":
                        cmd_idx = (cmd_idx + 1) % len(options)
                        flow["battle_mushy_cmd_idx"] = cmd_idx
                    elif key == "left" and options[cmd_idx] == "Attack":
                        flow["battle_target_cursor"] = _next_alive_index(pri_hp, cursor, -1)
                    elif key == "right" and options[cmd_idx] == "Attack":
                        flow["battle_target_cursor"] = _next_alive_index(pri_hp, cursor, 1)
                    elif confirm:
                        pick = options[cmd_idx]
                        flow["battle_mushy_action"] = pick
                        meta = _spell_targeting_meta("mushy", pick)
                        if pick == "Attack":
                            flow["battle_mushy_target"] = int(flow.get("battle_target_cursor", 0))
                        if isinstance(meta, dict) and str(meta.get("side")) == "ally":
                            stage_now = int(flow.get("battle_stage", 1))
                            targets = _alive_secondary_target_indices(flow, "mushy", pick, stage_now)
                            flow["battle_ally_select_actor"] = "mushy"
                            flow["battle_ally_action"] = pick
                            flow["battle_ally_desc"] = str(meta.get("desc", ""))
                            flow["battle_ally_supports_all"] = bool(meta.get("supports_all", False))
                            flow["battle_ally_target_mode"] = str(meta.get("default_mode", "single"))
                            flow["battle_ally_target_cursor"] = targets[0] if targets else 0
                            begin_transition("story_battle_ally_target")
                        elif int(flow.get("battle_stage", 1)) >= 3:
                            flow["battle_target_cursor"] = _first_alive(pri_hp, int(flow.get("battle_mushy_target", 0)))
                            begin_transition("story_battle_cmd_sharoom")
                        else:
                            flow["battle_queue"] = _build_battle_round_actions(flow)
                            flow["battle_queue_index"] = 0
                            flow["battle_action_t"] = 0.0
                            flow["battle_melt_index"] = None
                            flow["battle_melt_t"] = 0.0
                            begin_transition("story_battle_resolve")
                    elif back:
                        begin_transition("story_battle_cmd_player")
                elif screen == "story_battle_cmd_sharoom":
                    pri_hp = [int(v) for v in flow.get("battle_primary_hp", [10, 10, 10])]
                    options = _actor_action_options("sharoom")
                    cmd_idx = int(flow.get("battle_sharoom_cmd_idx", 0)) % len(options)
                    cursor = int(flow.get("battle_target_cursor", 0))
                    if key == "up":
                        cmd_idx = (cmd_idx - 1) % len(options)
                        flow["battle_sharoom_cmd_idx"] = cmd_idx
                    elif key == "down":
                        cmd_idx = (cmd_idx + 1) % len(options)
                        flow["battle_sharoom_cmd_idx"] = cmd_idx
                    elif key == "left" and options[cmd_idx] == "Attack":
                        flow["battle_target_cursor"] = _next_alive_index(pri_hp, cursor, -1)
                    elif key == "right" and options[cmd_idx] == "Attack":
                        flow["battle_target_cursor"] = _next_alive_index(pri_hp, cursor, 1)
                    elif confirm:
                        pick = options[cmd_idx]
                        flow["battle_sharoom_action"] = pick
                        meta = _spell_targeting_meta("sharoom", pick)
                        if pick == "Attack":
                            flow["battle_sharoom_target"] = int(flow.get("battle_target_cursor", 0))
                        if isinstance(meta, dict) and str(meta.get("side")) == "ally":
                            stage_now = int(flow.get("battle_stage", 1))
                            targets = _alive_secondary_target_indices(flow, "sharoom", pick, stage_now)
                            flow["battle_ally_select_actor"] = "sharoom"
                            flow["battle_ally_action"] = pick
                            flow["battle_ally_desc"] = str(meta.get("desc", ""))
                            flow["battle_ally_supports_all"] = bool(meta.get("supports_all", False))
                            flow["battle_ally_target_mode"] = str(meta.get("default_mode", "single"))
                            flow["battle_ally_target_cursor"] = targets[0] if targets else 0
                            begin_transition("story_battle_ally_target")
                        else:
                            flow["battle_queue"] = _build_battle_round_actions(flow)
                            flow["battle_queue_index"] = 0
                            flow["battle_action_t"] = 0.0
                            flow["battle_melt_index"] = None
                            flow["battle_melt_t"] = 0.0
                            begin_transition("story_battle3_resolve")
                    elif back:
                        begin_transition("story_battle_cmd_mushy")
                elif screen == "story_battle_ally_target":
                    actor_key = str(flow.get("battle_ally_select_actor", "mushy")).strip().lower()
                    action_name = str(flow.get("battle_ally_action", ""))
                    supports_all = bool(flow.get("battle_ally_supports_all", False))
                    stage_now = int(flow.get("battle_stage", 1))
                    targets = _alive_secondary_target_indices(flow, actor_key, action_name, stage_now)
                    mode = str(flow.get("battle_ally_target_mode", "single")).strip().lower()
                    cursor = int(flow.get("battle_ally_target_cursor", targets[0] if targets else 0))
                    if supports_all and key in ("up", "down"):
                        mode = "all" if mode == "single" else "single"
                        flow["battle_ally_target_mode"] = mode
                    elif mode == "single" and targets and key == "left":
                        if cursor not in targets:
                            cursor = targets[0]
                        else:
                            pos = targets.index(cursor)
                            cursor = targets[(pos - 1) % len(targets)]
                        flow["battle_ally_target_cursor"] = cursor
                    elif mode == "single" and targets and key == "right":
                        if cursor not in targets:
                            cursor = targets[0]
                        else:
                            pos = targets.index(cursor)
                            cursor = targets[(pos + 1) % len(targets)]
                        flow["battle_ally_target_cursor"] = cursor
                    elif confirm:
                        if actor_key == "mushy":
                            flow["battle_mushy_spell_target_mode"] = mode
                            flow["battle_mushy_spell_target"] = int(flow.get("battle_ally_target_cursor", 0))
                            if int(flow.get("battle_stage", 1)) >= 3:
                                pri_hp = [int(v) for v in flow.get("battle_primary_hp", [10, 10, 10])]
                                flow["battle_target_cursor"] = _first_alive(pri_hp, int(flow.get("battle_mushy_target", 0)))
                                begin_transition("story_battle_cmd_sharoom")
                            else:
                                flow["battle_queue"] = _build_battle_round_actions(flow)
                                flow["battle_queue_index"] = 0
                                flow["battle_action_t"] = 0.0
                                flow["battle_melt_index"] = None
                                flow["battle_melt_t"] = 0.0
                                begin_transition("story_battle_resolve")
                        elif actor_key == "sharoom":
                            flow["battle_sharoom_spell_target_mode"] = mode
                            flow["battle_sharoom_spell_target"] = int(flow.get("battle_ally_target_cursor", 0))
                            flow["battle_queue"] = _build_battle_round_actions(flow)
                            flow["battle_queue_index"] = 0
                            flow["battle_action_t"] = 0.0
                            flow["battle_melt_index"] = None
                            flow["battle_melt_t"] = 0.0
                            begin_transition("story_battle3_resolve")
                        else:
                            begin_transition("story_battle_cmd_player")
                    elif back:
                        if actor_key == "sharoom":
                            begin_transition("story_battle_cmd_sharoom")
                        elif actor_key == "mushy":
                            begin_transition("story_battle_cmd_mushy")
                        else:
                            begin_transition("story_battle_cmd_player")
                elif screen == "story_battle_victory":
                    if confirm:
                        target_sky_rows = 25
                        begin_transition("root_menu")
                elif screen == "story_more_crows":
                    if confirm:
                        flow["battle_stage"] = 2
                        flow["battle_primary_hp"] = [10, 10]
                        flow["battle_secondary_boost_atk"] = [0, 0]
                        flow["battle_secondary_boost_def"] = [0, 0]
                        flow["battle_player_cmd_idx"] = 0
                        flow["battle_mushy_cmd_idx"] = 0
                        flow["battle_player_action"] = "Attack"
                        flow["battle_mushy_action"] = "Attack"
                        flow["battle_target_cursor"] = _first_alive([10, 10], 0)
                        flow["battle_queue"] = []
                        flow["battle_queue_index"] = 0
                        flow["battle_action_t"] = 0.0
                        flow["battle_melt_index"] = None
                        flow["battle_melt_t"] = 0.0
                        flow["battle2_entrance"] = {"t": 0.0, "duration": 1.0}
                        begin_transition("story_battle2_entrance")
                elif screen == "story_sharoom_1":
                    if confirm:
                        flow["sharoom_entrance"] = {"t": 0.0, "duration": 1.0}
                        begin_transition("story_sharoom_entrance")
                elif screen == "story_sharoom_3":
                    if confirm:
                        begin_transition("story_sharoom_4")
                elif screen == "story_sharoom_4":
                    if confirm:
                        flow["battle_stage"] = 3
                        flow["battle_primary_hp"] = [10, 10, 10]
                        flow["battle_secondary_hp"] = [10, 20, 10]  # Sharoom, Player, Mushy
                        flow["battle_secondary_hp_max"] = [10, 20, 10]
                        flow["battle_secondary_mp"] = [6, 0, 6]
                        flow["battle_secondary_mp_max"] = [6, 0, 6]
                        flow["battle_secondary_boost_atk"] = [0, 0, 0]
                        flow["battle_secondary_boost_def"] = [0, 0, 0]
                        flow["battle_mushy_spell_target"] = 1
                        flow["battle_mushy_spell_target_mode"] = "single"
                        flow["battle_sharoom_spell_target"] = 1
                        flow["battle_sharoom_spell_target_mode"] = "single"
                        flow["battle_player_cmd_idx"] = 0
                        flow["battle_mushy_cmd_idx"] = 0
                        flow["battle_sharoom_cmd_idx"] = 0
                        flow["battle_player_action"] = "Attack"
                        flow["battle_mushy_action"] = "Attack"
                        flow["battle_sharoom_action"] = "Attack"
                        flow["battle_player_target"] = 0
                        flow["battle_mushy_target"] = 0
                        flow["battle_sharoom_target"] = 0
                        flow["battle_queue"] = []
                        flow["battle_queue_index"] = 0
                        flow["battle_action_t"] = 0.0
                        flow["battle_melt_index"] = None
                        flow["battle_melt_t"] = 0.0
                        start_pos, end_pos = _compute_sharoom_shift_positions(selected_card.get("sprite", []))
                        actor_ids = [aid for aid in ("sharoom", "player", "mushy", "crow1", "crow2", "crow3") if aid in start_pos and aid in end_pos]
                        flow["sharoom_lineup_transition"] = {
                            "t": 0.0,
                            "duration": 1.0,
                            "actors": [
                                {
                                    "id": aid,
                                    "rows": start_pos[aid]["rows"],
                                    "sx": int(start_pos[aid]["x"]),
                                    "sy": int(start_pos[aid]["y"]),
                                    "ex": int(end_pos[aid]["x"]),
                                    "ey": int(end_pos[aid]["y"]),
                                }
                                for aid in actor_ids
                            ],
                        }
                        begin_transition("story_sharoom_lineup_shift")

            screen = str(flow.get("screen", "root_menu"))
            story_action = flow.get("story_action")
            story_mode = screen.startswith("story_") or story_action is not None
            split_label = f"{zones['sky_bg'].height}/{zones['ground_bg'].height}"
            active_spec = _build_screen_spec(flow)

            if screen in ("story_1", "story_2"):
                scene_world_layer_level = 1
            elif story_mode:
                scene_world_layer_level = 3
            else:
                scene_world_layer_level = 1

            selected_idx = int(flow.get("player_index", 0)) % len(player_cards)
            selected_player_sprite = player_cards[selected_idx].get("sprite", [])
            primary_sprites: List[List[List[str]]] = []
            secondary_sprites: List[List[List[str]]] = []
            story_transition_actors: List[dict] | None = None
            battle_screens = {
                "story_battle_cmd_player",
                "story_battle_cmd_mushy",
                "story_battle_cmd_sharoom",
                "story_battle_ally_target",
                "story_battle_resolve",
                "story_battle3_resolve",
                "story_battle_victory",
            }
            battle_log_screens = set(battle_screens)
            if scene_world_layer_level >= 3:
                if screen in battle_screens:
                    enemy_count = max(1, len([int(v) for v in flow.get("battle_primary_hp", [10])]))
                    primary_sprites = [crow_sprite for _ in range(enemy_count)]
                    if int(flow.get("battle_stage", 1)) >= 3:
                        secondary_sprites = [sharoom_sprite, selected_player_sprite, mushy_sprite]
                    else:
                        secondary_sprites = [selected_player_sprite, mushy_sprite]
                elif screen == "story_battle2_entrance":
                    primary_sprites = []
                    secondary_sprites = [selected_player_sprite, mushy_sprite]
                    ent = flow.get("battle2_entrance")
                    if isinstance(ent, dict):
                        t = max(0.0, min(1.0, float(ent.get("t", 0.0)) / max(0.001, float(ent.get("duration", 1.0)))))
                        te = t * t * (3.0 - (2.0 * t))
                        targets = _compute_battle_primary_positions(2)
                        tmp: List[dict] = []
                        for idx, tg in enumerate(targets):
                            tx = int(tg.get("x", 0))
                            ty = int(tg.get("y", 0))
                            rows = tg.get("rows", [])
                            th = len(rows) if isinstance(rows, list) else 0
                            # Crows are flighted: enter from above.
                            sx = tx
                            sy = -max(2, th + 2 + (idx * 2))
                            tmp.append(
                                {
                                    "x": int(round(sx + ((tx - sx) * te))),
                                    "y": int(round(sy + ((ty - sy) * te))),
                                    "rows": tg.get("rows", []),
                                }
                            )
                        story_transition_actors = tmp
                elif screen == "story_battle3_entrance":
                    primary_sprites = []
                    secondary_sprites = [sharoom_sprite, selected_player_sprite, mushy_sprite]
                    ent = flow.get("battle3_entrance")
                    if isinstance(ent, dict):
                        t = max(0.0, min(1.0, float(ent.get("t", 0.0)) / max(0.001, float(ent.get("duration", 1.0)))))
                        te = t * t * (3.0 - (2.0 * t))
                        targets = _compute_battle_primary_positions(3)
                        tmp: List[dict] = []
                        for idx, tg in enumerate(targets):
                            tx = int(tg.get("x", 0))
                            ty = int(tg.get("y", 0))
                            rows = tg.get("rows", [])
                            th = len(rows) if isinstance(rows, list) else 0
                            sx = tx
                            sy = -max(2, th + 2 + (idx * 2))
                            tmp.append(
                                {
                                    "x": int(round(sx + ((tx - sx) * te))),
                                    "y": int(round(sy + ((ty - sy) * te))),
                                    "rows": rows,
                                }
                            )
                        story_transition_actors = tmp
                elif screen == "story_sharoom_lineup_shift":
                    primary_sprites = []
                    secondary_sprites = []
                    trans = flow.get("sharoom_lineup_transition")
                    if isinstance(trans, dict):
                        t = max(0.0, min(1.0, float(trans.get("t", 0.0)) / max(0.001, float(trans.get("duration", 1.0)))))
                        te = t * t * (3.0 - (2.0 * t))
                        actors = trans.get("actors", [])
                        if isinstance(actors, list):
                            tmp: List[dict] = []
                            for a in actors:
                                if not isinstance(a, dict):
                                    continue
                                sx = int(a.get("sx", 0))
                                sy = int(a.get("sy", 0))
                                ex = int(a.get("ex", sx))
                                ey = int(a.get("ey", sy))
                                x = int(round(sx + ((ex - sx) * te)))
                                y = int(round(sy + ((ey - sy) * te)))
                                rows = a.get("rows", [])
                                if isinstance(rows, list):
                                    tmp.append({"x": x, "y": y, "rows": rows})
                            story_transition_actors = tmp
                elif screen == "story_actor_entrance":
                    primary_sprites = []
                    secondary_sprites = []
                    ent = flow.get("actor_entrance")
                    if isinstance(ent, dict):
                        t = max(0.0, min(1.0, float(ent.get("t", 0.0)) / max(0.001, float(ent.get("duration", 1.0)))))
                        te = t * t * (3.0 - (2.0 * t))
                        targets = _compute_story_formation_positions(selected_player_sprite, "pre")
                        tmp: List[dict] = []
                        # Secondary policy: enter from below viewport.
                        if "player" in targets:
                            tg = targets["player"]
                            sx = int(tg["x"])
                            sy = SCREEN_H + 2
                            ex = int(tg["x"])
                            ey = int(tg["y"])
                            tmp.append(
                                {
                                    "x": int(round(sx + ((ex - sx) * te))),
                                    "y": int(round(sy + ((ey - sy) * te))),
                                    "rows": tg["rows"],
                                }
                            )
                        # Primary policy: enter from right side off viewport.
                        primary_ids = [aid for aid in ("mushy", "crow1") if aid in targets]
                        for idx, aid in enumerate(primary_ids):
                            tg = targets[aid]
                            rows = tg["rows"]
                            th = len(rows) if isinstance(rows, list) else 0
                            if aid in FLIGHTED_ACTOR_TAGS:
                                # Flighted opponents enter from above.
                                sx = int(tg["x"])
                                sy = -max(2, th + 2 + (idx * 2))
                            else:
                                # Default opponent entrance from the right.
                                sx = SCREEN_W + 2 + (idx * 4)
                                sy = int(tg["y"])
                            ex = int(tg["x"])
                            ey = int(tg["y"])
                            tmp.append(
                                {
                                    "x": int(round(sx + ((ex - sx) * te))),
                                    "y": int(round(sy + ((ey - sy) * te))),
                                    "rows": tg["rows"],
                                }
                            )
                        story_transition_actors = tmp
                elif screen == "story_lineup_shift":
                    primary_sprites = []
                    secondary_sprites = []
                    trans = flow.get("lineup_transition")
                    if isinstance(trans, dict):
                        t = max(0.0, min(1.0, float(trans.get("t", 0.0)) / max(0.001, float(trans.get("duration", 1.0)))))
                        # Smoothstep easing for softer start/end.
                        te = t * t * (3.0 - (2.0 * t))
                        actors = trans.get("actors", [])
                        if isinstance(actors, list):
                            tmp: List[dict] = []
                            for a in actors:
                                if not isinstance(a, dict):
                                    continue
                                sx = int(a.get("sx", 0))
                                sy = int(a.get("sy", 0))
                                ex = int(a.get("ex", sx))
                                ey = int(a.get("ey", sy))
                                x = int(round(sx + ((ex - sx) * te)))
                                y = int(round(sy + ((ey - sy) * te)))
                                rows = a.get("rows", [])
                                if isinstance(rows, list):
                                    tmp.append({"x": x, "y": y, "rows": rows})
                            story_transition_actors = tmp
                elif screen in ("story_more_crows", "story_sharoom_1"):
                    primary_sprites = []
                    secondary_sprites = [selected_player_sprite, mushy_sprite]
                elif screen == "story_sharoom_entrance":
                    primary_sprites = []
                    secondary_sprites = [selected_player_sprite, mushy_sprite]
                    ent = flow.get("sharoom_entrance")
                    if isinstance(ent, dict):
                        t = max(0.0, min(1.0, float(ent.get("t", 0.0)) / max(0.001, float(ent.get("duration", 1.0)))))
                        te = t * t * (3.0 - (2.0 * t))
                        ground_zone = zones.get("ground_bg")
                        if isinstance(ground_zone, LayoutZone):
                            pz = build_primary_zone(_treeline_lowest_row(ground_zone.y, world_anchor_stagger) + 1)
                            targets = layout_actor_strip(pz, [sharoom_sprite], spacing=1, stagger_rows=1)
                            if targets:
                                tg = targets[0]
                                tx = int(tg.get("x", 0))
                                ty = int(tg.get("y", 0))
                                sx = SCREEN_W + 4
                                sy = ty
                                story_transition_actors = [
                                    {
                                        "x": int(round(sx + ((tx - sx) * te))),
                                        "y": int(round(sy + ((ty - sy) * te))),
                                        "rows": tg.get("rows", []),
                                    }
                                ]
                elif screen in ("story_sharoom_3", "story_sharoom_4"):
                    primary_sprites = [sharoom_sprite]
                    secondary_sprites = [selected_player_sprite, mushy_sprite]
                else:
                    primary_sprites = [crow_sprite, mushy_sprite]
                    secondary_sprites = [selected_player_sprite]

            primary_placements_for_ui: List[dict] = []
            secondary_placements_for_ui: List[dict] = []
            if scene_world_layer_level >= 3:
                secondary_zone = build_secondary_zone()
                secondary_placements_for_ui = layout_actor_strip(
                    secondary_zone,
                    secondary_sprites,
                    spacing=1,
                    stagger_rows=1,
                    reverse_stagger=True,
                )
                ground_zone = zones.get("ground_bg")
                if isinstance(ground_zone, LayoutZone):
                    lowest_tree_row = _treeline_lowest_row(ground_zone.y, world_anchor_stagger)
                    primary_zone = build_primary_zone(lowest_tree_row + 1)
                    primary_placements_for_ui = layout_actor_strip(
                        primary_zone,
                        primary_sprites,
                        spacing=1,
                        stagger_rows=1,
                    )
            active_spec = _position_screen_box_for_actors(
                screen,
                active_spec,
                primary_placements_for_ui,
                secondary_placements_for_ui,
            )
            step_count = ui_box_step_count(active_spec) if isinstance(active_spec, UIBoxSpec) else 1
            ui_ready = wipe_progress >= 1.0
            if anim_mode == "open":
                anim_progress = 1.0
            else:
                anim_progress = anim_step / max(1, step_count)

            avatar_overlay = None
            ui_actor_status = None
            if screen == "avatar_select":
                pidx = int(flow.get("player_index", 0)) % len(player_cards)
                left = player_cards[0]
                right = player_cards[1]
                avatar_overlay = {
                    "left_rows": left.get("sprite", []),
                    "right_rows": right.get("sprite", []),
                    "left_label": left.get("label", "Left"),
                    "right_label": right.get("label", "Right"),
                    "selected": pidx,
                }
            if screen in ("story_battle_cmd_player", "story_battle_cmd_mushy", "story_battle_cmd_sharoom", "story_battle_ally_target"):
                sec_hp = [int(v) for v in flow.get("battle_secondary_hp", [20, 10])]
                sec_hp_max = [int(v) for v in flow.get("battle_secondary_hp_max", sec_hp)]
                sec_mp = [int(v) for v in flow.get("battle_secondary_mp", [0, 6])]
                sec_mp_max = [int(v) for v in flow.get("battle_secondary_mp_max", sec_mp)]
                actor_idx = 0
                if screen == "story_battle_cmd_mushy":
                    actor_idx = 2 if len(sec_hp) >= 3 else 1
                elif screen == "story_battle_cmd_player":
                    actor_idx = 1 if len(sec_hp) >= 3 else 0
                elif screen == "story_battle_cmd_sharoom":
                    actor_idx = 0
                elif screen == "story_battle_ally_target":
                    who = str(flow.get("battle_ally_select_actor", "mushy")).strip().lower()
                    actor_idx = 0 if who == "sharoom" else (2 if len(sec_hp) >= 3 and who == "mushy" else 1)
                if 0 <= actor_idx < len(sec_hp):
                    hp_total = sec_hp_max[actor_idx] if actor_idx < len(sec_hp_max) else max(1, sec_hp[actor_idx])
                    mp_total = sec_mp_max[actor_idx] if actor_idx < len(sec_mp_max) else (sec_mp[actor_idx] if actor_idx < len(sec_mp) else 0)
                    ui_actor_status = {
                        "hp": sec_hp[actor_idx],
                        "hp_total": max(1, hp_total),
                        "mp": sec_mp[actor_idx] if actor_idx < len(sec_mp) else 0,
                        "mp_total": max(1, mp_total),
                    }

            pri_hp_now = [int(v) for v in flow.get("battle_primary_hp", [10])]
            story_target_index = None
            if screen in ("story_battle_cmd_player", "story_battle_cmd_mushy", "story_battle_cmd_sharoom"):
                t = int(flow.get("battle_target_cursor", 0))
                if 0 <= t < len(pri_hp_now) and pri_hp_now[t] > 0:
                    story_target_index = t
            story_target_secondary_index = None
            story_target_secondary_indices = None
            story_secondary_hp = None
            story_secondary_hp_total = None
            story_secondary_mp = None
            story_secondary_mp_total = None
            story_secondary_hud_indices = None
            if screen == "story_battle_ally_target":
                stage_now = int(flow.get("battle_stage", 1))
                actor_key = str(flow.get("battle_ally_select_actor", "mushy"))
                action_name = str(flow.get("battle_ally_action", ""))
                targets = _alive_secondary_target_indices(flow, actor_key, action_name, stage_now)
                mode = str(flow.get("battle_ally_target_mode", "single")).strip().lower()
                story_secondary_hp = [int(v) for v in flow.get("battle_secondary_hp", [20, 10])]
                story_secondary_hp_total = [int(v) for v in flow.get("battle_secondary_hp_max", story_secondary_hp)]
                story_secondary_mp = [int(v) for v in flow.get("battle_secondary_mp", [0, 6])]
                story_secondary_mp_total = [int(v) for v in flow.get("battle_secondary_mp_max", story_secondary_mp)]
                story_secondary_hud_indices = list(targets)
                if mode == "all":
                    story_target_secondary_indices = list(targets)
                else:
                    c = int(flow.get("battle_ally_target_cursor", targets[0] if targets else 0))
                    story_target_secondary_index = c
            story_spell = None
            story_damage_hud = None
            story_mp_hud = None
            story_smash = None
            story_primary_hp = None
            story_primary_hp_total = 10
            if screen in ("story_battle_cmd_player", "story_battle_cmd_mushy", "story_battle_cmd_sharoom"):
                story_primary_hp = list(pri_hp_now)
            if screen in ("story_battle_resolve", "story_battle3_resolve"):
                queue = flow.get("battle_queue", [])
                qidx = int(flow.get("battle_queue_index", 0))
                if qidx < len(queue):
                    action = queue[qidx]
                    kind = str(action.get("kind", "physical"))
                    duration = 1.2 if kind == "spell" else 0.9
                    prog = min(1.0, float(flow.get("battle_action_t", 0.0)) / max(0.001, duration))
                    if kind in ("spell", "physical"):
                        story_damage_hud = {
                            "target_side": str(action.get("target_side", "primary")),
                            "target_index": int(action.get("target_index", 0)),
                            "progress": prog,
                            "pre_hp": int(action.get("pre_hp", 0)),
                            "post_hp": int(action.get("post_hp", 0)),
                            "total": 10,
                            "damage": int(action.get("damage", 0)),
                        }
                    if kind == "spell":
                        story_spell = {
                            "source_side": str(action.get("source_side", "secondary")),
                            "source_index": int(action.get("source_index", 0)),
                            "target_side": str(action.get("target_side", "primary")),
                            "target_index": int(action.get("target_index", 0)),
                            "progress": prog,
                        }
                        if bool(action.get("uses_mp", False)):
                            story_mp_hud = {
                                "source_side": str(action.get("source_side", "secondary")),
                                "source_index": int(action.get("source_index", 0)),
                                "progress": prog,
                                "pre_mp": int(action.get("pre_mp", 0)),
                                "post_mp": int(action.get("post_mp", 0)),
                                "total": 10,
                                "cost": int(action.get("mp_cost", 2)),
                            }
                    elif kind == "physical":
                        story_smash = {
                            "source_side": str(action.get("source_side", "secondary")),
                            "source_index": int(action.get("source_index", 0)),
                            "target_side": str(action.get("target_side", "primary")),
                            "target_index": int(action.get("target_index", 0)),
                            "progress": prog,
                        }
            melt_idx_raw = flow.get("battle_melt_index")
            story_melt_idx = int(melt_idx_raw) if melt_idx_raw is not None else None
            story_melt_progress = min(1.0, float(flow.get("battle_melt_t", 0.0)) / 0.8) if melt_idx_raw is not None else 0.0
            story_hidden_primary_indices: List[int] = []
            if screen in battle_screens:
                for idx, hp in enumerate(pri_hp_now):
                    if hp <= 0 and (story_melt_idx is None or idx != story_melt_idx):
                        story_hidden_primary_indices.append(idx)
            battle_log_lines = _battle_log_visible_lines(flow) if screen in battle_log_screens else None

            frame = render(
                clouds=clouds,
                ground_rows=ground_rows,
                zones=zones,
                sky_bottom_anchor=sky_bottom_anchor,
                foreground_split_label=split_label,
                world_layer_level=scene_world_layer_level,
                world_anchor_stagger=world_anchor_stagger,
                world_treeline_sprites=world_treeline_sprites,
                primary_actor_sprites=primary_sprites,
                primary_actor_stagger=1,
                secondary_actor_sprites=secondary_sprites,
                secondary_actor_stagger=1,
                secondary_actor_reverse_stagger=True,
                wipe_progress=wipe_progress,
                show_zone_guides=show_zone_guides,
                world_scene_label=world_scene_label,
                title_logo=title_logo,
                show_title_logo=(not screen.startswith("story_")),
                ui_active_box=(active_spec if (ui_ready and isinstance(active_spec, UIBoxSpec)) else None),
                ui_active_box_progress=(anim_progress if ui_ready else 0.0),
                ui_actor_status=(ui_actor_status if ui_ready else None),
                ui_avatar_overlay=(avatar_overlay if ui_ready else None),
                blink_phase=now,
                story_target_primary_index=story_target_index,
                story_target_blink=bool((int(now * 2.0) % 2) == 0),
                story_target_secondary_index=story_target_secondary_index,
                story_target_secondary_indices=story_target_secondary_indices,
                story_target_secondary_blink=bool((int(now * 2.0) % 2) == 0),
                story_spell=story_spell,
                story_primary_hp=story_primary_hp,
                story_primary_hp_total=story_primary_hp_total,
                story_secondary_hp=story_secondary_hp,
                story_secondary_hp_total=story_secondary_hp_total,
                story_secondary_mp=story_secondary_mp,
                story_secondary_mp_total=story_secondary_mp_total,
                story_secondary_hud_indices=story_secondary_hud_indices,
                story_damage_hud=story_damage_hud,
                story_mp_hud=story_mp_hud,
                story_smash=story_smash,
                story_melt_primary_index=story_melt_idx,
                story_melt_progress=story_melt_progress,
                story_hidden_primary_indices=story_hidden_primary_indices,
                story_transition_actors=story_transition_actors,
                battle_log_lines=battle_log_lines,
            )
            print(ANSI_HOME + frame, end="", flush=True)

            # Transition animation is now input-driven.
            if ui_ready:
                if anim_mode == "opening":
                    anim_step = min(step_count, anim_step + 4)
                    if anim_step >= step_count:
                        anim_mode = "open"
                elif anim_mode == "closing":
                    anim_step = max(0, anim_step - 4)
                    if anim_step <= 0:
                        nxt = str(flow.get("next_screen") or flow.get("screen"))
                        flow["screen"] = nxt
                        flow["next_screen"] = None
                        anim_mode = "opening"
                        anim_step = 0
                else:
                    anim_step = step_count
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        print(ANSI_SHOW_CURSOR + ANSI_RESET)


if __name__ == "__main__":
    main()
