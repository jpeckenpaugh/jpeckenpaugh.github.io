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
    # For dense 5+ member parties, collapse inter-actor margin to preserve viewport fit.
    effective_spacing = max(0, int(spacing))
    if len(active) >= 5:
        effective_spacing = 0
    sizes = [_sprite_size(rows) for rows in active]
    widths = [w for w, _h in sizes]
    total_width = sum(widths) + (max(0, len(active) - 1) * effective_spacing)
    start_x = area.x + ((area.width - total_width) // 2)
    # Keep the collective strip on-screen by shifting toward center as needed.
    if total_width <= SCREEN_W:
        start_x = max(0, min(SCREEN_W - total_width, start_x))
    else:
        # If artwork is wider than viewport, anchor to left so lead actor remains visible.
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
        x += w + effective_spacing
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


def _physical_hit_state_progress(progress: float) -> tuple[bool, bool, int]:
    # progress in [0,1]: blink twice, then play smash frames 1..5 once.
    p = max(0.0, min(1.0, float(progress)))
    blink_window = 0.50
    impact_window = 0.50
    if p < blink_window:
        step = int((p / max(0.001, blink_window)) * 4.0)
        blink_visible = (step % 2) == 0
        return (not blink_visible, False, 0)
    if p < (blink_window + impact_window):
        impact_t = (p - blink_window) / max(0.001, impact_window)
        frame_idx = min(4, int(impact_t * 5.0))
        return (False, True, frame_idx)
    return (False, False, 0)


def _physical_demo_state(clock: float) -> dict:
    # Sequence:
    # 1) Guy -> Fairy1 (2)
    # 2) Mushy -> Fairy1 (3)
    # 3) Chase -> Fairy2 (4)
    # 4) Ogrito -> Fairy1 (2, kill)
    attacks = [
        {"attacker_idx": 0, "target_idx": 0, "damage": 2},
        {"attacker_idx": 1, "target_idx": 0, "damage": 3},
        {"attacker_idx": 2, "target_idx": 1, "damage": 4},
        {"attacker_idx": 3, "target_idx": 0, "damage": 2},
    ]
    initial_hp = [7, 10, 10, 10]
    attack_window = 1.0
    between_pause = 2.0
    final_pause = 5.0

    total = (len(attacks) * attack_window) + (max(0, len(attacks) - 1) * between_pause) + final_pause
    t = float(clock) % max(0.001, total)
    hp_now = list(initial_hp)
    cursor = 0.0
    death_time = (3 * attack_window) + (3 * between_pause) + (0.75 * attack_window)
    death_elapsed = (t - death_time) if t >= death_time else None

    for idx, atk in enumerate(attacks):
        pre = hp_now[atk["target_idx"]]
        post = max(0, pre - int(atk["damage"]))
        atk_start = cursor
        atk_end = atk_start + attack_window
        if atk_start <= t < atk_end:
            progress = (t - atk_start) / max(0.001, attack_window)
            return {
                "phase": "attack",
                "attack_idx": idx,
                "attacker_idx": atk["attacker_idx"],
                "target_idx": atk["target_idx"],
                "damage": int(atk["damage"]),
                "pre_hp": pre,
                "post_hp": post,
                "hp_now": hp_now,
                "progress": progress,
                "phase_elapsed": (t - atk_start),
                "phase_duration": attack_window,
                "loop_t": t,
                "total": total,
                "death_elapsed": death_elapsed,
            }
        # apply this attack for subsequent windows
        hp_now[atk["target_idx"]] = post
        cursor = atk_end
        if idx < len(attacks) - 1:
            pause_end = cursor + between_pause
            if cursor <= t < pause_end:
                return {
                    "phase": "pause",
                    "attack_idx": idx,
                    "attacker_idx": atk["attacker_idx"],
                    "target_idx": atk["target_idx"],
                    "damage": int(atk["damage"]),
                    "pre_hp": pre,
                    "post_hp": post,
                    "hp_now": hp_now,
                    "progress": 1.0,
                    "phase_elapsed": (t - cursor),
                    "phase_duration": between_pause,
                    "loop_t": t,
                    "total": total,
                    "death_elapsed": death_elapsed,
                }
            cursor = pause_end

    # final hold after all attacks
    return {
        "phase": "final_pause",
        "attack_idx": len(attacks) - 1,
        "attacker_idx": attacks[-1]["attacker_idx"],
        "target_idx": attacks[-1]["target_idx"],
        "damage": int(attacks[-1]["damage"]),
        "pre_hp": 0,
        "post_hp": hp_now[attacks[-1]["target_idx"]],
        "hp_now": hp_now,
        "progress": 1.0,
        "phase_elapsed": max(0.0, t - cursor),
        "phase_duration": final_pause,
        "loop_t": t,
        "total": total,
        "death_elapsed": death_elapsed,
    }


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
    pct = filled / float(total)
    if pct >= 0.5:
        hp_color = "\x1b[38;2;56;186;72m"   # green: healthy
    elif pct >= 0.25:
        hp_color = "\x1b[38;2;236;201;58m"  # yellow: medium
    else:
        hp_color = "\x1b[38;2;220;70;70m"   # red: low
    miss_color = "\x1b[38;2;26;26;26m"     # missing hp
    frame_color = "\x1b[38;2;210;210;210m"  # frame

    inner_w = total
    box_w = inner_w + 2
    x0 = max(0, min(SCREEN_W - box_w, int(center_x) - (box_w // 2)))
    y0 = int(top_y)
    if y0 < 0 or (y0 + 2) >= SCREEN_H:
        return

    top_row: List[str] = [f"{frame_color}┌{ANSI_RESET}"]
    top_row.extend([f"{frame_color}─{ANSI_RESET}" for _ in range(inner_w)])
    top_row.append(f"{frame_color}┐{ANSI_RESET}")

    mid_row: List[str] = [f"{frame_color}│{ANSI_RESET}"]
    mid_row.extend([f"{hp_color}█{ANSI_RESET}" for _ in range(filled)])
    mid_row.extend([f"{miss_color}·{ANSI_RESET}" for _ in range(empty)])
    mid_row.append(f"{frame_color}│{ANSI_RESET}")

    bot_row: List[str] = [f"{frame_color}└{ANSI_RESET}"]
    bot_row.extend([f"{frame_color}─{ANSI_RESET}" for _ in range(inner_w)])
    bot_row.append(f"{frame_color}┘{ANSI_RESET}")

    for dx, cell in enumerate(top_row):
        x = x0 + dx
        if 0 <= x < SCREEN_W:
            canvas[y0][x] = cell
    for dx, cell in enumerate(mid_row):
        x = x0 + dx
        if 0 <= x < SCREEN_W:
            canvas[y0 + 1][x] = cell
    for dx, cell in enumerate(bot_row):
        x = x0 + dx
        if 0 <= x < SCREEN_W:
            canvas[y0 + 2][x] = cell


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

    inner_w = total
    box_w = inner_w + 2
    x0 = max(0, min(SCREEN_W - box_w, int(center_x) - (box_w // 2)))
    y0 = int(top_y)
    if y0 < 0 or (y0 + 2) >= SCREEN_H:
        return

    top_row: List[str] = [f"{frame_color}┌{ANSI_RESET}"]
    top_row.extend([f"{frame_color}─{ANSI_RESET}" for _ in range(inner_w)])
    top_row.append(f"{frame_color}┐{ANSI_RESET}")

    mid_row: List[str] = [f"{frame_color}│{ANSI_RESET}"]
    mid_row.extend([f"{fill_color}█{ANSI_RESET}" for _ in range(filled)])
    mid_row.extend([f"{miss_color}·{ANSI_RESET}" for _ in range(empty)])
    mid_row.append(f"{frame_color}│{ANSI_RESET}")
    if overlay_text:
        text = str(overlay_text)
        start = 1 + max(0, (inner_w - len(text)) // 2)
        for i, ch in enumerate(text):
            x = start + i
            if 1 <= x <= inner_w:
                mid_row[x] = f"{overlay_color}{ch}{ANSI_RESET}"

    bot_row: List[str] = [f"{frame_color}└{ANSI_RESET}"]
    bot_row.extend([f"{frame_color}─{ANSI_RESET}" for _ in range(inner_w)])
    bot_row.append(f"{frame_color}┘{ANSI_RESET}")

    for dy, row in enumerate([top_row, mid_row, bot_row]):
        y = y0 + dy
        for dx, cell in enumerate(row):
            x = x0 + dx
            if 0 <= x < SCREEN_W and 0 <= y < SCREEN_H:
                canvas[y][x] = cell


def _draw_physical_damage_hud(canvas: List[List[str]], target_actor: dict, clock: float) -> None:
    rows = target_actor.get("rows", [])
    if not isinstance(rows, list) or not rows:
        return
    w = max((len(row) for row in rows), default=0)
    x0 = int(target_actor.get("x", 0))
    y0 = int(target_actor.get("y", 0))
    center_x = x0 + (w // 2)
    bar_top = y0 - 4

    total = 10
    pre_filled = 8
    damage = 5
    post_filled = max(0, pre_filled - damage)
    phase = float(clock) % 1.0

    # 0.00-0.50: pre-hit bar visible (target not yet damaged)
    if phase < 0.50:
        _draw_health_bar_custom(canvas, center_x, bar_top, pre_filled, total=total)
        return

    # 0.50-0.75: impact + "-5" pop-up while bar flashes at pre-hit value.
    if phase < 0.75:
        flash_on = (int((phase - 0.50) / 0.06) % 2) == 0
        flash_fill = "\x1b[38;2;255;95;95m" if flash_on else None
        flash_frame = "\x1b[38;2;255;170;170m" if flash_on else None
        _draw_health_bar_custom(
            canvas,
            center_x,
            bar_top,
            pre_filled,
            total=total,
            fill_color=flash_fill,
            frame_color=flash_frame,
            overlay_text=f"-{damage}",
            overlay_color="\x1b[38;2;250;250;250m",
        )
        return

    # 0.75-1.00: settle on reduced HP value.
    _draw_health_bar_custom(
        canvas,
        center_x,
        bar_top,
        post_filled,
        total=total,
        overlay_text=f"-{damage}",
        overlay_color="\x1b[38;2;245;245;245m",
    )


def _draw_physical_damage_hud_step(
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
    center_x = x0 + (w // 2)
    bar_top = y0 - 4

    p = max(0.0, min(1.0, float(progress)))
    if p < 0.50:
        _draw_health_bar_custom(canvas, center_x, bar_top, pre_hp, total=total)
        return
    if p < 0.75:
        flash_on = (int((p - 0.50) / 0.06) % 2) == 0
        flash_fill = "\x1b[38;2;255;95;95m" if flash_on else None
        flash_frame = "\x1b[38;2;255;170;170m" if flash_on else None
        _draw_health_bar_custom(
            canvas,
            center_x,
            bar_top,
            pre_hp,
            total=total,
            fill_color=flash_fill,
            frame_color=flash_frame,
            overlay_text=f"-{damage}",
            overlay_color="\x1b[38;2;250;250;250m",
        )
        return
    _draw_health_bar_custom(
        canvas,
        center_x,
        bar_top,
        post_hp,
        total=total,
        overlay_text=f"-{damage}",
        overlay_color="\x1b[38;2;245;245;245m",
    )


def _grey_cell(cell: str) -> str:
    ch = _strip_ansi(cell)
    if ch == " ":
        return " "
    return f"\x1b[38;2;156;156;156m{ch}{ANSI_RESET}"


def _draw_actor_melt(canvas: List[List[str]], actor: dict, progress: float) -> None:
    rows = actor.get("rows", [])
    if not isinstance(rows, list) or not rows:
        return
    x0 = int(actor.get("x", 0))
    y0 = int(actor.get("y", 0))
    h = len(rows)
    p = max(0.0, min(1.0, float(progress)))
    # Round A (0.0-0.5): top->bottom decolor sweep.
    # Round B (0.5-1.0): top->bottom shift-and-disappear sweep.
    phase_a = min(1.0, p / 0.5) if p < 0.5 else 1.0
    phase_b = 0.0 if p < 0.5 else min(1.0, (p - 0.5) / 0.5)
    a_sweep = phase_a * h
    b_sweep = phase_b * h
    b_row = int(b_sweep)
    b_frac = b_sweep - b_row

    for dy, row in enumerate(rows):
        if not isinstance(row, list):
            continue
        y = y0 + dy
        if y < 0 or y >= SCREEN_H:
            continue

        # Round A result for this row.
        is_grey = dy < a_sweep
        shift = 0
        visible = True

        # Round B: once A is complete, rows start melting away top->bottom.
        if phase_b > 0.0:
            if dy < b_row:
                visible = False
            elif dy == b_row and b_row < h:
                # Brief shifted "wilt" before vanishing.
                if b_frac < 0.5:
                    shift = -1 if (dy % 2 == 0) else 1
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
            out = _grey_cell(cell) if is_grey else cell
            canvas[y][x] = out


def _mp_fill_color(pct: float) -> str:
    # Linear scale from light blue (0%) to bright blue (100%).
    p = max(0.0, min(1.0, float(pct)))
    r0, g0, b0 = (120, 170, 235)
    r1, g1, b1 = (56, 140, 255)
    r = int(r0 + ((r1 - r0) * p))
    g = int(g0 + ((g1 - g0) * p))
    b = int(b0 + ((b1 - b0) * p))
    return f"\x1b[38;2;{r};{g};{b}m"


def _draw_status_box(
    canvas: List[List[str]],
    center_x: int,
    top_y: int,
    hp_filled: int,
    total: int = 10,
    mp_filled: int | None = None,
) -> None:
    total = max(1, int(total))
    hp_filled = max(0, min(total, int(hp_filled)))
    hp_empty = total - hp_filled
    hp_pct = hp_filled / float(total)
    if hp_pct >= 0.5:
        hp_color = "\x1b[38;2;56;186;72m"
    elif hp_pct >= 0.25:
        hp_color = "\x1b[38;2;236;201;58m"
    else:
        hp_color = "\x1b[38;2;220;70;70m"
    miss_color = "\x1b[38;2;26;26;26m"
    frame_color = "\x1b[38;2;210;210;210m"
    mp_miss_color = "\x1b[38;2;18;24;36m"

    has_mp = mp_filled is not None
    mp_f = 0
    mp_empty = total
    mp_color = _mp_fill_color(0.0)
    if has_mp:
        mp_f = max(0, min(total, int(mp_filled)))
        mp_empty = total - mp_f
        mp_color = _mp_fill_color(mp_f / float(total))

    inner_w = total
    box_w = inner_w + 2
    box_h = 4 if has_mp else 3
    x0 = max(0, min(SCREEN_W - box_w, int(center_x) - (box_w // 2)))
    y0 = int(top_y)
    if y0 < 0 or (y0 + box_h - 1) >= SCREEN_H:
        return

    top_row: List[str] = [f"{frame_color}┌{ANSI_RESET}"]
    top_row.extend([f"{frame_color}─{ANSI_RESET}" for _ in range(inner_w)])
    top_row.append(f"{frame_color}┐{ANSI_RESET}")

    hp_row: List[str] = [f"{frame_color}│{ANSI_RESET}"]
    hp_row.extend([f"{hp_color}█{ANSI_RESET}" for _ in range(hp_filled)])
    hp_row.extend([f"{miss_color}·{ANSI_RESET}" for _ in range(hp_empty)])
    hp_row.append(f"{frame_color}│{ANSI_RESET}")

    mp_row: List[str] = [f"{frame_color}│{ANSI_RESET}"]
    if has_mp:
        mp_row.extend([f"{mp_color}█{ANSI_RESET}" for _ in range(mp_f)])
        mp_row.extend([f"{mp_miss_color}·{ANSI_RESET}" for _ in range(mp_empty)])
    else:
        mp_row.extend([f"{miss_color}·{ANSI_RESET}" for _ in range(inner_w)])
    mp_row.append(f"{frame_color}│{ANSI_RESET}")

    bot_row: List[str] = [f"{frame_color}└{ANSI_RESET}"]
    bot_row.extend([f"{frame_color}─{ANSI_RESET}" for _ in range(inner_w)])
    bot_row.append(f"{frame_color}┘{ANSI_RESET}")

    rows = [top_row, hp_row, mp_row, bot_row] if has_mp else [top_row, hp_row, bot_row]
    for dy, row in enumerate(rows):
        y = y0 + dy
        for dx, cell in enumerate(row):
            x = x0 + dx
            if 0 <= x < SCREEN_W:
                canvas[y][x] = cell


def _draw_actor_health_bars(
    canvas: List[List[str]],
    placements: List[dict],
    mixed: bool = True,
    demo_percents: List[int] | None = None,
) -> None:
    for idx, actor in enumerate(placements):
        rows = actor.get("rows", [])
        if not isinstance(rows, list) or not rows:
            continue
        w = max((len(row) for row in rows), default=0)
        x0 = int(actor.get("x", 0))
        y0 = int(actor.get("y", 0))
        center_x = x0 + (w // 2)
        bar_y = y0 - 3
        if demo_percents is not None and idx < len(demo_percents):
            pct = max(0, min(100, int(demo_percents[idx])))
            filled = int(round((pct / 100.0) * 10))
        elif mixed:
            # Demo fallback values.
            filled = 4 if idx % 2 == 0 else 2
        else:
            filled = 10
        _draw_health_bar(canvas, center_x, bar_y, filled, total=10)


def _draw_actor_status_bars(
    canvas: List[List[str]],
    placements: List[dict],
    hp_percents: List[int] | None = None,
    mp_percents: List[int | None] | None = None,
) -> None:
    for idx, actor in enumerate(placements):
        rows = actor.get("rows", [])
        if not isinstance(rows, list) or not rows:
            continue
        w = max((len(row) for row in rows), default=0)
        x0 = int(actor.get("x", 0))
        y0 = int(actor.get("y", 0))
        center_x = x0 + (w // 2)

        hp_pct = 100
        if hp_percents is not None and idx < len(hp_percents):
            hp_pct = max(0, min(100, int(hp_percents[idx])))
        hp_filled = int(round((hp_pct / 100.0) * 10))

        mp_filled: int | None = None
        if mp_percents is not None and idx < len(mp_percents):
            mp_pct = mp_percents[idx]
            if mp_pct is not None:
                mp_pct = max(0, min(100, int(mp_pct)))
                mp_filled = int(round((mp_pct / 100.0) * 10))

        bar_y = y0 - (4 if mp_filled is not None else 3)
        _draw_status_box(canvas, center_x, bar_y, hp_filled=hp_filled, total=10, mp_filled=mp_filled)


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
    hide_attacker_idx: int | None = None
    show_hit_impact = False
    impact_frame_hint = 0
    physical_state: dict | None = None
    if world_layer_level == 7:
        physical_state = _physical_demo_state(spell_clock)
        if physical_state.get("phase") == "attack":
            atk_progress = float(physical_state.get("progress", 0.0))
            hide_attacker, show_hit_impact, impact_frame_hint = _physical_hit_state_progress(atk_progress)
            hide_attacker_idx = int(physical_state.get("attacker_idx", 0))

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
            if hide_attacker and hide_attacker_idx is not None and idx == hide_attacker_idx:
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
        hp_now = physical_state.get("hp_now", []) if isinstance(physical_state, dict) else []
        death_elapsed = physical_state.get("death_elapsed") if isinstance(physical_state, dict) else None
        melt_progress: float | None = None
        if death_elapsed is not None:
            melt_progress = max(0.0, min(1.0, float(death_elapsed) / 1.0))
        for idx, actor in enumerate(primary_placements):
            if world_layer_level == 7 and idx == 0 and melt_progress is not None and melt_progress > 0.0:
                if melt_progress < 1.0:
                    _draw_actor_melt(canvas, actor, melt_progress)
                continue
            if world_layer_level == 7 and isinstance(hp_now, list) and idx < len(hp_now) and int(hp_now[idx]) <= 0:
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
    if world_layer_level == 7 and primary_placements and show_hit_impact and smash_frames and physical_state is not None:
        target_idx = int(physical_state.get("target_idx", 0))
        target_idx = max(0, min(len(primary_placements) - 1, target_idx))
        dst = primary_placements[target_idx]
        dst_rows = dst.get("rows", [])
        dst_w = max((len(row) for row in dst_rows), default=0) if isinstance(dst_rows, list) else 0
        dst_h = len(dst_rows) if isinstance(dst_rows, list) else 0
        target = (int(dst.get("x", 0)) + (dst_w // 2), int(dst.get("y", 0)) + (dst_h // 2))
        frame_idx = min(max(0, impact_frame_hint), len(smash_frames) - 1)
        _draw_smash_frame(canvas, smash_frames[frame_idx], target)
    if world_layer_level == 7 and primary_placements and physical_state is not None:
        phase = str(physical_state.get("phase", ""))
        show_hud = False
        target_idx = int(physical_state.get("target_idx", 0))
        target_idx = max(0, min(len(primary_placements) - 1, target_idx))
        if phase == "attack":
            show_hud = True
            _draw_physical_damage_hud_step(
                canvas,
                primary_placements[target_idx],
                progress=float(physical_state.get("progress", 0.0)),
                pre_hp=max(0, int(physical_state.get("pre_hp", 0))),
                post_hp=max(0, int(physical_state.get("post_hp", 0))),
                total=10,
                damage=max(0, int(physical_state.get("damage", 0))),
            )
        else:
            phase_elapsed = float(physical_state.get("phase_elapsed", 0.0))
            if phase_elapsed <= 0.6:
                show_hud = True
                hp_now = physical_state.get("hp_now", [])
                hp_val = 0
                if isinstance(hp_now, list) and target_idx < len(hp_now):
                    hp_val = max(0, int(hp_now[target_idx]))
                rows = primary_placements[target_idx].get("rows", [])
                if isinstance(rows, list) and rows:
                    w = max((len(row) for row in rows), default=0)
                    x0 = int(primary_placements[target_idx].get("x", 0))
                    y0 = int(primary_placements[target_idx].get("y", 0))
                    center_x = x0 + (w // 2)
                    _draw_health_bar_custom(canvas, center_x, y0 - 4, hp_val, total=10)
    # Next demo step: health bars above all actors in both panes.
    if world_layer_level == 8:
        # Primary (4 fairies): 20%, 40%, 100%, 100%.
        _draw_actor_health_bars(canvas, primary_placements, mixed=True, demo_percents=[20, 40, 100, 100])
        # Secondary team [Guy, Mushy, Chase, Ogrito, Beba]:
        # Guy 80%, Ogrito 60%, others 100%.
        _draw_actor_health_bars(canvas, secondary_placements, mixed=True, demo_percents=[80, 100, 100, 60, 100])
    # Duplicate status demo: HP + MP in a second row for MP-capable actors.
    if world_layer_level == 9:
        _draw_actor_status_bars(
            canvas,
            primary_placements,
            hp_percents=[20, 40, 100, 100],
            mp_percents=[75, 55, 85, 95],
        )
        _draw_actor_status_bars(
            canvas,
            secondary_placements,
            hp_percents=[80, 100, 100, 60, 100],
            mp_percents=[70, 65, None, None, 90],
        )
    if world_layer_level == 10 and primary_zone is not None:
        _draw_ui_dialogue_box(canvas, "Beba", UI_DIALOG_TEXT, primary_zone, secondary_zone)

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
    if world_layer_level >= 1:
        footer += f"[world][{max(1, min(3, int(world_anchor_stagger)))}]"
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
        footer += "[mp]"
    if world_layer_level >= 10:
        footer += "[dialogue]"
    if len(footer) <= SCREEN_W:
        x0 = (SCREEN_W - len(footer)) // 2
        y = SCREEN_H - 1
        for i, ch in enumerate(footer):
            canvas[y][x0 + i] = ch

    return "\n".join("".join(row) for row in canvas)


def main() -> None:
    base = os.getcwd()
    objects_path = os.path.join(base, "legecay", "data", "objects.json")
    colors_path = os.path.join(base, "legecay", "data", "colors.json")
    opponents_path = os.path.join(base, "legecay", "data", "opponents.json")
    players_path = os.path.join(base, "legecay", "data", "players.json")
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
    world_mode_count = 11
    world_anchor_stagger = 1
    world_treeline_sprites = build_world_treeline_sprites(objects, colors)
    guy_sprite = build_player_sprite(players, "player_01", color_codes)
    chase_sprite = build_opponent_sprite(opponents, "wolf", color_codes)
    mushy_sprite = build_opponent_sprite(opponents, "mushroom_teen", color_codes)
    ogrito_sprite = build_opponent_sprite(opponents, "ogre", color_codes)
    baby_fairy_sprite = build_opponent_sprite(opponents, "fairy_baby", color_codes)
    beba_rexa_sprite = build_opponent_sprite(opponents, "fairy_teen", color_codes)
    if not beba_rexa_sprite:
        beba_rexa_sprite = baby_fairy_sprite
    if not mushy_sprite:
        mushy_sprite = build_opponent_sprite(opponents, "mushroom_baby", color_codes)
    if not chase_sprite:
        chase_sprite = build_opponent_sprite(opponents, "wolf_pup", color_codes)
    if not ogrito_sprite:
        ogrito_sprite = build_opponent_sprite(opponents, "baby_ogre", color_codes)
    if not ogrito_sprite:
        ogrito_sprite = chase_sprite
    smash_frames = load_smash_frames(os.path.join(base, "smash.txt"))
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
            # Global animation clock at 50% default speed for all effects.
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
                primary_actor_sprites=[
                    baby_fairy_sprite,
                    baby_fairy_sprite,
                    baby_fairy_sprite,
                    baby_fairy_sprite,
                ],
                primary_actor_stagger=1,
                secondary_actor_sprites=[guy_sprite, mushy_sprite, chase_sprite, ogrito_sprite, beba_rexa_sprite],
                secondary_actor_stagger=1,
                secondary_actor_reverse_stagger=True,
                guy_sprite=guy_sprite,
                mushy_sprite=mushy_sprite,
                spell_phase=spell_phase,
                spell_clock=spell_clock,
                smash_frames=smash_frames,
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
