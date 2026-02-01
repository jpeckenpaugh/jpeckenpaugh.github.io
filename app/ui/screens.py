"""Screen composition helpers for game UI states."""

import random
import textwrap
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import List, Optional

from app.commands.scene_commands import command_is_enabled, format_commands, scene_commands
from app.data_access.commands_data import CommandsData
from app.data_access.colors_data import ColorsData
from app.data_access.continents_data import ContinentsData
from app.data_access.frames_data import FramesData
from app.data_access.glyphs_data import GlyphsData
from app.data_access.elements_data import ElementsData
from app.data_access.spells_art_data import SpellsArtData
from app.data_access.items_data import ItemsData
from app.data_access.menus_data import MenusData
from app.data_access.npcs_data import NpcsData
from app.data_access.objects_data import ObjectsData
from app.data_access.opponents_data import OpponentsData
from app.data_access.quests_data import QuestsData
from app.data_access.scenes_data import ScenesData
from app.data_access.spells_data import SpellsData
from app.data_access.stories_data import StoriesData
from app.data_access.title_screen_data import TitleScreenData
from app.data_access.venues_data import VenuesData
from app.data_access.text_data import TextData
from app.models import Frame, Player, Opponent
from app.ui.ansi import ANSI
from app.ui.layout import format_action_lines, format_command_lines, format_menu_actions, pad_or_trim_ansi, strip_ansi
from app.ui.constants import SCREEN_WIDTH, SCREEN_HEIGHT
from app.ui.rendering import (
    COLOR_BY_NAME,
    element_color_map,
    format_player_stats,
    render_scene_art,
    render_venue_art,
    render_venue_objects,
)
from app.ui.text import format_text
from app.venues import render_venue_body, venue_id_from_state


@dataclass
class ScreenContext:
    items: ItemsData
    opponents: OpponentsData
    scenes: ScenesData
    npcs: NpcsData
    objects: ObjectsData
    venues: VenuesData
    menus: MenusData
    commands: CommandsData
    spells: SpellsData
    text: TextData
    colors: ColorsData
    frames: FramesData
    continents: ContinentsData
    elements: ElementsData
    abilities: object
    spells_art: SpellsArtData
    glyphs: GlyphsData
    save_data: object
    quests: QuestsData
    stories: StoriesData
    title_screen: TitleScreenData


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


def _slice_ansi_wrap(text: str, start: int, width: int) -> str:
    visible = strip_ansi(text)
    vis_len = len(visible)
    if width <= 0:
        return ""
    if vis_len == 0:
        return " " * width
    start = start % vis_len
    if start + width <= vis_len:
        return _slice_ansi(text, start, width)
    first = vis_len - start
    return _slice_ansi(text, start, first) + _slice_ansi(text, 0, width - first)


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


def _title_state_config(
    ctx: ScreenContext,
    player,
    selected_index: int,
    menu_stack: list[str],
) -> tuple[list[str], list[dict], list[str]]:
    title_data = ctx.title_screen.all() if hasattr(ctx, "title_screen") else {}
    if title_data.get("version") != 2:
        scene_data = ctx.scenes.get("title", {})
        return scene_data.get("narrative", []), scene_commands(ctx.scenes, ctx.commands, "title", player, []), []
    menus = title_data.get("menus", {}) if isinstance(title_data, dict) else {}
    menu_id = menu_stack[-1] if menu_stack else title_data.get("root_menu", "title_root")
    if getattr(player, "title_name_input", False):
        menu_id = "title_name_input"
    if getattr(player, "title_name_select", False):
        menu_id = "title_name"
    if getattr(player, "title_confirm", False):
        menu_id = "title_confirm"
    if getattr(player, "title_fortune", False):
        menu_id = "title_fortune"
    if getattr(player, "title_slot_select", False):
        menu_id = "title_slot_select"
    if getattr(player, "title_start_confirm", False):
        menu_id = "title_start_confirm"
    menu_data = menus.get(menu_id, {}) if isinstance(menus, dict) else {}
    narrative = menu_data.get("narrative", [])
    if not isinstance(narrative, list):
        narrative = []
    items = menu_data.get("items", [])
    if items == "slot_select":
        summaries = []
        if hasattr(ctx, "save_data") and ctx.save_data:
            summaries = ctx.save_data.slot_summaries_sorted(max_slots=100)
        mode = getattr(player, "title_slot_mode", "continue")
        built = []
        for summary in summaries:
            slot_num = summary.get("slot", 0)
            if summary.get("empty"):
                label = f"{slot_num}.) Empty"
            else:
                level = summary.get("level", 1)
                location = summary.get("location", "Town")
                gold = summary.get("gold", 0)
                name = summary.get("name", "WARRIOR")
                element = summary.get("current_element")
                if hasattr(ctx, "continents") and element:
                    location = ctx.continents.name_for(str(element)) or location
                label = f"{slot_num}.) {name} Lv{level} {location} GP{gold}"
            entry = {"label": label, "command": f"TITLE_SLOT_{slot_num}"}
            built.append(entry)
        if not built:
            narrative = list(narrative)
            narrative.append("No save data found.")
        built.append({"label": "Back", "command": "TITLE_SLOT_BACK"})
        items = built
    detail_lines = menu_data.get("detail_lines", [])
    if isinstance(detail_lines, list) and detail_lines:
        narrative = list(narrative)
        narrative.append("")
        narrative.append(detail_lines[min(max(selected_index, 0), len(detail_lines) - 1)])
    if menu_id == "title_start_confirm":
        pending_name = str(getattr(player, "title_pending_name", "") or "WARRIOR")
        pending_fortune = str(getattr(player, "title_pending_fortune", "") or "")
        fortune_map = {
            "FORTUNE_POOR": "Poor (10 GP)",
            "FORTUNE_WELL_OFF": "Well-Off (100 GP)",
            "FORTUNE_ROYALTY": "Royalty (1,000 GP)",
        }
        fortune_label = fortune_map.get(pending_fortune, "Unknown")
        narrative = list(narrative)
        narrative.append("")
        narrative.append(f"Name: {pending_name[:16]}")
        narrative.append(f"Fortune: {fortune_label}")
    if not isinstance(items, list):
        items = []
    commands = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        cmd_entry = dict(entry)
        if cmd_entry.get("submenu"):
            cmd_entry["command"] = f"TITLE_MENU_SUB:{cmd_entry.get('submenu')}"
        if cmd_entry.get("back"):
            cmd_entry["command"] = "TITLE_MENU_BACK"
        commands.append(cmd_entry)
    filtered = []
    for entry in commands:
        if not isinstance(entry, dict):
            continue
        when = entry.get("when")
        if when == "has_save" and not getattr(player, "has_save", False):
            continue
        cmd_entry = dict(entry)
        if not command_is_enabled(cmd_entry, player, []):
            cmd_entry["_disabled"] = True
        filtered.append(cmd_entry)
    commands = filtered
    return narrative, commands, detail_lines if isinstance(detail_lines, list) else []


