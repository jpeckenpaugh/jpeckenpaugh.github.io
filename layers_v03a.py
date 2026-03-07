import os
import random
import re
import time
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
    for _ in range(max(0, row_count)):
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
    for y, raw in enumerate(art_rows):
        art = str(raw).ljust(width)
        mask = str(mask_rows[y]) if y < len(mask_rows) else ""
        row: List[str] = []
        for x, ch in enumerate(art):
            if ch == " ":
                row.append(" ")
                continue
            key = mask[x] if x < len(mask) else ""
            code = color_codes.get(key, "")
            row.append(f"{code}{ch}{ANSI_RESET}" if code else ch)
        out.append(row)
    return out


def build_world_treeline_sprites(objects_data: object, colors_data: object) -> List[dict]:
    if not isinstance(objects_data, dict):
        return []
    color_codes = _build_color_codes(colors_data)
    tree_ids = ["tree_large", "tree_large_2", "tree_large_3"]
    tree_ids = [obj_id for obj_id in tree_ids if isinstance(objects_data.get(obj_id), dict)]
    if not tree_ids:
        return []

    rng = random.Random(6611)
    sprites: List[dict] = []
    x = -2
    while x < SCREEN_W:
        obj_id = tree_ids[rng.randrange(len(tree_ids))]
        payload = objects_data.get(obj_id, {})
        art = payload.get("art", []) if isinstance(payload, dict) else []
        mask = payload.get("color_mask", []) if isinstance(payload, dict) else []
        rows = _colorize_object_rows(art, mask, color_codes)
        if not rows:
            x += 4
            continue
        width = len(rows[0])
        height = len(rows)
        visible_count = sum(1 for cell in rows[-1] if _strip_ansi(cell) != " ")
        spacing = rng.randint(2, 6) if visible_count > 2 else rng.randint(4, 8)
        sprites.append(
            {
                "x": x,
                "width": width,
                "height": height,
                "rows": rows,
                "anchor_offset": rng.randint(0, 2),
            }
        )
        x += max(4, width - 4) + spacing
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
    secondary_zone = build_secondary_zone()
    if world_layer_level >= 2:
        ground_zone = zones.get("ground_bg")
        if isinstance(ground_zone, LayoutZone):
            lowest_tree_row = _treeline_lowest_row(ground_zone.y, world_anchor_stagger)
            return {
                "primary": build_primary_zone(lowest_tree_row + 1),
                "secondary": secondary_zone,
            }
        return {"primary": build_primary_zone(SCREEN_H - 1), "secondary": secondary_zone}
    if not world_treeline_sprites:
        return {"secondary": secondary_zone}
    ground_zone = zones.get("ground_bg")
    if not isinstance(ground_zone, LayoutZone):
        return {"secondary": secondary_zone}
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
        "secondary": secondary_zone,
    }


def build_primary_zone(anchor_bottom_y: int) -> LayoutZone:
    width = 20
    height = 12
    x = (SCREEN_W - width) // 2
    y = anchor_bottom_y - height + 1
    return _make_zone("primary", x, y, width, height, LAYER_FOREGROUND)


