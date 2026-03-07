import json
import os
import random
import time
from typing import Dict, List

from app.rendering.title_panorama import TitlePanorama


SCREEN_W = 100
SCREEN_H = 30
SKY_H = 15
ANSI_RESET = "\x1b[0m"
ANSI_HIDE_CURSOR = "\x1b[?25l"
ANSI_SHOW_CURSOR = "\x1b[?25h"
ANSI_HOME = "\x1b[H"
ANSI_CLEAR = "\x1b[2J"

# Keep the same cloud palette family as title scene.
CLOUD_RGB_PALETTE = [
    (255, 255, 255),
    (236, 240, 246),
    (214, 222, 235),
    (198, 216, 246),
    (178, 204, 242),
]


def load_json(path: str) -> object:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def ansi_rgb(r: int, g: int, b: int) -> str:
    return f"\x1b[38;2;{r};{g};{b}m"


def cloud_color_code(object_id: str, row: int, col: int, mask_key: str) -> str:
    seed = 2166136261
    for ch in f"{object_id}:{row}:{col}:{mask_key}":
        seed ^= ord(ch)
        seed = (seed * 16777619) & 0xFFFFFFFF
    idx = seed % len(CLOUD_RGB_PALETTE)
    r, g, b = CLOUD_RGB_PALETTE[idx]
    return ansi_rgb(r, g, b)


def cloud_templates(objects: Dict[str, object]) -> List[dict]:
    templates: List[dict] = []
    for object_id, payload in objects.items():
        if not isinstance(object_id, str) or not object_id.startswith("cloud_"):
            continue
        if not isinstance(payload, dict):
            continue
        art = payload.get("art", [])
        mask = payload.get("color_mask", [])
        if not isinstance(art, list) or not art:
            continue
        if not isinstance(mask, list):
            mask = []

        width = max((len(str(line)) for line in art), default=1)
        rows: List[List[str]] = []
        for row_idx, raw_line in enumerate(art):
            line = str(raw_line).ljust(width)
            mask_line = str(mask[row_idx]) if row_idx < len(mask) else ""
            row: List[str] = []
            for col_idx, ch in enumerate(line):
                if ch == " ":
                    row.append(" ")
                    continue
                key = mask_line[col_idx] if col_idx < len(mask_line) else "l"
                code = cloud_color_code(object_id, row_idx, col_idx, key)
                row.append(f"{code}{ch}{ANSI_RESET}")
            rows.append(row)
        size = "small"
        if "_medium_" in object_id:
            size = "medium"
        elif "_large_" in object_id:
            size = "large"
        templates.append(
            {
                "id": object_id,
                "width": width,
                "height": len(rows),
                "rows": rows,
                "size": size,
            }
        )
    return templates


def title_like_cloud_speed(size: str, y: int, rng: random.Random) -> float:
    size_weight = {"large": 0.72, "medium": 1.0, "small": 1.28}.get(size, 1.0)
    y_norm = max(0.0, min(1.0, y / max(1, SKY_H - 1)))
    height_weight = 0.72 + (0.62 * y_norm)
    variance = 1.0 + (rng.random() * 3.0)
    return 1.0 * size_weight * height_weight * variance


