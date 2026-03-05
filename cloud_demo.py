import json
import os
import random
import time
from typing import Dict, List


SCREEN_W = 100
SCREEN_H = 30
SKY_H = 15
ANSI_RESET = "\x1b[0m"
ANSI_HIDE_CURSOR = "\x1b[?25l"
ANSI_SHOW_CURSOR = "\x1b[?25h"
ANSI_HOME = "\x1b[H"
ANSI_CLEAR = "\x1b[2J"

# Cloud-specific tones: whites, light grays, and sky blues.
CLOUD_RGB_PALETTE = [
    (255, 255, 255),  # white
    (236, 240, 246),  # very light gray
    (214, 222, 235),  # light gray-blue
    (198, 216, 246),  # pale sky blue
    (178, 204, 242),  # sky blue
]


def hex_to_ansi_fg(hex_code: str) -> str:
    value = str(hex_code or "").strip().lstrip("#")
    if len(value) != 6:
        return ""
    try:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
    except ValueError:
        return ""
    return f"\x1b[38;2;{r};{g};{b}m"


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


def load_json(path: str) -> object:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def cloud_templates(objects: Dict[str, object], colors: Dict[str, object]) -> List[dict]:
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
    # Parallax weighting:
    # - larger + higher => slower (farther)
    # - smaller + lower => faster (closer)
    size_weight = {"large": 0.72, "medium": 1.0, "small": 1.28}.get(size, 1.0)
    y_norm = max(0.0, min(1.0, y / max(1, SKY_H - 1)))
    height_weight = 0.72 + (0.62 * y_norm)  # higher sky is slower, lower sky is faster
    variance = 0.9 + (rng.random() * 0.2)
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
        # Start scattered across the visible sky (with slight edge clipping allowed).
        x = rng.randint(-max(1, w // 2), SCREEN_W - 1)
        speed = speed_for_cloud(str(template.get("size", "medium")), y, rng)
        clouds.append({"template": template, "x": float(x), "y": y, "speed": speed})
    return clouds


def render(clouds: List[dict]) -> str:
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

    # Sky divider + simple ground for orientation.
    for x in range(SCREEN_W):
        canvas[SKY_H][x] = "-"
    for y in range(SKY_H + 1, SCREEN_H):
        for x in range(SCREEN_W):
            canvas[y][x] = "."

    return "\n".join("".join(row) for row in canvas)


def main() -> None:
    base = os.getcwd()
    objects_path = os.path.join(base, "legecay", "data", "objects.json")
    colors_path = os.path.join(base, "legecay", "data", "colors.json")
    objects = load_json(objects_path)
    colors = load_json(colors_path)
    if not isinstance(objects, dict):
        raise RuntimeError("objects.json is not a JSON object")
    if not isinstance(colors, dict):
        raise RuntimeError("colors.json is not a JSON object")

    templates = cloud_templates(objects, colors)
    if not templates:
        raise RuntimeError("No cloud_* objects found in objects.json")

    clouds = spawn_clouds(templates, count=10)

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
                # Wrap-around: same cloud re-enters on right when fully off left.
                if cloud["x"] + w < 0:
                    cloud["x"] = SCREEN_W + (cloud["x"] + w)
            frame = render(clouds)
            print(ANSI_HOME + frame, end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        print(ANSI_SHOW_CURSOR + ANSI_RESET)


if __name__ == "__main__":
    main()