def build_secondary_zone() -> LayoutZone:
    # Bottom-left quadrant secondary slot:
    # - bottom-left corner anchor position = 1 row above screen bottom
    width = 20
    height = 12
    x_center = SCREEN_W // 4
    x = x_center - (width // 2)
    bottom_anchor_position = 1
    bottom_y = (SCREEN_H - 1) - bottom_anchor_position
    y = bottom_y - height + 1
    return _make_zone("secondary", x, y, width, height, LAYER_WORLD)


def _treeline_lowest_row(ground_top_y: int, world_anchor_stagger: int) -> int:
    stagger = max(1, min(3, int(world_anchor_stagger)))
    return ground_top_y + max(0, stagger - 1)


def _draw_sun(canvas: List[List[str]], sky_zone: LayoutZone) -> None:
    sun_rows = [
        "   .-***-.   ",
        " .*#######*. ",
        ".###########.",
        ".###########.",
        " .*#######*. ",
        "   '-***-'   ",
    ]
    color = "\x1b[38;2;255;220;120m"
    width = len(sun_rows[0])
    height = len(sun_rows)
    x0 = SCREEN_W - width - 8
    y0 = max(0, sky_zone.y + 1)
    if y0 + height - 1 > sky_zone.y1:
        y0 = max(sky_zone.y, sky_zone.y1 - height + 1)
    for dy, row in enumerate(sun_rows):
        y = y0 + dy
        if y < sky_zone.y or y > sky_zone.y1:
            continue
        for dx, ch in enumerate(row):
            if ch == " ":
                continue
            x = x0 + dx
            if 0 <= x < SCREEN_W:
                canvas[y][x] = f"{color}{ch}{ANSI_RESET}"


def render(
    clouds: List[dict],
    ground_rows: List[str],
    zones: Dict[str, LayoutZone],
    sky_bottom_anchor: int,
    foreground_split_label: str,
    world_layer_level: int = 0,
    world_anchor_stagger: int = 1,
    world_treeline_sprites: List[dict] | None = None,
    guy_sprite: List[List[str]] | None = None,
    mushy_sprite: List[List[str]] | None = None,
    wipe_progress: float = 1.0,
    show_zone_guides: bool = False,
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

    # Background sky base: sun behind cloud layer.
    _draw_sun(canvas, sky_zone)

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
    if world_layer_level > 0 and world_treeline_sprites:
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

    # World layer avatar pass: Guy in secondary zone.
    if world_layer_level > 0 and guy_sprite:
        sprite_h = len(guy_sprite)
        sprite_w = max((len(row) for row in guy_sprite), default=0)
        x0 = secondary_zone.x + max(0, (secondary_zone.width - sprite_w) // 2)
        y0 = secondary_zone.y1 - max(0, sprite_h - 1)
        for dy, row in enumerate(guy_sprite):
            y = y0 + dy
            if y < 0 or y >= SCREEN_H:
                continue
            for dx, cell in enumerate(row):
                x = x0 + dx
                if 0 <= x < SCREEN_W and cell != " ":
                    canvas[y][x] = cell

    # Foreground primary pass: Mushy follower in primary zone.
    if world_layer_level >= 2 and primary_zone is not None and mushy_sprite:
        sprite_h = len(mushy_sprite)
        sprite_w = max((len(row) for row in mushy_sprite), default=0)
        x0 = primary_zone.x + max(0, (primary_zone.width - sprite_w) // 2)
        y0 = primary_zone.y1 - max(0, sprite_h - 1)
        for dy, row in enumerate(mushy_sprite):
            y = y0 + dy
            if y < 0 or y >= SCREEN_H:
                continue
            for dx, cell in enumerate(row):
                x = x0 + dx
                if 0 <= x < SCREEN_W and cell != " ":
                    canvas[y][x] = cell

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

    # Scene foundation label on the very last row, centered.
    footer = f"[background][{foreground_split_label}]"
    if world_layer_level > 0:
        footer += f"[world][{max(1, min(3, int(world_anchor_stagger)))}]"
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

    target_split_index = SKY_ROWS_OPTIONS.index(DEFAULT_SKY_ROWS)
    current_sky_rows = SKY_ROWS_OPTIONS[target_split_index]
    target_sky_rows = current_sky_rows
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
    show_zone_guides = True
    world_layer_level = 0
    world_mode_count = 3
    world_anchor_stagger = 1
    world_treeline_sprites = build_world_treeline_sprites(objects, colors)
    guy_sprite = build_player_sprite(players, "player_01", color_codes)
    mushy_sprite = build_mushy_sprite(opponents, color_codes)
    transition_accum = 0.0
    transition_step_seconds = 0.06

    print(ANSI_HIDE_CURSOR + ANSI_CLEAR, end="", flush=True)
    try:
        last_tick = time.monotonic()
        while True:
            now = time.monotonic()
            dt = max(0.0, min(0.2, now - last_tick))
            last_tick = now
            wipe_progress = min(1.0, max(0.0, (now - wipe_started_at) / wipe_duration))

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
            if key == "up":
                if world_layer_level > 0:
                    world_anchor_stagger = (world_anchor_stagger % 3) + 1
                else:
                    target_split_index = (target_split_index - 1) % len(SKY_ROWS_OPTIONS)
                    target_sky_rows = SKY_ROWS_OPTIONS[target_split_index]
                    transition_accum = 0.0
            if key == "down":
                if world_layer_level > 0:
                    world_anchor_stagger = 3 if world_anchor_stagger <= 1 else (world_anchor_stagger - 1)
                else:
                    target_split_index = (target_split_index + 1) % len(SKY_ROWS_OPTIONS)
                    target_sky_rows = SKY_ROWS_OPTIONS[target_split_index]
                    transition_accum = 0.0
            if key == "right":
                world_layer_level = (world_layer_level + 1) % world_mode_count
            if key == "left":
                world_layer_level = (world_layer_level - 1) % world_mode_count

            split_label = f"{zones['sky_bg'].height}/{zones['ground_bg'].height}"

            frame = render(
                clouds=clouds,
                ground_rows=ground_rows,
                zones=zones,
                sky_bottom_anchor=sky_bottom_anchor,
                foreground_split_label=split_label,
                world_layer_level=world_layer_level,
                world_anchor_stagger=world_anchor_stagger,
                world_treeline_sprites=world_treeline_sprites,
                guy_sprite=guy_sprite,
                mushy_sprite=mushy_sprite,
                wipe_progress=wipe_progress,
                show_zone_guides=show_zone_guides,
            )
            print(ANSI_HOME + frame, end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        print(ANSI_SHOW_CURSOR + ANSI_RESET)


if __name__ == "__main__":
    main()

