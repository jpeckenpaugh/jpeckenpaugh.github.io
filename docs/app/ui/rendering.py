"""Rendering and animation helpers for ASCII UI frames."""

import colorsys
import json
import os
import random
import sys
import time
import textwrap
import zlib
from dataclasses import replace
from typing import List, Optional

from app.commands.scene_commands import format_commands, scene_commands
from app.models import Frame, Player, Opponent
from app.ui.ansi import ANSI, color
from app.ui.constants import (
    NARRATIVE_INDENT,
    OPPONENT_ART_WIDTH,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    STAT_LINES,
)
from app.ui.layout import center_ansi, center_crop_ansi, format_action_lines, pad_or_trim_ansi, pad_ansi, strip_ansi
from app.combat import battle_action_delay


COLOR_BY_NAME = {
    "white": ANSI.FG_WHITE,
    "cyan": ANSI.FG_CYAN,
    "green": ANSI.FG_GREEN,
    "yellow": ANSI.FG_YELLOW,
    "red": ANSI.FG_RED,
    "blue": ANSI.FG_BLUE,
}

_SESSION_RANDOM_SEED = random.SystemRandom().randint(0, 2**31 - 1)
_MASK_DIGITS = set("0123456789")
_JITTER_TICK_SECONDS = 0.6


def gradient_rgb(x: int, y: int, width: int, height: int) -> tuple[int, int, int]:
    # Diagonal gradient: light silver -> bright blue -> dark silver
    if width <= 1 and height <= 1:
        return (192, 192, 192)
    denom = max(1, (width - 1) + (height - 1))
    t = (x + y) / denom
    if t <= 0.5:
        t2 = t / 0.5
        start = (192, 192, 192)
        end = (77, 77, 255)
    else:
        t2 = (t - 0.5) / 0.5
        start = (77, 77, 255)
        end = (96, 96, 96)
    r = int(round(start[0] + (end[0] - start[0]) * t2))
    g = int(round(start[1] + (end[1] - start[1]) * t2))
    b = int(round(start[2] + (end[2] - start[2]) * t2))
    return (r, g, b)


def _mix64(value: int) -> int:
    mask = 0xFFFFFFFFFFFFFFFF
    value = (value + 0x9E3779B97F4A7C15) & mask
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
    return value ^ (value >> 31)


def _unit_from(value: int) -> float:
    return (_mix64(value) >> 11) / float(1 << 53)


def _random_seed_base(label: str) -> int:
    payload = f"{_SESSION_RANDOM_SEED}:{label}".encode("utf-8")
    return zlib.crc32(payload) & 0xFFFFFFFF


def _random_band_ranges(band: int, random_config: dict) -> tuple[float, float, float, float]:
    bands = random_config.get("bands", {}) if isinstance(random_config, dict) else {}
    band_entry = bands.get(str(band), {}) if isinstance(bands, dict) else {}
    s_min = float(random_config.get("s_min", 0.4))
    s_max = float(random_config.get("s_max", 0.9))
    if isinstance(band_entry, dict):
        l_min = float(band_entry.get("l_min", 0.2))
        l_max = float(band_entry.get("l_max", 0.8))
        s_min = float(band_entry.get("s_min", s_min))
        s_max = float(band_entry.get("s_max", s_max))
    else:
        bright_min = float(random_config.get("l_bright_min", 0.75))
        bright_max = float(random_config.get("l_bright_max", 0.95))
        dark_min = float(random_config.get("l_dark_min", 0.18))
        dark_max = float(random_config.get("l_dark_max", 0.45))
        rank = band % 5
        t = rank / 4.0 if rank else 0.0
        l_min = bright_min + (dark_min - bright_min) * t
        l_max = bright_max + (dark_max - bright_max) * t
    l_min = max(0.0, min(1.0, l_min))
    l_max = max(l_min, min(1.0, l_max))
    s_min = max(0.0, min(1.0, s_min))
    s_max = max(s_min, min(1.0, s_max))
    return l_min, l_max, s_min, s_max


def _random_color_code(mask_char: str, x: int, y: int, seed_base: int, random_config: dict) -> str:
    if mask_char not in _MASK_DIGITS or not isinstance(random_config, dict) or not random_config:
        return ""
    band = int(mask_char)
    l_min, l_max, s_min, s_max = _random_band_ranges(band, random_config)
    if band < 5:
        seed = (seed_base << 1) ^ (band * 0x9E3779B1) ^ (x * 0x85EBCA77) ^ (y * 0xC2B2AE3D)
    else:
        seed = (_SESSION_RANDOM_SEED << 1) ^ (band * 0x9E3779B1)
    h = _unit_from(seed)
    s = s_min + (_unit_from(seed + 1) * (s_max - s_min))
    l = l_min + (_unit_from(seed + 2) * (l_max - l_min))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return f"\033[38;2;{int(r * 255)};{int(g * 255)};{int(b * 255)}m"


def _hex_to_rgb(hex_code: str) -> Optional[tuple[int, int, int]]:
    value = hex_code.lstrip("#")
    if len(value) != 6:
        return None
    try:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
    except ValueError:
        return None
    return r, g, b


def _jitter_color_code(
    base_rgb: tuple[int, int, int],
    jitter: float,
    seed: int
) -> str:
    if jitter <= 0:
        r, g, b = base_rgb
        return f"\033[38;2;{r};{g};{b}m"
    r, g, b = base_rgb
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    delta = (_unit_from(seed) * 2.0 - 1.0) * jitter
    l = max(0.0, min(1.0, l + delta))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return f"\033[38;2;{int(r * 255)};{int(g * 255)};{int(b * 255)}m"


def mirror_line(line: str) -> str:
    swaps = str.maketrans({
        "/": "\\",
        "\\": "/",
        "(": ")",
        ")": "(",
        "<": ">",
        ">": "<",
        "[": "]",
        "]": "[",
        "{": "}",
        "}": "{",
    })
    return line[::-1].translate(swaps)


