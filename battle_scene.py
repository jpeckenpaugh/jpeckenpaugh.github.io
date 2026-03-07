import json
import os
import random
import time
import math
import textwrap
import sys
import select
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


def load_quest_dialog(quests_data: Dict[str, object], quest_id: str) -> List[dict]:
    quest = quests_data.get(quest_id, {}) if isinstance(quests_data, dict) else {}
    dialog = quest.get("dialog", []) if isinstance(quest, dict) else []
    if not isinstance(dialog, list):
        return []
    entries: List[dict] = []

    def infer_speaker(text_value: str, art_value: object) -> str:
        speaker_value = "narration"
        art_text = str(art_value).lower()
        if "mushroom_baby" in art_text:
            speaker_value = "mushy"
        elif "baby_crow" in art_text:
            speaker_value = "crow"
        low_text = text_value.lower()
        if low_text.startswith("mushy:"):
            speaker_value = "mushy"
        elif low_text.startswith("crow"):
            speaker_value = "crow"
        elif low_text.startswith("narration:"):
            speaker_value = "narration"
        return speaker_value

    for entry in dialog:
        text = ""
        speaker = "narration"
        if isinstance(entry, str):
            text = entry.strip()
        elif isinstance(entry, dict):
            if str(entry.get("type", "")).lower() == "choice":
                prompt = str(entry.get("prompt", "")).strip()
                options = entry.get("options", [])
                labels: List[str] = []
                option_branches: List[List[dict]] = []
                if isinstance(options, list):
                    for opt in options:
                        branch_lines: List[dict] = []
                        if isinstance(opt, dict):
                            label = str(opt.get("label", "")).strip()
                            if label:
                                labels.append(label)
                            actions = opt.get("actions", [])
                            if isinstance(actions, list):
                                for action in actions:
                                    if not isinstance(action, dict):
                                        continue
                                    if str(action.get("type", "")).lower() != "show_message":
                                        continue
                                    message = str(action.get("message", "")).strip()
                                    if not message:
                                        continue
                                    branch_lines.append(
                                        {
                                            "speaker": infer_speaker(message, action.get("art", "")),
                                            "type": "text",
                                            "text": message,
                                        }
                                    )
                        option_branches.append(branch_lines)
                text = prompt
                entries.append(
                    {
                        "speaker": "narration",
                        "type": "choice",
                        "text": text,
                        "options": labels,
                        "option_branches": option_branches,
                    }
                )
                continue
            else:
                text = str(entry.get("text", "")).strip()
                speaker = infer_speaker(text, entry.get("art", ""))
        if not text:
            continue
        entries.append({"speaker": speaker, "type": "text", "text": text})
    return entries


def _dialog_bottom_line(inner: int, button: str) -> str:
    if len(button) + 5 <= inner:
        right = 5
        left = max(0, inner - len(button) - right)
        return "o" + ("-" * left) + button + ("-" * right) + "o"
    return "o" + ("-" * inner) + "o"


def dialog_border_gradient_code(x: int, y: int, width: int, height: int) -> str:
    # Match title logo/frame white -> blue -> grey diagonal gradient.
    if width <= 1 and height <= 1:
        r, g, b = (192, 192, 192)
        return ansi_rgb(r, g, b)
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
    return ansi_rgb(r, g, b)


def dialog_box_lines(entry: dict, choice_cursor: int, max_inner_width: int = 44) -> List[str]:
    text = str(entry.get("text", "")).strip()
    entry_type = str(entry.get("type", "text"))
    options = entry.get("options", []) if isinstance(entry, dict) else []
    width = max(24, min(max_inner_width, SCREEN_W - 8))
    content_width = max(10, width - 2)
    wrapped = textwrap.wrap(text, width=content_width, break_long_words=False, break_on_hyphens=False)
    if not wrapped:
        wrapped = [""]
    body_lines: List[str] = list(wrapped)
    if entry_type == "choice" and isinstance(options, list):
        opts = [str(opt) for opt in options if str(opt).strip()]
        if body_lines:
            body_lines.append("")
        for idx, opt in enumerate(opts[:2]):
            if idx == choice_cursor:
                line = f"[ {opt} ]"
            else:
                line = f"  {opt}  "
            body_lines.append(line)
    inner_content = max(width, max(len(line) for line in body_lines))
    inner = inner_content + 2
    lines: List[str] = []
    lines.append("o" + ("-" * inner) + "o")
    lines.append("|" + (" " * inner) + "|")
    for line in body_lines:
        centered = line.center(inner_content)
        lines.append("| " + centered + " |")
    lines.append("|" + (" " * inner) + "|")
    if entry_type == "choice":
        bottom = _dialog_bottom_line(inner, "[ Select ]")
    else:
        bottom = _dialog_bottom_line(inner, "[ Continue ]")
    lines.append(bottom)
    return lines


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
            return None
        try:
            return ch.decode("utf-8").lower()
        except UnicodeDecodeError:
            return None
    ready, _, _ = select.select([sys.stdin], [], [], 0)
    if not ready:
        return None
    try:
        ch = sys.stdin.read(1)
    except Exception:
        return None
    return ch.lower() if ch else None


