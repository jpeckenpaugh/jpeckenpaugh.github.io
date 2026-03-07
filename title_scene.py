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


def render(clouds: List[dict], panorama_lines: List[str]) -> str:
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

    # Bottom half panorama (latest title panorama output).
    for y in range(SKY_H):
        src = panorama_lines[y] if y < len(panorama_lines) else ""
        cells = ansi_line_to_cells(src, SCREEN_W)
        canvas[SKY_H + y] = cells

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
            frame = render(clouds, pano_lines)
            print(ANSI_HOME + frame, end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        print(ANSI_SHOW_CURSOR + ANSI_RESET)


if __name__ == "__main__":
    main()