def spawn_clouds(templates: List[dict], count: int) -> List[dict]:
    rng = random.Random()
    clouds: List[dict] = []
    if not templates:
        return clouds
    for _ in range(max(0, count)):
        template = templates[rng.randrange(len(templates))]
        w = int(template["width"])
        h = int(template["height"])
        y_max = max(0, SKY_H - h)
        y = rng.randint(0, y_max) if y_max > 0 else 0
        x = rng.randint(-max(1, w // 2), SCREEN_W - 1)
        # Requested: 1/4 the title-screen cloud speed.
        speed = 0.25 * title_like_cloud_speed(str(template.get("size", "medium")), y, rng)
        clouds.append({"template": template, "x": float(x), "y": y, "speed": speed})
    return clouds


def ansi_line_to_cells(text: str, width: int) -> List[str]:
    cells: List[str] = []
    i = 0
    active = ""
    while i < len(text):
        ch = text[i]
        if ch == "\x1b" and i + 1 < len(text) and text[i + 1] == "[":
            j = i + 2
            while j < len(text) and text[j] != "m":
                j += 1
            if j < len(text):
                seq = text[i : j + 1]
                active = "" if seq == ANSI_RESET else seq
                i = j + 1
                continue
        if ch == " ":
            cells.append(" ")
        elif active:
            cells.append(f"{active}{ch}{ANSI_RESET}")
        else:
            cells.append(ch)
        i += 1
        if len(cells) >= width:
            break
    while len(cells) < width:
        cells.append(" ")
    return cells


def build_forest_band(
    scenes_data: Dict[str, object],
    objects_data: Dict[str, object],
    colors_data: Dict[str, object],
    opponents_data: Dict[str, object],
) -> List[str]:
    pano = TitlePanorama(
        viewport_width=SCREEN_W,
        height=15,
        speed=0.0,
        forest_width_scale=0.5,
        scenes_data=scenes_data,
        objects_data=objects_data,
        colors_data=colors_data,
        opponents_data=opponents_data,
    )
    # Build a focused forest strip: 6 random trees, Mushy, 6 random trees.
    tree_options = [
        "tree_large",
        "tree_large_2",
        "tree_large_3",
        "bush_large",
        "bush_large_2",
        "bush_large_3",
    ]
    tree_options = [obj_id for obj_id in tree_options if pano._object_art(obj_id)]
    if not tree_options:
        tree_options = ["tree_large", "bush_large", "grass_1"]

    rng = random.Random(4242)
    work_height = pano.content_height + 2
    rows: List[List[str]] = [[] for _ in range(work_height)]
    blank_by_width: Dict[int, str] = {}

    def append_piece_with_drop(art_rows: List[str], mask_rows: List[str], drop: int) -> None:
        if not art_rows:
            return
        width = len(art_rows[0])
        if width <= 0:
            return
        if width not in blank_by_width:
            blank_by_width[width] = " " * width
        drop = max(0, min(2, int(drop)))
        for y in range(work_height):
            src_y = y - drop
            if src_y < 0 or src_y >= len(art_rows):
                art_line = blank_by_width[width]
                mask_line = blank_by_width[width]
            else:
                art_line = art_rows[src_y]
                mask_line = mask_rows[src_y]
            for x, ch in enumerate(art_line):
                mask_char = mask_line[x] if x < len(mask_line) else " "
                rows[y].append(pano._colorize(ch, mask_char))

    def append_tree_with_drop(tree_id: str, drop: int) -> None:
        art_rows, mask_rows = pano._normalize_layers(pano._object_art(tree_id), pano._object_mask(tree_id))
        append_piece_with_drop(art_rows, mask_rows, drop)

    for _ in range(6):
        tree_id = tree_options[rng.randrange(len(tree_options))]
        append_tree_with_drop(tree_id, rng.randrange(3))

    # Space around Mushy so adjacent trees do not touch character art.
    append_piece_with_drop(["    "], ["    "], 0)
    mush_start_x = len(rows[0]) if rows else 0
    mush_art = pano._opponent_art("mushroom_baby")
    mush_mask = pano._opponent_mask("mushroom_baby")
    if mush_art:
        art_rows, mask_rows = pano._normalize_layers(mush_art, mush_mask)
        append_piece_with_drop(art_rows, mask_rows, 0)
        mush_width = max((len(line) for line in mush_art), default=0)
    else:
        mush_width = 0
    append_piece_with_drop(["    "], ["    "], 0)

    for _ in range(6):
        tree_id = tree_options[rng.randrange(len(tree_options))]
        append_tree_with_drop(tree_id, rng.randrange(3))

    # Center viewport on Mushy instead of left-aligning the strip.
    total_width = len(rows[0]) if rows else 0
    mush_center = mush_start_x + (mush_width // 2)
    start_x = max(0, mush_center - (SCREEN_W // 2))
    if total_width > SCREEN_W:
        start_x = min(start_x, total_width - SCREEN_W)
    else:
        start_x = 0

    forest_cells: List[List[str]] = []
    for row in rows:
        if total_width <= SCREEN_W:
            left_pad = max(0, (SCREEN_W - total_width) // 2)
            padded = ([" "] * left_pad) + row + ([" "] * (SCREEN_W - left_pad - total_width))
            forest_cells.append(padded[:SCREEN_W])
        else:
            forest_cells.append(row[start_x : start_x + SCREEN_W])

    forest_with_padding = pano._add_vertical_padding(forest_cells)
    base_rows: List[List[str]] = []
    for row in forest_with_padding[:15]:
        normalized = row[:SCREEN_W] if len(row) >= SCREEN_W else row + ([" "] * (SCREEN_W - len(row)))
        base_rows.append(normalized)
    while len(base_rows) < 15:
        base_rows.append([" " for _ in range(SCREEN_W)])

    # Shift scene up by 3 and add 3 grass rows at the bottom.
    shifted = base_rows[3:]
    overlay_rows = [list(row) for row in shifted]
    grass_art = pano._object_art("grass")
    grass_mask = pano._object_mask("grass")
    pattern = grass_art[0] if grass_art else "~"
    pattern_mask = grass_mask[0] if grass_mask else "g"
    scatter_obj = {}
    if isinstance(objects_data.get("battle_ground", {}), dict):
        scatter_obj = objects_data.get("battle_ground", {})
    elif isinstance(objects_data.get("pebble", {}), dict):
        scatter_obj = objects_data.get("pebble", {})
    dynamic = scatter_obj.get("dynamic", {}) if isinstance(scatter_obj, dict) else {}
    scatter_glyphs = dynamic.get("glyphs", []) if isinstance(dynamic, dict) else []
    scatter_keys = dynamic.get("color_keys", []) if isinstance(dynamic, dict) else []
    scatter_chance = float(dynamic.get("scatter_chance", 0.0) or 0.0) if isinstance(dynamic, dict) else 0.0
    scatter_chance *= 0.5
    scatter_enabled = bool(scatter_glyphs and scatter_keys and scatter_chance > 0.0)
    scatter_rng = random.Random(90517)

    def apply_scatter(row: List[str]) -> List[str]:
        if not scatter_enabled:
            return row
        out = list(row)
        for x, cell in enumerate(out):
            glyph = pano._strip_ansi(cell)
            if glyph != "~":
                continue
            if scatter_rng.random() >= scatter_chance:
                continue
            glyph = str(scatter_glyphs[scatter_rng.randrange(len(scatter_glyphs))])[:1] or "o"
            key = str(scatter_keys[scatter_rng.randrange(len(scatter_keys))])[:1] or "Z"
            out[x] = pano._colorize(glyph, key)
        return out

    # Fill transparent gaps with grass on rows that are already ground-heavy.
    for y, row in enumerate(shifted):
        visible = "".join(pano._strip_ansi(cell) for cell in row)
        grass_count = visible.count("~")
        if grass_count < 12:
            continue
        for x, cell in enumerate(row):
            glyph = pano._strip_ansi(cell)
            if glyph != " ":
                continue
            ch = pattern[x % max(1, len(pattern))]
            key = pattern_mask[x % max(1, len(pattern_mask))] if pattern_mask else "g"
            shifted[y][x] = pano._colorize(ch, key)
        shifted[y] = apply_scatter(shifted[y])

    for _ in range(3):
        row: List[str] = []
        for x in range(SCREEN_W):
            ch = pattern[x % max(1, len(pattern))]
            key = pattern_mask[x % max(1, len(pattern_mask))] if pattern_mask else "g"
            row.append(pano._colorize(ch, key))
        shifted.append(apply_scatter(row))

    # Ensure trees/characters render above grass base.
    for y, row in enumerate(overlay_rows):
        if y >= len(shifted):
            break
        for x, cell in enumerate(row):
            glyph = pano._strip_ansi(cell)
            if glyph != " ":
                shifted[y][x] = cell

    lines: List[str] = []
    for row in shifted[:15]:
        lines.append("".join(row[:SCREEN_W]).ljust(SCREEN_W))
    while len(lines) < 15:
        lines.append(" " * SCREEN_W)
    return lines


def render(clouds: List[dict], forest_lines: List[str]) -> str:
    canvas = [[" " for _ in range(SCREEN_W)] for _ in range(SCREEN_H)]

    # Top half sky clouds.
    for cloud in clouds:
        template = cloud["template"]
        x0 = int(cloud["x"])
        y0 = int(cloud["y"])
        rows = template["rows"]
        for dy, row in enumerate(rows):
            y = y0 + dy
            if y < 0 or y >= SKY_H:
                continue
            for dx, cell in enumerate(row):
                x = x0 + dx
                if x < 0 or x >= SCREEN_W:
                    continue
                if cell != " ":
                    canvas[y][x] = cell

    # Bottom half forest panorama band.
    for y in range(SKY_H):
        src = forest_lines[y] if y < len(forest_lines) else ""
        canvas[SKY_H + y] = ansi_line_to_cells(src, SCREEN_W)

    return "\n".join("".join(row) for row in canvas)


def main() -> None:
    base = os.getcwd()
    objects_path = os.path.join(base, "legacy", "data", "objects.json")
    colors_path = os.path.join(base, "legacy", "data", "colors.json")
    scenes_path = os.path.join(base, "legacy", "data", "scenes.json")
    opponents_path = os.path.join(base, "legacy", "data", "opponents.json")

    objects = load_json(objects_path)
    colors = load_json(colors_path)
    scenes = load_json(scenes_path)
    opponents = load_json(opponents_path)

    if not isinstance(objects, dict):
        raise RuntimeError("objects.json is not a JSON object")
    if not isinstance(colors, dict):
        raise RuntimeError("colors.json is not a JSON object")
    if not isinstance(scenes, dict):
        raise RuntimeError("scenes.json is not a JSON object")
    if not isinstance(opponents, dict):
        raise RuntimeError("opponents.json is not a JSON object")

    templates = cloud_templates(objects)
    if not templates:
        raise RuntimeError("No cloud_* objects found in objects.json")

    clouds = spawn_clouds(templates, count=10)
    forest_lines = build_forest_band(scenes, objects, colors, opponents)

    print(ANSI_HIDE_CURSOR + ANSI_CLEAR, end="", flush=True)
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
                    cloud["x"] = SCREEN_W + (cloud["x"] + w)
            frame = render(clouds, forest_lines)
            print(ANSI_HOME + frame, end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        print(ANSI_SHOW_CURSOR + ANSI_RESET)


if __name__ == "__main__":
    main()

