"""Screen composition helpers for game UI states."""

import random
import textwrap
import time
from dataclasses import dataclass
from typing import List, Optional

from app.commands.scene_commands import command_is_enabled, scene_commands
from app.data_access.commands_data import CommandsData
from app.data_access.colors_data import ColorsData
from app.data_access.continents_data import ContinentsData
from app.data_access.frames_data import FramesData
from app.data_access.elements_data import ElementsData
from app.data_access.spells_art_data import SpellsArtData
from app.data_access.items_data import ItemsData
from app.data_access.menus_data import MenusData
from app.data_access.npcs_data import NpcsData
from app.data_access.objects_data import ObjectsData
from app.data_access.opponents_data import OpponentsData
from app.data_access.scenes_data import ScenesData
from app.data_access.spells_data import SpellsData
from app.data_access.venues_data import VenuesData
from app.data_access.text_data import TextData
from app.models import Frame, Player, Opponent
from app.ui.ansi import ANSI
from app.ui.layout import format_action_lines, format_command_lines, format_menu_actions, strip_ansi
from app.ui.constants import SCREEN_WIDTH
from app.ui.rendering import (
    COLOR_BY_NAME,
    element_color_map,
    format_player_stats,
    render_scene_art,
    render_venue_art,
    render_venue_objects,
)
from app.ui.text import format_text
from app.shop import shop_commands, shop_inventory, shop_sell_inventory


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
    spells_art: SpellsArtData


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
    if not isinstance(effect, dict):
        return None
    effect_override = dict(effect)
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
            code = digit_colors.get(ch, "")
            if code:
                if flicker_digit and ch == flicker_digit:
                    flicker_code = code if flicker_on else f"{ANSI.FG_WHITE}{ANSI.DIM}"
                    out.append(f"{flicker_code}*{ANSI.RESET}")
                else:
                    out.append(f"{code}*{ANSI.RESET}")
                continue
        if ch.isdigit() and locked_color:
            out.append(f"{locked_color}*{ANSI.RESET}")
            continue
        if ch == "o":
            out.append(f"{ANSI.FG_WHITE}{ANSI.DIM}{ch}{ANSI.RESET}")
        elif ch == "w":
            out.append(f"{ANSI.FG_BLUE}~{ANSI.RESET}")
        elif ch in ("|", "-", "/", "\\"):
            out.append(f"{ANSI.FG_YELLOW}{ch}{ANSI.RESET}")
        else:
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
    spell_mode: bool = False,
    element_mode: bool = False,
    alchemist_mode: bool = False,
    alchemy_first: Optional[str] = None,
    temple_mode: bool = False,
    smithy_mode: bool = False,
    portal_mode: bool = False,
    options_mode: bool = False,
    action_cursor: int = 0,
    menu_cursor: int = 0,
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
    location_gradient = None
    portal_desc = None
    color_map_override = element_color_map(ctx.colors.all(), player.current_element)
    art_anchor_x = None
    if leveling_mode:
        level_options = [
            "  +HP",
            "  +MP",
            "  +ATK",
            "  +DEF",
            "  Balanced allocation",
            "  Random allocation",
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
    elif player.location == "Town" and shop_mode:
        venue = ctx.venues.get("town_shop", {})
        display_location = venue.get("name", display_location)
        npc_lines = []
        npc_ids = venue.get("npc_ids", [])
        npc = {}
        if npc_ids:
            npc_lines = ctx.npcs.format_greeting(npc_ids[0])
            npc = ctx.npcs.get(npc_ids[0], {})
        body = []
        if npc_lines:
            body += npc_lines + [""]
        element = getattr(player, "current_element", "base")
        if shop_view == "menu":
            body.append("What would you like to do?")
        elif shop_view == "buy":
            for entry in shop_inventory(venue, ctx.items, element):
                item_id = entry.get("item_id")
                item = ctx.items.get(item_id, {})
                label = entry.get("label", item.get("name", item_id))
                price = item.get("price", 0)
                body.append(f"{label}  {price} GP")
        elif shop_view == "sell":
            for entry in shop_sell_inventory(player, ctx.items):
                label = entry.get("label", "Item")
                price = entry.get("price", 0)
                body.append(f"{label}  {price} GP")
        body.append("")
        body += venue.get("narrative", [])
        art_anchor_x = None
        if venue.get("objects"):
            art_lines, art_color, art_anchor_x = render_venue_objects(venue, npc, ctx.objects, color_map_override)
        else:
            art_lines, art_color = render_venue_art(venue, npc, color_map_override)
        actions = format_command_lines(
            shop_commands(venue, ctx.items, element, shop_view, player),
            selected_index=action_cursor if action_cursor >= 0 else None
        )
    elif player.location == "Town" and hall_mode:
        venue = ctx.venues.get("town_hall", {})
        display_location = venue.get("name", display_location)
        info_sections = venue.get("info_sections", [])
        npc_lines = []
        npc_ids = venue.get("npc_ids", [])
        npc = {}
        if npc_ids:
            npc_lines = ctx.npcs.format_greeting(npc_ids[0])
            npc = ctx.npcs.get(npc_ids[0], {})
        section = next((entry for entry in info_sections if entry.get("key") == hall_view), None)
        source = section.get("source") if section else None
        if source == "items":
            info_lines = ctx.items.list_descriptions()
        elif source == "opponents":
            info_lines = ctx.opponents.list_descriptions()
        else:
            info_lines = []
        body = []
        if npc_lines:
            body += npc_lines + [""]
        body += info_lines
        body += venue.get("narrative", [])
        actions = format_command_lines(venue.get("commands", []), selected_index=action_cursor if action_cursor >= 0 else None)
        art_anchor_x = None
        if venue.get("objects"):
            art_lines, art_color, art_anchor_x = render_venue_objects(venue, npc, ctx.objects, color_map_override)
        else:
            art_lines, art_color = render_venue_art(venue, npc, color_map_override)
    elif player.location == "Town" and inn_mode:
        venue = ctx.venues.get("town_inn", {})
        display_location = venue.get("name", display_location)
        npc_lines = []
        npc_ids = venue.get("npc_ids", [])
        npc = {}
        if npc_ids:
            npc_lines = ctx.npcs.format_greeting(npc_ids[0])
            npc = ctx.npcs.get(npc_ids[0], {})
        body = []
        if npc_lines:
            body += npc_lines + [""]
        body += venue.get("narrative", [])
        actions = format_command_lines(venue.get("commands", []), selected_index=action_cursor if action_cursor >= 0 else None)
        art_anchor_x = None
        if venue.get("objects"):
            art_lines, art_color, art_anchor_x = render_venue_objects(venue, npc, ctx.objects, color_map_override)
        else:
            art_lines, art_color = render_venue_art(venue, npc, color_map_override)
    elif alchemist_mode:
        alchemy_menu = ctx.menus.get("alchemist", {})
        title = alchemy_menu.get("title", "Alchemist")
        body = [title, ""]
        gear_items = [g for g in player.gear_inventory if isinstance(g, dict)]
        if alchemy_first:
            first = next((g for g in gear_items if g.get("id") == alchemy_first), None)
            if first:
                body.append(f"First: {first.get('name', 'Gear')}")
                body.append("")
        if gear_items:
            menu_cursor = max(0, min(menu_cursor, len(gear_items) - 1))
            for idx, gear in enumerate(gear_items):
                label = gear.get("name", "Gear")
                prefix = "> " if idx == menu_cursor else "  "
                body.append(f"{prefix}{label}")
        else:
            body.append("No gear to fuse.")
        actions = format_menu_actions(alchemy_menu, selected_index=menu_cursor if menu_cursor >= 0 else None)
        art_lines = []
        art_color = ANSI.FG_WHITE
    elif player.location == "Town" and temple_mode:
        venue = ctx.venues.get("town_temple", {})
        display_location = venue.get("name", display_location)
        npc_lines = []
        npc_ids = venue.get("npc_ids", [])
        npc = {}
        if npc_ids:
            npc_lines = ctx.npcs.format_greeting(npc_ids[0])
            npc = ctx.npcs.get(npc_ids[0], {})
        body = []
        if npc_lines:
            body += npc_lines + [""]
        body += venue.get("narrative", [])
        actions = format_command_lines(venue.get("commands", []), selected_index=action_cursor if action_cursor >= 0 else None)
        art_anchor_x = None
        if venue.get("objects"):
            art_lines, art_color, art_anchor_x = render_venue_objects(venue, npc, ctx.objects, color_map_override)
        else:
            art_lines, art_color = render_venue_art(venue, npc, color_map_override)
    elif player.location == "Town" and smithy_mode:
        venue = ctx.venues.get("town_smithy", {})
        display_location = venue.get("name", display_location)
        npc_lines = []
        npc_ids = venue.get("npc_ids", [])
        npc = {}
        if npc_ids:
            npc_lines = ctx.npcs.format_greeting(npc_ids[0])
            npc = ctx.npcs.get(npc_ids[0], {})
        body = []
        if npc_lines:
            body += npc_lines + [""]
        body += venue.get("narrative", [])
        actions = format_command_lines(venue.get("commands", []), selected_index=action_cursor if action_cursor >= 0 else None)
        art_anchor_x = None
        if venue.get("objects"):
            art_lines, art_color, art_anchor_x = render_venue_objects(venue, npc, ctx.objects, color_map_override)
        else:
            art_lines, art_color = render_venue_art(venue, npc, color_map_override)
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
        body = [title, ""]
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
    elif spell_mode:
        spell_menu = ctx.menus.get("spellbook", {})
        available_spells = ctx.spells.available(player.level)
        body = [
            spell_menu.get("title", "Spellbook"),
            "",
        ]
        if available_spells:
            color_codes = _color_codes_by_key(ctx.colors.all())
            for idx, (_, spell) in enumerate(available_spells):
                name = spell.get("name", "Spell")
                mp_cost = int(spell.get("mp_cost", 0))
                rank = ctx.spells.rank_for(spell, player.level)
                prefix = "> " if idx == menu_cursor else "  "
                body.append(f"{prefix}{name} ({mp_cost} MP) Rank {rank}")
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
    elif portal_mode:
        portal_menu = ctx.menus.get("portal", {})
        elements = list(getattr(player, "elements", []) or [])
        if hasattr(ctx, "continents"):
            order = list(ctx.continents.order() or [])
            elements = [e for e in order if e in elements] or elements
        title = portal_menu.get("title", "Portal")
        body = [title, ""]
        atlas = ctx.glyphs.get("atlas", {}) if hasattr(ctx, "glyphs") else {}
        atlas_lines = atlas.get("art", []) if isinstance(atlas, dict) else []
        if elements:
            menu_cursor = max(0, min(menu_cursor, len(elements) - 1))
            left_lines = []
            for idx, element in enumerate(elements):
                if hasattr(ctx, "continents"):
                    label = ctx.continents.name_for(element)
                else:
                    label = element.title()
                prefix = "> " if idx == menu_cursor else "  "
                left_lines.append(f"{prefix}{label}")
            if hasattr(ctx, "continents") and 0 <= menu_cursor < len(elements):
                entry = ctx.continents.continents().get(elements[menu_cursor], {})
                if isinstance(entry, dict):
                    portal_desc = entry.get("description")
        else:
            left_lines = ["No continents unlocked."]
        right_lines = list(atlas_lines)
        total_lines = max(len(left_lines), len(right_lines))
        left_width = max((len(line) for line in left_lines), default=0)
        right_width = max((len(r) for r in right_lines), default=0)
        content_width = max(0, SCREEN_WIDTH - 2)
        right_margin = 14
        right_width = min(right_width, 24)
        right_width = min(right_width, max(0, content_width - right_margin))
        for i in range(total_lines):
            left = left_lines[i] if i < len(left_lines) else ""
            right = right_lines[i] if i < len(right_lines) else ""
            gap = 1 if left and right else 0
            right_col = max(0, content_width - right_margin - right_width)
            left_width = max(0, right_col - gap)
            if left_width and len(left) > left_width:
                left = left[:left_width]
            line = left.ljust(left_width)
            if right:
                if right_width and len(right) > right_width:
                    right = right[:right_width]
                digit_colors = {}
                flicker_digit = None
                flicker_on = True
                locked_color = f"{ANSI.FG_WHITE}{ANSI.DIM}"
                if hasattr(ctx, "elements"):
                    colors = ctx.colors.all()
                    unlocked = set(getattr(player, "elements", []) or [])
                    unlocked_digits = set()
                    if "base" in unlocked:
                        unlocked_digits.add("1")
                    if "earth" in unlocked:
                        unlocked_digits.add("2")
                    if "wind" in unlocked or "air" in unlocked:
                        unlocked_digits.add("3")
                    if "fire" in unlocked:
                        unlocked_digits.add("4")
                    if "water" in unlocked:
                        unlocked_digits.add("5")
                    if "light" in unlocked:
                        unlocked_digits.add("6")
                    if "lightning" in unlocked:
                        unlocked_digits.add("7")
                    if "dark" in unlocked:
                        unlocked_digits.add("8")
                    if "ice" in unlocked:
                        unlocked_digits.add("9")
                    elem_colors = {
                        "1": ctx.elements.colors_for("base"),
                        "2": ctx.elements.colors_for("earth"),
                        "3": ctx.elements.colors_for("wind"),
                        "4": ctx.elements.colors_for("fire"),
                        "5": ctx.elements.colors_for("water"),
                        "6": ctx.elements.colors_for("light"),
                        "7": ctx.elements.colors_for("lightning"),
                        "8": ctx.elements.colors_for("dark"),
                        "9": ctx.elements.colors_for("ice"),
                    }
                    for digit, palette in elem_colors.items():
                        if palette and digit in unlocked_digits:
                            digit_colors[digit] = _color_code_for_key(colors, palette[0])
                    selected = None
                    if elements and 0 <= menu_cursor < len(elements):
                        selected = elements[menu_cursor]
                    if selected is None:
                        selected = getattr(player, "current_element", None)
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
                    if selected in selected_map:
                        flicker_digit = selected_map[selected]
                        flicker_on = int(time.time() / 0.35) % 2 == 0
                colored_right = _colorize_atlas_line(right, digit_colors, flicker_digit, flicker_on, locked_color)
                line = line + (" " * gap) + colored_right
            body.append(line)
        actions = format_menu_actions(portal_menu, selected_index=menu_cursor if menu_cursor >= 0 else None)
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
        scene_data = ctx.scenes.get("title", {})
        art_lines = scene_data.get("art", [])
        art_color = COLOR_BY_NAME.get(scene_data.get("color", "cyan").lower(), ANSI.FG_WHITE)
        scroll_cfg = scene_data.get("scroll") if isinstance(scene_data.get("scroll"), dict) else None
        if scroll_cfg:
            height = int(scroll_cfg.get("height", 10) or 10)
            speed = float(scroll_cfg.get("speed", 1) or 1)
            forest_scale = float(scroll_cfg.get("forest_width_scale", 1) or 1)
            forest_scale = max(0.1, min(1.0, forest_scale))
            pano_lines = scene_data.get("_panorama_lines")
            pano_width = scene_data.get("_panorama_width")
            if not pano_lines or not pano_width:
                forest_scene = ctx.scenes.get("forest", {})
                gap_min = int(forest_scene.get("gap_min", 0) or 0)
                base_width = max(0, (SCREEN_WIDTH - 2 - gap_min) // 2)
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
                    color_map_override=ctx.colors.all(),
                )
                town_scene = ctx.scenes.get("town", {})
                town_lines, _ = render_scene_art(
                    town_scene,
                    [],
                    objects_data=ctx.objects,
                    color_map_override=ctx.colors.all(),
                )
                def pad_height(lines: list[str], height: int) -> list[str]:
                    if len(lines) >= height:
                        return lines[-height:]
                    return ([" " * len(strip_ansi(lines[0]))] * (height - len(lines))) + lines
                forest_lines = pad_height(forest_lines, height)
                town_lines = pad_height(town_lines, height)
                pano_lines = []
                for row in range(height):
                    pano_lines.append(forest_lines[row] + town_lines[row] + forest_lines[row])
                pano_width = len(strip_ansi(pano_lines[0])) if pano_lines else 0
                scene_data["_panorama_lines"] = pano_lines
                scene_data["_panorama_width"] = pano_width
            view_width = SCREEN_WIDTH - 2
            offset = int(time.time() * speed) % max(pano_width, 1)
            art_lines = [
                _slice_ansi_wrap(line, offset, view_width)
                for line in pano_lines
            ]

            logo_lines = []
            blocking_map = []
            blocking_char = None
            if scene_data.get("objects"):
                venue_stub = {
                    "objects": scene_data.get("objects"),
                    "color": scene_data.get("color", "white"),
                }
                logo_lines, _logo_color, _ = render_venue_objects(
                    venue_stub,
                    {},
                    ctx.objects,
                    ctx.colors.all(),
                )
                first_obj = scene_data.get("objects")[0] if scene_data.get("objects") else None
                obj_id = first_obj.get("id") if isinstance(first_obj, dict) else None
                if isinstance(obj_id, str):
                    obj_def = ctx.objects.get(obj_id, {})
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
        elif scene_data.get("objects"):
            art_lines, art_color = render_scene_art(
                scene_data,
                opponents,
                objects_data=ctx.objects,
                color_map_override=color_map_override,
            )
        if getattr(player, "title_confirm", False):
            body = scene_data.get("confirm_narrative", [])
            actions = format_command_lines(scene_data.get("confirm_commands", []), selected_index=action_cursor if action_cursor >= 0 else None)
        else:
            body = scene_data.get("narrative", [])
            actions = format_command_lines(
                scene_commands(ctx.scenes, ctx.commands, "title", player, opponents),
                selected_index=action_cursor if action_cursor >= 0 else None,
            )
        display_location = "Lokarta - World Maker"
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
        art_anchor_x=art_anchor_x,
    )
