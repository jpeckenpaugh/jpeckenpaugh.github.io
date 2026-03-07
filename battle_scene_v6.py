import os
import re
import time
import random
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
    SKY_H,
    ansi_line_to_cells,
    build_forest_band,
    cloud_templates,
    load_json,
    read_key_nonblocking,
    spawn_clouds,
)


@dataclass(frozen=True)
class LayoutZone:
    name: str
    x: int
    y: int
    width: int
    height: int

    @property
    def x1(self) -> int:
        return self.x + max(0, self.width) - 1

    @property
    def y1(self) -> int:
        return self.y + max(0, self.height) - 1


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _is_ground_row(line: str) -> bool:
    visible = _strip_ansi(line)
    chars = [ch for ch in visible if ch != " "]
    if not chars:
        return False
    allowed = set("~oO.")
    return all(ch in allowed for ch in chars)


def _expand_ground_rows(forest_lines: List[str], ground_count: int = 14) -> List[str]:
    rows = list(forest_lines[:SKY_H])
    while len(rows) < SKY_H:
        rows.append(" " * SCREEN_W)
    ground_start = len(rows)
    while ground_start > 0 and _is_ground_row(rows[ground_start - 1]):
        ground_start -= 1
    top_rows = rows[:ground_start] if ground_start > 0 else []
    ground_pool = rows[ground_start:] if ground_start < len(rows) else [rows[-1]]
    if not ground_pool:
        ground_pool = [rows[-1]]
    # Keep full tree/canopy stack so crowns can rise into the sky when bottom-anchored.
    expanded = list(top_rows)
    rng = random.Random(9051701)
    seen_patterns: set[str] = set()
    for i in range(max(0, ground_count)):
        base_row = ground_pool[i % len(ground_pool)]
        row = _randomize_ground_row(base_row, rng, rock_scale=0.5)
        pattern = _strip_ansi(row)
        attempts = 0
        while pattern in seen_patterns and attempts < 8:
            row = _randomize_ground_row(base_row, rng, rock_scale=0.5)
            pattern = _strip_ansi(row)
            attempts += 1
        seen_patterns.add(pattern)
        expanded.append(row)
    return expanded[:SCREEN_H]


def _replace_cell_glyph(cell: str, glyph: str) -> str:
    m = re.match(r"^(\x1b\[[0-9;]*m).(\x1b\[0m)$", cell)
    if m:
        return f"{m.group(1)}{glyph}{m.group(2)}"
    return glyph


def _randomize_ground_row(base_line: str, rng: random.Random, rock_scale: float = 0.5) -> str:
    cells = ansi_line_to_cells(base_line, SCREEN_W)
    ground_indices: List[int] = []
    original_rock_count = 0
    for x, cell in enumerate(cells):
        visible = _strip_ansi(cell)
        if visible in ("~", "o", "O", "."):
            ground_indices.append(x)
            cells[x] = _replace_cell_glyph(cell, "~")
            if visible in ("o", "O", "."):
                original_rock_count += 1
    if not ground_indices:
        return "".join(cells)

    target_rocks = max(0, min(len(ground_indices), int(round(original_rock_count * max(0.0, rock_scale)))))
    if target_rocks > 0:
        chosen = rng.sample(ground_indices, target_rocks)
        for x in chosen:
            rock = rng.choice(["o", "O", "."])
            cells[x] = _replace_cell_glyph(cells[x], rock)
    return "".join(cells)


def _make_zone(name: str, x: int, y: int, width: int, height: int) -> LayoutZone:
    x = max(0, min(SCREEN_W, x))
    y = max(0, min(SCREEN_H, y))
    width = max(0, min(width, SCREEN_W - x))
    height = max(0, min(height, SCREEN_H - y))
    return LayoutZone(name=name, x=x, y=y, width=width, height=height)


def build_scene_zones(forest_lines: List[str], ground_rows: int = 11) -> Dict[str, LayoutZone]:
    forest_height = max(0, min(SCREEN_H, len(forest_lines)))
    forest_top = SCREEN_H - forest_height
    ground_height = max(0, min(ground_rows, forest_height))
    ground_top = forest_top + max(0, forest_height - ground_height)
    tree_height = max(0, ground_top - forest_top)

    enemy_w = SCREEN_W // 3
    ally_w = SCREEN_W // 3
    lane_w = SCREEN_W - enemy_w - ally_w
    actor_h = min(8, max(4, ground_height))
    actor_top = max(0, ground_top - actor_h)

    return {
        "sky": _make_zone("sky", 0, 0, SCREEN_W, SKY_H),
        "forest": _make_zone("forest", 0, forest_top, SCREEN_W, forest_height),
        "treeline": _make_zone("treeline", 0, forest_top, SCREEN_W, tree_height),
        "ground": _make_zone("ground", 0, ground_top, SCREEN_W, ground_height),
        "enemy_side": _make_zone("enemy_side", 0, actor_top, enemy_w, actor_h),
        "center_lane": _make_zone("center_lane", enemy_w, actor_top, lane_w, actor_h),
        "ally_side": _make_zone("ally_side", enemy_w + lane_w, actor_top, ally_w, actor_h),
    }