def _draw_box(width: int, height: int, *, style: str = "round") -> list[str]:
    width = max(2, width)
    height = max(2, height)
    if style == "round":
        tl = tr = bl = br = "o"
    else:
        tl = tr = bl = br = "+"
    top = tl + ("-" * (width - 2)) + tr
    bottom = bl + ("-" * (width - 2)) + br
    middle = "|" + (" " * (width - 2)) + "|"
    lines = [top]
    for _ in range(height - 2):
        lines.append(middle)
    lines.append(bottom)
    return lines


def _title_menu_lines(
    menu_cfg: dict,
    narrative: list[str],
    commands: list[dict],
    selected_index: int,
    detail_lines: Optional[list[str]] = None,
) -> tuple[list[str], int, int, int]:
    center_x = int(menu_cfg.get("x", SCREEN_WIDTH // 2) or (SCREEN_WIDTH // 2))
    center_y = int(menu_cfg.get("y", SCREEN_HEIGHT // 2) or (SCREEN_HEIGHT // 2))
    margin = int(menu_cfg.get("margin", 1) or 1)
    margin = max(0, min(margin, 10))
    width = int(menu_cfg.get("width", 0) or 0)
    height = int(menu_cfg.get("height", 0) or 0)
    style = str(menu_cfg.get("frame_style", "round") or "round")
    box_lines = _draw_box(width, height, style=style)
    content_lines = list(narrative)
    spacer = content_lines and content_lines[-1] != ""
    labels = format_commands(commands)
    display_labels = []
    for idx, line in enumerate(labels):
        if selected_index >= 0 and idx == selected_index:
            line = f"> {line.strip()}"
        display_labels.append(line)
    max_label_len = max((len(strip_ansi(line)) for line in display_labels), default=0)
    max_content = max((len(strip_ansi(line)) for line in content_lines), default=0)
    max_content = max(max_content, max_label_len)
    if detail_lines:
        max_detail = max((len(strip_ansi(line)) for line in detail_lines), default=0)
        max_content = max(max_content, max_detail)
    if width <= 0:
        width = min(SCREEN_WIDTH - 2, max(10, max_content + 2 + (margin * 2)))
    if height <= 0:
        desired = len(content_lines) + (1 if spacer else 0) + len(display_labels) + 2 + (margin * 2)
        height = min(SCREEN_HEIGHT - 2, max(3, desired))
    width = min(width, SCREEN_WIDTH - 2)
    height = max(3, min(height, SCREEN_HEIGHT - 2))
    box_lines = _draw_box(width, height, style=style)
    inner_width = width - 2
    inner_height = height - 2
    available_lines = max(0, inner_height - (margin * 2))
    if content_lines:
        if spacer:
            content_lines.append("")
        available_lines = max(1, available_lines - len(content_lines))
    offset = 0
    if display_labels and selected_index >= 0:
        if selected_index < offset:
            offset = selected_index
        elif selected_index >= offset + available_lines:
            offset = selected_index - available_lines + 1
    visible_labels = display_labels[offset:offset + available_lines]
    content = [" " * inner_width for _ in range(inner_height)]
    inner_content_width = max(0, inner_width - (margin * 2))
    cursor_row = margin
    if content_lines:
        for line in content_lines:
            if cursor_row >= inner_height - margin:
                break
            content[cursor_row] = (
                (" " * margin) + pad_or_trim_ansi(line, inner_content_width) + (" " * margin)
            )
            cursor_row += 1
    for line in visible_labels:
        if cursor_row >= inner_height - margin:
            break
        content[cursor_row] = (
            (" " * margin) + pad_or_trim_ansi(line, inner_content_width) + (" " * margin)
        )
        cursor_row += 1
    for i in range(inner_height):
        box_lines[i + 1] = "|" + content[i] + "|"
    menu_lines = []
    start_x = max(0, min(SCREEN_WIDTH - width, center_x - (width // 2)))
    start_y = max(0, min(SCREEN_HEIGHT - height, center_y - (height // 2)))
    for line in box_lines:
        prefix = " " * max(0, start_x)
        menu_lines.append(pad_or_trim_ansi(prefix + line, SCREEN_WIDTH))
    return menu_lines, start_y, start_x, width


def _title_keyboard_lines(
    menu_cfg: dict,
    name_buffer: str,
    cursor: tuple[int, int],
    shift_lock: bool,
) -> tuple[list[str], int, int, int]:
    center_x = int(menu_cfg.get("x", SCREEN_WIDTH // 2) or (SCREEN_WIDTH // 2))
    center_y = int(menu_cfg.get("y", SCREEN_HEIGHT // 2) or (SCREEN_HEIGHT // 2))
    margin = int(menu_cfg.get("margin", 1) or 1)
    margin = max(0, min(margin, 10))
    width = int(menu_cfg.get("width", 0) or 0)
    height = int(menu_cfg.get("height", 0) or 0)
    style = str(menu_cfg.get("frame_style", "round") or "round")
    keyboard = [
        ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
        ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        ["K", "L", "M", "N", "O", "P", "Q", "R", "S", "T"],
        ["U", "V", "W", "X", "Y", "Z", "-", "'", " ", "<"],
        ["SHIFT", "DONE", "CANCEL"],
    ]
    row = max(0, min(int(cursor[0]), len(keyboard) - 1))
    col = max(0, min(int(cursor[1]), len(keyboard[row]) - 1))
    case_label = "UPPER" if shift_lock else "lower"
    name_line = f"Name: {name_buffer[:16]} ({case_label})"
    content_lines = [name_line, ""]
    for r_idx, row_keys in enumerate(keyboard):
        cell_width = max(len(label) for label in row_keys)
        parts = []
        for c_idx, label in enumerate(row_keys):
            if label.isalpha():
                label = label.upper() if shift_lock else label.lower()
            padded = label.ljust(cell_width)
            if r_idx == row and c_idx == col:
                parts.append(f"[{padded}]")
            else:
                parts.append(f" {padded} ")
        content_lines.append(" ".join(parts))
    max_content = max((len(strip_ansi(line)) for line in content_lines), default=0)
    if width <= 0:
        width = min(SCREEN_WIDTH - 2, max(10, max_content + 2 + (margin * 2)))
    if height <= 0:
        desired = len(content_lines) + 2 + (margin * 2)
        height = min(SCREEN_HEIGHT - 2, max(3, desired))
    width = min(width, SCREEN_WIDTH - 2)
    height = max(3, min(height, SCREEN_HEIGHT - 2))
    box_lines = _draw_box(width, height, style=style)
    inner_width = width - 2
    inner_height = height - 2
    content = [" " * inner_width for _ in range(inner_height)]
    inner_content_width = max(0, inner_width - (margin * 2))
    cursor_row = margin
    for line in content_lines:
        if cursor_row >= inner_height - margin:
            break
        content[cursor_row] = (" " * margin) + pad_or_trim_ansi(line, inner_content_width) + (" " * margin)
        cursor_row += 1
    for i in range(inner_height):
        box_lines[i + 1] = "|" + content[i] + "|"
    menu_lines = []
    start_x = max(0, min(SCREEN_WIDTH - width, center_x - (width // 2)))
    start_y = max(0, min(SCREEN_HEIGHT - height, center_y - (height // 2)))
    for line in box_lines:
        prefix = " " * max(0, start_x)
        menu_lines.append(pad_or_trim_ansi(prefix + line, SCREEN_WIDTH))
    return menu_lines, start_y, start_x, width


def _truecolor(hex_code: str) -> str:
    value = hex_code.lstrip("#")
    if len(value) != 6:
        return ""
    try:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
    except ValueError:
        return ""
    return f"\033[38;2;{r};{g};{b}m"


def _color_code_for_key(colors: dict, key: str) -> str:
    if not key:
        return ""
    entry = colors.get(key)
    if isinstance(entry, dict):
        hex_code = entry.get("hex", "") if isinstance(entry.get("hex"), str) else ""
        name = entry.get("name", "") if isinstance(entry.get("name"), str) else ""
    elif isinstance(entry, str):
        hex_code = ""
        name = entry
    else:
        return ""
    name = name.strip()
    hex_code = hex_code.strip()
    if not hex_code:
        hex_start = name.find("#")
        hex_code = name[hex_start:] if hex_start != -1 else ""
    if hex_code:
        code = _truecolor(hex_code)
        if code:
            return code
    lowered = name.lower()
    if lowered == "brown":
        return ANSI.FG_YELLOW + ANSI.DIM
    if lowered in ("gray", "grey"):
        return ANSI.FG_WHITE + ANSI.DIM
    return COLOR_BY_NAME.get(lowered, "")


def _color_key_to_rgb(colors: dict, key: str) -> Optional[tuple[int, int, int]]:
    entry = colors.get(key)
    if isinstance(entry, dict):
        hex_code = entry.get("hex", "") if isinstance(entry.get("hex"), str) else ""
        name = entry.get("name", "") if isinstance(entry.get("name"), str) else ""
    elif isinstance(entry, str):
        hex_code = ""
        name = entry
    else:
        return None
    name = name.strip()
    hex_code = hex_code.strip()
    if not hex_code:
        hex_start = name.find("#")
        hex_code = name[hex_start:] if hex_start != -1 else ""
    if not hex_code:
        return None
    value = hex_code.lstrip("#")
    if len(value) != 6:
        return None
    try:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
    except ValueError:
        return None
    return (r, g, b)

def _color_codes_by_key(colors: dict) -> dict:
    if not isinstance(colors, dict):
        return {}
    codes = {}
    for key in colors:
        if not isinstance(key, str):
            continue
        code = _color_code_for_key(colors, key)
        if code:
            codes[key] = code
    return codes


def _colorize_effect_line(line: str, code: str) -> str:
    if not code:
        return line
    out = []
    for ch in line:
        if ch == " ":
            out.append(" ")
        else:
            out.append(f"{code}{ch}{ANSI.RESET}")
    return "".join(out)


def _colorize_effect_line_map(line: str, color_map: dict, color_codes: dict, glyph: Optional[str] = None) -> str:
    if not color_map or not color_codes:
        return line
    out = []
    for ch in line:
        if ch == " ":
            out.append(" ")
            continue
        if ch in color_map:
            key = color_map.get(ch)
            code = color_codes.get(key, "")
            if code:
                out.append(f"{code}{glyph or ch}{ANSI.RESET}")
                continue
        out.append(ch)
    return "".join(out)



def _spell_preview_lines(
    frame_art: List[str],
    effect: Optional[dict],
    color_code: str,
    frame_index: int,
    color_codes: Optional[dict] = None,
    color_map: Optional[dict] = None,
    glyph: Optional[str] = None,
) -> List[str]:
    if not frame_art:
        return []
    width = max(len(line) for line in frame_art)
    lines = [line.ljust(width) for line in frame_art]
    interior = []
    for idx, line in enumerate(lines):
        left = line.find("|")
        if left == -1:
            continue
        right = line.rfind("|")
        if right <= left:
            continue
        interior.append((idx, left, right))
    if not interior:
        return lines
    inner_width = min((right - left - 1) for _, left, right in interior)
    inner_height = len(interior)
    content_lines = []
    mask_lines = []
    if isinstance(effect, dict):
        frames = effect.get("frames", [])
        mask_frames = effect.get("mask_frames", [])
        if isinstance(frames, list) and frames:
            frame = frames[frame_index % len(frames)]
            if isinstance(frame, list):
                content_lines = [str(row) for row in frame]
            if isinstance(mask_frames, list) and mask_frames:
                mask_frame = mask_frames[frame_index % len(mask_frames)]
                if isinstance(mask_frame, list):
                    mask_lines = [str(row) for row in mask_frame]
    content_height = len(content_lines)
    content_width = max((len(row) for row in content_lines), default=0)
    top_pad = max(0, (inner_height - content_height) // 2)
    left_pad = max(0, (inner_width - content_width) // 2)
    for row, (line_idx, left, right) in enumerate(interior):
        if row < top_pad or row >= top_pad + content_height:
            content = " " * inner_width
        else:
            src = content_lines[row - top_pad][:inner_width]
            content = (" " * left_pad) + src
            if len(content) < inner_width:
                content = content.ljust(inner_width)
            else:
                content = content[:inner_width]
        if color_map and color_codes and mask_lines:
            mask_index = row - top_pad
            mask_row = mask_lines[mask_index] if 0 <= mask_index < len(mask_lines) else ""
            if mask_row:
                padded_mask = (" " * left_pad) + mask_row
                if len(padded_mask) < inner_width:
                    padded_mask = padded_mask.ljust(inner_width)
                else:
                    padded_mask = padded_mask[:inner_width]
                mapped = ""
                for idx, ch in enumerate(content):
                    mask_ch = padded_mask[idx] if idx < len(padded_mask) else ""
                    if ch == " ":
                        mapped += " "
                        continue
                    key = color_map.get(mask_ch, "") if mask_ch else ""
                    code = color_codes.get(key, "") if key else ""
                    if code:
                        mapped += f"{code}{glyph or ch}{ANSI.RESET}"
                    else:
                        mapped += ch
                content = mapped
            else:
                content = _colorize_effect_line_map(content, color_map, color_codes, glyph)
        elif color_map and color_codes:
            content = _colorize_effect_line_map(content, color_map, color_codes, glyph)
        else:
            content = _colorize_effect_line(content, color_code)
        line = lines[line_idx]
        lines[line_idx] = line[:left + 1] + content + line[right:]
    return lines


def _spell_effect_with_art(ctx: ScreenContext, spell: dict) -> Optional[dict]:
    if not isinstance(spell, dict):
        return None
    effect = spell.get("effect")
    if isinstance(effect, dict):
        effect_override = dict(effect)
    else:
        art_id = spell.get("art_id")
        if not art_id:
            return None
        effect_override = {"art_id": art_id}
    art_id = effect_override.get("art_id")
    if art_id and hasattr(ctx, "spells_art"):
        art = ctx.spells_art.get(art_id)
        if isinstance(art, dict):
            merged = dict(art)
            merged.update(effect_override)
            effect_override = merged
    element = spell.get("element")
    if element and hasattr(ctx, "elements"):
        colors = ctx.elements.colors_for(element)
        if len(colors) >= 3:
            effect_override["color_map"] = {"1": colors[0], "2": colors[1], "3": colors[2]}
            effect_override["color_key"] = colors[0]
    return effect_override


def _colorize_atlas_line(
    line: str,
    digit_colors: Optional[dict] = None,
    flicker_digit: Optional[str] = None,
    flicker_on: bool = True,
    locked_color: Optional[str] = None,
) -> str:
    if not line:
        return line
    out = []
    for ch in line:
        if digit_colors and ch in digit_colors:
            if flicker_digit and ch == flicker_digit and not flicker_on:
                out.append(f"{ANSI.FG_WHITE}{ANSI.DIM}*{ANSI.RESET}")
            else:
                out.append(f"{digit_colors[ch]}*{ANSI.RESET}")
            continue
        if ch.isdigit() and locked_color:
            out.append(f"{locked_color}*{ANSI.RESET}")
            continue
        if ch == "w":
            out.append(f"{ANSI.FG_BLUE}~{ANSI.RESET}")
            continue
        if ch == "o":
            out.append(f"{ANSI.FG_WHITE}o{ANSI.RESET}")
            continue
        if ch in ("|", "-", "/", "\\"):
            out.append(f"{ANSI.FG_YELLOW}{ch}{ANSI.RESET}")
            continue
        out.append(ch)
    return "".join(out)


def generate_frame(
    ctx: ScreenContext,
    player: Player,
    opponents: List[Opponent],
    message: str = "",
    leveling_mode: bool = False,
    shop_mode: bool = False,
    shop_view: str = "menu",
    inventory_mode: bool = False,
    inventory_items: Optional[List[tuple[str, str]]] = None,
    hall_mode: bool = False,
    hall_view: str = "menu",
    inn_mode: bool = False,
    stats_mode: bool = False,
    followers_mode: bool = False,
    spell_mode: bool = False,
    element_mode: bool = False,
    alchemist_mode: bool = False,
    alchemy_first: Optional[str] = None,
    alchemy_selecting: bool = False,
    temple_mode: bool = False,
    smithy_mode: bool = False,
    portal_mode: bool = False,
    title_menu_stack: Optional[list[str]] = None,
    options_mode: bool = False,
    action_cursor: int = 0,
    menu_cursor: int = 0,
    followers_focus: str = "list",
    followers_action_cursor: int = 0,
    spell_cast_rank: int = 1,
    level_cursor: int = 0,
    level_up_notes: Optional[List[str]] = None,
    suppress_actions: bool = False
) -> Frame:
    """Build a screen frame from game state and UI data."""
    healing = ctx.spells.get("healing", {})
    spark = ctx.spells.get("spark", {})
    heal_name = healing.get("name", "Healing")
    spark_name = spark.get("name", "Spark")
    display_location = player.location
    continent_prefix = None
    if hasattr(ctx, "continents"):
        continent_prefix = ctx.continents.name_for(player.current_element)

    def _continent_title(name: str) -> str:
        if not name:
            return name
        if continent_prefix:
            if name.startswith("Town "):
                return f"{continent_prefix} {name[len('Town '):]}"
            if name.startswith("Town"):
                return f"{continent_prefix}{name[len('Town'):]}"
            if not name.startswith(continent_prefix):
                return f"{continent_prefix} {name}"
        return name
    location_gradient = None
    portal_desc = None
    color_map_override = element_color_map(ctx.colors.all(), player.current_element)
    art_anchor_x = None
    raw_lines = None
    if leveling_mode:
        level_options = [
            "  +HP",
            "  +MP",
            "  +ATK",
            "  +DEF",
            "  Balanced allocation",
            "  Random allocation",
            "  Bank points",
        ]
        level_cursor = max(0, min(level_cursor, len(level_options) - 1))
        level_lines = []
        for idx, line in enumerate(level_options):
            prefix = "> " if idx == level_cursor else "  "
            level_lines.append(f"{prefix}{line.strip()}")
            if idx == 3:
                level_lines.append("")
        body = [
            "Level Up!",
            "",
            f"You reached level {player.level}.",
            "",
            f"Stat points available: {player.stat_points}",
            "",
            "Choose how to spend your points:",
            *level_lines,
        ]
        if level_up_notes:
            body.append("")
            body.append("Spell updates:")
            for note in level_up_notes:
                body.append(f"  - {note}")
        actions = format_action_lines([])
        art_lines = []
        art_color = ANSI.FG_WHITE
        art_lines = []
    elif player.location == "Town" and (shop_mode or hall_mode or inn_mode or alchemist_mode or temple_mode or smithy_mode or portal_mode):
        view_state = SimpleNamespace(
            player=player,
            shop_mode=shop_mode,
            shop_view=shop_view,
            hall_mode=hall_mode,
            hall_view=hall_view,
            inn_mode=inn_mode,
            alchemist_mode=alchemist_mode,
            alchemy_first=alchemy_first,
            alchemy_selecting=alchemy_selecting,
            temple_mode=temple_mode,
            smithy_mode=smithy_mode,
            portal_mode=portal_mode,
            action_cursor=action_cursor,
            current_venue_id=None,
        )
        venue_id = venue_id_from_state(view_state)
        venue_render = render_venue_body(ctx, view_state, venue_id or "", color_map_override=color_map_override)
        display_location = _continent_title(venue_render.title or display_location)
        body = venue_render.body
        art_lines = venue_render.art_lines
        art_color = venue_render.art_color
        art_anchor_x = venue_render.art_anchor_x
        actions = format_command_lines(
            venue_render.actions,
            selected_index=action_cursor if action_cursor >= 0 else None
        )
        if venue_render.message:
            portal_desc = venue_render.message
    elif options_mode:
        options_menu = ctx.menus.get("options", {})
        options_actions = []
        for entry in options_menu.get("actions", []):
            cmd_entry = dict(entry)
            if not command_is_enabled(cmd_entry, player, opponents):
                cmd_entry["_disabled"] = True
            options_actions.append(cmd_entry)
        options_menu = dict(options_menu)
        options_menu["actions"] = options_actions
        title = options_menu.get("title", "Options")
        display_location = title
        body = []
        if options_actions:
            for idx, entry in enumerate(options_actions):
                label = str(entry.get("label", "")).strip() or entry.get("command", "")
                prefix = "> " if idx == menu_cursor else "  "
                if entry.get("_disabled"):
                    body.append(f"{ANSI.DIM}{prefix}{label}{ANSI.RESET}")
                else:
                    body.append(f"{prefix}{label}")
        else:
            body.append("No options available.")
        actions = format_menu_actions(options_menu, selected_index=menu_cursor if menu_cursor >= 0 else None)
        art_lines = []
        art_color = ANSI.FG_WHITE
    elif followers_mode:
        followers_menu = ctx.menus.get("followers", {})
        followers = list(getattr(player, "followers", []) or [])
        title = followers_menu.get("title", "Followers")
        display_location = title
        body = [f"Followers: {len(followers)}/{player.follower_limit()}"]
        body.append("")
        if followers:
            for idx, follower in enumerate(followers):
                name = follower.get("name", "Follower") if isinstance(follower, dict) else "Follower"
                f_type = follower.get("type", "follower") if isinstance(follower, dict) else "follower"
                effect = ""
                if f_type == "fairy":
                    effect = "Heals after each round."
                label = f"{name} ({f_type})"
                if effect:
                    label = f"{label} - {effect}"
                prefix = "> " if idx == menu_cursor and followers_focus == "list" else "  "
                body.append(f"{prefix}{label}")
        else:
            body.append("No followers.")
        followers_actions = []
        if followers and 0 <= menu_cursor < len(followers) and isinstance(followers[menu_cursor], dict):
            abilities = followers[menu_cursor].get("abilities", [])
            if isinstance(abilities, list):
                for ability_id in abilities:
                    label = str(ability_id)
                    min_level = 1
                    if hasattr(ctx, "abilities"):
                        ability = ctx.abilities.get(ability_id, {})
                        if isinstance(ability, dict):
                            label = ability.get("label", label)
                            min_level = int(ability.get("min_level", 1) or 1)
                    cmd_entry = {
                        "label": f"Enable {label}",
                        "command": f"FOLLOWER_ABILITY:{ability_id}",
                    }
                    if int(followers[menu_cursor].get("level", 1) or 1) < min_level:
                        cmd_entry["_disabled"] = True
                        cmd_entry["label"] = f"{label} (Level {min_level}+)"
                    followers_actions.append(cmd_entry)
            active_label = ""
            active_id = str(followers[menu_cursor].get("active_ability", "") or "")
            if active_id and hasattr(ctx, "abilities"):
                ability = ctx.abilities.get(active_id, {})
                if isinstance(ability, dict):
                    active_label = ability.get("label", active_id)
            if active_label:
                followers_actions.insert(0, {"label": f"Active: {active_label}", "_disabled": True})
        gear_items = player.list_gear_items() if hasattr(player, "list_gear_items") else []
        selected_follower = followers[menu_cursor] if followers and 0 <= menu_cursor < len(followers) else {}
        for entry in followers_menu.get("actions", []):
            cmd_entry = dict(entry)
            if cmd_entry.get("command") == "FOLLOWER_DISMISS" and not followers:
                cmd_entry["_disabled"] = True
            if cmd_entry.get("command") == "FOLLOWER_EQUIP" and not gear_items:
                cmd_entry["_disabled"] = True
            if cmd_entry.get("command") == "FOLLOWER_UNEQUIP":
                equip = selected_follower.get("equipment", {}) if isinstance(selected_follower, dict) else {}
                if not isinstance(equip, dict) or not equip:
                    cmd_entry["_disabled"] = True
            followers_actions.append(cmd_entry)
        followers_menu = dict(followers_menu)
        followers_menu["actions"] = followers_actions
        action_selected = followers_action_cursor if followers_focus == "actions" else None
        actions = format_menu_actions(followers_menu, selected_index=action_selected)
        if followers:
            body.append("")
            body.append("Use left/right to switch list and actions.")
        art_lines = []
        art_color = ANSI.FG_WHITE
    elif inventory_mode:
        inventory_menu = ctx.menus.get("inventory", {})
        items = inventory_items or []
        title = inventory_menu.get("title", "Inventory")
        body = [title, ""]
        if items:
            for i, (_, label) in enumerate(items[:9], start=1):
                prefix = "> " if (i - 1) == menu_cursor else "  "
                body.append(f"{prefix}{label}")
        else:
            body.append(inventory_menu.get("empty", "Inventory is empty."))
        actions = format_menu_actions(inventory_menu, selected_index=menu_cursor if menu_cursor >= 0 else None)
        art_lines = []
        art_color = ANSI.FG_WHITE
    elif stats_mode:
        stats_menu = ctx.menus.get("stats", {})
        title = stats_menu.get("title", "Stats")
        display_location = title
        atk_bonus = int(player.gear_atk) + int(getattr(player, "temp_atk_bonus", 0))
        def_bonus = int(player.gear_defense) + int(getattr(player, "temp_def_bonus", 0))
        temp_hp = int(getattr(player, "temp_hp_bonus", 0))
        hp_total = player.max_hp + temp_hp
        hp_line = f"HP: {player.hp} / {player.max_hp}"
        if temp_hp:
            hp_line = f"HP: {player.hp} / {player.max_hp} (+{temp_hp})"
        body = [
            hp_line,
            f"MP: {player.mp} / {player.max_mp}",
            f"ATK: {player.atk} (+{atk_bonus})",
            f"DEF: {player.defense} (+{def_bonus})",
            f"Level: {player.level}  XP: {player.xp}  GP: {player.gold}",
            f"Stat points available: {player.stat_points}",
        ]
        actions_list = []
        for entry in stats_menu.get("actions", []):
            if not entry.get("command"):
                continue
            cmd_entry = dict(entry)
            if cmd_entry.get("command", "").startswith("STAT_") and player.stat_points <= 0:
                cmd_entry["_disabled"] = True
            actions_list.append(cmd_entry)
        stats_menu = dict(stats_menu)
        stats_menu["actions"] = actions_list
        actions = format_menu_actions(stats_menu, selected_index=menu_cursor if menu_cursor >= 0 else None)
        art_lines = []
        art_color = ANSI.FG_WHITE
    elif spell_mode:
        spell_menu = ctx.menus.get("spellbook", {})
        available_spells = ctx.spells.available(player, ctx.items)
        display_location = spell_menu.get("title", "Spellbook")
        body = []
        if available_spells:
            color_codes = _color_codes_by_key(ctx.colors.all())
            for idx, (_, spell) in enumerate(available_spells):
                name = spell.get("name", "Spell")
                base_cost = int(spell.get("mp_cost", 0))
                max_rank = ctx.spells.rank_for(spell, player.level)
                element = spell.get("element")
                has_charge = False
                if element:
                    charges = player.wand_charges()
                    has_charge = int(charges.get(str(element), 0)) > 0
                max_affordable = max_rank
                if not has_charge and base_cost > 0:
                    max_affordable = min(max_rank, player.mp // base_cost)
                disabled = (max_affordable < 1)
                selected_rank = max_rank
                if idx == menu_cursor:
                    selected_rank = max(1, min(spell_cast_rank, max_rank))
                    if not has_charge and max_affordable >= 1:
                        selected_rank = min(selected_rank, max_affordable)
                mp_cost = base_cost * max(1, selected_rank)
                prefix = "> " if idx == menu_cursor else "  "
                star_color = ""
                if element and hasattr(ctx, "elements"):
                    colors = ctx.elements.colors_for(str(element))
                    if colors:
                        star_color = _color_code_for_key(ctx.colors.all(), colors[0])
                enabled = "*" * selected_rank
                disabled = "*" * max(0, max_rank - selected_rank)
                if star_color and enabled:
                    enabled = f"{star_color}{enabled}{ANSI.RESET}"
                if disabled:
                    disabled = f"{ANSI.FG_WHITE}{ANSI.DIM}{disabled}{ANSI.RESET}"
                rank_bar = f"[{(enabled + disabled).ljust(3)}]"
                line = f"{prefix}{name} ({mp_cost} MP) {rank_bar}"
                if disabled:
                    line = f"{ANSI.DIM}{line}{ANSI.RESET}"
                body.append(line)
            selection = max(0, min(menu_cursor, len(available_spells) - 1))
            _, spell = available_spells[selection]
            effect = _spell_effect_with_art(ctx, spell) if isinstance(spell, dict) else None
            rank = ctx.spells.rank_for(spell, player.level)
            color_key = ""
            if isinstance(effect, dict):
                if rank >= 3:
                    color_key = str(spell.get("overlay_color_key_rank3", ""))[:1]
                elif rank >= 2:
                    color_key = str(spell.get("overlay_color_key_rank2", ""))[:1]
                if not color_key:
                    color_key = str(effect.get("color_key", ""))[:1]
            color_code = _color_code_for_key(ctx.colors.all(), color_key)
            delay = 0.08
            if isinstance(effect, dict):
                delay = float(effect.get("frame_delay", delay) or delay)
            frame_art = ctx.frames.get("spell_preview", {}).get("art", [])
            frames = effect.get("frames", []) if isinstance(effect, dict) else []
            frame_count = len(frames) if isinstance(frames, list) else 0
            tick = int(time.time() / max(0.01, delay))
            effect_index = tick % max(frame_count, 1)
            art_lines = _spell_preview_lines(
                frame_art,
                effect,
                color_code,
                effect_index,
                color_codes=color_codes,
                color_map=effect.get("color_map") if isinstance(effect, dict) else None,
                glyph=effect.get("glyph") if isinstance(effect, dict) else None,
            )
        else:
            body.append("  No spells learned.")
            art_lines = []
        actions = format_menu_actions(
            spell_menu,
            replacements={
                "{heal_name}": heal_name,
                "{spark_name}": spark_name,
            },
            selected_index=menu_cursor if menu_cursor >= 0 else None,
        )
        art_color = ANSI.FG_WHITE
    elif element_mode:
        elements_menu = ctx.menus.get("elements", {})
        elements = list(getattr(player, "elements", []) or [])
        if hasattr(ctx, "continents"):
            order = list(ctx.continents.order() or [])
            elements = [e for e in order if e in elements] or elements
        title = elements_menu.get("title", "Elements")
        body = [title, ""]
        if elements:
            menu_cursor = max(0, min(menu_cursor, len(elements) - 1))
            for idx, element in enumerate(elements):
                if hasattr(ctx, "continents"):
                    label = ctx.continents.name_for(element)
                else:
                    label = element.title()
                suffix = " (current)" if element == player.current_element else ""
                prefix = "> " if idx == menu_cursor else "  "
                body.append(f"{prefix}{label}{suffix}")
        else:
            body.append("No elements unlocked.")
        actions = format_menu_actions(elements_menu, selected_index=menu_cursor if menu_cursor >= 0 else None)
        art_lines = []
        art_color = ANSI.FG_WHITE
    elif player.location == "Town":
        scene_data = ctx.scenes.get("town", {})
        art_lines, art_color = render_scene_art(
            scene_data,
            opponents,
            objects_data=ctx.objects,
            color_map_override=color_map_override,
        )
        if not art_lines:
            art_lines = scene_data.get("art", [])
            art_color = COLOR_BY_NAME.get(scene_data.get("color", "yellow").lower(), ANSI.FG_WHITE)
        body = scene_data.get("narrative", [])
        actions = format_command_lines(
            scene_commands(ctx.scenes, ctx.commands, "town", player, opponents),
            selected_index=action_cursor if action_cursor >= 0 else None,
        )
        if hasattr(ctx, "continents"):
            display_location = ctx.continents.name_for(player.current_element)
    elif player.location == "Title":
        title_data = ctx.title_screen.all() if hasattr(ctx, "title_screen") else {}
        layout = title_data.get("layout", {}) if isinstance(title_data, dict) else {}
        menu_cfg = layout.get("menu", {}) if isinstance(layout, dict) else {}
        scroll_cfg = title_data.get("scroll") if isinstance(title_data.get("scroll"), dict) else None
        menu_height = int(menu_cfg.get("height", 9) or 9)
        art_color = ANSI.FG_WHITE
        art_lines = []
        title_element = None
        unlocked_elements = ["base"]
        if hasattr(ctx, "save_data") and ctx.save_data:
            if getattr(player, "title_slot_select", False):
                _narrative, commands, _detail = _title_state_config(ctx, player, action_cursor, title_menu_stack or [])
                if commands and 0 <= action_cursor < len(commands):
                    cmd = commands[action_cursor].get("command", "")
                    if isinstance(cmd, str) and cmd.startswith("TITLE_SLOT_"):
                        slot_raw = cmd.replace("TITLE_SLOT_", "")
                        if slot_raw.isdigit():
                            slot_id = int(slot_raw)
                            summary = ctx.save_data.slot_summary(slot_id)
                            element = summary.get("current_element")
                            if element:
                                title_element = str(element)
                            slot_data = ctx.save_data.load(slot_id)
                            if isinstance(slot_data, dict):
                                slot_player = slot_data.get("player", {})
                                if isinstance(slot_player, dict):
                                    elements = slot_player.get("elements")
                                    if isinstance(elements, list) and elements:
                                        unlocked_elements = elements
            if not title_element:
                last_slot = ctx.save_data.last_played_slot()
                if last_slot:
                    summary = ctx.save_data.slot_summary(int(last_slot))
                    element = summary.get("current_element")
                    if element:
                        title_element = str(element)
                    slot_data = ctx.save_data.load(int(last_slot))
                    if isinstance(slot_data, dict):
                        slot_player = slot_data.get("player", {})
                        if isinstance(slot_player, dict):
                            elements = slot_player.get("elements")
                            if isinstance(elements, list) and elements:
                                unlocked_elements = elements
        title_color_map = element_color_map(ctx.colors.all(), title_element or "base")
        if scroll_cfg:
            height = int(scroll_cfg.get("height", 10) or 10)
            speed = float(scroll_cfg.get("speed", 1) or 1)
            forest_scale = float(scroll_cfg.get("forest_width_scale", 1) or 1)
            forest_scale = max(0.1, min(1.0, forest_scale))
            pano_lines = title_data.get("_panorama_lines")
            pano_width = title_data.get("_panorama_width")
            cached_element = title_data.get("_panorama_element")
            if cached_element != (title_element or "base"):
                pano_lines = None
                pano_width = None
            if not pano_lines or not pano_width:
                forest_scene = ctx.scenes.get("forest", {})
                gap_min = int(forest_scene.get("gap_min", 0) or 0)
                base_width = max(0, (SCREEN_WIDTH - gap_min) // 2)
                target_width = max(1, int(base_width * forest_scale))
                objects_data = ctx.objects
                if objects_data:
                    def obj_width(obj_id: str) -> int:
                        obj = objects_data.get(obj_id, {})
                        art = obj.get("art", [])
                        return max((len(line) for line in art), default=0)
                    options = [
                        "tree_large",
                        "tree_large_2",
                        "tree_large_3",
                        "bush_large",
                        "bush_large_2",
                        "bush_large_3",
                    ]
                    options = [obj_id for obj_id in options if objects_data.get(obj_id, {}).get("art")]
                    rng = random.Random(4242)
                    def build_strip() -> list[dict]:
                        strip = []
                        width = 0
                        while width < target_width and options:
                            obj_id = rng.choice(options)
                            strip.append({"id": obj_id})
                            width += obj_width(obj_id)
                            if obj_width(obj_id) == 0:
                                break
                            if width < target_width and objects_data.get("grass_1", {}).get("art"):
                                strip.append({"id": "grass_1"})
                                width += obj_width("grass_1")
                        return strip
                    forest_scene["objects_left"] = build_strip()
                    forest_scene["objects_right"] = build_strip()
                    forest_scene["gap_min"] = 0
                forest_lines, _ = render_scene_art(
                    forest_scene,
                    [],
                    objects_data=ctx.objects,
                    color_map_override=title_color_map,
                )
                town_scene = ctx.scenes.get("town", {})
                town_lines, _ = render_scene_art(
                    town_scene,
                    [],
                    objects_data=ctx.objects,
                    color_map_override=title_color_map,
                )
                def pad_height(lines: list[str], height: int) -> list[str]:
                    if len(lines) >= height:
                        return lines[:height]
                    pad_width = len(strip_ansi(lines[0])) if lines else SCREEN_WIDTH
                    return lines + ([" " * pad_width] * (height - len(lines)))
                forest_lines = pad_height(forest_lines, height)
                town_lines = pad_height(town_lines, height)
                pano_lines = []
                for row in range(height):
                    pano_lines.append(forest_lines[row] + town_lines[row] + forest_lines[row])
                pano_width = len(strip_ansi(pano_lines[0])) if pano_lines else 0
                title_data["_panorama_lines"] = pano_lines
                title_data["_panorama_width"] = pano_width
                title_data["_panorama_element"] = title_element or "base"
            view_width = SCREEN_WIDTH
            offset = int(time.time() * speed) % max(pano_width, 1)
            art_lines = [
                _slice_ansi_wrap(line, offset, view_width)
                for line in pano_lines
            ]

            logo_lines = []
            blocking_map = []
            blocking_char = None
            logo_object_id = title_data.get("logo_object_id")
            if logo_object_id:
                venue_stub = {
                    "objects": [{"id": logo_object_id}],
                    "color": "white",
                }
                logo_lines, _logo_color, _ = render_venue_objects(
                    venue_stub,
                    {},
                    ctx.objects,
                    title_color_map,
                )
                obj_def = ctx.objects.get(str(logo_object_id), {})
                blocking_char = obj_def.get("blocking_space")
                if isinstance(blocking_char, str) and len(blocking_char) == 1:
                    art = obj_def.get("art", [])
                    if isinstance(art, list):
                        for line in art:
                            row = [(ch == blocking_char) for ch in line]
                            blocking_map.append(row)
            if logo_lines:
                logo_height = len(logo_lines)
                logo_width = max((len(strip_ansi(line)) for line in logo_lines), default=0)
                start_y = max(0, (height - logo_height) // 2)
                start_x = max(0, (view_width - logo_width) // 2)
                for idx, logo_line in enumerate(logo_lines):
                    target_row = start_y + idx
                    if target_row < 0 or target_row >= len(art_lines):
                        continue
                    base_cells = _ansi_cells(art_lines[target_row])
                    logo_cells = _ansi_cells(logo_line)
                    for col, (ch, code) in enumerate(logo_cells):
                        if ch == " ":
                            if blocking_map and idx < len(blocking_map) and col < len(blocking_map[idx]):
                                if blocking_map[idx][col]:
                                    pos = start_x + col
                                    if 0 <= pos < len(base_cells):
                                        base_cells[pos] = (" ", "")
                            continue
                        pos = start_x + col
                        if 0 <= pos < len(base_cells):
                            base_cells[pos] = (ch, code)
                    art_lines[target_row] = "".join(code + ch for ch, code in base_cells) + ANSI.RESET
        if getattr(player, "title_name_input", False):
            buffer = str(getattr(player, "title_pending_name", "") or "")
            cursor = getattr(player, "title_name_cursor", (0, 0))
            shift_lock = bool(getattr(player, "title_name_shift", True))
            try:
                cursor = (int(cursor[0]), int(cursor[1]))
            except (TypeError, ValueError, IndexError):
                cursor = (0, 0)
            menu_lines, menu_y, menu_x, menu_w = _title_keyboard_lines(menu_cfg, buffer, cursor, shift_lock)
        else:
            narrative, commands, detail_lines = _title_state_config(ctx, player, action_cursor, title_menu_stack or [])
            menu_lines, menu_y, menu_x, menu_w = _title_menu_lines(
                menu_cfg,
                narrative,
                commands,
                action_cursor,
                detail_lines,
            )
        canvas = []
        for idx in range(SCREEN_HEIGHT):
            art_line = art_lines[idx] if idx < len(art_lines) else ""
            canvas.append(pad_or_trim_ansi(art_line, SCREEN_WIDTH))
        atlas_lines = []
        if hasattr(ctx, "glyphs"):
            atlas = ctx.glyphs.get("atlas", {}) if ctx.glyphs else {}
            if isinstance(atlas, dict):
                atlas_lines = atlas.get("art", []) if isinstance(atlas.get("art"), list) else []
        if atlas_lines:
            start_y = SCREEN_HEIGHT - len(atlas_lines)
            digit_colors = {}
            flicker_digit = None
            flicker_on = True
            if title_element and hasattr(ctx, "elements"):
                colors = ctx.colors.all()
                elem_colors = {
                    "1": ("base", ctx.elements.colors_for("base")),
                    "2": ("earth", ctx.elements.colors_for("earth")),
                    "3": ("wind", ctx.elements.colors_for("wind")),
                    "4": ("fire", ctx.elements.colors_for("fire")),
                    "5": ("water", ctx.elements.colors_for("water")),
                    "6": ("light", ctx.elements.colors_for("light")),
                    "7": ("lightning", ctx.elements.colors_for("lightning")),
                    "8": ("dark", ctx.elements.colors_for("dark")),
                    "9": ("ice", ctx.elements.colors_for("ice")),
                }
                unlocked = set(str(e) for e in (unlocked_elements or []))
                for digit, (element_key, palette) in elem_colors.items():
                    if palette and element_key in unlocked:
                        digit_colors[digit] = _color_code_for_key(colors, palette[0])
                selected_map = {
                    "base": "1",
                    "earth": "2",
                    "wind": "3",
                    "air": "3",
                    "fire": "4",
                    "water": "5",
                    "light": "6",
                    "lightning": "7",
                    "dark": "8",
                    "ice": "9",
                }
                if title_element in selected_map:
                    flicker_digit = selected_map[title_element]
                    flicker_on = int(time.time() / 0.35) % 2 == 0
            for idx, line in enumerate(atlas_lines):
                row = start_y + idx
                if 0 <= row < SCREEN_HEIGHT:
                    colored = ANSI.RESET + _colorize_atlas_line(
                        line,
                        digit_colors,
                        flicker_digit,
                        flicker_on,
                        f"{ANSI.FG_WHITE}{ANSI.DIM}",
                    )
                    base_cells = _ansi_cells(canvas[row])
                    overlay_cells = _ansi_cells(pad_or_trim_ansi(colored, SCREEN_WIDTH))
                    merged = []
                    for (base_ch, base_code), (over_ch, over_code) in zip(base_cells, overlay_cells):
                        if over_ch == " ":
                            merged.append(ANSI.RESET + base_code + base_ch)
                        else:
                            merged.append(ANSI.RESET + over_code + over_ch)
                    canvas[row] = "".join(merged) + ANSI.RESET
        for idx, line in enumerate(menu_lines):
            row = menu_y + idx
            if 0 <= row < SCREEN_HEIGHT:
                base_cells = _ansi_cells(canvas[row])
                overlay_cells = _ansi_cells(pad_or_trim_ansi(line, SCREEN_WIDTH))
                merged = []
                for col, ((base_ch, base_code), (over_ch, over_code)) in enumerate(zip(base_cells, overlay_cells)):
                    in_box = menu_x <= col < (menu_x + menu_w)
                    if in_box:
                        if col == menu_x:
                            merged.append(ANSI.RESET + over_code + over_ch)
                        else:
                            merged.append(ANSI.RESET + over_code + over_ch)
                    else:
                        merged.append(ANSI.RESET + base_code + base_ch)
                canvas[row] = "".join(merged) + ANSI.RESET
        body = []
        actions = []
        display_location = "Lokarta - World Maker"
        raw_lines = canvas
    else:
        scene_data = ctx.scenes.get("forest", {})
        forest_art, art_color = render_scene_art(
            scene_data,
            opponents,
            objects_data=ctx.objects,
            color_map_override=color_map_override,
        )
        alive = [o for o in opponents if o.hp > 0]
        default_text = ctx.text.get("battle", "quiet", "All is quiet. No enemies in sight.")
        default_narrative = scene_data.get("narrative", [default_text])
        if alive:
            if len(alive) > 1:
                arrival = ctx.text.get("battle", "opponent_arrival_plural", "Opponents emerge from the forest.")
                body = [arrival]
            else:
                primary = alive[0]
                arrival = ctx.text.get("battle", "opponent_arrival", "A {name} {arrival}.")
                body = [format_text(arrival, name=primary.name, arrival=primary.arrival)]
        else:
            body = [*default_narrative]
        if message:
            body = [line for line in message.splitlines() if line.strip()]
        actions = format_command_lines(
            scene_commands(ctx.scenes, ctx.commands, "forest", player, opponents),
            selected_index=action_cursor if action_cursor >= 0 else None,
        )
        art_lines = forest_art
        art_anchor_x = None

    if portal_desc:
        message = portal_desc
    if player.location == "Forest":
        status_lines = []
    elif message and "\n" in message:
        status_lines = [line for line in message.splitlines() if line.strip() != ""]
    else:
        status_lines = (
            textwrap.wrap(message, width=SCREEN_WIDTH - 2)
            if message
            else []
        )

    if player.location == "Town" and hasattr(ctx, "elements"):
        colors = ctx.colors.all()
        palette = ctx.elements.colors_for(player.current_element)
        if palette:
            start_rgb = _color_key_to_rgb(colors, palette[0]) or (192, 192, 192)
            end_rgb = _color_key_to_rgb(colors, palette[1] if len(palette) > 1 else palette[0]) or start_rgb
            location_gradient = (*start_rgb, *end_rgb)

    return Frame(
        title="Lokarta - World Maker — PROTOTYPE",
        body_lines=body,
        action_lines=(format_action_lines([]) if suppress_actions else actions),
        stat_lines=format_player_stats(player),
        footer_hint=(
            "D-pad move  A=Confirm  S=Balanced"
            if leveling_mode
            else "D-pad move  A/Enter=Confirm  S=Back  Shift/Tab=Options"
        ),
        location=display_location,
        location_gradient=location_gradient,
        art_lines=art_lines,
        art_color=art_color,
        status_lines=status_lines,
        raw_lines=raw_lines,
        art_anchor_x=art_anchor_x,
    )
