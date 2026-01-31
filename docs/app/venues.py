"""Venue helpers for centralized venue behavior."""

from dataclasses import dataclass
import time
from typing import Any, Optional

from app.shop import shop_commands, shop_inventory, shop_sell_inventory, purchase_item, sell_item
from app.ui.ansi import ANSI
from app.ui.constants import SCREEN_WIDTH
from app.ui.rendering import render_venue_art, render_venue_objects


@dataclass
class VenueRender:
    title: str
    body: list[str]
    art_lines: list[str]
    art_color: str
    art_anchor_x: Optional[int]
    actions: list[dict]
    message: Optional[str] = None


def _leave_action(label: str = "Leave") -> dict:
    return {"label": label, "command": "LEAVE"}


def _append_leave(commands: list[dict]) -> list[dict]:
    if not any(cmd.get("command") == "LEAVE" for cmd in commands):
        commands.append(_leave_action())
    return commands


def _fusable_gear(state: Any, first_id: Optional[str] = None) -> list[dict]:
    gear_items = [g for g in state.player.gear_inventory if isinstance(g, dict)]
    if first_id:
        first = next((g for g in gear_items if g.get("id") == first_id), None)
        if not first:
            return []
        slot = first.get("slot")
        if not slot:
            return []
        return [g for g in gear_items if g.get("id") != first_id and g.get("slot") == slot]
    slot_counts: dict[str, int] = {}
    for gear in gear_items:
        slot = str(gear.get("slot", "") or "")
        if not slot:
            continue
        slot_counts[slot] = slot_counts.get(slot, 0) + 1
    return [
        g for g in gear_items
        if slot_counts.get(str(g.get("slot", "") or ""), 0) >= 2
    ]


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
    return ""


def _colorize_atlas_line(
    line: str,
    digit_colors: dict[str, str],
    flicker_digit: Optional[str],
    flicker_on: bool,
    locked_color: str,
) -> str:
    if not line:
        return line
    out = []
    for ch in line:
        if ch in digit_colors:
            if flicker_digit and ch == flicker_digit and not flicker_on:
                out.append(f"{ANSI.FG_WHITE}{ANSI.DIM}*{ANSI.RESET}")
            else:
                out.append(f"{digit_colors[ch]}*{ANSI.RESET}")
            continue
        if ch.isdigit():
            out.append(f"{locked_color}*{ANSI.RESET}")
            continue
        if ch == "w":
            out.append(f"{ANSI.FG_BLUE}~{ANSI.RESET}")
            continue
        if ch == "o":
            out.append(f"{ANSI.FG_WHITE}o{ANSI.RESET}")
            continue
        if ch in "|-/\\":
            out.append(f"{ANSI.FG_YELLOW}{ch}{ANSI.RESET}")
            continue
        out.append(ch)
    return "".join(out)


def _highlight_label(label: str) -> str:
    text = f"[ {label.strip()} ]" if label.strip() else "[]"
    return f"{ANSI.BG_LIGHT_GRAY}{ANSI.FG_BLUE}{ANSI.BOLD}{text}{ANSI.RESET}"


def venue_id_from_state(state: Any) -> Optional[str]:
    if getattr(state, "current_venue_id", None):
        return state.current_venue_id
    if getattr(state, "shop_mode", False):
        return "town_shop"
    if getattr(state, "hall_mode", False):
        return "town_hall"
    if getattr(state, "inn_mode", False):
        return "town_inn"
    if getattr(state, "alchemist_mode", False):
        return "town_alchemist"
    if getattr(state, "temple_mode", False):
        return "town_temple"
    if getattr(state, "smithy_mode", False):
        return "town_smithy"
    if getattr(state, "portal_mode", False):
        return "town_portal"
    return None


