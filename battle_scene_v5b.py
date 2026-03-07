import os
import re
import time
import random
from typing import List

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


def _mushy_art_bounds(art_rows: object) -> tuple[int, int, int]:
    if not isinstance(art_rows, list) or not art_rows:
        return (0, 0, 0)
    width = max((len(str(line)) for line in art_rows), default=0)
    top = len(art_rows)
    bottom = -1
    for y, raw in enumerate(art_rows):
        line = str(raw).ljust(width)
        if any(ch != " " for ch in line):
            top = min(top, y)
            bottom = max(bottom, y)
    if bottom < 0:
        return (width, 0, 0)
    return (width, top, bottom)


def _apply_mushy_tree_margin(
    forest_lines: List[str],
    actor_meta: object,
    opponents_data: object,
    mushy_tree_margin: int,
) -> None:
    if not isinstance(actor_meta, dict):
        return
    mush_meta = actor_meta.get("mushy", {})
    if not isinstance(mush_meta, dict):
        return
    base_opponents = opponents_data.get("base_opponents", {}) if isinstance(opponents_data, dict) else {}
    mush_data = base_opponents.get("mushroom_baby", {}) if isinstance(base_opponents, dict) else {}
    mush_art = mush_data.get("art", []) if isinstance(mush_data, dict) else []
    mush_w, mush_top, mush_bottom = _mushy_art_bounds(mush_art)
    if mush_w <= 0:
        return

    center_x = int(mush_meta.get("x", SCREEN_W // 2))
    mush_top_screen = int(mush_meta.get("y", SKY_H + 5))
    forest_origin_y = SCREEN_H - len(forest_lines)
    top_local = mush_top_screen - forest_origin_y
    bottom_local = top_local + max(0, mush_bottom - mush_top)
    left = max(0, center_x - (mush_w // 2) - max(0, int(mushy_tree_margin)))
    right = min(SCREEN_W - 1, left + mush_w + (2 * max(0, int(mushy_tree_margin))) - 1)

    for y in range(top_local, bottom_local + 1):
        if y < 0 or y >= len(forest_lines):
            continue
        if _is_ground_row(forest_lines[y]):
            continue
        cells = ansi_line_to_cells(forest_lines[y], SCREEN_W)
        for x in range(left, right + 1):
            cells[x] = " "
        forest_lines[y] = "".join(cells)


def render(clouds: List[dict], forest_lines: List[str], ground_rows: int = 11, wipe_progress: float = 1.0) -> str:
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
    forest_lines, _crow_meta, actor_meta = build_forest_band(scenes, objects, colors, opponents)
    forest_lines = _expand_ground_rows(forest_lines, ground_count=ground_rows)
    mushy_tree_margin = 3  # margin: blank columns kept on left/right of Mushy before trees.
    _apply_mushy_tree_margin(forest_lines, actor_meta, opponents, mushy_tree_margin)
    wipe_duration = 1.0
    wipe_started_at = time.monotonic()

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

            frame = render(
                clouds=clouds,
                forest_lines=forest_lines,
                ground_rows=ground_rows,
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

