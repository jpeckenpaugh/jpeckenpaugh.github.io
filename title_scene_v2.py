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

CLOUD_RGB_PALETTE = [
    (255, 255, 255),
    (236, 240, 246),
    (214, 222, 235),
    (198, 216, 246),
    (178, 204, 242),
]


def logo_gradient_code(x: int, y: int, width: int, height: int) -> str:
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


def frame_gradient_code(x: int, y: int) -> str:
    return logo_gradient_code(x, y, SCREEN_W, SCREEN_H)


def subtitle_text() -> str:
    return "*-----<{([  AI World Engine  ])}>-----*"


def subtitle_cells(y: int, start_x: int) -> List[str]:
    text = subtitle_text()
    left = "*-----<{([  "
    mid = "AI World Engine"
    out: List[str] = []
    for i, ch in enumerate(text):
        if ch == " ":
            out.append(" ")
        elif len(left) <= i < len(left) + len(mid):
            out.append(f"\x1b[38;2;255;255;255m{ch}{ANSI_RESET}")
        else:
            out.append(f"{frame_gradient_code(start_x + i, y)}{ch}{ANSI_RESET}")
    return out


def strip_ansi(text: str) -> str:
    out: List[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\x1b" and i + 1 < len(text) and text[i + 1] == "[":
            j = i + 2
            while j < len(text) and text[j] != "m":
                j += 1
            if j < len(text):
                i = j + 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def colorize_menu_line(text: str, y: int, start_x: int) -> str:
    visible_text = strip_ansi(text)
    width = len(visible_text)
    is_top_bottom = width >= 2 and visible_text[0] == "o" and visible_text[-1] == "o"
    out: List[str] = []
    i = 0
    visible_idx = 0
    style_active = False
    while i < len(text):
        ch = text[i]
        if ch == "\x1b" and i + 1 < len(text) and text[i + 1] == "[":
            j = i + 2
            while j < len(text) and text[j] != "m":
                j += 1
            if j < len(text):
                seq = text[i : j + 1]
                out.append(seq)
                style_active = seq != ANSI_RESET
                i = j + 1
                continue
        if ch == " ":
            out.append(" ")
        else:
            is_side_border = visible_idx == 0 or visible_idx == width - 1
            is_top_bottom_border = is_top_bottom and ch in ("o", "-")
            is_frame = is_side_border or is_top_bottom_border
            if style_active and not is_frame:
                out.append(ch)
            else:
                code = frame_gradient_code(start_x + visible_idx, y) if is_frame else "\x1b[38;2;255;255;255m"
                out.append(f"{code}{ch}{ANSI_RESET}")
        visible_idx += 1
        i += 1
    return "".join(out)


def menu_button_row(inner: int) -> str:
    accept = "\x1b[30;42m[ A / Accept ]\x1b[0m"
    cancel = "\x1b[90m[ S / Cancel ]\x1b[0m"
    spacer = " " * 5
    body = accept + spacer + cancel
    visible = len(strip_ansi(body))
    pad_left = max(0, (inner - visible) // 2)
    pad_right = max(0, inner - visible - pad_left)
    return (" " * pad_left) + body + (" " * pad_right)


def menu_box_lines() -> List[str]:
    width = 46
    inner = width - 2
    options = ["Continue", "New Game", "Asset Explorer", "Quit"]
    lines: List[str] = []
    lines.append("o" + ("-" * inner) + "o")
    lines.append("|" + (" " * inner) + "|")
    for idx, label in enumerate(options):
        if idx == 0:
            text = f" [ {label} ]"
        else:
            text = f"   {label}"
        lines.append("|" + text.ljust(inner)[:inner] + "|")
    lines.append("|" + (" " * inner) + "|")
    lines.append("|" + menu_button_row(inner) + "|")
    lines.append("|" + (" " * inner) + "|")  # blank line after A/S button row
    lines.append("o" + ("-" * inner) + "o")
    return lines


def overlay_menu(canvas: List[List[str]], start_y: int) -> None:
    lines = menu_box_lines()
    for idx, line in enumerate(lines):
        y = start_y + idx
        if y < 0 or y >= SCREEN_H:
            continue
        visible_len = len(strip_ansi(line))
        start_x = max(0, (SCREEN_W - visible_len) // 2)
        styled = colorize_menu_line(line, y, start_x)
        cells = ansi_line_to_cells(styled, visible_len)
        for x, cell in enumerate(cells):
            px = start_x + x
            if 0 <= px < SCREEN_W:
                canvas[y][px] = cell


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
        templates.append(
            {
                "id": object_id,
                "width": width,
                "height": len(rows),
                "rows": rows,
                "size": (
                    "large"
                    if "_large_" in object_id
                    else ("medium" if "_medium_" in object_id else "small")
                ),
            }
        )
    return templates


def logo_cells_from_objects(objects: Dict[str, object]) -> dict:
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
                # Opaque empty cell: blocks cloud layer behind logo.
                row.append(f"{ANSI_RESET} ")
            else:
                row.append(f"{logo_gradient_code(x, y, width, height)}{ch}{ANSI_RESET}")
        rows.append(row)
    return {"width": width, "height": height, "rows": rows}


def speed_for_cloud(size: str, y: int, rng: random.Random) -> float:
    size_weight = {"large": 0.72, "medium": 1.0, "small": 1.28}.get(size, 1.0)
    y_norm = max(0.0, min(1.0, y / max(1, SKY_H - 1)))
    height_weight = 0.72 + (0.62 * y_norm)
    variance = 1.0 + (rng.random() * 3.0)  # 100% - 400%
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
        speed = speed_for_cloud(str(template.get("size", "medium")), y, rng)
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


def render(clouds: List[dict], panorama_lines: List[str], logo: dict) -> str:
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

    # Stationary Lokarta logo in front of clouds.
    logo_rows = logo.get("rows", [])
    logo_w = int(logo.get("width", 0))
    logo_h = int(logo.get("height", 0))
    if isinstance(logo_rows, list) and logo_w > 0 and logo_h > 0:
        x0 = max(0, (SCREEN_W - logo_w) // 2)
        y0 = 1
        for dy, row in enumerate(logo_rows):
            y = y0 + dy
            if y < 0 or y >= SKY_H:
                continue
            if not isinstance(row, list):
                continue
            for dx, cell in enumerate(row):
                x = x0 + dx
                if x < 0 or x >= SCREEN_W:
                    continue
                if cell != " ":
                    canvas[y][x] = cell
        # Subtitle directly below logo.
        sub_y = y0 + logo_h + 1
        sub = subtitle_text()
        sub_x = max(0, (SCREEN_W - len(sub)) // 2)
        if 0 <= sub_y < SKY_H:
            cells = subtitle_cells(sub_y, sub_x)
            for i, cell in enumerate(cells):
                x = sub_x + i
                if 0 <= x < SCREEN_W and cell != " ":
                    canvas[sub_y][x] = cell

    # Bottom half panorama (latest title panorama output).
    for y in range(SKY_H):
        src = panorama_lines[y] if y < len(panorama_lines) else ""
        cells = ansi_line_to_cells(src, SCREEN_W)
        canvas[SKY_H + y] = cells

    # Title menu/UI over logo + panorama (opaque frame/text).
    overlay_menu(canvas, start_y=9)

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
    logo = logo_cells_from_objects(objects)

    clouds = spawn_clouds(templates, count=10)
    panorama = TitlePanorama(
        viewport_width=SCREEN_W,
        height=15,
        speed=2.0,
        forest_width_scale=0.5,
        scenes_data=scenes,
        objects_data=objects,
        colors_data=colors,
        opponents_data=opponents,
    )

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
            pano_lines = panorama.viewport()
            frame = render(clouds, pano_lines, logo)
            print(ANSI_HOME + frame, end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        print(ANSI_SHOW_CURSOR + ANSI_RESET)


if __name__ == "__main__":
    main()