def venue_actions(ctx: Any, state: Any, venue_id: str) -> list[dict]:
    venue = ctx.venues.get(venue_id, {}) if venue_id else {}
    if venue_id == "town_shop":
        element = getattr(state.player, "current_element", "base")
        commands = shop_commands(venue, ctx.items, element, state.shop_view, state.player)
        return commands
    if venue_id == "town_alchemist":
        commands: list[dict] = []
        if not getattr(state, "alchemy_selecting", False):
            can_fuse = len(_fusable_gear(state)) >= 2
            entry = {"label": "Fuse", "command": "ALCHEMY_FUSE"}
            if not can_fuse:
                entry["_disabled"] = True
            commands.append(entry)
            return _append_leave(commands)
        candidates = _fusable_gear(state, getattr(state, "alchemy_first", None))
        for idx, gear in enumerate(candidates[:9], start=1):
            label = gear.get("name", "Gear")
            command = f"ALCHEMY_PICK:{idx}"
            commands.append({"label": label, "command": command})
        if not commands:
            commands.append({"label": "No compatible gear.", "_disabled": True})
        return _append_leave(commands)

    if venue_id == "town_portal":
        elements = list(getattr(state.player, "elements", []) or [])
        if hasattr(ctx, "continents"):
            order = list(ctx.continents.order() or [])
            elements = [e for e in order if e in elements] or elements
        commands = []
        current_element = getattr(state.player, "current_element", None)
        for element in elements:
            label = ctx.continents.name_for(element) if hasattr(ctx, "continents") else element.title()
            entry = {"label": label, "command": f"PORTAL:{element}"}
            if element == current_element:
                entry["_disabled"] = True
            commands.append(entry)
        if not commands:
            commands.append({"label": "No continents unlocked.", "_disabled": True})
        return _append_leave(commands)

    commands = list(venue.get("commands", [])) if isinstance(venue.get("commands"), list) else []
    return _append_leave(commands)


def handle_venue_command(ctx: Any, state: Any, venue_id: str, command_id: str) -> bool:
    if not command_id:
        return False
    if command_id in ("B_KEY", "LEAVE"):
        venue = ctx.venues.get(venue_id, {}) if venue_id else {}
        state.shop_mode = False
        state.shop_view = "menu"
        state.hall_mode = False
        state.inn_mode = False
        state.alchemist_mode = False
        state.alchemy_first = None
        state.alchemy_selecting = False
        state.temple_mode = False
        state.smithy_mode = False
        state.portal_mode = False
        state.current_venue_id = None
        state.last_message = venue.get("leave_message", "You leave the venue.")
        return True

    if venue_id == "town_shop":
        venue = ctx.venues.get(venue_id, {})
        element = getattr(state.player, "current_element", "base")
        if command_id == "SHOP_BUY":
            state.shop_view = "buy"
            state.last_message = "Choose an item to buy."
            return True
        if command_id == "SHOP_SELL":
            state.shop_view = "sell"
            state.last_message = "Choose an item to sell."
            return True
        if state.shop_view == "buy":
            selection = next(
                (entry for entry in shop_inventory(venue, ctx.items, element) if entry.get("command") == command_id),
                None
            )
            if selection:
                item_id = selection.get("item_id")
                if item_id:
                    state.last_message = purchase_item(state.player, ctx.items, item_id)
                    ctx.save_data.save_player(state.player)
                return True
        if state.shop_view == "sell":
            selection = next(
                (entry for entry in shop_sell_inventory(state.player, ctx.items) if entry.get("command") == command_id),
                None
            )
            if selection:
                item_id = selection.get("item_id")
                if item_id:
                    state.last_message = sell_item(state.player, ctx.items, item_id)
                    ctx.save_data.save_player(state.player)
                return True

    if venue_id == "town_alchemist":
        if command_id == "ALCHEMY_FUSE":
            if len(_fusable_gear(state)) < 2:
                state.last_message = "You need at least two compatible items."
                return True
            state.alchemy_selecting = True
            state.alchemy_first = None
            state.action_cursor = 0
            state.last_message = "Select the first item to fuse."
            return True
        if command_id.startswith("ALCHEMY_PICK:"):
            idx_raw = command_id.split(":", 1)[1]
            if not idx_raw.isdigit():
                return False
            candidates = _fusable_gear(state, getattr(state, "alchemy_first", None))
            idx = int(idx_raw) - 1
            if idx < 0 or idx >= len(candidates):
                return False
            gear_id = candidates[idx].get("id")
            if not gear_id:
                return False
            if not state.alchemy_first:
                state.alchemy_first = gear_id
                state.action_cursor = 0
                state.last_message = "Select a second item to fuse."
                return True
            if state.alchemy_first == gear_id:
                state.last_message = "Choose a different item."
                return True
            fused = state.player.fuse_gear(state.alchemy_first, gear_id)
            state.alchemy_first = None
            state.alchemy_selecting = False
            state.action_cursor = 0
            if fused:
                state.last_message = f"Fused into {fused.get('name', 'gear')}."
                ctx.save_data.save_player(state.player)
            else:
                state.last_message = "Fusion failed."
            return True

    return False