def render_venue_art(venue: dict, npc: dict, color_map_override: Optional[dict] = None) -> tuple[List[str], str]:
    art_color = COLOR_BY_NAME.get(venue.get("color", "white").lower(), ANSI.FG_WHITE)
    npc_art = npc.get("art", [])
    npc_color = COLOR_BY_NAME.get(npc.get("color", "white").lower(), ANSI.FG_WHITE)
    gap_width = int(venue.get("gap_width", 0))
    left = venue.get("left", [])
    right = venue.get("right", [])
    top = venue.get("top")
    top_color = venue.get("top_color", "")
    left_color = venue.get("left_color", [])
    right_color = venue.get("right_color", [])
    color_map = {}
    if isinstance(color_map_override, dict):
        color_map.update(color_map_override)
    venue_color_map = venue.get("color_map")
    if isinstance(venue_color_map, dict):
        color_map.update(venue_color_map)
    random_config = color_map.get("random", {}) if isinstance(color_map.get("random"), dict) else {}
    venue_seed_base = _random_seed_base(f"venue:{venue.get('name', '')}")

    def truecolor(code: str) -> str:
        value = code.lstrip("#")
        if len(value) != 6:
            return ""
        try:
            r = int(value[0:2], 16)
            g = int(value[2:4], 16)
            b = int(value[4:6], 16)
        except ValueError:
            return ""
        return f"\033[38;2;{r};{g};{b}m"

    color_by_key = {}
    gradient_keys = set()
    color_rgb_by_key = {}
    for key, entry in color_map.items():
        if key == "random" or key in _MASK_DIGITS:
            continue
        if isinstance(entry, dict):
            hex_code = entry.get("hex", "") if isinstance(entry.get("hex"), str) else ""
            name = entry.get("name", "") if isinstance(entry.get("name"), str) else ""
        elif isinstance(entry, str):
            hex_code = ""
            name = entry
        else:
            continue
        name = name.strip()
        hex_code = hex_code.strip()
        if name.lower() == "gradient":
            gradient_keys.add(key)
            continue
        if not hex_code:
            hex_start = name.find("#")
            hex_code = name[hex_start:] if hex_start != -1 else ""
        if hex_code:
            code = truecolor(hex_code)
            if code:
                color_by_key[key] = code
                rgb = _hex_to_rgb(hex_code)
                if rgb:
                    color_rgb_by_key[key] = rgb
                continue
        lowered = name.lower()
        if lowered == "brown":
            color_by_key[key] = ANSI.FG_YELLOW + ANSI.DIM
        elif lowered in ("gray", "grey"):
            color_by_key[key] = ANSI.FG_WHITE + ANSI.DIM
        else:
            color_by_key[key] = COLOR_BY_NAME.get(lowered, ANSI.FG_WHITE)

    def apply_color_mask(line: str, mask: str, row_index: int) -> str:
        if not mask:
            return line
        if not color_by_key and not random_config:
            return line
        base = art_color
        out = []
        for i, ch in enumerate(line):
            mask_char = mask[i] if i < len(mask) else ""
            code = ""
            if mask_char in gradient_keys:
                r, g, b = gradient_rgb(i, row_index, len(line), len(left) if left else len(art_template))
                code = f"\033[38;2;{r};{g};{b}m"
            if mask_char in _MASK_DIGITS:
                code = _random_color_code(mask_char, i, row_index, venue_seed_base, random_config)
            if not code:
                code = color_by_key.get(mask_char) if mask_char else None
            if code:
                out.append(code + ch + ANSI.RESET + base)
            else:
                out.append(ch)
        return "".join(out)

    def apply_npc_mask(line: str, mask: str, row_index: int) -> str:
        if not mask:
            return npc_color + line + art_color
        if not color_by_key and not random_config:
            return npc_color + line + art_color
        base = npc_color
        out = [base]
        for i, ch in enumerate(line):
            mask_char = mask[i] if i < len(mask) else ""
            code = ""
            if mask_char in gradient_keys:
                r, g, b = gradient_rgb(i, row_index, len(line), len(left) if left else len(art_template))
                code = f"\033[38;2;{r};{g};{b}m"
            if mask_char in _MASK_DIGITS:
                code = _random_color_code(mask_char, i, row_index, venue_seed_base, random_config)
            if not code:
                code = color_by_key.get(mask_char) if mask_char else None
            if code:
                out.append(code + ch + ANSI.RESET + base)
            else:
                out.append(ch)
        out.append(art_color)
        return "".join(out)

    if left:
        if not right:
            right = [mirror_line(line) for line in left]
        max_left = max((len(line) for line in left), default=0)
        max_right = max((len(line) for line in right), default=0)
        left = [line.ljust(max_left) for line in left]
        right = [line.ljust(max_right) for line in right]
        raw_lines = [line[:gap_width].rstrip() for line in npc_art]
        max_len = max((len(line) for line in raw_lines), default=0)
        left_aligned = [line.ljust(max_len) for line in raw_lines]
        centered = [line.center(gap_width) for line in left_aligned]
        max_rows = max(len(left), len(right))
        start_row = max(0, max_rows - len(centered))
        art_lines = []
        for i in range(max_rows):
            left_line = left[i] if i < len(left) else (" " * max_left)
            right_line = right[i] if i < len(right) else (" " * max_right)
            left_mask = left_color[i] if i < len(left_color) else ""
            right_mask = right_color[i] if i < len(right_color) else ""
            left_line = apply_color_mask(left_line, left_mask, i)
            right_line = apply_color_mask(right_line, right_mask, i)
            gap_fill = " " * gap_width
            if top and i == 0:
                mask = ""
                if isinstance(top_color, str) and top_color:
                    mask = (top_color * gap_width)[:gap_width] if len(top_color) == 1 else top_color[:gap_width]
                gap_fill = apply_color_mask("=" * gap_width, mask, i)
            elif centered and start_row <= i < start_row + len(centered):
                npc_line = centered[i - start_row]
                npc_mask_line = ""
                npc_mask = npc.get("color_map")
                if isinstance(npc_mask, list):
                    npc_mask_line = npc_mask[i - start_row] if i - start_row < len(npc_mask) else ""
                if npc_mask_line:
                    gap_fill = apply_npc_mask(npc_line, npc_mask_line, i)
                else:
                    gap_fill = npc_color + npc_line + art_color
            art_lines.append(left_line + gap_fill + right_line)
        gap_ground = scene_data.get("gap_ground", [])
        if isinstance(gap_ground, list) and gap_ground and objects_data is not None and gap_width > 0:
            scatter_id = scene_data.get("gap_ground_scatter")
            scatter_obj = objects_data.get(scatter_id, {}) if scatter_id else {}
            def _repeat_line(line: str, target_width: int) -> str:
                if not line or target_width <= 0:
                    return ""
                repeats = (target_width // len(line)) + 1
                return (line * repeats)[:target_width]

            def _apply_scatter(
                line: str,
                mask: str,
                base_width: int,
                scatter_obj: dict,
                row_index: int
            ) -> tuple[str, str]:
                if not scatter_obj or base_width <= 0:
                    return line, mask
                dynamic = scatter_obj.get("dynamic", {}) if isinstance(scatter_obj, dict) else {}
                if not isinstance(dynamic, dict) or dynamic.get("mode") != "scatter":
                    return line, mask
                glyphs = dynamic.get("glyphs", [])
                color_keys = dynamic.get("color_keys", [])
                if not isinstance(glyphs, list) or not glyphs:
                    return line, mask
                if not isinstance(color_keys, list) or not color_keys:
                    return line, mask
                chance = float(dynamic.get("scatter_chance", 0.0) or 0.0)
                if chance <= 0:
                    return line, mask
                art_chars = list(line)
                mask_chars = list(mask)
                tiles = max(1, (len(line) + base_width - 1) // base_width)
                seed_base = _random_seed_base(f"gap_ground:{row_index}")
                for tile_idx in range(tiles):
                    seed = seed_base ^ (row_index * 0x9E3779B1) ^ (tile_idx * 0x85EBCA77)
                    if _unit_from(seed) > chance:
                        continue
                    glyph = glyphs[int(_unit_from(seed + 1) * len(glyphs)) % len(glyphs)]
                    color_key = color_keys[int(_unit_from(seed + 2) * len(color_keys)) % len(color_keys)]
                    offset = int(_unit_from(seed + 3) * base_width)
                    pos = tile_idx * base_width + offset
                    if pos < 0 or pos >= len(art_chars):
                        continue
                    art_chars[pos] = str(glyph)[0]
                    mask_chars[pos] = str(color_key)[0]
                return "".join(art_chars), "".join(mask_chars)

            ground_lines = []
            for row_idx, obj_id in enumerate(gap_ground):
                obj = objects_data.get(obj_id, {})
                art = obj.get("art", [])
                mask = obj.get("color_mask", [])
                base_line = art[0] if isinstance(art, list) and art else ""
                base_mask = mask[0] if isinstance(mask, list) and mask else (" " * len(base_line))
                if not base_line:
                    ground_lines.append(" " * gap_width)
                    continue
                base_width = len(base_line)
                line = _repeat_line(base_line, gap_width)
                mask_line = _repeat_line(base_mask, gap_width)
                if scatter_obj:
                    line, mask_line = _apply_scatter(line, mask_line, base_width, scatter_obj, row_idx)
                seed_base = _random_seed_base(f"gap_ground:{row_idx}")
                ground_lines.append(
                    apply_mask(
                        line,
                        mask_line,
                        row_idx,
                        seed_base,
                        0.0,
                        True,
                        tick,
                        None,
                        "y",
                        0.0,
                        True,
                        len(gap_ground)
                    )
                )
            if ground_lines:
                for row_idx in range(1, min(len(ground_lines), len(art_lines)) + 1):
                    line_index = -row_idx
                    left_line = left[line_index] if abs(line_index) <= len(left) else (" " * max_left)
                    right_line = right[line_index] if abs(line_index) <= len(right) else (" " * max_right)
                    art_lines[line_index] = left_line + ground_lines[-row_idx] + right_line
        bottom_objects = scene_data.get("objects_bottom", [])
        if isinstance(bottom_objects, list) and bottom_objects and objects_data is not None:
            layout_seed = scene_data.get("layout_seed")
            if not isinstance(layout_seed, int):
                layout_seed = _random_seed_base(f"scene:{scene_data.get('name', 'forest')}")

            def _repeat_line(line: str, target_width: int) -> str:
                if not line or target_width <= 0:
                    return ""
                repeats = (target_width // len(line)) + 1
                return (line * repeats)[:target_width]

            def _apply_scatter(
                line: str,
                mask: str,
                base_width: int,
                scatter_obj: dict,
                row_index: int,
                side_tag: int
            ) -> tuple[str, str]:
                if not scatter_obj or base_width <= 0:
                    return line, mask
                dynamic = scatter_obj.get("dynamic", {}) if isinstance(scatter_obj, dict) else {}
                if not isinstance(dynamic, dict):
                    return line, mask
                if dynamic.get("mode") != "scatter":
                    return line, mask
                glyphs = dynamic.get("glyphs", [])
                color_keys = dynamic.get("color_keys", [])
                if not isinstance(glyphs, list) or not glyphs:
                    return line, mask
                if not isinstance(color_keys, list) or not color_keys:
                    return line, mask
                chance = float(dynamic.get("scatter_chance", 0.0) or 0.0)
                if chance <= 0:
                    return line, mask
                art_chars = list(line)
                mask_chars = list(mask)
                tiles = max(1, (len(line) + base_width - 1) // base_width)
                for tile_idx in range(tiles):
                    seed = layout_seed ^ (row_index * 0x9E3779B1) ^ (tile_idx * 0x85EBCA77) ^ side_tag
                    if _unit_from(seed) > chance:
                        continue
                    glyph = glyphs[int(_unit_from(seed + 1) * len(glyphs)) % len(glyphs)]
                    color_key = color_keys[int(_unit_from(seed + 2) * len(color_keys)) % len(color_keys)]
                    offset = int(_unit_from(seed + 3) * base_width)
                    pos = tile_idx * base_width + offset
                    if pos < 0 or pos >= len(art_chars):
                        continue
                    art_chars[pos] = str(glyph)[0]
                    mask_chars[pos] = str(color_key)[0]
                return "".join(art_chars), "".join(mask_chars)

            def _render_bottom_line(entry: dict, target_width: int, row_index: int, side_tag: int) -> str:
                if target_width <= 0:
                    return ""
                obj_id = entry.get("id") if isinstance(entry, dict) else entry
                if not isinstance(obj_id, str) or not obj_id:
                    return " " * target_width
                obj = objects_data.get(obj_id, {})
                art = obj.get("art", [])
                mask = obj.get("color_mask", [])
                base_line = art[0] if isinstance(art, list) and art else ""
                base_mask = mask[0] if isinstance(mask, list) and mask else (" " * len(base_line))
                if not base_line:
                    return " " * target_width
                base_width = len(base_line)
                line = _repeat_line(base_line, target_width)
                mask_line = _repeat_line(base_mask, target_width)
                scatter_id = entry.get("scatter") if isinstance(entry, dict) else None
                scatter_obj = objects_data.get(scatter_id, {}) if scatter_id else None
                if scatter_obj:
                    line, mask_line = _apply_scatter(line, mask_line, base_width, scatter_obj, row_index, side_tag)
                seed_base = layout_seed ^ (row_index * 0xC2B2AE3D) ^ side_tag
                return apply_mask(
                    line,
                    mask_line,
                    row_index,
                    seed_base,
                    0.0,
                    True,
                    tick,
                    None,
                    "y",
                    0.0,
                    True,
                    len(bottom_objects)
                )

            for row_index, entry in enumerate(bottom_objects):
                left_line = _render_bottom_line(entry, max_left, row_index, 0x1A2B3C4D)
                right_line = _render_bottom_line(entry, max_right, row_index, 0x5E6F7081)
                art_lines.append(left_line + (" " * gap_width) + right_line)
        return art_lines, art_color

    art_template = venue.get("art", [])
    if art_template:
        if gap_width > 0:
            raw_lines = [line[:gap_width].rstrip() for line in npc_art]
            max_len = max((len(line) for line in raw_lines), default=0)
            left_aligned = [line.ljust(max_len) for line in raw_lines]
            centered = [line.center(gap_width) for line in left_aligned]
            art_lines = []
            start_row = max(0, len(art_template) - len(centered))
            for i, line in enumerate(art_template):
                gap_fill = " " * gap_width
                if centered and start_row <= i < start_row + len(centered):
                    npc_line = centered[i - start_row]
                    npc_mask_line = ""
                    npc_mask = npc.get("color_map")
                    if isinstance(npc_mask, list):
                        npc_mask_line = npc_mask[i - start_row] if i - start_row < len(npc_mask) else ""
                    if npc_mask_line:
                        gap_fill = apply_npc_mask(npc_line, npc_mask_line, i)
                    else:
                        gap_fill = npc_color + npc_line + art_color
                art_lines.append(line.replace("{GAP}", gap_fill))
            return art_lines, art_color
        return art_template, art_color
    return [], art_color


def render_venue_objects(
    venue: dict,
    npc: dict,
    objects_data: object,
    color_map_override: Optional[dict] = None
) -> tuple[List[str], str, Optional[int]]:
    art_color = COLOR_BY_NAME.get(venue.get("color", "white").lower(), ANSI.FG_WHITE)
    npc_color = COLOR_BY_NAME.get(npc.get("color", "white").lower(), ANSI.FG_WHITE)
    color_map = {}
    if isinstance(color_map_override, dict):
        color_map.update(color_map_override)
    venue_color_map = venue.get("color_map")
    if isinstance(venue_color_map, dict):
        color_map.update(venue_color_map)

    def truecolor(code: str) -> str:
        value = code.lstrip("#")
        if len(value) != 6:
            return ""
        try:
            r = int(value[0:2], 16)
            g = int(value[2:4], 16)
            b = int(value[4:6], 16)
        except ValueError:
            return ""
        return f"\033[38;2;{r};{g};{b}m"

    color_by_key = {}
    gradient_keys = set()
    color_rgb_by_key = {}
    for key, entry in color_map.items():
        if key == "random" or key in _MASK_DIGITS:
            continue
        if isinstance(entry, dict):
            hex_code = entry.get("hex", "") if isinstance(entry.get("hex"), str) else ""
            name = entry.get("name", "") if isinstance(entry.get("name"), str) else ""
        elif isinstance(entry, str):
            hex_code = ""
            name = entry
        else:
            continue
        name = name.strip()
        hex_code = hex_code.strip()
        if name.lower() == "gradient":
            gradient_keys.add(key)
            continue
        if not hex_code:
            hex_start = name.find("#")
            hex_code = name[hex_start:] if hex_start != -1 else ""
        if hex_code:
            code = truecolor(hex_code)
            if code:
                color_by_key[key] = code
                rgb = _hex_to_rgb(hex_code)
                if rgb:
                    color_rgb_by_key[key] = rgb
                continue
        lowered = name.lower()
        if lowered == "brown":
            color_by_key[key] = ANSI.FG_YELLOW + ANSI.DIM
        elif lowered in ("gray", "grey"):
            color_by_key[key] = ANSI.FG_WHITE + ANSI.DIM
        else:
            color_by_key[key] = COLOR_BY_NAME.get(lowered, ANSI.FG_WHITE)

    npc_key = "@"
    color_by_key[npc_key] = npc_color
    def _build_npc_parts(npc_data: dict) -> tuple[list, list]:
        parts = npc_data.get("parts")
        if not isinstance(parts, list) or not parts:
            return [], []
        parts_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "npc_parts.json")
        try:
            with open(parts_path, "r", encoding="utf-8") as f:
                parts_data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return [], []
        collected = []
        max_width = 0
        for entry in parts:
            if not isinstance(entry, dict):
                continue
            part_id = entry.get("id")
            if not part_id:
                continue
            part = parts_data.get(part_id, {})
            part_art = part.get("art", [])
            part_mask = part.get("color_mask", [])
            if not isinstance(part_art, list) or not isinstance(part_mask, list):
                continue
            part_width = max((len(line) for line in part_art), default=0)
            max_width = max(max_width, part_width)
            collected.append((part_art, part_mask, part_width))
        art_lines = []
        mask_lines = []
        for part_art, part_mask, part_width in collected:
            pad_left = max(0, (max_width - part_width) // 2)
            for idx, line in enumerate(part_art):
                padded = (" " * pad_left) + line
                art_lines.append(padded.ljust(max_width))
                mask_line = part_mask[idx] if idx < len(part_mask) else ""
                mask_padded = (" " * pad_left) + mask_line
                mask_lines.append(mask_padded.ljust(max_width))
        return art_lines, mask_lines

    npc_art_lines = npc.get("art", []) if isinstance(npc.get("art"), list) else []
    npc_mask_lines = npc.get("color_map", []) if isinstance(npc.get("color_map"), list) else []
    if not npc_art_lines:
        npc_art_lines, npc_mask_lines = _build_npc_parts(npc)
    npc_has_mask = len(npc_mask_lines) > 0

    random_config = color_map.get("random", {}) if isinstance(color_map.get("random"), dict) else {}
    venue_seed_base = _random_seed_base(f"venue:{venue.get('name', '')}")

    def apply_color_mask(
        line: str,
        mask: str,
        rand_row: Optional[list],
        jitter_row: Optional[list],
        row_index: int,
        tick: int,
        label_variation: float,
        label_jitter_stability: bool
    ) -> str:
        if not mask:
            return line
        if not color_by_key and not random_config:
            return line
        base = art_color
        out = []
        for i, ch in enumerate(line):
            mask_char = mask[i] if i < len(mask) else ""
            code = ""
            if mask_char in gradient_keys:
                r, g, b = gradient_rgb(i, row_index, max_width, max_height)
                code = f"\033[38;2;{r};{g};{b}m"
            if mask_char in _MASK_DIGITS:
                seed_base = rand_row[i] if rand_row and i < len(rand_row) else venue_seed_base
                local_x, local_y = i, row_index
                if isinstance(seed_base, tuple):
                    seed_base, local_x, local_y = seed_base
                code = _random_color_code(mask_char, local_x, local_y, seed_base, random_config)
            if not code:
                code = color_by_key.get(mask_char) if mask_char else None
            if not code and mask_char and mask_char.isalpha():
                code = color_by_key.get(mask_char)
            if mask_char.isalpha():
                jitter_info = jitter_row[i] if jitter_row and i < len(jitter_row) else None
                if jitter_info and mask_char in color_rgb_by_key:
                    seed_base, jitter_amount, jitter_stability, local_x, local_y = jitter_info
                    seed = seed_base ^ (ord(mask_char) << 4) ^ (local_x * 0x85EBCA77) ^ (local_y * 0xC2B2AE3D)
                    if not jitter_stability:
                        seed ^= (tick * 0x9E3779B1)
                    code = _jitter_color_code(color_rgb_by_key[mask_char], jitter_amount, seed)
                elif label_variation > 0 and mask_char in color_rgb_by_key:
                    seed = (row_index * 0x9E3779B1) ^ (i * 0x85EBCA77) ^ (ord(mask_char) << 4)
                    if not label_jitter_stability:
                        seed ^= (tick * 0x9E3779B1)
                    code = _jitter_color_code(color_rgb_by_key[mask_char], label_variation, seed)
            if code:
                out.append(code + ch + ANSI.RESET + base)
            else:
                out.append(ch)
        return "".join(out)

    venue_objects = venue.get("objects", [])
    if not isinstance(venue_objects, list) or not venue_objects:
        return [], art_color, None

    def _obj_def(obj_id: str) -> dict:
        return objects_data.get(obj_id, {}) if hasattr(objects_data, "get") else {}

    def _obj_art(obj_id: str) -> List[str]:
        if obj_id == "npc":
            return npc_art_lines
        return _obj_def(obj_id).get("art", [])

    def _obj_mask(obj_id: str) -> List[str]:
        if obj_id == "npc":
            return npc_mask_lines
        return _obj_def(obj_id).get("color_mask", [])

    def _apply_label(art: List[str], mask: List[str], entry: dict) -> tuple[List[str], List[str]]:
        label = entry.get("label")
        if not isinstance(label, str) or not label.strip():
            return art, mask
        label_row = entry.get("label_row", 1)
        try:
            label_row = int(label_row)
        except (TypeError, ValueError):
            label_row = 1
        if label_row < 0 or label_row >= len(art):
            return art, mask
        line = art[label_row]
        if not isinstance(line, str):
            return art, mask
        width = len(line)
        left_bound = None
        right_bound = None
        for idx, ch in enumerate(line):
            if ch != " ":
                if left_bound is None:
                    left_bound = idx
                right_bound = idx
        if left_bound is None:
            left_bound = 0
            right_bound = width - 1 if width else 0
        content_width = max(1, right_bound - left_bound + 1)
        label_text = f"[ {label.strip()} ]"
        if len(label_text) > content_width:
            label_text = label_text[:content_width]
        start = left_bound + max(0, (content_width - len(label_text)) // 2)
        line_chars = list(line)
        for i, ch in enumerate(label_text):
            if start + i < width:
                line_chars[start + i] = ch
        art = list(art)
        art[label_row] = "".join(line_chars)
        label_key = entry.get("label_key", "y")
        if not isinstance(label_key, str) or not label_key:
            label_key = "y"
        label_key = label_key[0]
        label_variation = entry.get("label_variation", 0.0)
        label_jitter_stability = entry.get("label_jitter_stability", True)
        if isinstance(mask, list) and label_key.strip():
            mask_line = mask[label_row] if label_row < len(mask) else ""
            mask_chars = list(mask_line.ljust(width))
            for i in range(len(label_text)):
                if start + i < width:
                    mask_chars[start + i] = label_key
            mask = list(mask)
            while len(mask) < len(art):
                mask.append("")
            mask[label_row] = "".join(mask_chars)
        entry["_label_variation"] = label_variation
        entry["_label_jitter_stability"] = label_jitter_stability
        return art, mask

    def _obj_align(entry: dict, obj_id: str) -> float:
        align = entry.get("align", None)
        if align is None:
            align = _obj_def(obj_id).get("align", 0)
        try:
            return float(align)
        except (TypeError, ValueError):
            return 0.0

    def _obj_size(entry: dict, obj_id: str) -> tuple[int, int]:
        if obj_id == "space":
            width = int(entry.get("width", 1) or 1)
            return max(0, width), 0
        art = _obj_art(obj_id)
        width = max((len(line) for line in art), default=0)
        height = len(art)
        return width, height

    expanded = []
    for entry in venue_objects:
        if not isinstance(entry, dict):
            continue
        repeat = int(entry.get("repeat", 1) or 1)
        repeat = max(1, repeat)
        for _ in range(repeat):
            expanded.append(entry)

    positions = []
    cursor = 0
    max_height = 0
    for entry in expanded:
        obj_id = entry.get("id", "")
        mode = entry.get("mode", "")
        width, height = _obj_size(entry, obj_id)
        if mode == "span_until":
            width = 0
        positions.append({"entry": entry, "id": obj_id, "x": cursor})
        cursor += width
        max_height = max(max_height, height)

    min_height = int(venue.get("min_height", 0) or 0)
    if min_height > 0:
        max_height = max(max_height, min_height)

    if max_height <= 0 or cursor <= 0:
        return [], art_color, None

    canvas = [[" " for _ in range(cursor)] for _ in range(max_height)]
    mask_canvas = [[" " for _ in range(cursor)] for _ in range(max_height)]
    rand_canvas: list[list[Optional[tuple[int, int, int]]]] = [
        [None for _ in range(cursor)] for _ in range(max_height)
    ]
    jitter_canvas: list[list[Optional[tuple[int, float, bool, int, int]]]] = [
        [None for _ in range(cursor)] for _ in range(max_height)
    ]
    npc_anchor = None

    def _place_mask(
        mask_char: str,
        x: int,
        y: int,
        seed_info: Optional[tuple[int, int, int]] = None,
        jitter_info: Optional[tuple[int, float, bool, int, int]] = None
    ):
        if 0 <= y < max_height and 0 <= x < cursor and mask_char:
            mask_canvas[y][x] = mask_char
            if seed_info and mask_char in _MASK_DIGITS:
                rand_canvas[y][x] = seed_info
            if jitter_info and mask_char.isalpha():
                jitter_canvas[y][x] = jitter_info

    def _blit(
        art: List[str],
        mask: List[str],
        x: int,
        y: int,
        seed_base: int,
        jitter_amount: float,
        jitter_stability: bool,
        mask_override: Optional[str] = None,
        blocking_char: Optional[str] = None
    ):
        for row_idx, line in enumerate(art):
            target_y = y + row_idx
            if target_y < 0 or target_y >= max_height:
                continue
            mask_line = mask[row_idx] if row_idx < len(mask) else ""
            for col_idx, ch in enumerate(line):
                target_x = x + col_idx
                if target_x < 0 or target_x >= cursor:
                    continue
                if blocking_char and ch == blocking_char:
                    canvas[target_y][target_x] = " "
                    mask_canvas[target_y][target_x] = " "
                    rand_canvas[target_y][target_x] = None
                    jitter_canvas[target_y][target_x] = None
                    continue
                if ch != " ":
                    canvas[target_y][target_x] = ch
                if mask_override:
                    if ch != " ":
                        _place_mask(mask_override, target_x, target_y)
                else:
                    mask_char = mask_line[col_idx] if col_idx < len(mask_line) else ""
                    if mask_char and ch != " ":
                        rand_info = (seed_base, col_idx, row_idx)
                        jitter_info = None
                        if jitter_amount > 0 and mask_char.isalpha():
                            jitter_info = (seed_base, jitter_amount, jitter_stability, col_idx, row_idx)
                        _place_mask(mask_char, target_x, target_y, rand_info, jitter_info)

    for idx, item in enumerate(positions):
        entry = item["entry"]
        obj_id = item["id"]
        mode = entry.get("mode", "")
        x = item["x"]
        seed_base = _random_seed_base(f"{obj_id}:{idx}")
        obj_def = _obj_def(obj_id)
        blocking_char = obj_def.get("blocking_space")
        if not isinstance(blocking_char, str) or len(blocking_char) != 1:
            blocking_char = None
        jitter_source = obj_def
        if obj_id == "npc":
            jitter_source = npc if isinstance(npc, dict) else {}
        jitter_amount = entry.get("variation", jitter_source.get("variation", 0.0))
        try:
            jitter_amount = float(jitter_amount)
        except (TypeError, ValueError):
            jitter_amount = 0.0
        jitter_stability = entry.get("jitter_stability", jitter_source.get("jitter_stability", True))
        jitter_stability = bool(jitter_stability)
        label_variation = entry.get("_label_variation", 0.0)
        try:
            label_variation = float(label_variation)
        except (TypeError, ValueError):
            label_variation = 0.0
        label_jitter_stability = bool(entry.get("_label_jitter_stability", True))
        align = _obj_align(entry, obj_id)

        if mode == "span_until":
            target_id = entry.get("target")
            if not target_id:
                continue
            target_index = None
            for next_idx in range(idx + 1, len(positions)):
                if positions[next_idx]["id"] == target_id:
                    target_index = next_idx
                    break
            if target_index is None:
                continue
            span = positions[target_index]["x"] - x
            if span <= 0:
                continue
            art = _obj_art(obj_id)
            mask = _obj_mask(obj_id)
            if not art:
                continue
            char = art[0][0] if art[0] else " "
            mask_char = mask[0][0] if mask and mask[0] else ""
            y = int((1 - align) * max(0, max_height - 1))
            for dx in range(span):
                if char != " ":
                    canvas[y][x + dx] = char
                if mask_char and char != " ":
                    mask_canvas[y][x + dx] = mask_char
            continue

        if obj_id == "space":
            continue

        art = _obj_art(obj_id)
        if not art:
            continue
        mask = _obj_mask(obj_id)
        if obj_id != "npc":
            art, mask = _apply_label(art, mask, entry)
        obj_height = len(art)
        y = int((1 - align) * max(0, max_height - obj_height))

        if obj_id == "npc":
            if npc_anchor is None:
                min_x = None
                max_x = -1
                for line in art:
                    for idx, ch in enumerate(line):
                        if ch != " ":
                            if min_x is None or idx < min_x:
                                min_x = idx
                            if idx > max_x:
                                max_x = idx
                if min_x is None:
                    min_x = 0
                    max_x = max((len(line) for line in art), default=1) - 1
                npc_anchor = x + min_x + max(0, (max_x - min_x) // 2)
            if npc_has_mask:
                _blit(art, mask, x, y, seed_base, jitter_amount, jitter_stability, blocking_char=blocking_char)
            else:
                _blit(art, mask, x, y, seed_base, jitter_amount, jitter_stability, mask_override=npc_key, blocking_char=blocking_char)
        else:
            _blit(art, mask, x, y, seed_base, jitter_amount, jitter_stability, blocking_char=blocking_char)

    max_width = max(len(row) for row in canvas) if canvas else 0
    art_lines = []
    tick = int(time.time() / _JITTER_TICK_SECONDS) if _JITTER_TICK_SECONDS > 0 else 0
    for row_idx in range(max_height):
        line = "".join(canvas[row_idx])
        mask_line = "".join(mask_canvas[row_idx])
        rand_row = rand_canvas[row_idx] if row_idx < len(rand_canvas) else None
        jitter_row = jitter_canvas[row_idx] if row_idx < len(jitter_canvas) else None
        art_lines.append(apply_color_mask(line, mask_line, rand_row, jitter_row, row_idx, tick, label_variation, label_jitter_stability))
    return art_lines, art_color, npc_anchor


def render_scene_art(
    scene_data: dict,
    opponents: List[Opponent],
    gap_override: Optional[int] = None,
    flash_index: Optional[int] = None,
    flash_color: Optional[str] = None,
    overlay_target_index: Optional[int] = None,
    overlay_effect: Optional[dict] = None,
    overlay_frame_index: int = 0,
    visible_indices: Optional[set] = None,
    include_bars: bool = True,
    manual_lines_indices: Optional[set] = None,
    objects_data: Optional[object] = None,
    color_map_override: Optional[dict] = None
) -> tuple[List[str], str]:
    """Compose scene art with optional opponent blocks in the gap."""
    art_color = COLOR_BY_NAME.get(scene_data.get("color", "white").lower(), ANSI.FG_WHITE)
    has_left_objects = bool(scene_data.get("objects_left"))
    color_map = color_map_override or {}

    scene_objects = scene_data.get("objects")
    if isinstance(scene_objects, list) and scene_objects and objects_data is not None:
        venue_stub = {
            "objects": scene_objects,
            "color": scene_data.get("color", "white"),
        }
        if isinstance(scene_data.get("color_map"), dict):
            venue_stub["color_map"] = scene_data.get("color_map")
        lines, art_color, _ = render_venue_objects(venue_stub, {}, objects_data, color_map_override)
        if lines:
            return lines, art_color

    def truecolor(code: str) -> str:
        value = code.lstrip("#")
        if len(value) != 6:
            return ""
        try:
            r = int(value[0:2], 16)
            g = int(value[2:4], 16)
            b = int(value[4:6], 16)
        except ValueError:
            return ""
        return f"\033[38;2;{r};{g};{b}m"

    random_config = color_map.get("random", {}) if isinstance(color_map.get("random"), dict) else {}

    def build_color_by_key() -> tuple[dict, set]:
        color_by_key = {}
        gradient_keys = set()
        for key, entry in (color_map or {}).items():
            if key == "random" or key in _MASK_DIGITS:
                continue
            if isinstance(entry, dict):
                hex_code = entry.get("hex", "") if isinstance(entry.get("hex"), str) else ""
                name = entry.get("name", "") if isinstance(entry.get("name"), str) else ""
            elif isinstance(entry, str):
                hex_code = ""
                name = entry
            else:
                continue
            name = name.strip()
            hex_code = hex_code.strip()
            if name.lower() == "gradient":
                gradient_keys.add(key)
                continue
            if not hex_code:
                hex_start = name.find("#")
                hex_code = name[hex_start:] if hex_start != -1 else ""
            if hex_code:
                code = truecolor(hex_code)
                if code:
                    color_by_key[key] = code
                    continue
            lowered = name.lower()
            if lowered == "brown":
                color_by_key[key] = ANSI.FG_YELLOW + ANSI.DIM
            elif lowered in ("gray", "grey"):
                color_by_key[key] = ANSI.FG_WHITE + ANSI.DIM
            else:
                color_by_key[key] = COLOR_BY_NAME.get(lowered, ANSI.FG_WHITE)
        return color_by_key, gradient_keys

    color_by_key, gradient_keys = build_color_by_key()
    color_rgb_by_key = {}
    for key, entry in (color_map or {}).items():
        if key == "random" or key in _MASK_DIGITS:
            continue
        if isinstance(entry, dict):
            hex_code = entry.get("hex", "") if isinstance(entry.get("hex"), str) else ""
            name = entry.get("name", "") if isinstance(entry.get("name"), str) else ""
        elif isinstance(entry, str):
            hex_code = ""
            name = entry
        else:
            continue
        name = name.strip()
        hex_code = hex_code.strip()
        if not hex_code:
            hex_start = name.find("#")
            hex_code = name[hex_start:] if hex_start != -1 else ""
        if hex_code:
            rgb = _hex_to_rgb(hex_code)
            if rgb:
                color_rgb_by_key[key] = rgb

    def apply_mask(
        line: str,
        mask: str,
        row_index: int,
        seed_base: int,
        jitter_amount: float,
        jitter_stability: bool,
        tick: int,
        overlay_row: Optional[dict],
        overlay_color_key: str,
        overlay_variation: float,
        overlay_jitter_stability: bool,
        art_height: int
    ) -> str:
        if not mask:
            return line
        if not color_by_key and not random_config:
            return line
        out = []
        for i, ch in enumerate(line):
            mask_char = mask[i] if i < len(mask) else ""
            overlay_cell = overlay_row.get(i) if overlay_row else None
            code = ""
            if overlay_cell:
                ch = overlay_cell
                base_rgb = color_rgb_by_key.get(overlay_color_key)
                if base_rgb:
                    overlay_seed = seed_base ^ (ord(overlay_color_key) << 4) ^ (i * 0x85EBCA77) ^ (row_index * 0xC2B2AE3D)
                    if not overlay_jitter_stability:
                        overlay_seed ^= (tick * 0x9E3779B1)
                    code = _jitter_color_code(base_rgb, overlay_variation, overlay_seed)
                else:
                    code = color_by_key.get(overlay_color_key, "")
            elif mask_char in gradient_keys:
                r, g, b = gradient_rgb(i, row_index, len(line), art_height)
                code = f"\033[38;2;{r};{g};{b}m"
            elif mask_char in _MASK_DIGITS:
                code = _random_color_code(mask_char, i, row_index, seed_base, random_config)
            elif mask_char.isalpha() and mask_char in color_rgb_by_key and jitter_amount > 0:
                jitter_seed = seed_base ^ (ord(mask_char) << 4) ^ (i * 0x85EBCA77) ^ (row_index * 0xC2B2AE3D)
                if not jitter_stability:
                    jitter_seed ^= (tick * 0x9E3779B1)
                code = _jitter_color_code(color_rgb_by_key[mask_char], jitter_amount, jitter_seed)
            if not code:
                code = color_by_key.get(mask_char) if mask_char else None
            if code:
                out.append(code + ch + ANSI.RESET)
            else:
                out.append(ANSI.RESET + ch)
        return "".join(out)
    gap_base = (
        int(scene_data.get("gap_min", 2))
        if scene_data.get("left") or has_left_objects
        else int(scene_data.get("gap_width", 20))
    )
    gap_width = gap_override if gap_override is not None else gap_base
    tick = int(time.time() / _JITTER_TICK_SECONDS) if _JITTER_TICK_SECONDS > 0 else 0
    opponent_blocks = []
    for i, opponent in enumerate(opponents):
        if not opponent.art_lines:
            continue
        is_visible = visible_indices is None or i in visible_indices
        if manual_lines_indices and i in manual_lines_indices:
            raw_lines = [line[:OPPONENT_ART_WIDTH] for line in opponent.art_lines]
            max_len = max((len(line) for line in raw_lines), default=0)
            left_aligned = [line.ljust(max_len) for line in raw_lines]
            art_lines = [line.center(OPPONENT_ART_WIDTH) for line in left_aligned]
        elif opponent.hp > 0 and is_visible:
            raw_lines = [line[:OPPONENT_ART_WIDTH].rstrip() for line in opponent.art_lines]
            max_len = max((len(line) for line in raw_lines), default=0)
            left_aligned = [line.ljust(max_len) for line in raw_lines]
            art_lines = [line.center(OPPONENT_ART_WIDTH) for line in left_aligned]
            if include_bars:
                art_lines.append(pad_ansi(format_opponent_bar(opponent), OPPONENT_ART_WIDTH))
        elif is_visible:
            art_lines = [" " * OPPONENT_ART_WIDTH for _ in opponent.art_lines]
            if include_bars:
                art_lines.append(" " * OPPONENT_ART_WIDTH)
        else:
            art_lines = [" " * OPPONENT_ART_WIDTH for _ in opponent.art_lines]
            if include_bars:
                art_lines.append(" " * OPPONENT_ART_WIDTH)
        if manual_lines_indices and i in manual_lines_indices and include_bars:
            art_lines.append(" " * OPPONENT_ART_WIDTH)
        color_to_use = opponent.art_color
        if flash_index == i and flash_color:
            color_to_use = flash_color
        has_mask = bool(opponent.color_map) and bool(color_by_key)
        mask_lines = []
        if has_mask:
            raw_masks = [line[:OPPONENT_ART_WIDTH] for line in opponent.color_map]
            max_mask = max((len(line) for line in raw_masks), default=0)
            left_masks = [line.ljust(max_mask) for line in raw_masks]
            mask_lines = [line.center(OPPONENT_ART_WIDTH) for line in left_masks]
            if include_bars:
                mask_lines = mask_lines + [""]
            if manual_lines_indices and i in manual_lines_indices and include_bars:
                mask_lines.append("")
        opponent_bounds = None
        if opponent.art_lines:
            raw_lines = [line[:OPPONENT_ART_WIDTH].rstrip() for line in opponent.art_lines]
            max_len = max((len(line) for line in raw_lines), default=0)
            left_aligned = [line.ljust(max_len) for line in raw_lines]
            centered_lines = [line.center(OPPONENT_ART_WIDTH) for line in left_aligned]
            top = None
            bottom = None
            left = None
            right = None
            for r_idx, row in enumerate(centered_lines):
                for c_idx, ch in enumerate(row):
                    if ch == " ":
                        continue
                    if top is None or r_idx < top:
                        top = r_idx
                    if bottom is None or r_idx > bottom:
                        bottom = r_idx
                    if left is None or c_idx < left:
                        left = c_idx
                    if right is None or c_idx > right:
                        right = c_idx
            if top is not None:
                opponent_bounds = (top, bottom, left, right)
        overlay_rows = None
        overlay_color_key = "y"
        overlay_variation = 0.0
        overlay_jitter_stability = True
        if overlay_effect and overlay_target_index == i:
            frames = overlay_effect.get("frames", [])
            if isinstance(frames, list) and frames:
                max_frame_width = 0
                max_frame_height = 0
                for frame in frames:
                    if not isinstance(frame, list):
                        continue
                    max_frame_height = max(max_frame_height, len(frame))
                    frame_width = max((len(line) for line in frame), default=0)
                    max_frame_width = max(max_frame_width, frame_width)
                frame_index = overlay_frame_index % len(frames)
                overlay_frame = frames[frame_index]
                if isinstance(overlay_frame, list) and overlay_frame:
                    overlay_color_key = str(overlay_effect.get("color_key", "y"))[:1] or "y"
                    overlay_variation = float(overlay_effect.get("variation", 0.0) or 0.0)
                    overlay_jitter_stability = bool(overlay_effect.get("jitter_stability", True))
                    overlay_height = len(overlay_frame)
                    overlay_width = max((len(line) for line in overlay_frame), default=0)
                    pad_top = (max_frame_height - overlay_height) // 2
                    pad_left = (max_frame_width - overlay_width) // 2
                    bar_lines = 1 if include_bars else 0
                    if manual_lines_indices and i in manual_lines_indices and include_bars:
                        bar_lines += 1
                    art_height = max(0, len(art_lines) - bar_lines)
                    row_start = (art_height - max_frame_height) // 2
                    col_start = (OPPONENT_ART_WIDTH - max_frame_width) // 2
                    if opponent_bounds:
                        opp_top, opp_bottom, opp_left, opp_right = opponent_bounds
                        opp_width = opp_right - opp_left + 1
                        opp_height = opp_bottom - opp_top + 1
                        col_start = opp_left + ((opp_width - max_frame_width) // 2)
                        row_start = opp_top + ((opp_height - max_frame_height) // 2)
                    overlay_rows = {}
                    for r_idx, row in enumerate(overlay_frame):
                        target_row = row_start + pad_top + r_idx
                        if target_row < 0 or target_row >= art_height:
                            continue
                        for c_idx, ch in enumerate(row):
                            if ch == " ":
                                continue
                            target_col = col_start + pad_left + c_idx
                            if 0 <= target_col < OPPONENT_ART_WIDTH:
                                overlay_rows.setdefault(target_row, {})[target_col] = ch
        if has_mask:
            colored = []
            if flash_index == i and flash_color:
                for line in art_lines:
                    colored.append(flash_color + line + ANSI.RESET)
            else:
                seed_base = _random_seed_base(f"opponent:{i}:{opponent.name}")
                jitter_amount = float(getattr(opponent, "variation", 0.0) or 0.0)
                jitter_stability = bool(getattr(opponent, "jitter_stability", True))
                for idx, line in enumerate(art_lines):
                    mask_line = mask_lines[idx] if idx < len(mask_lines) else ""
                    colored.append(
                        apply_mask(
                            line,
                            mask_line,
                            idx,
                            seed_base,
                            jitter_amount,
                            jitter_stability,
                            tick,
                            overlay_rows.get(idx) if overlay_rows else None,
                            overlay_color_key,
                            overlay_variation,
                            overlay_jitter_stability,
                            len(art_lines)
                        )
                    )
            art_lines = colored
            color_to_use = ""
        opponent_blocks.append(
            {
                "lines": art_lines,
                "width": OPPONENT_ART_WIDTH,
                "color": color_to_use,
            }
        )
    if opponent_blocks:
        max_opp_rows = max((len(block["lines"]) for block in opponent_blocks), default=0)
        for block in opponent_blocks:
            pad = max_opp_rows - len(block["lines"])
            if pad > 0:
                block["lines"] = ([" " * block["width"]] * pad) + block["lines"]
    if has_left_objects:
        def _render_object_strip(objects_list: list) -> list[str]:
            if not objects_list or objects_data is None:
                return []
            venue_stub = {
                "objects": objects_list,
                "color": scene_data.get("color", "white"),
            }
            if isinstance(scene_data.get("color_map"), dict):
                venue_stub["color_map"] = scene_data.get("color_map")
            lines, _, _ = render_venue_objects(venue_stub, {}, objects_data, color_map_override)
            return lines

        left = _render_object_strip(scene_data.get("objects_left", []))
        right = _render_object_strip(scene_data.get("objects_right", []))
        if not right and left:
            right = [mirror_line(strip_ansi(line)) for line in left]
        max_left = max((len(strip_ansi(line)) for line in left), default=0)
        max_right = max((len(strip_ansi(line)) for line in right), default=0)
        left = [pad_ansi(line, max_left) for line in left]
        right = [pad_ansi(line, max_right) for line in right]
    if scene_data.get("left") and not has_left_objects:
        left = scene_data.get("left", [])
        right = scene_data.get("right", [])
        if not right:
            right = [mirror_line(line) for line in left]
        max_left = max((len(line) for line in left), default=0)
        max_right = max((len(line) for line in right), default=0)
        left = [line.ljust(max_left) for line in left]
        right = [line.ljust(max_right) for line in right]
    if has_left_objects or scene_data.get("left"):
        max_left = max((len(strip_ansi(line)) for line in left), default=0)
        max_right = max((len(strip_ansi(line)) for line in right), default=0)
        if opponent_blocks:
            gap_pad = 2
            inter_pad = 2
            content_width = (
                (gap_pad * 2)
                + sum(block["width"] for block in opponent_blocks)
                + (inter_pad * (len(opponent_blocks) - 1))
            )
            gap_width = max(gap_width, content_width)
        art_lines = []
        max_opp_rows = max((len(block["lines"]) for block in opponent_blocks), default=0)
        max_rows = max(len(left), len(right), max_opp_rows)
        def _ansi_cells(text: str) -> list[tuple[str, str]]:
            cells = []
            i = 0
            current = ""
            while i < len(text):
                ch = text[i]
                if ch == "\x1b" and i + 1 < len(text) and text[i + 1] == "[":
                    j = i + 2
                    while j < len(text) and text[j] != "m":
                        j += 1
                    if j < len(text):
                        current = text[i:j + 1]
                        i = j + 1
                        continue
                cells.append((ch, current))
                i += 1
            return cells

        def _merge_ansi(base: str, top: str) -> str:
            base_cells = _ansi_cells(base)
            top_cells = _ansi_cells(top)
            width = min(len(base_cells), len(top_cells))
            out = []
            for idx in range(width):
                ch, code = top_cells[idx]
                if ch == " ":
                    ch, code = base_cells[idx]
                out.append(code + ch)
            for idx in range(width, len(base_cells)):
                ch, code = base_cells[idx]
                out.append(code + ch)
            return "".join(out) + ANSI.RESET

        def _slice_ansi(text: str, start: int, width: int) -> str:
            if width <= 0:
                return ""
            out = []
            vis_idx = 0
            i = 0
            end = start + width
            while i < len(text):
                ch = text[i]
                if ch == "\x1b" and i + 1 < len(text) and text[i + 1] == "[":
                    j = i + 2
                    while j < len(text) and text[j] != "m":
                        j += 1
                    if j < len(text):
                        seq = text[i:j + 1]
                        if start <= vis_idx < end:
                            out.append(seq)
                        i = j + 1
                        continue
                if start <= vis_idx < end:
                    out.append(ch)
                vis_idx += 1
                i += 1
            return "".join(out)

        gap_ground = scene_data.get("gap_ground", [])
        ground_lines = []
        if isinstance(gap_ground, list) and gap_ground and objects_data is not None and gap_width > 0:
            scatter_id = scene_data.get("gap_ground_scatter")
            scatter_obj = objects_data.get(scatter_id, {}) if scatter_id else {}

            def _repeat_line(line: str, target_width: int) -> str:
                if not line or target_width <= 0:
                    return ""
                repeats = (target_width // len(line)) + 1
                return (line * repeats)[:target_width]

            def _apply_scatter(
                line: str,
                mask: str,
                base_width: int,
                scatter_obj: dict,
                row_index: int
            ) -> tuple[str, str]:
                if not scatter_obj or base_width <= 0:
                    return line, mask
                dynamic = scatter_obj.get("dynamic", {}) if isinstance(scatter_obj, dict) else {}
                if not isinstance(dynamic, dict) or dynamic.get("mode") != "scatter":
                    return line, mask
                glyphs = dynamic.get("glyphs", [])
                color_keys = dynamic.get("color_keys", [])
                if not isinstance(glyphs, list) or not glyphs:
                    return line, mask
                if not isinstance(color_keys, list) or not color_keys:
                    return line, mask
                chance = float(dynamic.get("scatter_chance", 0.0) or 0.0)
                if chance <= 0:
                    return line, mask
                art_chars = list(line)
                mask_chars = list(mask)
                tiles = max(1, (len(line) + base_width - 1) // base_width)
                seed_base = _random_seed_base(f"gap_ground:{row_index}")
                for tile_idx in range(tiles):
                    seed = seed_base ^ (row_index * 0x9E3779B1) ^ (tile_idx * 0x85EBCA77)
                    if _unit_from(seed) > chance:
                        continue
                    glyph = glyphs[int(_unit_from(seed + 1) * len(glyphs)) % len(glyphs)]
                    color_key = color_keys[int(_unit_from(seed + 2) * len(color_keys)) % len(color_keys)]
                    offset = int(_unit_from(seed + 3) * base_width)
                    pos = tile_idx * base_width + offset
                    if pos < 0 or pos >= len(art_chars):
                        continue
                    art_chars[pos] = str(glyph)[0]
                    mask_chars[pos] = str(color_key)[0]
                return "".join(art_chars), "".join(mask_chars)

            for row_idx, obj_id in enumerate(gap_ground):
                obj = objects_data.get(obj_id, {})
                art = obj.get("art", [])
                mask = obj.get("color_mask", [])
                base_line = art[0] if isinstance(art, list) and art else ""
                base_mask = mask[0] if isinstance(mask, list) and mask else (" " * len(base_line))
                if not base_line:
                    ground_lines.append(" " * gap_width)
                    continue
                base_width = len(base_line)
                line = _repeat_line(base_line, gap_width)
                mask_line = _repeat_line(base_mask, gap_width)
                if scatter_obj:
                    line, mask_line = _apply_scatter(line, mask_line, base_width, scatter_obj, row_idx)
                seed_base = _random_seed_base(f"gap_ground:{row_idx}")
                ground_lines.append(
                    apply_mask(
                        line,
                        mask_line,
                        row_idx,
                        seed_base,
                        0.0,
                        True,
                        tick,
                        None,
                        "y",
                        0.0,
                        True,
                        len(gap_ground)
                    )
                )
        ground_rows = len(ground_lines)
        start_row = (max_rows - max_opp_rows) if max_opp_rows else 0
        if start_row < 0:
            start_row = 0
        for i in range(max_rows):
            left_line = left[i] if i < len(left) else (" " * max_left)
            right_line = right[i] if i < len(right) else (" " * max_right)
            gap_fill = " " * gap_width
            if opponent_blocks and start_row <= i < start_row + max_opp_rows:
                row_index = i - start_row
                segments = []
                for block in opponent_blocks:
                    art_line = block["lines"][row_index] if row_index < len(block["lines"]) else ""
                    width = block["width"]
                    art_line = pad_ansi(art_line, width)
                    if art_line.strip():
                        if block["color"]:
                            segments.append(block["color"] + art_line + art_color)
                        else:
                            segments.append(art_line)
                    else:
                        segments.append(" " * width)
                inter_pad = 2
                gap_pad = 2
                content = (" " * inter_pad).join(segments)
                visible_width = len(strip_ansi(content))
                content_width = (gap_pad * 2) + visible_width
                pad_left = max(0, (gap_width - content_width) // 2)
                pad_right = max(0, gap_width - content_width - pad_left)
                gap_fill = (
                    (" " * pad_left)
                    + (" " * gap_pad)
                    + content
                    + (" " * gap_pad)
                    + (" " * pad_right)
                )
            art_lines.append(left_line + gap_fill + right_line)
        bottom_objects = scene_data.get("objects_bottom", [])
        if isinstance(bottom_objects, list) and bottom_objects and objects_data is not None:
            layout_seed = scene_data.get("layout_seed")
            if not isinstance(layout_seed, int):
                layout_seed = _random_seed_base(f"scene:{scene_data.get('name', 'forest')}")

            def _repeat_line(line: str, target_width: int) -> str:
                if not line or target_width <= 0:
                    return ""
                repeats = (target_width // len(line)) + 1
                return (line * repeats)[:target_width]

            def _apply_scatter(
                line: str,
                mask: str,
                base_width: int,
                scatter_obj: dict,
                row_index: int,
                side_tag: int
            ) -> tuple[str, str]:
                if not scatter_obj or base_width <= 0:
                    return line, mask
                dynamic = scatter_obj.get("dynamic", {}) if isinstance(scatter_obj, dict) else {}
                if not isinstance(dynamic, dict):
                    return line, mask
                if dynamic.get("mode") != "scatter":
                    return line, mask
                glyphs = dynamic.get("glyphs", [])
                color_keys = dynamic.get("color_keys", [])
                if not isinstance(glyphs, list) or not glyphs:
                    return line, mask
                if not isinstance(color_keys, list) or not color_keys:
                    return line, mask
                chance = float(dynamic.get("scatter_chance", 0.0) or 0.0)
                if chance <= 0:
                    return line, mask
                art_chars = list(line)
                mask_chars = list(mask)
                tiles = max(1, (len(line) + base_width - 1) // base_width)
                for tile_idx in range(tiles):
                    seed = layout_seed ^ (row_index * 0x9E3779B1) ^ (tile_idx * 0x85EBCA77) ^ side_tag
                    if _unit_from(seed) > chance:
                        continue
                    glyph = glyphs[int(_unit_from(seed + 1) * len(glyphs)) % len(glyphs)]
                    color_key = color_keys[int(_unit_from(seed + 2) * len(color_keys)) % len(color_keys)]
                    offset = int(_unit_from(seed + 3) * base_width)
                    pos = tile_idx * base_width + offset
                    if pos < 0 or pos >= len(art_chars):
                        continue
                    art_chars[pos] = str(glyph)[0]
                    mask_chars[pos] = str(color_key)[0]
                return "".join(art_chars), "".join(mask_chars)

            def _render_bottom_line(entry: object, target_width: int, row_index: int, side_tag: int) -> str:
                if target_width <= 0:
                    return ""
                obj_id = entry.get("id") if isinstance(entry, dict) else entry
                if not isinstance(obj_id, str) or not obj_id:
                    return " " * target_width
                obj = objects_data.get(obj_id, {})
                art = obj.get("art", [])
                mask = obj.get("color_mask", [])
                base_line = art[0] if isinstance(art, list) and art else ""
                base_mask = mask[0] if isinstance(mask, list) and mask else (" " * len(base_line))
                if not base_line:
                    return " " * target_width
                base_width = len(base_line)
                line = _repeat_line(base_line, target_width)
                mask_line = _repeat_line(base_mask, target_width)
                scatter_id = entry.get("scatter") if isinstance(entry, dict) else None
                scatter_obj = objects_data.get(scatter_id, {}) if scatter_id else None
                if scatter_obj:
                    line, mask_line = _apply_scatter(line, mask_line, base_width, scatter_obj, row_index, side_tag)
                seed_base = layout_seed ^ (row_index * 0xC2B2AE3D) ^ side_tag
                return apply_mask(
                    line,
                    mask_line,
                    row_index,
                    seed_base,
                    0.0,
                    True,
                    tick,
                    None,
                    "y",
                    0.0,
                    True,
                    len(bottom_objects)
                )

            for row_index, entry in enumerate(bottom_objects):
                left_line = _render_bottom_line(entry, max_left, row_index, 0x1A2B3C4D)
                right_line = _render_bottom_line(entry, max_right, row_index, 0x5E6F7081)
                art_lines.append(left_line + (" " * gap_width) + right_line)
        if ground_rows:
            for row_idx in range(1, min(ground_rows, len(art_lines)) + 1):
                line_index = -row_idx
                full_line = art_lines[line_index]
                left_part = _slice_ansi(full_line, 0, max_left)
                gap_part = _slice_ansi(full_line, max_left, gap_width)
                right_part = _slice_ansi(full_line, max_left + gap_width, max_right)
                merged_gap = _merge_ansi(ground_lines[-row_idx], gap_part)
                art_lines[line_index] = left_part + merged_gap + right_part
        return art_lines, art_color
    forest_template = scene_data.get("art", [])
    forest_art = []
    for i, line in enumerate(forest_template):
        gap_fill = " " * gap_width
        if opponent_blocks:
            max_opp_rows = max((len(block["lines"]) for block in opponent_blocks), default=0)
            start_row = (len(forest_template) - max_opp_rows)
            if start_row <= i < start_row + max_opp_rows:
                row_index = i - start_row
                segments = []
                for block in opponent_blocks:
                    art_line = block["lines"][row_index] if row_index < len(block["lines"]) else ""
                    width = block["width"]
                    art_line = pad_ansi(art_line, width)
                    if art_line.strip():
                        if block["color"]:
                            segments.append(block["color"] + art_line + art_color)
                        else:
                            segments.append(art_line)
                    else:
                        segments.append(" " * width)
                inter_pad = 2
                gap_pad = 2
                content = (" " * inter_pad).join(segments)
                visible_width = len(strip_ansi(content))
                content_width = (gap_pad * 2) + visible_width
                gap_width = max(gap_width, content_width)
                pad_left = max(0, (gap_width - content_width) // 2)
                pad_right = max(0, gap_width - content_width - pad_left)
                gap_fill = (
                    (" " * pad_left)
                    + (" " * gap_pad)
                    + content
                    + (" " * gap_pad)
                    + (" " * pad_right)
                )
        forest_art.append(line.replace("{GAP}", gap_fill))
    return forest_art, art_color


def compute_scene_gap_target(scene_data: dict, opponents: List[Opponent]) -> int:
    if not scene_data:
        return 0
    gap_base = (
        int(scene_data.get("gap_min", 2))
        if scene_data.get("left") or scene_data.get("objects_left")
        else int(scene_data.get("gap_width", 20))
    )
    opponent_blocks = [m for m in opponents if m.art_lines]
    if not opponent_blocks:
        return gap_base
    widest_block = max(OPPONENT_ART_WIDTH, 0)
    blocks_width = widest_block * len(opponent_blocks)
    inter_pad = 2
    gap_pad = 2
    total = blocks_width + (inter_pad * max(0, len(opponent_blocks) - 1)) + (gap_pad * 2)
    return max(gap_base, total)


def render_scene_frame(
    scenes_data,
    commands_data,
    scene_id: str,
    player: Player,
    opponents: List[Opponent],
    message: str,
    gap_override: int,
    objects_data: Optional[object] = None,
    color_map_override: Optional[dict] = None,
    art_opponents: Optional[List[Opponent]] = None,
    flash_index: Optional[int] = None,
    flash_color: Optional[str] = None,
    overlay_target_index: Optional[int] = None,
    overlay_effect: Optional[dict] = None,
    overlay_frame_index: int = 0,
    visible_indices: Optional[set] = None,
    include_bars: bool = True,
    manual_lines_indices: Optional[set] = None,
    suppress_actions: bool = False,
    suppress_narrative: bool = False,
    show_target_prompt: bool = False,
):
    scene_data = scenes_data.get(scene_id, {})
    art_lines, art_color = render_scene_art(
        scene_data,
        art_opponents if art_opponents is not None else opponents,
        gap_override=gap_override,
        flash_index=flash_index,
        flash_color=flash_color,
        overlay_target_index=overlay_target_index,
        overlay_effect=overlay_effect,
        overlay_frame_index=overlay_frame_index,
        visible_indices=visible_indices,
        include_bars=include_bars,
        manual_lines_indices=manual_lines_indices,
        objects_data=objects_data,
        color_map_override=color_map_override,
    )
    alive_source = art_opponents if art_opponents is not None else opponents
    alive = [o for o in alive_source if o.hp > 0]
    if alive:
        if len(alive) > 1:
            body = ["Opponents emerge from the forest."]
        else:
            primary = alive[0]
            body = [f"A {primary.name} {primary.arrival}."]
    else:
        body = ["All is quiet. No enemies in sight."]
    if message:
        lines = [line for line in message.splitlines() if line.strip() != ""]
        if lines:
            body += lines
    if suppress_narrative:
        body = []
    commands = scene_commands(scenes_data, commands_data, scene_id, player, opponents)
    actions = format_action_lines(format_commands(commands))
    if suppress_actions:
        actions = format_action_lines([])
    frame = Frame(
        title="Lokarta - World Maker — PROTOTYPE",
        body_lines=body,
        action_lines=actions,
        stat_lines=format_player_stats(player),
        footer_hint="" if suppress_actions else "Keys: use the action panel",
        location=player.location,
        art_lines=art_lines,
        art_color=art_color,
        status_lines=["Select target (←/→, Enter)"] if show_target_prompt else [],
    )
    render_frame(frame)


def animate_scene_gap(
    scenes_data,
    commands_data,
    scene_id: str,
    player: Player,
    opponents: List[Opponent],
    message: str,
    start_gap: int,
    end_gap: int,
    steps: int = 6,
    delay: float = 0.06,
    art_opponents: Optional[List[Opponent]] = None,
    objects_data: Optional[object] = None,
    color_map_override: Optional[dict] = None
):
    if start_gap == end_gap or steps <= 0:
        return
    for step in range(1, steps + 1):
        t = step / steps
        gap = int(round(start_gap + (end_gap - start_gap) * t))
        render_scene_frame(
            scenes_data,
            commands_data,
            scene_id,
            player,
            opponents,
            message,
            gap,
            objects_data=objects_data,
            color_map_override=color_map_override,
            art_opponents=art_opponents,
            suppress_actions=True,
            suppress_narrative=True
        )
        time.sleep(delay)


def animate_battle_start(
    scenes_data,
    commands_data,
    scene_id: str,
    player: Player,
    opponents: List[Opponent],
    message: str,
    objects_data: Optional[object] = None,
    color_map_override: Optional[dict] = None
):
    if not opponents:
        return
    scene_data = scenes_data.get(scene_id, {})
    gap_base = (
        int(scene_data.get("gap_min", 2))
        if scene_data.get("left") or scene_data.get("objects_left")
        else int(scene_data.get("gap_width", 20))
    )
    gap_target = compute_scene_gap_target(scene_data, opponents)
    animate_scene_gap(
        scenes_data,
        commands_data,
        scene_id,
        player,
        opponents,
        message,
        gap_base,
        gap_target,
        art_opponents=[],
        objects_data=objects_data,
        color_map_override=color_map_override
    )


def animate_battle_end(
    scenes_data,
    commands_data,
    scene_id: str,
    player: Player,
    opponents: List[Opponent],
    message: str,
    objects_data: Optional[object] = None,
    color_map_override: Optional[dict] = None
):
    if not opponents:
        return
    scene_data = scenes_data.get(scene_id, {})
    gap_base = (
        int(scene_data.get("gap_min", 2))
        if scene_data.get("left") or scene_data.get("objects_left")
        else int(scene_data.get("gap_width", 20))
    )
    gap_target = compute_scene_gap_target(scene_data, opponents)
    animate_scene_gap(
        scenes_data,
        commands_data,
        scene_id,
        player,
        opponents,
        message,
        gap_target,
        gap_base,
        art_opponents=[],
        objects_data=objects_data,
        color_map_override=color_map_override
    )


def flash_opponent(
    scenes_data,
    commands_data,
    scene_id: str,
    player: Player,
    opponents: List[Opponent],
    message: str,
    index: Optional[int],
    flash_color: str,
    objects_data: Optional[object] = None,
    color_map_override: Optional[dict] = None
):
    if index is None:
        return
    scene_data = scenes_data.get(scene_id, {})
    gap_target = compute_scene_gap_target(scene_data, opponents)
    render_scene_frame(
        scenes_data,
        commands_data,
        scene_id,
        player,
        opponents,
        message,
        gap_target,
        objects_data=objects_data,
        color_map_override=color_map_override,
        flash_index=index,
        flash_color=flash_color,
        suppress_actions=True,
        suppress_narrative=True
    )
    time.sleep(max(0.08, battle_action_delay(player) / 2))


def animate_spell_overlay(
    scenes_data,
    commands_data,
    scene_id: str,
    player: Player,
    opponents: List[Opponent],
    message: str,
    index: Optional[int],
    effect: dict,
    objects_data: Optional[object] = None,
    color_map_override: Optional[dict] = None
):
    if index is None:
        return
    frames = effect.get("frames", [])
    if not isinstance(frames, list) or not frames:
        return
    loops = int(effect.get("loops", 1) or 1)
    frame_delay = float(effect.get("frame_delay", 0.06) or 0.06)
    scene_data = scenes_data.get(scene_id, {})
    gap_target = compute_scene_gap_target(scene_data, opponents)
    art_overrides = []
    for i, current in enumerate(opponents):
        if i == index and current.hp <= 0:
            art_overrides.append(replace(current, hp=1))
        else:
            art_overrides.append(current)
    for _ in range(max(1, loops)):
        for frame_index in range(len(frames)):
            render_scene_frame(
                scenes_data,
                commands_data,
                scene_id,
                player,
                opponents,
                message,
                gap_target,
                objects_data=objects_data,
                color_map_override=color_map_override,
                art_opponents=art_overrides,
                overlay_target_index=index,
                overlay_effect=effect,
                overlay_frame_index=frame_index,
                suppress_actions=True,
                suppress_narrative=True
            )
            time.sleep(max(0.03, min(frame_delay, battle_action_delay(player))))


def melt_opponent(
    scenes_data,
    commands_data,
    scene_id: str,
    player: Player,
    opponents: List[Opponent],
    message: str,
    index: Optional[int],
    objects_data: Optional[object] = None,
    color_map_override: Optional[dict] = None
):
    if index is None:
        return
    if index < 0 or index >= len(opponents):
        return
    opponent = opponents[index]
    if not opponent.art_lines:
        return
    width = OPPONENT_ART_WIDTH
    raw_lines = [line[:width].rstrip() for line in opponent.art_lines]
    max_len = max((len(line) for line in raw_lines), default=0)
    left_aligned = [line.ljust(max_len) for line in raw_lines]
    display_lines = [line.center(width) for line in left_aligned]
    scene_data = scenes_data.get(scene_id, {})
    gap_target = compute_scene_gap_target(scene_data, opponents)
    for removed in range(1, len(display_lines) + 1):
        trimmed = (
            [" " * width for _ in range(removed)]
            + display_lines[removed:]
        )
        art_overrides = []
        for i, current in enumerate(opponents):
            if i == index:
                art_overrides.append(replace(current, art_lines=trimmed, hp=1))
            else:
                art_overrides.append(current)
        render_scene_frame(
            scenes_data,
            commands_data,
            scene_id,
            player,
            opponents,
            message,
            gap_target,
            objects_data=objects_data,
            color_map_override=color_map_override,
            art_opponents=art_overrides,
            manual_lines_indices={index},
            suppress_actions=True,
            suppress_narrative=True
        )
        time.sleep(max(0.05, battle_action_delay(player) / 3))


def animate_art_transition(
    frame_from: Frame,
    frame_to: Frame,
    player: Player,
    pause_ticks: int = 2,
) -> None:
    from_lines = frame_from.art_lines or []
    to_lines = frame_to.art_lines or []
    height = max(len(from_lines), len(to_lines))
    if height <= 0:
        return
    from_padded = ([""] * (height - len(from_lines))) + list(from_lines)
    to_padded = ([""] * (height - len(to_lines))) + list(to_lines)
    blank_lines = [""] * height
    delay = max(0.05, battle_action_delay(player) / 3) / 4
    blank_actions = format_action_lines([])

    for removed in range(1, height + 1):
        lines = ([""] * removed) + from_padded[removed:]
        frame = replace(
            frame_from,
            art_lines=lines,
            body_lines=[],
            status_lines=[],
            action_lines=blank_actions,
        )
        render_frame(frame)
        time.sleep(delay)

    pause_frame = replace(
        frame_to,
        art_lines=blank_lines,
        body_lines=[],
        status_lines=[],
        action_lines=blank_actions,
    )
    for _ in range(max(0, pause_ticks)):
        render_frame(pause_frame)
        time.sleep(delay)

    for visible in range(1, height + 1):
        lines = ([""] * (height - visible)) + to_padded[height - visible:]
        frame = replace(
            frame_to,
            art_lines=lines,
            body_lines=[],
            status_lines=[],
            action_lines=blank_actions,
        )
        render_frame(frame)
        time.sleep(delay)


def format_player_stats(player: Player) -> List[str]:
    hp_text = color(f"HP: {player.hp} / {player.max_hp}", ANSI.FG_GREEN)
    mp_text = color(f"MP: {player.mp} / {player.max_mp}", ANSI.FG_MAGENTA)
    atk_text = color(f"ATK: {player.atk}", ANSI.DIM)
    def_text = color(f"DEF: {player.defense}", ANSI.DIM)
    level_text = color(f"Level: {player.level}", ANSI.FG_CYAN)
    xp_text = color(f"XP: {player.xp}", ANSI.FG_GREEN)
    gp_text = color(f"GP: {player.gold}", ANSI.FG_YELLOW)
    return [
        f"{hp_text}  {mp_text}  {atk_text}  {def_text}",
        f"{level_text}    {xp_text}    {gp_text}",
    ]


def clear_screen():
    sys.stdout.write("\033[H\033[J")
    sys.stdout.flush()



def format_gradient_location_text(location: str) -> str:
    """Applies a gradient color effect to the location text and its embellishments."""
    left_embellishment = "*-----<{([  "
    right_embellishment = "  ])}>-----*"

    def _truecolor(r, g, b):
        return f"\033[38;2;{r};{g};{b}m"

    def _gradient(text, start_color, end_color):
        colored_text = ""
        n = len(text)
        for i, char in enumerate(text):
            r = int(start_color[0] + (end_color[0] - start_color[0]) * i / (n - 1))
            g = int(start_color[1] + (end_color[1] - start_color[1]) * i / (n - 1))
            b = int(start_color[2] + (end_color[2] - start_color[2]) * i / (n - 1))
            colored_text += f"{_truecolor(r, g, b)}{char}"
        return colored_text

    start_color = (192, 192, 192)
    end_color = (0, 0, 128)

    left_colored = _gradient(left_embellishment, start_color, end_color)
    right_colored = _gradient(right_embellishment, end_color, start_color)

    return f"{left_colored}{ANSI.FG_WHITE}{location}{right_colored}{ANSI.RESET}"


def render_frame(frame: Frame):
    sys.stdout.write(ANSI.CURSOR_HIDE)
    clear_screen()
    output = []
    cols, rows = SCREEN_WIDTH, SCREEN_HEIGHT
    pad_left = 0
    pad_right = 0
    pad_top = 0
    pad_bottom = 0

    def _truecolor(r: int, g: int, b: int) -> str:
        return f"\033[38;2;{r};{g};{b}m"

    def _gradient_rgb(x: int, y: int, width: int, height: int) -> tuple[int, int, int]:
        return gradient_rgb(x, y, width, height)

    def _gradient_char(x: int, y: int, width: int, height: int, ch: str) -> str:
        r, g, b = _gradient_rgb(x, y, width, height)
        return _truecolor(r, g, b) + ch + ANSI.RESET

    def _gradient_line(y: int, line: str) -> str:
        width = len(line)
        height = SCREEN_HEIGHT
        out = []
        for x, ch in enumerate(line):
            out.append(_gradient_char(x, y, width, height, ch))
        return "".join(out)

    def _gradient_segment(y: int, start_x: int, text: str) -> str:
        out = []
        for i, ch in enumerate(text):
            x = start_x + i
            out.append(_gradient_char(x, y, SCREEN_WIDTH, SCREEN_HEIGHT, ch))
        return "".join(out)

    def _compose_line(_y: int, canvas_line: str) -> str:
        return canvas_line

    def _bg_for_row(y: int, x: int) -> str:
        # Solid background (no gradient).
        r, g, b = (50, 50, 50)
        return f"\033[48;2;{r};{g};{b}m"

    def _apply_bg(line: str, y: int) -> str:
        out = []
        vis_x = 0
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == "\x1b" and i + 1 < len(line) and line[i + 1] == "[":
                j = i + 2
                while j < len(line) and line[j] != "m":
                    j += 1
                if j < len(line):
                    out.append(line[i:j + 1])
                    i = j + 1
                    continue
            bg = _bg_for_row(y, vis_x)
            out.append(bg + ch)
            vis_x += 1
            i += 1
        out.append(ANSI.RESET)
        return "".join(out)

    def _gradient_content_line(y: int, content: str) -> str:
        out = []
        for i, ch in enumerate(content):
            x = i + 1  # content starts after left border
            out.append(_gradient_char(x, y, SCREEN_WIDTH, SCREEN_HEIGHT, ch))
        return "".join(out)

    row_idx = 0
    abs_row_base = 0
    top_border = "+" + "-" * (SCREEN_WIDTH - 2) + "+"
    output.append(_compose_line(abs_row_base + row_idx, _apply_bg(_gradient_line(row_idx, top_border), row_idx)))
    row_idx += 1

    gradient_location = format_gradient_location_text(frame.location)
    location_row = center_ansi(gradient_location, SCREEN_WIDTH - 2)



    used_rows = (
        1 +  # top border
        1 +  # location line
        1 +  # location separator border
        1 +  # actions separator border
        len(frame.action_lines) +
        1 +  # stat separator border
        STAT_LINES +
        1    # bottom border
    )
    body_height = SCREEN_HEIGHT - used_rows

    left_border = _gradient_char(0, row_idx, SCREEN_WIDTH, SCREEN_HEIGHT, "|")
    right_border = _gradient_char(SCREEN_WIDTH - 1, row_idx, SCREEN_WIDTH, SCREEN_HEIGHT, "|")
    output.append(_compose_line(abs_row_base + row_idx, _apply_bg(left_border + location_row + right_border, row_idx)))
    row_idx += 1
    sep_border = "+" + "-" * (SCREEN_WIDTH - 2) + "+"
    output.append(_compose_line(abs_row_base + row_idx, _apply_bg(_gradient_line(row_idx, sep_border), row_idx)))
    row_idx += 1

    status_lines = frame.status_lines[:]
    art_count = len(frame.art_lines)
    divider_count = 1 if art_count > 0 else 0
    max_status = max(0, body_height - art_count - divider_count)
    if len(status_lines) > max_status:
        status_lines = status_lines[-max_status:]
    status_count = len(status_lines)

    narrative_space = body_height - art_count - divider_count - status_count
    narrative_space = max(0, narrative_space)
    body_rows = []

    for i in range(art_count):
        art_line = frame.art_lines[i]
        cropped = center_crop_ansi(
            art_line,
            SCREEN_WIDTH - 2,
            anchor_x=frame.art_anchor_x
        )
        if len(strip_ansi(cropped)) < (SCREEN_WIDTH - 2):
            cropped = center_ansi(cropped, SCREEN_WIDTH - 2)
        styled = color(cropped, frame.art_color)
        body_rows.append(styled)

    divider_row = None
    if art_count > 0:
        divider_row = "-" * (SCREEN_WIDTH - 2)
        body_rows.append(divider_row)

    if frame.location == "Forest":
        visible_lines = frame.body_lines[-narrative_space:] if narrative_space > 0 else []
    else:
        visible_lines = frame.body_lines[:narrative_space]

    for i in range(narrative_space):
        raw = visible_lines[i] if i < len(visible_lines) else ""
        if raw:
            raw = (" " * NARRATIVE_INDENT) + raw
        body_rows.append(pad_or_trim_ansi(raw, SCREEN_WIDTH - 2))

    for line in status_lines:
        colored = color(line, ANSI.FG_YELLOW)
        body_rows.append(center_ansi(colored, SCREEN_WIDTH - 2))

    for i in range(body_height):
        line = body_rows[i] if i < len(body_rows) else ""
        left_border = _gradient_char(0, row_idx, SCREEN_WIDTH, SCREEN_HEIGHT, "|")
        right_border = _gradient_char(SCREEN_WIDTH - 1, row_idx, SCREEN_WIDTH, SCREEN_HEIGHT, "|")
        if divider_row is not None and i < len(body_rows) and body_rows[i] == divider_row:
            line = _gradient_content_line(row_idx, divider_row)
        output.append(_compose_line(abs_row_base + row_idx, _apply_bg(left_border + line + right_border, row_idx)))
        row_idx += 1

    actions_label = "Actions"
    actions_label_row = actions_label.center(SCREEN_WIDTH - 2, "-")
    label_start = actions_label_row.find(actions_label)
    label_end = label_start + len(actions_label) if label_start != -1 else 0
    left_border = _gradient_char(0, row_idx, SCREEN_WIDTH, SCREEN_HEIGHT, "+")
    right_border = _gradient_char(SCREEN_WIDTH - 1, row_idx, SCREEN_WIDTH, SCREEN_HEIGHT, "+")
    left_content = actions_label_row[:label_start] if label_start != -1 else actions_label_row
    mid_label = actions_label if label_start != -1 else ""
    right_content = actions_label_row[label_end:] if label_start != -1 else ""
    output.append(_compose_line(abs_row_base + row_idx, _apply_bg(
        left_border
        + _gradient_segment(row_idx, 1, left_content)
        + color(mid_label, ANSI.FG_WHITE, ANSI.BOLD)
        + _gradient_segment(row_idx, 1 + len(left_content) + len(mid_label), right_content)
        + right_border,
        row_idx
    )))
    row_idx += 1

    for i in range(len(frame.action_lines)):
        line = frame.action_lines[i] if i < len(frame.action_lines) else ""
        left_border = _gradient_char(0, row_idx, SCREEN_WIDTH, SCREEN_HEIGHT, "|")
        right_border = _gradient_char(SCREEN_WIDTH - 1, row_idx, SCREEN_WIDTH, SCREEN_HEIGHT, "|")
        output.append(_compose_line(abs_row_base + row_idx, _apply_bg(
            left_border
            + pad_or_trim_ansi(line, SCREEN_WIDTH - 2)
            + right_border,
            row_idx
        )))
        row_idx += 1

    stats_label = "Player-Stats"
    stats_label_row = stats_label.center(SCREEN_WIDTH - 2, "-")
    label_start = stats_label_row.find(stats_label)
    label_end = label_start + len(stats_label) if label_start != -1 else 0
    left_border = _gradient_char(0, row_idx, SCREEN_WIDTH, SCREEN_HEIGHT, "+")
    right_border = _gradient_char(SCREEN_WIDTH - 1, row_idx, SCREEN_WIDTH, SCREEN_HEIGHT, "+")
    left_content = stats_label_row[:label_start] if label_start != -1 else stats_label_row
    mid_label = stats_label if label_start != -1 else ""
    right_content = stats_label_row[label_end:] if label_start != -1 else ""
    output.append(_compose_line(abs_row_base + row_idx, _apply_bg(
        left_border
        + _gradient_segment(row_idx, 1, left_content)
        + color(mid_label, ANSI.FG_WHITE, ANSI.BOLD)
        + _gradient_segment(row_idx, 1 + len(left_content) + len(mid_label), right_content)
        + right_border,
        row_idx
    )))
    row_idx += 1
    for i in range(STAT_LINES):
        raw = frame.stat_lines[i] if i < len(frame.stat_lines) else ""
        styled = raw
        if raw.startswith("HP:"):
            styled = color(raw, ANSI.FG_RED)
        elif raw.startswith("Level:"):
            styled = color(raw, ANSI.FG_YELLOW)
        elif raw.startswith("Name:"):
            styled = color(raw, ANSI.FG_GREEN, ANSI.BOLD)
        elif raw.startswith("Location:"):
            styled = color(raw, ANSI.FG_CYAN)

        centered = center_ansi(styled, SCREEN_WIDTH - 2)
        left_border = _gradient_char(0, row_idx, SCREEN_WIDTH, SCREEN_HEIGHT, "|")
        right_border = _gradient_char(SCREEN_WIDTH - 1, row_idx, SCREEN_WIDTH, SCREEN_HEIGHT, "|")
        output.append(_compose_line(abs_row_base + row_idx, _apply_bg(left_border + centered + right_border, row_idx)))
        row_idx += 1

    bottom_border = "+" + "-" * (SCREEN_WIDTH - 2) + "+"
    output.append(_compose_line(abs_row_base + row_idx, _apply_bg(_gradient_line(row_idx, bottom_border), row_idx)))
    row_idx += 1

    sys.stdout.write("\n".join(output) + "\n")
    sys.stdout.write(ANSI.CURSOR_SHOW)
    sys.stdout.flush()


def format_opponent_bar(opponent: Opponent) -> str:
    if opponent.max_hp <= 0:
        ratio = 0
    else:
        ratio = max(0.0, min(1.0, opponent.hp / opponent.max_hp))
    filled = int(ratio * (OPPONENT_ART_WIDTH - 2))
    filled = max(0, min(OPPONENT_ART_WIDTH - 2, filled))
    bar = "#" * filled + "_" * ((OPPONENT_ART_WIDTH - 2) - filled)
    return (
        ANSI.FG_WHITE
        + "["
        + ANSI.FG_GREEN + ("#" * filled)
        + ANSI.FG_WHITE + ("_" * ((OPPONENT_ART_WIDTH - 2) - filled))
        + "]"
    )