def overlay_dialog_box(canvas: List[List[str]], lines: List[str], x0: int, y0: int) -> None:
    if not lines:
        return
    box_w = len(lines[0])
    box_h = len(lines)
    x0 = max(0, min(SCREEN_W - box_w, x0))
    y0 = max(0, min(SCREEN_H - box_h, y0))
    for dy, raw in enumerate(lines):
        y = y0 + dy
        if y < 0 or y >= SCREEN_H:
            continue
        cells = ansi_line_to_cells(raw, box_w)
        for dx, cell in enumerate(cells):
            x = x0 + dx
            if 0 <= x < SCREEN_W:
                is_border = dy == 0 or dy == box_h - 1 or dx == 0 or dx == box_w - 1
                if is_border and cell != " " and not str(cell).startswith("\x1b["):
                    code = dialog_border_gradient_code(dx, dy, box_w, box_h)
                    canvas[y][x] = f"{code}{cell}{ANSI_RESET}"
                else:
                    canvas[y][x] = cell


def build_forest_band(
    scenes_data: Dict[str, object],
    objects_data: Dict[str, object],
    colors_data: Dict[str, object],
    opponents_data: Dict[str, object],
) -> tuple[List[str], dict, dict]:
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
    mush_top_raw = 0
    mush_height = 0
    if mush_art:
        art_rows, mask_rows = pano._normalize_layers(mush_art, mush_mask)
        append_piece_with_drop(art_rows, mask_rows, 0)
        mush_width = max((len(line) for line in mush_art), default=0)
        mush_height = len(art_rows)
        for iy, line in enumerate(art_rows):
            if any(ch != " " for ch in line):
                mush_top_raw = iy
                break
    else:
        mush_width = 0
    append_piece_with_drop(["    "], ["    "], 0)

    for _ in range(6):
        tree_id = tree_options[rng.randrange(len(tree_options))]
        append_tree_with_drop(tree_id, rng.randrange(3))

    crow_meta: dict = {}
    # Build crow sprite meta for animated overlay (not baked into forest rows).
    crow_art = pano._opponent_art("baby_crow")
    crow_mask = pano._opponent_mask("baby_crow")
    if crow_art and mush_width > 0:
        crow_w = max((len(line) for line in crow_art), default=0)
        if crow_w > 0:
            mush_rows, _ = pano._normalize_layers(mush_art, mush_mask) if mush_art else ([], [])

            def non_space_bounds(lines: List[str]) -> tuple[int, int]:
                min_y = len(lines)
                max_y = -1
                for iy, line in enumerate(lines):
                    if any(ch != " " for ch in line):
                        min_y = min(min_y, iy)
                        max_y = max(max_y, iy)
                if max_y < 0:
                    return (0, 0)
                return (min_y, max_y)

            mush_top, _mush_bottom = non_space_bounds(mush_rows)
            crow_h = len(crow_art)

            mush_center_x = mush_start_x + (mush_width // 2)
            crow_x0 = max(0, mush_center_x - (crow_w // 2))
            crow_y0 = max(0, mush_top - crow_h - 1)
            crow_rows: List[List[str]] = []
            for y in range(len(crow_art)):
                art_line = str(crow_art[y]).ljust(crow_w)
                mask_line = str(crow_mask[y]) if y < len(crow_mask) else ""
                crow_row: List[str] = []
                for x, ch in enumerate(art_line):
                    if ch == " ":
                        crow_row.append(" ")
                    else:
                        key = mask_line[x] if x < len(mask_line) else " "
                        crow_row.append(pano._colorize(ch, key))
                crow_rows.append(crow_row)
            crow_meta = {
                "rows": crow_rows,
                "raw_x": crow_x0,
                "raw_target_y": crow_y0,
                "width": crow_w,
                "height": crow_h,
            }

    # Center viewport on Mushy instead of left-aligning the strip.
    total_width = len(rows[0]) if rows else 0
    mush_center = mush_start_x + (mush_width // 2)
    start_x = max(0, mush_center - (SCREEN_W // 2))
    if total_width > SCREEN_W:
        start_x = min(start_x, total_width - SCREEN_W)
    else:
        start_x = 0

    forest_cells: List[List[str]] = []
    crow_x = int(crow_meta.get("raw_x", 0)) if crow_meta else 0
    for row in rows:
        if total_width <= SCREEN_W:
            left_pad = max(0, (SCREEN_W - total_width) // 2)
            padded = ([" "] * left_pad) + row + ([" "] * (SCREEN_W - left_pad - total_width))
            forest_cells.append(padded[:SCREEN_W])
            if crow_meta:
                crow_x = left_pad + int(crow_meta.get("raw_x", 0))
        else:
            forest_cells.append(row[start_x : start_x + SCREEN_W])
            if crow_meta:
                crow_x = int(crow_meta.get("raw_x", 0)) - start_x

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
    actor_meta: dict = {}
    if crow_meta:
        target_band_y = int(crow_meta.get("raw_target_y", 0))
        target_band_y = max(0, min(14, target_band_y))
        crow_meta = {
            "rows": crow_meta.get("rows", []),
            "x": crow_x,
            "target_y": SKY_H + target_band_y,
            "start_y": -max(1, int(crow_meta.get("height", 1))),
            "speed": 8.0,
        }
    actor_meta["mushy"] = {
        "x": int(mush_start_x + (mush_width // 2) - start_x) if total_width > SCREEN_W else int(max(0, (SCREEN_W - total_width) // 2) + mush_start_x + (mush_width // 2)),
        "y": SKY_H + max(0, min(14, mush_top_raw)),
    }
    return lines, crow_meta, actor_meta


def draw_panel(canvas: List[List[str]], x0: int, y0: int, width: int, height: int, title: str, lines: List[str]) -> None:
    if width < 4 or height < 4:
        return
    x0 = max(0, min(SCREEN_W - width, x0))
    y0 = max(0, min(SCREEN_H - height, y0))
    for y in range(height):
        for x in range(width):
            gx = x0 + x
            gy = y0 + y
            if y == 0 or y == height - 1:
                ch = "o" if x in (0, width - 1) else "-"
            elif x == 0 or x == width - 1:
                ch = "|"
            else:
                ch = " "
            if ch != " ":
                color = dialog_border_gradient_code(x, y, width, height)
                canvas[gy][gx] = f"{color}{ch}{ANSI_RESET}"
            else:
                canvas[gy][gx] = " "

    if title:
        title_text = f"[ {title} ]"
        title_x = x0 + max(1, (width - len(title_text)) // 2)
        title_y = y0
        for i, ch in enumerate(title_text):
            tx = title_x + i
            if x0 < tx < x0 + width - 1:
                canvas[title_y][tx] = f"\x1b[37m{ch}{ANSI_RESET}"

    inner_w = width - 2
    max_lines = height - 2
    for idx, raw in enumerate(lines[:max_lines]):
        row = y0 + 1 + idx
        text = str(raw)[:inner_w].ljust(inner_w)
        cells = ansi_line_to_cells(text, inner_w)
        for dx, cell in enumerate(cells):
            canvas[row][x0 + 1 + dx] = cell


def render(
    clouds: List[dict],
    forest_lines: List[str],
    crow_meta: dict,
    crow_x: float,
    crow_y: float,
    command_items: List[str],
    command_cursor: int,
    log_lines: List[str],
    wipe_progress: float = 1.0,
) -> str:
    canvas = [[" " for _ in range(SCREEN_W)] for _ in range(SCREEN_H)]

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

    for y in range(SKY_H):
        src = forest_lines[y] if y < len(forest_lines) else ""
        canvas[SKY_H + y] = ansi_line_to_cells(src, SCREEN_W)

    crow_rows = crow_meta.get("rows", []) if isinstance(crow_meta, dict) else []
    crow_xi = int(round(crow_x))
    crow_yi = int(crow_y)
    if isinstance(crow_rows, list):
        for dy, row in enumerate(crow_rows):
            y = crow_yi + dy
            if y < 0 or y >= SCREEN_H:
                continue
            if not isinstance(row, list):
                continue
            for dx, cell in enumerate(row):
                x = crow_xi + dx
                if x < 0 or x >= SCREEN_W:
                    continue
                if cell != " ":
                    canvas[y][x] = cell

    command_lines: List[str] = []
    for idx, item in enumerate(command_items):
        if idx == command_cursor:
            command_lines.append(f"[ {item} ]")
        else:
            command_lines.append(f"  {item}  ")
    command_lines.append("")
    command_lines.append("\x1b[37mA:\x1b[0m Select   \x1b[37mS:\x1b[0m Back")

    draw_panel(
        canvas,
        x0=2,
        y0=1,
        width=56,
        height=7,
        title="Battle Log",
        lines=log_lines,
    )
    draw_panel(
        canvas,
        x0=60,
        y0=1,
        width=38,
        height=7,
        title="Opponents",
        lines=[
            "Baby Crow Lv 1",
            "HP: 24/24",
            "Status: Normal",
        ],
    )
    draw_panel(
        canvas,
        x0=2,
        y0=18,
        width=38,
        height=11,
        title="Party",
        lines=[
            "Hero      HP 40/40  MP 12/12",
            "Mushy     HP 22/22  MP 18/18",
            "",
            "Turn: Hero",
        ],
    )
    draw_panel(
        canvas,
        x0=42,
        y0=18,
        width=56,
        height=11,
        title="Commands",
        lines=command_lines,
    )

    progress = max(0.0, min(1.0, wipe_progress))
    if progress < 1.0:
        max_cover = SCREEN_W // 2
        cover = int(round(max_cover * (1.0 - progress)))
        left_end = cover
        right_start = SCREEN_W - cover
        for y in range(SCREEN_H):
            for x in range(left_end):
                canvas[y][x] = " "
            for x in range(right_start, SCREEN_W):
                canvas[y][x] = " "

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
    forest_lines, crow_meta, _actor_meta = build_forest_band(scenes, objects, colors, opponents)
    crow_y = float(crow_meta.get("start_y", -1)) if isinstance(crow_meta, dict) else -1.0
    crow_x = float(crow_meta.get("x", 0.0)) if isinstance(crow_meta, dict) else 0.0
    wipe_duration = 1.0
    wipe_started_at = time.monotonic()
    commands = ["Attack", "Spellbook", "Items", "Run"]
    command_cursor = 0
    log_lines = [
        "A wild Baby Crow appears!",
        "Use this scene as the battle layout template.",
    ]

    print(ANSI_HIDE_CURSOR + ANSI_CLEAR, end="", flush=True)
    try:
        last_tick = time.monotonic()
        while True:
            now = time.monotonic()
            dt = max(0.0, min(0.2, now - last_tick))
            last_tick = now
            wipe_progress = min(1.0, max(0.0, (now - wipe_started_at) / wipe_duration))
            wipe_done = wipe_progress >= 1.0

            for cloud in clouds:
                speed = float(cloud.get("speed", 1.0))
                cloud["x"] = float(cloud.get("x", 0.0)) - (speed * dt)
                w = int(cloud["template"]["width"])
                if cloud["x"] + w < 0:
                    cloud["x"] = SCREEN_W + (cloud["x"] + w)

            key = read_key_nonblocking()
            if key == "q":
                break

            if wipe_done and isinstance(crow_meta, dict) and crow_meta:
                target = float(crow_meta.get("target_y", 0.0))
                speed = float(crow_meta.get("speed", 8.0))
                start = float(crow_meta.get("start_y", -1.0))
                base_x = float(crow_meta.get("x", 0.0))
                crow_y = min(target, crow_y + (speed * dt))
                if crow_y < target:
                    span = max(1.0, target - start)
                    progress = max(0.0, min(1.0, (crow_y - start) / span))
                    cycles = 0.85
                    amplitude = 15.0 * ((1.0 - progress) ** 0.6)
                    phase = progress * math.pi * 2.0 * cycles
                    sway = math.sin(phase) * amplitude
                    crow_x = base_x + sway
                else:
                    crow_x = base_x

                if key in ("up", "w"):
                    command_cursor = (command_cursor - 1) % len(commands)
                elif key in ("down", "s"):
                    command_cursor = (command_cursor + 1) % len(commands)
                elif key == "a":
                    selected = commands[command_cursor]
                    log_lines = [
                        f"Selected command: {selected}",
                        "Battle execution flow not wired yet.",
                    ]

            frame = render(
                clouds=clouds,
                forest_lines=forest_lines,
                crow_meta=crow_meta,
                crow_x=crow_x,
                crow_y=crow_y,
                command_items=commands,
                command_cursor=command_cursor,
                log_lines=log_lines,
                wipe_progress=wipe_progress,
            )
            print(ANSI_HOME + frame, end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        print(ANSI_SHOW_CURSOR + ANSI_RESET)


if __name__ == "__main__":
    main()

