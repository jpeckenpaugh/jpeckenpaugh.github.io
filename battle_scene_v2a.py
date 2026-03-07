import os
import re
import time
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
    for i in range(max(0, ground_count)):
        expanded.append(ground_pool[i % len(ground_pool)])
    return expanded[:SCREEN_H]


def _hex_to_rgb(hex_value: str) -> tuple[int, int, int]:
    value = hex_value.strip().lstrip("#")
    if len(value) != 6:
        return (255, 255, 255)
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _build_color_map(colors_data: Dict[str, object]) -> Dict[str, str]:
    mapped: Dict[str, str] = {}
    for key, payload in colors_data.items():
        if not isinstance(key, str) or len(key) != 1:
            continue
        if not isinstance(payload, dict):
            continue
        hex_value = payload.get("hex")
        if not isinstance(hex_value, str):
            continue
        r, g, b = _hex_to_rgb(hex_value)
        mapped[key] = f"\x1b[38;2;{r};{g};{b}m"
    return mapped


def _colorized_rows(art: object, mask: object, color_codes: Dict[str, str]) -> List[List[str]]:
    if not isinstance(art, list) or not art:
        return []
    if not isinstance(mask, list):
        mask = []
    width = max((len(str(line)) for line in art), default=0)
    rows: List[List[str]] = []
    for y, raw in enumerate(art):
        line = str(raw).ljust(width)
        mask_line = str(mask[y]) if y < len(mask) else ""
        out: List[str] = []
        for x, ch in enumerate(line):
            if ch == " ":
                out.append(" ")
                continue
            key = mask_line[x] if x < len(mask_line) else ""
            code = color_codes.get(key, "")
            out.append(f"{code}{ch}{ANSI_RESET}" if code else ch)
        rows.append(out)
    return rows


def _sprite_bounds(rows: List[List[str]]) -> tuple[int, int]:
    min_y = len(rows)
    max_y = -1
    for y, row in enumerate(rows):
        if any(cell != " " for cell in row):
            min_y = min(min_y, y)
            max_y = max(max_y, y)
    if max_y < 0:
        return (0, 0)
    return (min_y, max_y)


def _overlay_sprite_on_forest(forest_lines: List[str], rows: List[List[str]], x0: int, y0: int) -> None:
    for dy, row in enumerate(rows):
        y = y0 + dy
        if y < 0 or y >= len(forest_lines):
            continue
        cells = ansi_line_to_cells(forest_lines[y], SCREEN_W)
        for dx, cell in enumerate(row):
            x = x0 + dx
            if x < 0 or x >= SCREEN_W:
                continue
            if cell != " ":
                cells[x] = cell
        forest_lines[y] = "".join(cells)


def _clear_sprite_shape_on_forest(
    forest_lines: List[str],
    rows: List[List[str]],
    x0: int,
    y0: int,
    skip_ground: bool = True,
    y_min: int | None = None,
    y_max: int | None = None,
) -> None:
    for dy, row in enumerate(rows):
        y = y0 + dy
        if y < 0 or y >= len(forest_lines):
            continue
        if y_min is not None and y < y_min:
            continue
        if y_max is not None and y > y_max:
            continue
        if skip_ground and _is_ground_row(forest_lines[y]):
            continue
        cells = ansi_line_to_cells(forest_lines[y], SCREEN_W)
        for dx, cell in enumerate(row):
            x = x0 + dx
            if x < 0 or x >= SCREEN_W:
                continue
            if cell != " ":
                cells[x] = " "
        forest_lines[y] = "".join(cells)


def _center_gap_width(line: str, center_x: int) -> int:
    visible = _strip_ansi(line)
    if not (0 <= center_x < len(visible)):
        return 0
    if visible[center_x] != " ":
        return 0
    left = center_x
    while left - 1 >= 0 and visible[left - 1] == " ":
        left -= 1
    right = center_x
    while right + 1 < len(visible) and visible[right + 1] == " ":
        right += 1
    return right - left + 1


def _push_tree_line_apart(forest_lines: List[str], row_idx: int, center_x: int, shift: int) -> None:
    if row_idx < 0 or row_idx >= len(forest_lines):
        return
    move = max(0, shift)
    if move <= 0:
        return
    cells = ansi_line_to_cells(forest_lines[row_idx], SCREEN_W)
    widened = [" " for _ in range(SCREEN_W)]
    split = max(0, min(SCREEN_W, center_x))
    for x in range(split):
        nx = x - move
        if 0 <= nx < SCREEN_W and cells[x] != " ":
            widened[nx] = cells[x]
    for x in range(split, SCREEN_W):
        nx = x + move
        if 0 <= nx < SCREEN_W and cells[x] != " ":
            widened[nx] = cells[x]
    forest_lines[row_idx] = "".join(widened)


def render(clouds: List[dict], forest_lines: List[str], ground_rows: int = 9, wipe_progress: float = 1.0) -> str:
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
    ground_rows = 9
    forest_lines, _crow_meta, actor_meta = build_forest_band(scenes, objects, colors, opponents)
    forest_lines = _expand_ground_rows(forest_lines, ground_count=ground_rows)
    color_codes = _build_color_map(colors)
    base_opponents = opponents.get("base_opponents", {}) if isinstance(opponents, dict) else {}
    mushy_data = base_opponents.get("mushroom_baby", {}) if isinstance(base_opponents, dict) else {}
    crow_data = base_opponents.get("baby_crow", {}) if isinstance(base_opponents, dict) else {}

    mushy_rows = _colorized_rows(
        mushy_data.get("art", []) if isinstance(mushy_data, dict) else [],
        mushy_data.get("color_map", []) if isinstance(mushy_data, dict) else [],
        color_codes,
    )
    crow_rows = _colorized_rows(
        crow_data.get("art", []) if isinstance(crow_data, dict) else [],
        crow_data.get("color_map", []) if isinstance(crow_data, dict) else [],
        color_codes,
    )

    # Swap center Mushy out for Baby Crow.
    mushy_center_x = int(actor_meta.get("mushy", {}).get("x", SCREEN_W // 2)) if isinstance(actor_meta, dict) else SCREEN_W // 2
    mushy_local_y = int(actor_meta.get("mushy", {}).get("y", SKY_H + 6)) - SKY_H if isinstance(actor_meta, dict) else 6
    mushy_w = max((len(r) for r in mushy_rows), default=0)
    crow_w = max((len(r) for r in crow_rows), default=0)
    mushy_x0 = max(0, mushy_center_x - (mushy_w // 2))
    crow_x0 = max(0, mushy_center_x - (crow_w // 2))
    _mushy_top, mushy_bottom = _sprite_bounds(mushy_rows)
    _crow_top, crow_bottom = _sprite_bounds(crow_rows)
    mushy_foot_local = mushy_local_y + mushy_bottom
    crow_y0 = mushy_foot_local - crow_bottom

    # Tree-line spacing rule: ensure crow + 2 spaces on both sides by pushing trees apart.
    tree_line_idx = max(0, len(forest_lines) - ground_rows - 1)
    target_gap = crow_w + 4
    current_gap = _center_gap_width(forest_lines[tree_line_idx], mushy_center_x)
    needed = max(0, target_gap - current_gap)
    _push_tree_line_apart(forest_lines, tree_line_idx, mushy_center_x, (needed + 1) // 2)

    _overlay_sprite_on_forest(forest_lines, crow_rows, crow_x0, crow_y0)
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