def _overlay_zone_guides(canvas: List[List[str]], zones: Dict[str, LayoutZone]) -> None:
    colors = [
        "\x1b[38;2;255;230;120m",
        "\x1b[38;2;135;210;255m",
        "\x1b[38;2;170;255;150m",
        "\x1b[38;2;255;170;170m",
        "\x1b[38;2;255;200;140m",
        "\x1b[38;2;220;160;255m",
        "\x1b[38;2;160;255;240m",
    ]
    for idx, zone in enumerate(zones.values()):
        if zone.width <= 0 or zone.height <= 0:
            continue
        color = colors[idx % len(colors)]
        x0, y0 = zone.x, zone.y
        x1, y1 = zone.x1, zone.y1
        for x in range(x0, x1 + 1):
            canvas[y0][x] = f"{color}-{ANSI_RESET}"
            canvas[y1][x] = f"{color}-{ANSI_RESET}"
        for y in range(y0, y1 + 1):
            canvas[y][x0] = f"{color}|{ANSI_RESET}"
            canvas[y][x1] = f"{color}|{ANSI_RESET}"
        canvas[y0][x0] = f"{color}+{ANSI_RESET}"
        canvas[y0][x1] = f"{color}+{ANSI_RESET}"
        canvas[y1][x0] = f"{color}+{ANSI_RESET}"
        canvas[y1][x1] = f"{color}+{ANSI_RESET}"
        label = f"[{zone.name}]"
        lx = min(x1 - 1, x0 + 2)
        for i, ch in enumerate(label):
            x = lx + i
            if x >= x1:
                break
            canvas[y0][x] = f"{color}{ch}{ANSI_RESET}"


def render(
    clouds: List[dict],
    forest_lines: List[str],
    zones: Dict[str, LayoutZone],
    ground_rows: int = 11,
    wipe_progress: float = 1.0,
    show_zone_guides: bool = False,
) -> str:
    canvas = [[" " for _ in range(SCREEN_W)] for _ in range(SCREEN_H)]

    # Sky clouds.
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
                if 0 <= x < SCREEN_W and cell != " ":
                    canvas[y][x] = cell

    # Forest band bottom-aligned to viewport (last ground row at screen row 30).
    forest_origin_y = SCREEN_H - len(forest_lines)
    for i, src in enumerate(forest_lines):
        y = forest_origin_y + i
        if 0 <= y < SCREEN_H:
            cells = ansi_line_to_cells(src, SCREEN_W)
            for x, cell in enumerate(cells):
                if cell != " ":
                    canvas[y][x] = cell

    # Vertical wipe-in from bottom: visible area grows upward.
    progress = max(0.0, min(1.0, wipe_progress))
    if progress < 1.0:
        visible_rows = int(round(SCREEN_H * progress))
        top_hidden_rows = max(0, SCREEN_H - visible_rows)
        for y in range(top_hidden_rows):
            for x in range(SCREEN_W):
                canvas[y][x] = " "

    if show_zone_guides:
        _overlay_zone_guides(canvas, zones)

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
    ground_rows = 11
    forest_lines, _crow_meta, _actor_meta = build_forest_band(scenes, objects, colors, opponents)
    forest_lines = _expand_ground_rows(forest_lines, ground_count=ground_rows)
    zones = build_scene_zones(forest_lines, ground_rows=ground_rows)
    wipe_duration = 1.0
    wipe_started_at = time.monotonic()
    show_zone_guides = True

    print(ANSI_HIDE_CURSOR + ANSI_CLEAR, end="", flush=True)
    try:
        last_tick = time.monotonic()
        while True:
            now = time.monotonic()
            dt = max(0.0, min(0.2, now - last_tick))
            last_tick = now
            wipe_progress = min(1.0, max(0.0, (now - wipe_started_at) / wipe_duration))
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

            frame = render(
                clouds=clouds,
                forest_lines=forest_lines,
                zones=zones,
                ground_rows=ground_rows,
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