def render_venue_body(
    ctx: Any,
    state: Any,
    venue_id: str,
    *,
    color_map_override: Optional[dict] = None,
) -> VenueRender:
    venue = ctx.venues.get(venue_id, {}) if venue_id else {}
    npc_lines = []
    npc_ids = venue.get("npc_ids", []) if isinstance(venue, dict) else []
    npc = {}
    if npc_ids:
        npc_lines = ctx.npcs.format_greeting(npc_ids[0])
        npc = ctx.npcs.get(npc_ids[0], {})
    body: list[str] = []
    if npc_lines:
        body += npc_lines + [""]

    if getattr(state, "hall_mode", False):
        info_sections = venue.get("info_sections", []) if isinstance(venue, dict) else []
        section = next((entry for entry in info_sections if entry.get("key") == state.hall_view), None)
        source = section.get("source") if section else None
        if source == "items":
            body += ctx.items.list_descriptions()
        elif source == "opponents":
            body += ctx.opponents.list_descriptions()

    if venue_id == "town_shop":
        element = getattr(state.player, "current_element", "base")
        if state.shop_view == "menu":
            body.append("What would you like to do?")
        elif state.shop_view == "buy":
            for entry in shop_inventory(venue, ctx.items, element):
                item_id = entry.get("item_id")
                item = ctx.items.get(item_id, {})
                label = entry.get("label", item.get("name", item_id))
                price = item.get("price", 0)
                body.append(f"{label}  {price} GP")
        elif state.shop_view == "sell":
            for entry in shop_sell_inventory(state.player, ctx.items):
                label = entry.get("label", "Item")
                price = entry.get("price", 0)
                body.append(f"{label}  {price} GP")

    if getattr(state, "alchemist_mode", False) and state.alchemy_first:
        gear_items = [g for g in state.player.gear_inventory if isinstance(g, dict)]
        first = next((g for g in gear_items if g.get("id") == state.alchemy_first), None)
        if first:
            body.append(f"First: {first.get('name', 'Gear')}")
            body.append("")

    portal_message = None
    portal_commands = None
    if getattr(state, "portal_mode", False):
        atlas = ctx.glyphs.get("atlas", {}) if hasattr(ctx, "glyphs") else {}
        atlas_lines = atlas.get("art", []) if isinstance(atlas, dict) else []
        commands = venue_actions(ctx, state, venue_id)
        portal_commands = commands
        portal_cmds = [
            (idx, cmd) for idx, cmd in enumerate(commands)
            if str(cmd.get("command", "")).startswith("PORTAL:")
        ]
        left_lines = []
        selected_element = None
        if state.action_cursor is not None:
            selected = next((cmd for idx, cmd in portal_cmds if idx == state.action_cursor), None)
            if selected:
                selected_element = str(selected.get("command", "")).split(":", 1)[1]
        if selected_element is None:
            selected_element = getattr(state.player, "current_element", None)
        if selected_element and hasattr(ctx, "continents"):
            entry = ctx.continents.continents().get(selected_element, {})
            if isinstance(entry, dict):
                portal_message = entry.get("description")
        right_lines = list(atlas_lines)
        total_lines = max(len(left_lines), len(right_lines))
        content_width = max(0, SCREEN_WIDTH - 2)
        right_width = max((len(r) for r in right_lines), default=0)
        right_width = min(right_width, 24)
        right_width = min(right_width, max(0, content_width))
        left_width = max(0, (content_width - right_width) // 2)
        for i in range(total_lines):
            left = left_lines[i] if i < len(left_lines) else ""
            right = right_lines[i] if i < len(right_lines) else ""
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
                    unlocked = set(getattr(state.player, "elements", []) or [])
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
                    if selected_element in selected_map:
                        flicker_digit = selected_map[selected_element]
                        flicker_on = int(time.time() / 0.35) % 2 == 0
                colored_right = _colorize_atlas_line(right, digit_colors, flicker_digit, flicker_on, locked_color)
                line = line + colored_right
            body.append(line)

    if not getattr(state, "portal_mode", False):
        body += venue.get("narrative", []) if isinstance(venue, dict) else []

    art_anchor_x = None
    if venue.get("objects"):
        art_lines, art_color, art_anchor_x = render_venue_objects(venue, npc, ctx.objects, color_map_override)
    else:
        art_lines, art_color = render_venue_art(venue, npc, color_map_override)

    actions = venue_actions(ctx, state, venue_id)
    title = venue.get("name", "Venue") if isinstance(venue, dict) else "Venue"
    return VenueRender(
        title=title,
        body=body,
        art_lines=art_lines,
        art_color=art_color or ANSI.FG_WHITE,
        art_anchor_x=art_anchor_x,
        actions=actions,
        message=portal_message,
    )
