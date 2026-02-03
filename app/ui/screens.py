"""Screen composition helpers for game UI states."""

import random
import textwrap
import time
from dataclasses import dataclass
import json
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
from app.data_access.music_data import MusicData
from app.data_access.npcs_data import NpcsData
from app.data_access.objects_data import ObjectsData
from app.data_access.opponents_data import OpponentsData
from app.data_access.players_data import PlayersData
from app.data_access.quests_data import QuestsData
from app.data_access.scenes_data import ScenesData
from app.data_access.spells_data import SpellsData
from app.data_access.stories_data import StoriesData
from app.data_access.portal_screen_data import PortalScreenData
from app.data_access.quests_screen_data import QuestsScreenData
from app.data_access.spellbook_screen_data import SpellbookScreenData
from app.data_access.followers_screen_data import FollowersScreenData
from app.data_access.title_screen_data import TitleScreenData
from app.data_access.venues_data import VenuesData
from app.data_access.text_data import TextData
from app.models import Frame, Player, Opponent
from app.questing import ordered_quest_ids, quest_entries, requirement_summary
from app.ui.ansi import ANSI, color
from app.ui.layout import (
    center_ansi,
    format_action_lines,
    format_command_lines,
    format_menu_actions,
    pad_or_trim_ansi,
    strip_ansi,
)
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
    players: PlayersData
    title_screen: TitleScreenData
    portal_screen: PortalScreenData
    spellbook_screen: SpellbookScreenData
    quests_screen: QuestsScreenData
    followers_screen: FollowersScreenData
    music: MusicData


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


def _menu_line(label: str, selected: bool) -> str:
    text = label.strip()
    if selected:
        return f"[ {text} ]"
    return f"  {text}"


def _asset_explorer_music_assets(ctx: ScreenContext, asset_type: str) -> dict:
    data = ctx.music.all() if hasattr(ctx, "music") else {}
    if not isinstance(data, dict):
        data = {}
    if asset_type == "music":
        songs = data.get("songs", {})
        return songs if isinstance(songs, dict) else {}
    if asset_type == "sfx":
        sequences = data.get("sequences", {})
        songs = data.get("songs", {})
        listed = {}
        if isinstance(sequences, dict):
            for key, value in sequences.items():
                if "sfx" in str(key).lower():
                    listed[key] = value
        if isinstance(songs, dict):
            for key, value in songs.items():
                if isinstance(value, dict) and value.get("sfx"):
                    listed[key] = value
        return listed
    return {}


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
    menu_id = _title_menu_id(title_data, player, menu_stack)
    menu_data = menus.get(menu_id, {}) if isinstance(menus, dict) else {}
    narrative = menu_data.get("narrative", [])
    if not isinstance(narrative, list):
        narrative = []
    items = menu_data.get("items", [])
    if menu_id == "title_assets_list":
        asset_type = getattr(player, "asset_explorer_type", "") or ""
        if not asset_type:
            narrative = ["Asset Explorer", "Select an asset type."]
            items = [
                {"label": "Objects", "command": "TITLE_ASSET_TYPE:objects"},
                {"label": "Opponents", "command": "TITLE_ASSET_TYPE:opponents"},
                {"label": "Items", "command": "TITLE_ASSET_TYPE:items"},
                {"label": "Spells", "command": "TITLE_ASSET_TYPE:spells"},
                {"label": "Spells Art", "command": "TITLE_ASSET_TYPE:spells_art"},
                {"label": "Glyphs", "command": "TITLE_ASSET_TYPE:glyphs"},
                {"label": "Music", "command": "TITLE_ASSET_TYPE:music"},
                {"label": "SFX", "command": "TITLE_ASSET_TYPE:sfx"},
                {"label": "Back", "command": "TITLE_ASSET_BACK"},
            ]
        else:
            asset_label = {
                "objects": "Objects",
                "opponents": "Opponents",
                "items": "Items",
                "spells": "Spells",
                "spells_art": "Spells Art",
                "glyphs": "Glyphs",
                "music": "Music",
                "sfx": "SFX",
            }.get(asset_type, "Assets")
            narrative = [f"Asset Explorer: {asset_label}"]
            assets = {}
            if asset_type == "objects":
                assets = ctx.objects.all()
            elif asset_type == "opponents":
                opp_data = ctx.opponents.all()
                if isinstance(opp_data, dict):
                    assets = opp_data
            elif asset_type == "items":
                assets = ctx.items.all()
            elif asset_type == "spells":
                assets = ctx.spells.all()
            elif asset_type == "spells_art":
                assets = ctx.spells_art.all()
            elif asset_type == "glyphs":
                assets = ctx.glyphs.all()
            elif asset_type in ("music", "sfx"):
                assets = _asset_explorer_music_assets(ctx, asset_type)
            if not isinstance(assets, dict):
                assets = {}
            asset_ids = sorted(str(key) for key in assets.keys())
            items = [{"label": asset_id, "command": f"TITLE_ASSET_SELECT:{asset_id}"} for asset_id in asset_ids]
            items.append({
                "label": f"Show Art: {'On' if getattr(player, 'asset_explorer_show_art', True) else 'Off'}",
                "command": "TITLE_ASSET_TOGGLE:art",
            })
            items.append({
                "label": f"Show Stats: {'On' if getattr(player, 'asset_explorer_show_stats', True) else 'Off'}",
                "command": "TITLE_ASSET_TOGGLE:stats",
            })
            items.append({
                "label": f"Show JSON: {'On' if getattr(player, 'asset_explorer_show_json', False) else 'Off'}",
                "command": "TITLE_ASSET_TOGGLE:json",
            })
            if asset_type in ("music", "sfx"):
                wave = getattr(player, "asset_explorer_waveform", "square") or "square"
                items.append({
                    "label": f"Waveform: {wave.title()}",
                    "command": "TITLE_ASSET_TOGGLE:wave",
                })
            items.append({"label": "Refresh", "command": "TITLE_ASSET_REFRESH"})
            items.append({"label": "Back", "command": "TITLE_ASSET_BACK"})
            selected_id = None
            if asset_ids:
                if 0 <= selected_index < len(asset_ids):
                    selected_id = asset_ids[selected_index]
                else:
                    selected_id = asset_ids[0]
            asset = assets.get(selected_id, {}) if selected_id is not None else {}
            if isinstance(asset, dict):
                name = asset.get("name")
                if name:
                    narrative.append(str(name)[:64])
                desc = asset.get("description") or asset.get("desc")
                if desc:
                    narrative.append(str(desc)[:80])
                if getattr(player, "asset_explorer_show_stats", True):
                    stats = []
                    for key in ("level", "hp", "atk", "defense", "speed", "mp_cost", "price"):
                        if key in asset:
                            stats.append(f"{key}:{asset.get(key)}")
                    if stats:
                        narrative.append("Stats: " + " ".join(stats))
                if getattr(player, "asset_explorer_show_art", True):
                    art = asset.get("art")
                    if isinstance(art, list):
                        narrative.append("")
                        narrative.extend(str(line)[:80] for line in art[:10])
                if getattr(player, "asset_explorer_show_json", False):
                    raw = json.dumps(asset, indent=2, ensure_ascii=True)
                    lines = raw.splitlines()[:8]
                    if lines:
                        narrative.append("")
                        narrative.extend(line[:80] for line in lines)
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
    if items == "player_select":
        players = ctx.players.all() if hasattr(ctx, "players") else {}
        if not isinstance(players, dict):
            players = {}
        player_ids = sorted(str(key) for key in players.keys())
        if not player_ids:
            narrative = list(narrative)
            narrative.append("No player art found.")
        else:
            narrative = list(narrative)
            if narrative and narrative[-1] != "":
                narrative.append("")
            selected_idx = getattr(player, "title_player_cursor", 0)
            if selected_idx < 0 or selected_idx >= len(player_ids):
                selected_idx = 0
            arts = []
            colors = ctx.colors.all() if hasattr(ctx, "colors") else {}
            def _apply_mask_line(line: str, mask: str) -> str:
                if not line or not isinstance(colors, dict):
                    return line
                out = []
                padded_mask = mask.ljust(len(line))
                for idx, ch in enumerate(line):
                    mask_ch = padded_mask[idx] if idx < len(padded_mask) else ""
                    code = _color_code_for_key(colors, mask_ch) if mask_ch else ""
                    if code and ch != " ":
                        out.append(f"{code}{ch}{ANSI.RESET}")
                    else:
                        out.append(ch)
                return "".join(out)
            for idx, player_id in enumerate(player_ids[:2]):
                entry = players.get(player_id, {})
                art = entry.get("art", [])
                art_lines = [str(line) for line in art] if isinstance(art, list) else []
                masks = entry.get("color_map", []) if isinstance(entry, dict) else []
                if isinstance(masks, list) and masks and isinstance(colors, dict):
                    colored = []
                    for line, mask in zip(art_lines, masks):
                        colored.append(_apply_mask_line(str(line), str(mask)))
                    art_lines = colored
                width = max((len(strip_ansi(line)) for line in art_lines), default=0)
                height = max(len(art_lines), 1)
                padded = [pad_or_trim_ansi(line, width).ljust(width) for line in art_lines]
                while len(padded) < height:
                    padded.append(" " * width)
                arts.append((padded, width, height))
            if arts:
                max_height = max(height for _, _, height in arts)
                gap = "   "
                left_lines, left_width, left_height = arts[0]
                right_lines = []
                if len(arts) > 1:
                    right_lines, right_width, right_height = arts[1]
                for i in range(max_height):
                    left = left_lines[i] if i < left_height else " " * left_width
                    if right_lines:
                        right = right_lines[i] if i < right_height else " " * right_width
                        narrative.append(f"{left}{gap}{right}")
                    else:
                        narrative.append(left)
                underline_left = " " * left_width
                underline_right = ""
                if selected_idx == 0 and left_width:
                    underline_left = "_" * left_width
                if len(arts) > 1:
                    underline_right = " " * right_width
                    if selected_idx == 1 and right_width:
                        underline_right = "_" * right_width
                    narrative.append(f"{underline_left}{gap}{underline_right}")
                else:
                    narrative.append(underline_left)
        items = [
            {"label": "Confirm", "command": "TITLE_PLAYER_CONFIRM"},
            {"label": "Back", "command": "TITLE_PLAYER_BACK"},
        ]
    detail_lines = menu_data.get("detail_lines", [])
    if isinstance(detail_lines, list) and detail_lines:
        narrative = list(narrative)
        narrative.append("")
        narrative.append(detail_lines[min(max(selected_index, 0), len(detail_lines) - 1)])
    if menu_id == "title_start_confirm":
        pending_name = str(getattr(player, "title_pending_name", "") or "WARRIOR")
        pending_fortune = str(getattr(player, "title_pending_fortune", "") or "")
        pending_avatar = str(getattr(player, "title_pending_player_id", "") or "")
        fortune_map = {
            "FORTUNE_POOR": "Poor (10 GP)",
            "FORTUNE_WELL_OFF": "Well-Off (100 GP)",
            "FORTUNE_ROYALTY": "Royalty (1,000 GP)",
        }
        fortune_label = fortune_map.get(pending_fortune, "Unknown")
        avatar_label = pending_avatar or "Unknown"
        if pending_avatar and hasattr(ctx, "players"):
            avatar_entry = ctx.players.get(pending_avatar, {})
            label = avatar_entry.get("label")
            if label:
                avatar_label = str(label)
        narrative = list(narrative)
        narrative.append("")
        narrative.append(f"Name: {pending_name[:16]}")
        narrative.append(f"Avatar: {avatar_label}")
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
    if commands:
        audio_mode = str(getattr(player, "flags", {}).get("audio_mode", "on"))
        label_map = {
            "on": "Audio: On",
            "off": "Audio: Off",
            "music": "Audio: Music Only",
            "sfx": "Audio: SFX Only",
        }
        for entry in commands:
            if entry.get("command") == "TOGGLE_AUDIO":
                entry["label"] = label_map.get(audio_mode, "Audio: On")
    if menu_id == "title_audio" and commands:
        flags = getattr(player, "flags", {}) if hasattr(player, "flags") else {}
        if not isinstance(flags, dict):
            flags = {}
        music_volume = int(flags.get("audio_music_volume", 5) or 0)
        sfx_volume = int(flags.get("audio_sfx_volume", 5) or 0)
        music_volume = max(0, min(5, music_volume))
        sfx_volume = max(0, min(5, sfx_volume))
        wave = str(flags.get("audio_wave", "square") or "square")
        def _bar(value: int) -> str:
            return "[" + ("#" * value) + ("." * (5 - value)) + "]"
        for entry in commands:
            cmd = entry.get("command")
            if cmd == "TITLE_AUDIO_MUSIC":
                entry["label"] = f"Music: {_bar(music_volume)}"
            elif cmd == "TITLE_AUDIO_SFX":
                entry["label"] = f"SFX: {_bar(sfx_volume)}"
            elif cmd == "TITLE_AUDIO_WAVE":
                entry["label"] = f"Instrument: {wave.title()}"
    return narrative, commands, detail_lines if isinstance(detail_lines, list) else []


def _title_menu_id(title_data: dict, player, menu_stack: list[str]) -> str:
    menu_id = menu_stack[-1] if menu_stack else title_data.get("root_menu", "title_root")
    if getattr(player, "title_name_input", False):
        menu_id = "title_name_input"
    if getattr(player, "title_player_select", False):
        menu_id = "title_player"
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
    return menu_id


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
    base_labels = []
    for idx, line in enumerate(labels):
        is_dim = ANSI.DIM in line
        base = strip_ansi(line)
        base_labels.append(base)
        line = _menu_line(base, selected_index >= 0 and idx == selected_index)
        if is_dim:
            line = f"{ANSI.DIM}{line}{ANSI.RESET}"
        display_labels.append(line)
    max_label_len = max((len(label) for label in base_labels), default=0)
    if max_label_len:
        max_label_len += 4
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


def _colorize_element_atlas_line(
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
        if ch in ("a", "b"):
            out.append(f"{ANSI.FG_BLUE}~{ANSI.RESET}")
            continue
        if ch in ("|", "-", "/", "\\"):
            out.append(f"{ANSI.FG_YELLOW}{ch}{ANSI.RESET}")
            continue
        if ch == "o":
            out.append(f"{ANSI.FG_WHITE}{ANSI.DIM}{ch}{ANSI.RESET}")
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
    quest_mode: bool = False,
    quest_detail_mode: bool = False,
    title_menu_stack: Optional[list[str]] = None,
    options_mode: bool = False,
    action_cursor: int = 0,
    menu_cursor: int = 0,
    followers_focus: str = "list",
    followers_action_cursor: int = 0,
    spell_cast_rank: int = 1,
    spell_target_mode: bool = False,
    spell_target_cursor: int = 0,
    spell_target_command: Optional[str] = None,
    quest_continent_index: int = 0,
    quest_detail_id: Optional[str] = None,
    quest_detail_page: int = 0,
    level_cursor: int = 0,
    level_up_notes: Optional[List[str]] = None,
    suppress_actions: bool = False
) -> Frame:
    """Build a screen frame from game state and UI data."""
    life_boost = ctx.spells.get("life_boost", {})
    spark = ctx.spells.get("spark", {})
    heal_name = life_boost.get("name", "Healing")
    spark_name = spark.get("name", "Spark")
    if not isinstance(menu_cursor, int):
        try:
            menu_cursor = int(menu_cursor)
        except (TypeError, ValueError):
            menu_cursor = -1
    if not isinstance(action_cursor, int):
        try:
            action_cursor = int(action_cursor)
        except (TypeError, ValueError):
            action_cursor = -1
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
    art_lines = []
    art_color = ANSI.FG_WHITE
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
            level_lines.append(_menu_line(line, idx == level_cursor))
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
    elif quest_mode:
        quest_data = ctx.quests_screen.all() if hasattr(ctx, "quests_screen") else {}
        layout = quest_data.get("layout", {}) if isinstance(quest_data, dict) else {}
        menu_cfg = layout.get("menu", {}) if isinstance(layout, dict) else {}
        atlas_cfg = layout.get("atlas", {}) if isinstance(layout, dict) else {}
        desc_cfg = layout.get("description", {}) if isinstance(layout, dict) else {}

        def _box_lines(width: int, height: int, content: list[str], *, margin: int, style: str) -> list[str]:
            width = max(2, width)
            height = max(2, height)
            box = _draw_box(width, height, style=style)
            inner_width = width - 2
            inner_height = height - 2
            pad_margin = max(0, min(margin, max(0, inner_width // 2)))
            content_lines = [" " * inner_width for _ in range(inner_height)]
            inner_content_width = max(0, inner_width - (pad_margin * 2))
            row = pad_margin
            for line in content:
                if row >= inner_height - pad_margin:
                    break
                content_lines[row] = (" " * pad_margin) + pad_or_trim_ansi(line, inner_content_width) + (" " * pad_margin)
                row += 1
            for i in range(inner_height):
                box[i + 1] = "|" + content_lines[i] + "|"
            return box

        elements = list(getattr(player, "elements", []) or [])
        if hasattr(ctx, "continents"):
            order = list(ctx.continents.order() or [])
            if order:
                elements = [e for e in order if e in elements] or elements
        if not elements:
            elements = ["base"]
        quest_continent_index = max(0, min(quest_continent_index, len(elements) - 1))
        selected_element = elements[quest_continent_index]
        continent_label = ctx.continents.name_for(selected_element) if hasattr(ctx, "continents") else str(selected_element).title()
        continent_label = f"<{{([ {continent_label} ])}}>"

        ordered_ids = ordered_quest_ids(ctx.stories, ctx.quests, selected_element) if hasattr(ctx, "stories") else []
        entries = quest_entries(
            player,
            ctx.quests,
            ctx.items,
            continent=selected_element,
            include_locked_next=True,
            ordered_ids=ordered_ids,
        ) if hasattr(ctx, "quests") else []
        commands = []
        detail_quest = None
        dialog_lines = []
        if quest_detail_mode and quest_detail_id:
            detail_quest = ctx.quests.get(quest_detail_id, {}) if hasattr(ctx, "quests") else {}
            dialog = detail_quest.get("dialog", [])
            if not isinstance(dialog, list):
                dialog = []
            dialog_lines = [str(line) for line in dialog if line is not None]
            total_pages = max(1, len(dialog_lines))
            quest_detail_page = max(0, min(quest_detail_page, total_pages - 1))
            is_last = quest_detail_page >= total_pages - 1
            commands = [
                {"label": "Start Quest" if is_last else "Next"},
                {"label": "Cancel", "command": "B_KEY"},
            ]
        else:
            commands = [
                {"label": continent_label, "_disabled": True, "_header": True},
                {"label": "", "_disabled": True, "_spacer": True},
            ]
            if entries:
                for entry in entries:
                    quest = entry.get("quest", {})
                    quest_id = entry.get("id", "")
                    short_name = str(quest.get("title") or "").strip()
                    if not short_name:
                        summary = str(quest.get("summary") or quest_id)
                        words = summary.split()
                        short_name = " ".join(words[:5]) if words else str(quest_id)
                    commands.append({
                        "label": short_name,
                        "quest_id": quest_id,
                        "status": entry.get("status", "available"),
                        "_disabled": entry.get("status") == "complete",
                        "quest": quest,
                    })
            else:
                commands.append({"label": "No quests available.", "_disabled": True})
            commands.append({"label": "Back", "command": "B_KEY"})

        enabled = [i for i, cmd in enumerate(commands) if not cmd.get("_disabled")]
        if not enabled:
            action_cursor = -1
        elif action_cursor not in enabled:
            action_cursor = enabled[0]
        else:
            action_cursor = max(0, min(action_cursor, len(commands) - 1))

        menu_labels = []
        base_menu_labels = []
        for idx, entry in enumerate(commands):
            label = str(entry.get("label", ""))
            if entry.get("_header"):
                label = label.strip()
            base_menu_labels.append(label.strip() if entry.get("_header") else label.strip())
        max_label = max((len(label) for label in base_menu_labels), default=0)
        if max_label:
            max_label += 4
        menu_margin = int(menu_cfg.get("margin", 1) or 1)
        menu_style = str(menu_cfg.get("frame_style", "round") or "round")
        menu_width = max(10, max_label + 2 + (menu_margin * 2))

        menu_inner_width = max(1, menu_width - 2 - (menu_margin * 2))
        for idx, entry in enumerate(commands):
            label = str(entry.get("label", ""))
            if entry.get("_header"):
                line = center_ansi(label.strip(), menu_inner_width)
            elif entry.get("_spacer"):
                line = " " * menu_inner_width
            else:
                line = _menu_line(label.strip(), idx == action_cursor)
            if entry.get("_disabled") and not entry.get("_spacer"):
                line = f"{ANSI.DIM}{line}{ANSI.RESET}"
            menu_labels.append(line)

        desc_margin = int(desc_cfg.get("margin", 1) or 1)
        desc_style = str(desc_cfg.get("frame_style", "round") or "round")
        desc_width = max(10, int(desc_cfg.get("width", 20) or 20))
        desc_inner_width = max(1, desc_width - 2 - (desc_margin * 2))
        desc_text = ""
        selected_entry = commands[action_cursor] if 0 <= action_cursor < len(commands) else {}
        quest_id = selected_entry.get("quest_id")
        if quest_detail_mode and detail_quest:
            if dialog_lines:
                desc_text = dialog_lines[quest_detail_page]
        elif quest_id:
            quest = selected_entry.get("quest", {})
            status = selected_entry.get("status", "")
            if status == "complete":
                desc_text = str(quest.get("summary_complete", "Quest complete.") or "Quest complete.")
            elif status == "locked":
                desc_text = requirement_summary(player, quest)
            elif status == "active":
                desc_text = str(quest.get("summary_active", "") or quest.get("summary_pre", "") or "")
            else:
                desc_text = str(quest.get("summary_pre", "") or "")
        elif hasattr(ctx, "continents"):
            entry = ctx.continents.continents().get(selected_element, {})
            if isinstance(entry, dict):
                desc_text = str(entry.get("description", "") or "")
        descriptions = []
        if quest_detail_mode and detail_quest:
            descriptions.extend(dialog_lines or [""])
        else:
            for entry in entries:
                quest = entry.get("quest", {})
                status = entry.get("status", "")
                if status == "locked":
                    desc = requirement_summary(player, quest)
                else:
                    desc = str(quest.get("summary", "") or "")
                descriptions.append(desc)
            if hasattr(ctx, "continents"):
                for element in elements:
                    entry = ctx.continents.continents().get(element, {})
                    if isinstance(entry, dict):
                        descriptions.append(str(entry.get("description", "") or ""))
        wrapped_sets = [
            textwrap.wrap(desc, width=desc_inner_width) if desc else [""]
            for desc in descriptions
        ]
        max_desc_lines = max((len(lines) for lines in wrapped_sets), default=1)
        desc_lines = textwrap.wrap(desc_text, width=desc_inner_width) if desc_text else [""]
        desc_height = max(3, max_desc_lines + 2 + (desc_margin * 2))
        desc_center_x = int(desc_cfg.get("x", 2) or 2)
        anchor = str(desc_cfg.get("anchor", "") or "").lower()
        if anchor == "bottom":
            desc_center_y = SCREEN_HEIGHT - (desc_height // 2) - 1
        else:
            desc_center_y = int(desc_cfg.get("y", SCREEN_HEIGHT - desc_height - 1) or (SCREEN_HEIGHT - desc_height - 1))
        desc_height = min(desc_height, SCREEN_HEIGHT - 2)
        desc_width = min(desc_width, SCREEN_WIDTH - 2)
        desc_x = max(0, min(SCREEN_WIDTH - desc_width, desc_center_x - (desc_width // 2)))
        desc_y = max(0, min(SCREEN_HEIGHT - desc_height, desc_center_y - (desc_height // 2)))
        desc_inner_height = max(1, desc_height - 2 - (desc_margin * 2))
        if len(desc_lines) > desc_inner_height:
            desc_lines = desc_lines[:desc_inner_height]

        menu_center_x = int(menu_cfg.get("x", 2) or 2)
        menu_center_y = int(menu_cfg.get("y", 1) or 1)
        menu_height = max(3, len(menu_labels) + 2 + (menu_margin * 2))
        menu_height = min(menu_height, max(3, desc_y - 1))
        menu_x = max(0, min(SCREEN_WIDTH - menu_width, menu_center_x - (menu_width // 2)))
        menu_y = max(0, min(SCREEN_HEIGHT - menu_height, menu_center_y - (menu_height // 2)))

        atlas_margin = int(atlas_cfg.get("margin", 1) or 1)
        atlas_style = str(atlas_cfg.get("frame_style", "round") or "round")
        atlas_lines = []
        opponent_masks = []
        art_opponent_id = None
        if quest_detail_mode and detail_quest:
            art_opponent_id = str(detail_quest.get("art_opponent") or "").strip()
        if art_opponent_id and hasattr(ctx, "opponents"):
            opponent_entry = ctx.opponents.get(art_opponent_id, {})
            if isinstance(opponent_entry, dict):
                atlas_lines = opponent_entry.get("art", []) if isinstance(opponent_entry.get("art"), list) else []
                if isinstance(opponent_entry.get("color_map"), list):
                    opponent_masks = opponent_entry.get("color_map")
        if not atlas_lines:
            atlas_id = atlas_cfg.get("glyph_id", "atlas")
            atlas = ctx.glyphs.get(atlas_id, {}) if hasattr(ctx, "glyphs") else {}
            atlas_lines = atlas.get("art", []) if isinstance(atlas, dict) else []
        atlas_inner_width = max((len(strip_ansi(line)) for line in atlas_lines), default=0)
        atlas_width = max(10, atlas_inner_width + 2 + (atlas_margin * 2))
        atlas_height = max(3, len(atlas_lines) + 2 + (atlas_margin * 2))
        atlas_center_x = int(atlas_cfg.get("x", menu_x + menu_width + 2) or (menu_x + menu_width + 2))
        atlas_center_y = int(atlas_cfg.get("y", menu_y) or menu_y)
        atlas_width = min(atlas_width, SCREEN_WIDTH - 2)
        atlas_height = min(atlas_height, SCREEN_HEIGHT - 2)
        atlas_x = max(0, min(SCREEN_WIDTH - atlas_width, atlas_center_x - (atlas_width // 2)))
        atlas_y = max(0, min(SCREEN_HEIGHT - atlas_height, atlas_center_y - (atlas_height // 2)))

        digit_colors = {}
        flicker_digit = None
        flicker_on = True
        if selected_element and hasattr(ctx, "elements"):
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
            unlocked_set = set(str(e) for e in elements)
            for digit, (element_key, palette) in elem_colors.items():
                if palette and element_key in unlocked_set:
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
        if art_opponent_id and atlas_lines:
            if opponent_masks and hasattr(ctx, "colors"):
                colors = ctx.colors.all()
                if isinstance(colors, dict):
                    colored = []
                    for line, mask in zip(atlas_lines, opponent_masks):
                        line_str = str(line)
                        mask_str = str(mask)
                        padded_mask = mask_str.ljust(len(line_str))
                        out = []
                        for idx, ch in enumerate(line_str):
                            mask_ch = padded_mask[idx] if idx < len(padded_mask) else ""
                            code = _color_code_for_key(colors, mask_ch) if mask_ch else ""
                            if code and ch != " ":
                                out.append(f"{code}{ch}{ANSI.RESET}")
                            else:
                                out.append(ch)
                        colored.append("".join(out))
                    if len(opponent_masks) < len(atlas_lines):
                        colored.extend(str(line) for line in atlas_lines[len(opponent_masks):])
                    colored_atlas = colored
                else:
                    colored_atlas = list(atlas_lines)
            else:
                colored_atlas = list(atlas_lines)
        else:
            colored_atlas = [
                _colorize_atlas_line(
                    line,
                    digit_colors,
                    flicker_digit,
                    flicker_on,
                    f"{ANSI.FG_WHITE}{ANSI.DIM}",
                )
                for line in atlas_lines
            ]

        menu_box = _box_lines(menu_width, menu_height, menu_labels, margin=menu_margin, style=menu_style)
        atlas_box = _box_lines(atlas_width, atlas_height, colored_atlas, margin=atlas_margin, style=atlas_style)
        desc_box = _box_lines(desc_width, desc_height, desc_lines, margin=desc_margin, style=desc_style)

        canvas = [" " * SCREEN_WIDTH for _ in range(SCREEN_HEIGHT)]

        def _overlay_box(box_lines: list[str], start_x: int, start_y: int) -> None:
            for idx, line in enumerate(box_lines):
                row = start_y + idx
                if 0 <= row < SCREEN_HEIGHT:
                    overlay = pad_or_trim_ansi((" " * start_x) + line, SCREEN_WIDTH)
                    base_cells = _ansi_cells(canvas[row])
                    overlay_cells = _ansi_cells(overlay)
                    merged = []
                    for (base_ch, base_code), (over_ch, over_code) in zip(base_cells, overlay_cells):
                        if over_ch == " ":
                            merged.append(ANSI.RESET + base_code + base_ch)
                        else:
                            merged.append(ANSI.RESET + over_code + over_ch)
                    canvas[row] = "".join(merged) + ANSI.RESET

        _overlay_box(menu_box, menu_x, menu_y)
        _overlay_box(atlas_box, atlas_x, atlas_y)
        _overlay_box(desc_box, desc_x, desc_y)

        body = []
        actions = []
        display_location = "Quests"
        raw_lines = canvas
    elif player.location == "Town" and (shop_mode or hall_mode or inn_mode or alchemist_mode or temple_mode or smithy_mode or portal_mode):
        if portal_mode:
            portal_data = ctx.portal_screen.all() if hasattr(ctx, "portal_screen") else {}
            layout = portal_data.get("layout", {}) if isinstance(portal_data, dict) else {}
            menu_cfg = layout.get("menu", {}) if isinstance(layout, dict) else {}
            atlas_cfg = layout.get("atlas", {}) if isinstance(layout, dict) else {}
            desc_cfg = layout.get("description", {}) if isinstance(layout, dict) else {}

            def _box_lines(width: int, height: int, content: list[str], *, margin: int, style: str) -> list[str]:
                width = max(2, width)
                height = max(2, height)
                box = _draw_box(width, height, style=style)
                inner_width = width - 2
                inner_height = height - 2
                pad_margin = max(0, min(margin, max(0, inner_width // 2)))
                content_lines = [" " * inner_width for _ in range(inner_height)]
                inner_content_width = max(0, inner_width - (pad_margin * 2))
                row = pad_margin
                for line in content:
                    if row >= inner_height - pad_margin:
                        break
                    content_lines[row] = (" " * pad_margin) + pad_or_trim_ansi(line, inner_content_width) + (" " * pad_margin)
                    row += 1
                for i in range(inner_height):
                    box[i + 1] = "|" + content_lines[i] + "|"
                return box

            elements = list(ctx.continents.order() or []) if hasattr(ctx, "continents") else []
            if not elements and hasattr(ctx, "continents"):
                elements = list(ctx.continents.continents().keys())
            unlocked = set(getattr(player, "elements", []) or [])
            current_element = getattr(player, "current_element", None)
            commands = []
            for element in elements:
                label = ctx.continents.name_for(element) if hasattr(ctx, "continents") else str(element).title()
                entry = {"label": label, "command": f"PORTAL:{element}"}
                if element not in unlocked:
                    entry["_disabled"] = True
                if element == current_element:
                    entry["_current"] = True
                    entry["_disabled"] = True
                commands.append(entry)
            if not commands:
                commands.append({"label": "No continents available.", "_disabled": True})
            commands.append({"label": "Back", "command": "B_KEY"})

            action_cursor = max(0, min(action_cursor, len(commands) - 1)) if commands else -1
            selected_command = commands[action_cursor] if 0 <= action_cursor < len(commands) else {}
            selected_element = current_element
            cmd_id = str(selected_command.get("command", ""))
            if cmd_id.startswith("PORTAL:"):
                selected_element = cmd_id.split(":", 1)[1]

            menu_labels = []
            base_menu_labels = []
            for idx, entry in enumerate(commands):
                label = str(entry.get("label", "")).strip()
                base_menu_labels.append(label)
                line = _menu_line(label, idx == action_cursor)
                if entry.get("_current"):
                    wrapped = f"< {label} >"
                    line = _menu_line(wrapped, idx == action_cursor)
                    line = f"{ANSI.FG_YELLOW}{ANSI.BOLD}{line}{ANSI.RESET}"
                elif entry.get("_disabled"):
                    line = f"{ANSI.DIM}{line}{ANSI.RESET}"
                menu_labels.append(line)
            max_label = max((len(label) for label in base_menu_labels), default=0)
            current_label_len = 0
            if current_element:
                current_name = ctx.continents.name_for(current_element) if hasattr(ctx, "continents") else str(current_element).title()
                current_label_len = len(f"< {current_name} >")
            max_label = max(max_label, current_label_len)
            if max_label:
                max_label += 4
            menu_margin = int(menu_cfg.get("margin", 1) or 1)
            menu_style = str(menu_cfg.get("frame_style", "round") or "round")
            menu_width = max(10, max_label + 2 + (menu_margin * 2))

            desc_margin = int(desc_cfg.get("margin", 1) or 1)
            desc_style = str(desc_cfg.get("frame_style", "round") or "round")
            desc_x = int(desc_cfg.get("x", 2) or 2)
            desc_width = max(10, int(desc_cfg.get("width", 20) or 20))
            desc_inner_width = max(1, desc_width - 2 - (desc_margin * 2))
            descriptions = []
            if hasattr(ctx, "continents"):
                for element, entry in ctx.continents.continents().items():
                    if not isinstance(entry, dict):
                        continue
                    desc = str(entry.get("description", "") or "")
                    descriptions.append(desc)
            wrapped_sets = [
                textwrap.wrap(desc, width=desc_inner_width) if desc else [""]
                for desc in descriptions
            ]
            max_desc_lines = max((len(lines) for lines in wrapped_sets), default=1)
            desc_height = max(3, max_desc_lines + 2 + (desc_margin * 2))
            desc_center_x = int(desc_cfg.get("x", 2) or 2)
            anchor = str(desc_cfg.get("anchor", "") or "").lower()
            if anchor == "bottom":
                desc_center_y = SCREEN_HEIGHT - (desc_height // 2) - 1
            else:
                desc_center_y = int(desc_cfg.get("y", SCREEN_HEIGHT - desc_height - 1) or (SCREEN_HEIGHT - desc_height - 1))
            desc_height = min(desc_height, SCREEN_HEIGHT - 2)
            desc_width = min(desc_width, SCREEN_WIDTH - 2)
            desc_x = max(0, min(SCREEN_WIDTH - desc_width, desc_center_x - (desc_width // 2)))
            desc_y = max(0, min(SCREEN_HEIGHT - desc_height, desc_center_y - (desc_height // 2)))
            desc_inner_height = max(1, desc_height - 2 - (desc_margin * 2))

            menu_center_x = int(menu_cfg.get("x", 2) or 2)
            menu_center_y = int(menu_cfg.get("y", 1) or 1)
            menu_height = max(3, len(menu_labels) + 2 + (menu_margin * 2))
            menu_height = min(menu_height, max(3, desc_y - 1))
            menu_x = max(0, min(SCREEN_WIDTH - menu_width, menu_center_x - (menu_width // 2)))
            menu_y = max(0, min(SCREEN_HEIGHT - menu_height, menu_center_y - (menu_height // 2)))

            atlas_margin = int(atlas_cfg.get("margin", 1) or 1)
            atlas_style = str(atlas_cfg.get("frame_style", "round") or "round")
            atlas_id = atlas_cfg.get("glyph_id", "atlas")
            atlas = ctx.glyphs.get(atlas_id, {}) if hasattr(ctx, "glyphs") else {}
            atlas_lines = atlas.get("art", []) if isinstance(atlas, dict) else []
            atlas_inner_width = max((len(strip_ansi(line)) for line in atlas_lines), default=0)
            atlas_width = max(10, atlas_inner_width + 2 + (atlas_margin * 2))
            atlas_height = max(3, len(atlas_lines) + 2 + (atlas_margin * 2))
            atlas_center_x = int(atlas_cfg.get("x", menu_x + menu_width + 2) or (menu_x + menu_width + 2))
            atlas_center_y = int(atlas_cfg.get("y", menu_y) or menu_y)
            atlas_width = min(atlas_width, SCREEN_WIDTH - 2)
            atlas_height = min(atlas_height, SCREEN_HEIGHT - 2)
            atlas_x = max(0, min(SCREEN_WIDTH - atlas_width, atlas_center_x - (atlas_width // 2)))
            atlas_y = max(0, min(SCREEN_HEIGHT - atlas_height, atlas_center_y - (atlas_height // 2)))

            digit_colors = {}
            flicker_digit = None
            flicker_on = True
            if selected_element and hasattr(ctx, "elements"):
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
                unlocked_set = set(str(e) for e in unlocked)
                for digit, (element_key, palette) in elem_colors.items():
                    if palette and element_key in unlocked_set:
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
            colored_atlas = [
                _colorize_atlas_line(
                    line,
                    digit_colors,
                    flicker_digit,
                    flicker_on,
                    f"{ANSI.FG_WHITE}{ANSI.DIM}",
                )
                for line in atlas_lines
            ]

            desc_text = ""
            if hasattr(ctx, "continents") and selected_element:
                entry = ctx.continents.continents().get(selected_element, {})
                if isinstance(entry, dict):
                    desc_text = str(entry.get("description", "") or "")
            desc_lines = textwrap.wrap(desc_text, width=desc_inner_width) if desc_text else [""]
            if len(desc_lines) > desc_inner_height:
                desc_lines = desc_lines[:desc_inner_height]

            menu_box = _box_lines(menu_width, menu_height, menu_labels, margin=menu_margin, style=menu_style)
            atlas_box = _box_lines(atlas_width, atlas_height, colored_atlas, margin=atlas_margin, style=atlas_style)
            desc_box = _box_lines(desc_width, desc_height, desc_lines, margin=desc_margin, style=desc_style)

            canvas = [" " * SCREEN_WIDTH for _ in range(SCREEN_HEIGHT)]

            def _overlay_box(box_lines: list[str], start_x: int, start_y: int) -> None:
                for idx, line in enumerate(box_lines):
                    row = start_y + idx
                    if 0 <= row < SCREEN_HEIGHT:
                        overlay = pad_or_trim_ansi((" " * start_x) + line, SCREEN_WIDTH)
                        base_cells = _ansi_cells(canvas[row])
                        overlay_cells = _ansi_cells(overlay)
                        merged = []
                        for (base_ch, base_code), (over_ch, over_code) in zip(base_cells, overlay_cells):
                            if over_ch == " ":
                                merged.append(ANSI.RESET + base_code + base_ch)
                            else:
                                merged.append(ANSI.RESET + over_code + over_ch)
                        canvas[row] = "".join(merged) + ANSI.RESET

            _overlay_box(menu_box, menu_x, menu_y)
            _overlay_box(atlas_box, atlas_x, atlas_y)
            _overlay_box(desc_box, desc_x, desc_y)

            body = []
            actions = []
            display_location = "Portal"
            raw_lines = canvas
        else:
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
            if portal_mode:
                portal_desc = None
    elif options_mode:
        options_menu = ctx.menus.get("options", {})
        options_actions = []
        available_spells = ctx.spells.available(player, ctx.items) if hasattr(ctx, "spells") else []
        for entry in options_menu.get("actions", []):
            cmd_entry = dict(entry)
            if cmd_entry.get("command") == "TOGGLE_AUDIO":
                audio_mode = str(getattr(player, "flags", {}).get("audio_mode", "on"))
                label_map = {
                    "on": "Audio: On",
                    "off": "Audio: Off",
                    "music": "Audio: Music Only",
                    "sfx": "Audio: SFX Only",
                }
                cmd_entry["label"] = label_map.get(audio_mode, "Audio: On")
            if not command_is_enabled(cmd_entry, player, opponents):
                cmd_entry["_disabled"] = True
            if cmd_entry.get("command") == "SPELLBOOK" and not available_spells:
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
                line = _menu_line(label, idx == menu_cursor)
                if entry.get("_disabled"):
                    body.append(f"{ANSI.DIM}{line}{ANSI.RESET}")
                else:
                    body.append(line)
        else:
            body.append("No options available.")
        if not isinstance(menu_cursor, int):
            try:
                menu_cursor = int(menu_cursor)
            except (TypeError, ValueError):
                menu_cursor = -1
        actions = format_menu_actions(options_menu, selected_index=menu_cursor if menu_cursor >= 0 else None)
        art_lines = []
        art_color = ANSI.FG_WHITE
    elif followers_mode:
        followers_data = ctx.followers_screen.all() if hasattr(ctx, "followers_screen") else {}
        layout = followers_data.get("layout", {}) if isinstance(followers_data, dict) else {}
        menu_cfg = layout.get("menu", {}) if isinstance(layout, dict) else {}
        art_cfg = layout.get("art", {}) if isinstance(layout, dict) else {}
        desc_cfg = layout.get("description", {}) if isinstance(layout, dict) else {}

        def _box_lines(width: int, height: int, content: list[str], *, margin: int, style: str) -> list[str]:
            width = max(2, width)
            height = max(2, height)
            box = _draw_box(width, height, style=style)
            inner_width = width - 2
            inner_height = height - 2
            pad_margin = max(0, min(margin, max(0, inner_width // 2)))
            content_lines = [" " * inner_width for _ in range(inner_height)]
            inner_content_width = max(0, inner_width - (pad_margin * 2))
            row = pad_margin
            for line in content:
                if row >= inner_height - pad_margin:
                    break
                content_lines[row] = (" " * pad_margin) + pad_or_trim_ansi(line, inner_content_width) + (" " * pad_margin)
                row += 1
            for i in range(inner_height):
                box[i + 1] = "|" + content_lines[i] + "|"
            return box

        followers_menu = ctx.menus.get("followers", {})
        followers = list(getattr(player, "followers", []) or [])
        count = len(followers)
        menu_cursor = max(0, min(menu_cursor, max(0, count - 1))) if count else 0
        selected_follower = followers[menu_cursor] if followers and 0 <= menu_cursor < len(followers) else {}

        menu_labels = []
        base_labels = []
        menu_header = f"Followers: {count}/{player.follower_limit()}"
        menu_labels.append(center_ansi(menu_header, max(1, len(menu_header))))
        menu_labels.append("")

        if followers_focus == "actions":
            actions_list = []
            selected_type = selected_follower.get("type") if isinstance(selected_follower, dict) else None
            type_count = 0
            if selected_type:
                type_count = sum(
                    1
                    for follower in followers
                    if isinstance(follower, dict) and follower.get("type") == selected_type
                )
            gear_items = player.list_gear_items() if hasattr(player, "list_gear_items") else []
            for entry in followers_menu.get("actions", []):
                cmd_entry = dict(entry)
                if cmd_entry.get("command") == "FOLLOWER_DISMISS" and not followers:
                    cmd_entry["_disabled"] = True
                if cmd_entry.get("command") == "FOLLOWER_FUSE" and type_count < 3:
                    cmd_entry["_disabled"] = True
                if cmd_entry.get("command") == "FOLLOWER_EQUIP" and not gear_items:
                    cmd_entry["_disabled"] = True
                if cmd_entry.get("command") == "FOLLOWER_UNEQUIP":
                    equip = selected_follower.get("equipment", {}) if isinstance(selected_follower, dict) else {}
                    if not isinstance(equip, dict) or not equip:
                        cmd_entry["_disabled"] = True
                actions_list.append(cmd_entry)
            actions_list.append({"label": "Back", "command": "FOLLOWER_BACK"})
            followers_action_cursor = max(0, min(followers_action_cursor, len(actions_list) - 1)) if actions_list else 0
            for idx, entry in enumerate(actions_list):
                label = str(entry.get("label", "")).strip() or entry.get("command", "")
                base_labels.append(label)
                line = _menu_line(label, idx == followers_action_cursor)
                if entry.get("_disabled"):
                    line = f"{ANSI.DIM}{line}{ANSI.RESET}"
                menu_labels.append(line)
        else:
            if followers:
                for idx, follower in enumerate(followers):
                    name = follower.get("name", "Follower") if isinstance(follower, dict) else "Follower"
                    label = f"{name}"
                    base_labels.append(label)
                    menu_labels.append(_menu_line(label, idx == menu_cursor))
            else:
                base_labels.append("No followers.")
                menu_labels.append("No followers.")

        menu_margin = int(menu_cfg.get("margin", 1) or 1)
        menu_style = str(menu_cfg.get("frame_style", "round") or "round")
        max_label = max((len(label) for label in base_labels), default=len(menu_header))
        max_label = max(max_label, len(menu_header))
        menu_width = max(10, max_label + 4 + (menu_margin * 2))

        desc_margin = int(desc_cfg.get("margin", 1) or 1)
        desc_style = str(desc_cfg.get("frame_style", "round") or "round")
        desc_x = int(desc_cfg.get("x", 2) or 2)
        desc_width = max(10, int(desc_cfg.get("width", 20) or 20))
        desc_inner_width = max(1, desc_width - 2 - (desc_margin * 2))

        desc_lines = []
        if isinstance(selected_follower, dict) and selected_follower:
            name = selected_follower.get("name", "Follower")
            f_type = selected_follower.get("type", "follower")
            type_label = f_type.replace("_", " ").title()
            level = int(selected_follower.get("level", 1) or 1)
            xp = int(selected_follower.get("xp", 0) or 0)
            max_level = int(selected_follower.get("max_level", 5) or 5)
            max_hp = player.follower_total_max_hp(selected_follower)
            hp = int(selected_follower.get("hp", max_hp) or max_hp)
            max_mp = int(selected_follower.get("max_mp", 0) or 0)
            mp = int(selected_follower.get("mp", max_mp) or max_mp)
            atk_total = int(player.follower_total_atk(selected_follower))
            def_total = int(player.follower_total_defense(selected_follower))
            desc_lines.append(f"Name: {name}")
            desc_lines.append(f"Type: {type_label}")
            desc_lines.append(f"Level {level}/{max_level}  XP {xp}")
            desc_lines.append(f"HP {hp}/{max_hp}  MP {mp}/{max_mp}  ATK {atk_total}  DEF {def_total}")

            abilities = selected_follower.get("abilities", [])
            if isinstance(abilities, list) and abilities:
                ability_labels = []
                for ability_id in abilities:
                    label = str(ability_id)
                    if hasattr(ctx, "abilities"):
                        ability = ctx.abilities.get(ability_id, {})
                        if isinstance(ability, dict):
                            label = ability.get("label", label)
                    ability_labels.append(label)
                desc_lines.append(f"Abilities: {', '.join(ability_labels)}")
            else:
                desc_lines.append("Abilities: None")

            equip = selected_follower.get("equipment", {}) if isinstance(selected_follower, dict) else {}
            equip_parts = []
            if isinstance(equip, dict):
                for slot in ("sword", "shield", "armor", "ring", "bracelet", "wand"):
                    gear_id = equip.get(slot)
                    if not gear_id:
                        continue
                    gear = player.gear_instance(gear_id) if hasattr(player, "gear_instance") else None
                    name_part = gear.get("name", slot.title()) if isinstance(gear, dict) else slot.title()
                    equip_parts.append(f"{slot[:2].title()}: {name_part}")
            equip_line = "Equipment: " + (", ".join(equip_parts) if equip_parts else "None")
            desc_lines.append(equip_line)

            if hasattr(ctx, "opponents"):
                opp_entry = ctx.opponents.get(str(f_type), {})
                if isinstance(opp_entry, dict):
                    desc = str(opp_entry.get("desc", "") or "")
                    if desc:
                        desc_lines.append(desc)
        else:
            desc_lines.append("No followers.")

        desc_lines = [line for part in desc_lines for line in (textwrap.wrap(part, width=desc_inner_width) if part else [""])]
        desc_height = max(3, len(desc_lines) + 2 + (desc_margin * 2))
        desc_center_x = int(desc_cfg.get("x", 2) or 2)
        anchor = str(desc_cfg.get("anchor", "") or "").lower()
        if anchor == "bottom":
            desc_center_y = SCREEN_HEIGHT - (desc_height // 2) - 1
        else:
            desc_center_y = int(desc_cfg.get("y", SCREEN_HEIGHT - desc_height - 1) or (SCREEN_HEIGHT - desc_height - 1))
        desc_height = min(desc_height, SCREEN_HEIGHT - 2)
        desc_width = min(desc_width, SCREEN_WIDTH - 2)
        desc_x = max(0, min(SCREEN_WIDTH - desc_width, desc_center_x - (desc_width // 2)))
        desc_y = max(0, min(SCREEN_HEIGHT - desc_height, desc_center_y - (desc_height // 2)))
        desc_inner_height = max(1, desc_height - 2 - (desc_margin * 2))
        if len(desc_lines) > desc_inner_height:
            desc_lines = desc_lines[:desc_inner_height]

        menu_center_x = int(menu_cfg.get("x", 2) or 2)
        menu_center_y = int(menu_cfg.get("y", 1) or 1)
        menu_height = max(3, len(menu_labels) + 2 + (menu_margin * 2))
        menu_height = min(menu_height, max(3, desc_y - 1))
        menu_x = max(0, min(SCREEN_WIDTH - menu_width, menu_center_x - (menu_width // 2)))
        menu_y = max(0, min(SCREEN_HEIGHT - menu_height, menu_center_y - (menu_height // 2)))

        art_margin = int(art_cfg.get("margin", 1) or 1)
        art_style = str(art_cfg.get("frame_style", "round") or "round")
        art_lines = []
        if isinstance(selected_follower, dict):
            art_id = str(selected_follower.get("type", "") or "").strip()
            if art_id and hasattr(ctx, "opponents"):
                opp_entry = ctx.opponents.get(art_id, {})
                if isinstance(opp_entry, dict):
                    art_lines = opp_entry.get("art", []) if isinstance(opp_entry.get("art"), list) else []
        art_inner_width = max((len(strip_ansi(line)) for line in art_lines), default=0)
        art_width = max(10, art_inner_width + 2 + (art_margin * 2))
        art_height = max(3, len(art_lines) + 2 + (art_margin * 2))
        art_center_x = int(art_cfg.get("x", menu_x + menu_width + 2) or (menu_x + menu_width + 2))
        art_center_y = int(art_cfg.get("y", menu_y) or menu_y)
        art_width = min(art_width, SCREEN_WIDTH - 2)
        art_height = min(art_height, SCREEN_HEIGHT - 2)
        art_x = max(0, min(SCREEN_WIDTH - art_width, art_center_x - (art_width // 2)))
        art_y = max(0, min(SCREEN_HEIGHT - art_height, art_center_y - (art_height // 2)))

        menu_box = _box_lines(menu_width, menu_height, menu_labels, margin=menu_margin, style=menu_style)
        art_box = _box_lines(art_width, art_height, art_lines, margin=art_margin, style=art_style)
        desc_box = _box_lines(desc_width, desc_height, desc_lines, margin=desc_margin, style=desc_style)

        canvas = [" " * SCREEN_WIDTH for _ in range(SCREEN_HEIGHT)]

        def _overlay_box(box_lines: list[str], start_x: int, start_y: int) -> None:
            for idx, line in enumerate(box_lines):
                row = start_y + idx
                if 0 <= row < SCREEN_HEIGHT:
                    overlay = pad_or_trim_ansi((" " * start_x) + line, SCREEN_WIDTH)
                    base_cells = _ansi_cells(canvas[row])
                    overlay_cells = _ansi_cells(overlay)
                    merged = []
                    for (base_ch, base_code), (over_ch, over_code) in zip(base_cells, overlay_cells):
                        if over_ch == " ":
                            merged.append(ANSI.RESET + base_code + base_ch)
                        else:
                            merged.append(ANSI.RESET + over_code + over_ch)
                    canvas[row] = "".join(merged) + ANSI.RESET

        _overlay_box(menu_box, menu_x, menu_y)
        _overlay_box(art_box, art_x, art_y)
        _overlay_box(desc_box, desc_x, desc_y)

        body = []
        actions = []
        display_location = "Followers"
        raw_lines = canvas
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
        spell_data = ctx.spellbook_screen.all() if hasattr(ctx, "spellbook_screen") else {}
        layout = spell_data.get("layout", {}) if isinstance(spell_data, dict) else {}
        menu_cfg = layout.get("menu", {}) if isinstance(layout, dict) else {}
        art_cfg = layout.get("art", {}) if isinstance(layout, dict) else {}
        desc_cfg = layout.get("description", {}) if isinstance(layout, dict) else {}

        def _box_lines(width: int, height: int, content: list[str], *, margin: int, style: str) -> list[str]:
            width = max(2, width)
            height = max(2, height)
            box = _draw_box(width, height, style=style)
            inner_width = width - 2
            inner_height = height - 2
            pad_margin = max(0, min(margin, max(0, inner_width // 2)))
            content_lines = [" " * inner_width for _ in range(inner_height)]
            inner_content_width = max(0, inner_width - (pad_margin * 2))
            row = pad_margin
            for line in content:
                if row >= inner_height - pad_margin:
                    break
                content_lines[row] = (" " * pad_margin) + pad_or_trim_ansi(line, inner_content_width) + (" " * pad_margin)
                row += 1
            for i in range(inner_height):
                box[i + 1] = "|" + content_lines[i] + "|"
            return box

        spell_menu = ctx.menus.get("spellbook", {})
        available_spells = ctx.spells.available(player, ctx.items)
        display_location = spell_menu.get("title", "Spellbook")
        selected_spell = None
        selected_spell_id = None
        if spell_target_mode and spell_target_command:
            spell_entry = ctx.spells.by_command_id(spell_target_command)
            if spell_entry:
                selected_spell_id, selected_spell = spell_entry
            spell_name = selected_spell.get("name", spell_target_command) if isinstance(selected_spell, dict) else spell_target_command
            targets = [player.name]
            followers = getattr(player, "followers", []) or []
            if isinstance(followers, list):
                for follower in followers:
                    if isinstance(follower, dict):
                        targets.append(follower.get("name", "Follower"))
            target_lines = [
                _menu_line(name, idx == spell_target_cursor)
                for idx, name in enumerate(targets)
            ]
            menu_labels = [f"Select target for {spell_name}", "", *target_lines]
            base_labels = [f"Select target for {spell_name}"] + [name for name in targets]
        elif not available_spells:
            menu_labels = ["No spells learned."]
            base_labels = ["No spells learned."]
        else:
            menu_labels = []
            base_labels = []
            for idx, (spell_id, spell) in enumerate(available_spells):
                name = spell.get("name", "Spell")
                base_cost = int(spell.get("mp_cost", 0))
                max_rank = ctx.spells.rank_for(spell, player, spell_id)
                element = spell.get("element")
                has_charge = False
                if element:
                    charges = player.wand_charges()
                    has_charge = int(charges.get(str(element), 0)) > 0
                max_affordable = max_rank
                if not has_charge and base_cost > 0:
                    max_affordable = min(max_rank, player.mp // base_cost)
                is_disabled = (max_affordable < 1)
                selected_rank = max_rank
                if idx == menu_cursor:
                    selected_rank = max(1, min(spell_cast_rank, max_rank))
                    if not has_charge and max_affordable >= 1:
                        selected_rank = min(selected_rank, max_affordable)
                    selected_spell = spell
                    selected_spell_id = spell_id
                mp_cost = base_cost * max(1, selected_rank)
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
                rank_bar = f"{{{(enabled + disabled).ljust(3)}}}"
                label = f"{name} ({mp_cost} MP) {rank_bar}"
                base_labels.append(strip_ansi(label))
                line = _menu_line(label, idx == menu_cursor)
                if is_disabled:
                    line = f"{ANSI.DIM}{line}{ANSI.RESET}"
                menu_labels.append(line)

        max_label = max((len(label) for label in base_labels), default=0)
        if max_label:
            max_label += 4
        menu_margin = int(menu_cfg.get("margin", 1) or 1)
        menu_style = str(menu_cfg.get("frame_style", "round") or "round")
        menu_width = max(10, max_label + 2 + (menu_margin * 2))
        menu_center_x = int(menu_cfg.get("x", 2) or 2)
        menu_center_y = int(menu_cfg.get("y", 1) or 1)
        menu_height = max(3, len(menu_labels) + 2 + (menu_margin * 2))
        menu_height = min(menu_height, SCREEN_HEIGHT - 2)
        menu_x = max(0, min(SCREEN_WIDTH - menu_width, menu_center_x - (menu_width // 2)))
        menu_y = max(0, min(SCREEN_HEIGHT - menu_height, menu_center_y - (menu_height // 2)))

        art_margin = int(art_cfg.get("margin", 1) or 1)
        art_style = str(art_cfg.get("frame_style", "round") or "round")
        art_center_x = int(art_cfg.get("x", menu_x + menu_width + 2) or (menu_x + menu_width + 2))
        art_center_y = int(art_cfg.get("y", menu_y) or menu_y)
        spell_art = []
        desc_text = ""
        if selected_spell is None and available_spells:
            selection = max(0, min(menu_cursor, len(available_spells) - 1))
            selected_spell_id, selected_spell = available_spells[selection]
        if isinstance(selected_spell, dict):
            effect = _spell_effect_with_art(ctx, selected_spell) if isinstance(selected_spell, dict) else None
            rank = ctx.spells.rank_for(selected_spell, player, selected_spell_id)
            color_key = ""
            if isinstance(effect, dict):
                if rank >= 3:
                    color_key = str(selected_spell.get("overlay_color_key_rank3", ""))[:1]
                elif rank >= 2:
                    color_key = str(selected_spell.get("overlay_color_key_rank2", ""))[:1]
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
            spell_art = _spell_preview_lines(
                frame_art,
                effect,
                color_code,
                effect_index,
                color_codes=_color_codes_by_key(ctx.colors.all()),
                color_map=effect.get("color_map") if isinstance(effect, dict) else None,
                glyph=effect.get("glyph") if isinstance(effect, dict) else None,
            )
            desc_text = str(selected_spell.get("desc", "") or "")

        art_inner_width = max((len(strip_ansi(line)) for line in spell_art), default=0)
        art_width = max(10, art_inner_width + 2 + (art_margin * 2))
        art_height = max(3, len(spell_art) + 2 + (art_margin * 2))
        art_width = min(art_width, SCREEN_WIDTH - 2)
        art_height = min(art_height, SCREEN_HEIGHT - 2)
        art_x = max(0, min(SCREEN_WIDTH - art_width, art_center_x - (art_width // 2)))
        art_y = max(0, min(SCREEN_HEIGHT - art_height, art_center_y - (art_height // 2)))

        desc_margin = int(desc_cfg.get("margin", 1) or 1)
        desc_style = str(desc_cfg.get("frame_style", "round") or "round")
        desc_width = max(10, int(desc_cfg.get("width", 96) or 96))
        desc_width = min(desc_width, SCREEN_WIDTH - 2)
        desc_center_x = int(desc_cfg.get("x", 2) or 2)
        anchor = str(desc_cfg.get("anchor", "") or "").lower()
        desc_inner_width = max(1, desc_width - 2 - (desc_margin * 2))
        if spell_target_mode:
            targets = [player]
            followers = getattr(player, "followers", []) or []
            if isinstance(followers, list):
                for follower in followers:
                    if isinstance(follower, dict):
                        targets.append(follower)
            target = targets[spell_target_cursor] if 0 <= spell_target_cursor < len(targets) else player
            if target is player:
                base_max_hp = int(player.max_hp)
                temp_hp = int(getattr(player, "temp_hp_bonus", 0) or 0)
                hp = int(player.hp)
                mp = int(player.mp)
                max_mp = int(player.max_mp)
                atk_total = int(player.total_atk())
                def_total = int(player.total_defense())
                atk_bonus = int(player.gear_atk) + int(getattr(player, "temp_atk_bonus", 0) or 0)
                def_bonus = int(player.gear_defense) + int(getattr(player, "temp_def_bonus", 0) or 0)
                hp_text = f"HP: {hp} / {base_max_hp}"
                if temp_hp:
                    hp_text = f"{hp_text} (+{temp_hp})"
                mp_text = f"MP: {mp} / {max_mp}"
                atk_text = f"ATK: {atk_total}"
                if atk_bonus:
                    atk_text = f"{atk_text} (+{atk_bonus})"
                def_text = f"DEF: {def_total}"
                if def_bonus:
                    def_text = f"{def_text} (+{def_bonus})"
            else:
                base_max_hp = int(target.get("max_hp", 0) or 0)
                temp_hp = int(target.get("temp_hp_bonus", 0) or 0)
                max_hp = int(player.follower_total_max_hp(target))
                hp = int(target.get("hp", max_hp) or max_hp)
                max_mp = int(target.get("max_mp", 0) or 0)
                mp = int(target.get("mp", max_mp) or max_mp)
                atk_total = int(player.follower_total_atk(target))
                def_total = int(player.follower_total_defense(target))
                atk_bonus = atk_total - int(target.get("atk", 0) or 0)
                def_bonus = def_total - int(target.get("defense", 0) or 0)
                hp_text = f"HP: {hp} / {base_max_hp}"
                if temp_hp:
                    hp_text = f"{hp_text} (+{temp_hp})"
                mp_text = f"MP: {mp} / {max_mp}"
                atk_text = f"ATK: {atk_total}"
                if atk_bonus:
                    atk_text = f"{atk_text} (+{atk_bonus})"
                def_text = f"DEF: {def_total}"
                if def_bonus:
                    def_text = f"{def_text} (+{def_bonus})"
            stat_line = (
                f"{color(hp_text, ANSI.FG_GREEN)}  "
                f"{color(mp_text, ANSI.FG_MAGENTA)}  "
                f"{color(atk_text, ANSI.DIM)}  "
                f"{color(def_text, ANSI.DIM)}"
            )
            desc_lines = [center_ansi(stat_line, desc_inner_width)]
        else:
            desc_lines = textwrap.wrap(desc_text, width=desc_inner_width) if desc_text else [""]
        desc_height = max(3, len(desc_lines) + 2 + (desc_margin * 2))
        if anchor == "bottom":
            desc_center_y = SCREEN_HEIGHT - (desc_height // 2) - 1
        else:
            desc_center_y = int(desc_cfg.get("y", SCREEN_HEIGHT - desc_height - 1) or (SCREEN_HEIGHT - desc_height - 1))
        desc_height = min(desc_height, SCREEN_HEIGHT - 2)
        desc_x = max(0, min(SCREEN_WIDTH - desc_width, desc_center_x - (desc_width // 2)))
        desc_y = max(0, min(SCREEN_HEIGHT - desc_height, desc_center_y - (desc_height // 2)))

        menu_box = _box_lines(menu_width, menu_height, menu_labels, margin=menu_margin, style=menu_style)
        art_box = _box_lines(art_width, art_height, spell_art, margin=art_margin, style=art_style)
        desc_box = _box_lines(desc_width, desc_height, desc_lines, margin=desc_margin, style=desc_style)

        canvas = [" " * SCREEN_WIDTH for _ in range(SCREEN_HEIGHT)]

        def _overlay_box(box_lines: list[str], start_x: int, start_y: int) -> None:
            for idx, line in enumerate(box_lines):
                row = start_y + idx
                if 0 <= row < SCREEN_HEIGHT:
                    overlay = pad_or_trim_ansi((" " * start_x) + line, SCREEN_WIDTH)
                    base_cells = _ansi_cells(canvas[row])
                    overlay_cells = _ansi_cells(overlay)
                    merged = []
                    for (base_ch, base_code), (over_ch, over_code) in zip(base_cells, overlay_cells):
                        if over_ch == " ":
                            merged.append(ANSI.RESET + base_code + base_ch)
                        else:
                            merged.append(ANSI.RESET + over_code + over_ch)
                    canvas[row] = "".join(merged) + ANSI.RESET

        _overlay_box(menu_box, menu_x, menu_y)
        _overlay_box(art_box, art_x, art_y)
        _overlay_box(desc_box, desc_x, desc_y)

        body = []
        actions = []
        raw_lines = canvas
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
                body.append(_menu_line(f"{label}{suffix}", idx == menu_cursor))
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
        title_followers = []
        title_avatar_id = ""
        menu_id = _title_menu_id(title_data, player, title_menu_stack or [])
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
                                    avatar_id = slot_player.get("avatar_id")
                                    if avatar_id:
                                        title_avatar_id = str(avatar_id)
                                    elements = slot_player.get("elements")
                                    if isinstance(elements, list) and elements:
                                        unlocked_elements = elements
                                    followers = slot_player.get("followers")
                                    if isinstance(followers, list):
                                        title_followers = followers
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
                            avatar_id = slot_player.get("avatar_id")
                            if avatar_id:
                                title_avatar_id = str(avatar_id)
                            elements = slot_player.get("elements")
                            if isinstance(elements, list) and elements:
                                unlocked_elements = elements
                            followers = slot_player.get("followers")
                            if isinstance(followers, list):
                                title_followers = followers
        title_color_map = element_color_map(ctx.colors.all(), title_element or "base")
        if menu_id == "title_assets_list":
            asset_type = getattr(player, "asset_explorer_type", "") or ""
            def _box(width: int, height: int, content: list[str]) -> list[str]:
                width = max(2, width)
                height = max(2, height)
                box = _draw_box(width, height, style="round")
                inner_w = width - 2
                inner_h = height - 2
                lines = [" " * inner_w for _ in range(inner_h)]
                for i, line in enumerate(content[:inner_h]):
                    lines[i] = pad_or_trim_ansi(line, inner_w)
                for i in range(inner_h):
                    box[i + 1] = box[i + 1][0] + lines[i] + box[i + 1][-1]
                return box

            left_w = 33
            right_w = SCREEN_WIDTH - left_w - 1
            left_h = SCREEN_HEIGHT
            top_h = 16
            bottom_h = max(4, left_h - top_h)

            _narrative, commands, _detail = _title_state_config(ctx, player, action_cursor, title_menu_stack or [])
            list_window = max(0, left_h - 4)
            total = len(commands)
            if action_cursor < 0:
                cursor = 0
            else:
                cursor = min(action_cursor, max(0, total - 1))
            start = 0
            if total > list_window:
                if cursor >= start + list_window:
                    start = cursor - list_window + 1
                if cursor < start:
                    start = cursor
                start = max(0, min(start, total - list_window))
            visible = commands[start:start + list_window] if total else []

            if not asset_type:
                list_title = f"{ANSI.FG_CYAN}[ Asset Types ]{ANSI.RESET}"
                list_lines = [list_title] + [""]
                for idx, entry in enumerate(visible, start=start):
                    label = str(entry.get("label", "")).strip()
                    if idx == cursor:
                        label = f"{ANSI.FG_YELLOW}> {label}{ANSI.RESET}"
                    else:
                        label = f"{ANSI.DIM}{label}{ANSI.RESET}"
                    list_lines.append(label)
                left_box = _box(left_w, left_h, list_lines)

                right_lines = [
                    f"{ANSI.FG_CYAN}Preview:{ANSI.RESET}",
                    "",
                    f"{ANSI.DIM}Select an asset type to browse.{ANSI.RESET}",
                ]
                right_box = _box(right_w, top_h, right_lines)
                info_lines = [f"{ANSI.DIM}Up/Down select, A/Enter to choose, S to go back.{ANSI.RESET}"]
                bottom_box = _box(right_w, bottom_h, info_lines)
            else:
                asset_label = {
                    "objects": "Objects",
                    "opponents": "Opponents",
                    "items": "Items",
                    "spells": "Spells",
                    "spells_art": "Spells Art",
                    "glyphs": "Glyphs",
                    "music": "Music",
                    "sfx": "SFX",
                }.get(asset_type, "Assets")
                assets = {}
                if asset_type == "objects":
                    assets = ctx.objects.all()
                elif asset_type == "opponents":
                    opp_data = ctx.opponents.all()
                    if isinstance(opp_data, dict):
                        assets = opp_data
                elif asset_type == "items":
                    assets = ctx.items.all()
                elif asset_type == "spells":
                    assets = ctx.spells.all()
                elif asset_type == "spells_art":
                    assets = ctx.spells_art.all()
                elif asset_type == "glyphs":
                    assets = ctx.glyphs.all()
                elif asset_type in ("music", "sfx"):
                    assets = _asset_explorer_music_assets(ctx, asset_type)
                if not isinstance(assets, dict):
                    assets = {}
                asset_ids = sorted(str(key) for key in assets.keys())

                selected_asset = None
                if commands and 0 <= action_cursor < len(commands):
                    cmd = commands[action_cursor].get("command", "")
                    if isinstance(cmd, str) and cmd.startswith("TITLE_ASSET_SELECT:"):
                        selected_asset = cmd.split(":", 1)[1]
                if selected_asset is None and asset_ids:
                    selected_asset = asset_ids[0]
                asset = assets.get(selected_asset, {}) if selected_asset is not None else {}
                if not isinstance(asset, dict) or not asset:
                    if asset_type == "objects":
                        asset = ctx.objects.get(selected_asset, {}) if selected_asset else {}
                    elif asset_type == "opponents":
                        asset = ctx.opponents.get(selected_asset, {}) if selected_asset else {}
                    elif asset_type == "items":
                        asset = ctx.items.get(selected_asset, {}) if selected_asset else {}
                    elif asset_type == "spells":
                        asset = ctx.spells.get(selected_asset, {}) if selected_asset else {}
                    elif asset_type == "spells_art":
                        asset = ctx.spells_art.get(selected_asset, {}) if selected_asset else {}
                    elif asset_type == "glyphs":
                        asset = ctx.glyphs.get(selected_asset, {}) if selected_asset else {}

                list_title = f"{ANSI.FG_CYAN}[ {asset_label} ]{ANSI.RESET}"
                list_lines = [list_title] + [""]
                for idx, entry in enumerate(visible, start=start):
                    label = str(entry.get("label", "")).strip()
                    if idx == cursor:
                        label = f"{ANSI.FG_YELLOW}> {label}{ANSI.RESET}"
                    else:
                        label = f"{ANSI.DIM}{label}{ANSI.RESET}"
                    list_lines.append(label)
                left_box = _box(left_w, left_h, list_lines)

                right_lines = [f"{ANSI.FG_CYAN}Preview:{ANSI.RESET} {selected_asset or ''}"]
                if isinstance(asset, dict):
                    name = asset.get("name")
                    if name:
                        right_lines.append(f"{ANSI.FG_YELLOW}{name}{ANSI.RESET}")
                    desc = asset.get("description") or asset.get("desc")
                    if desc:
                        right_lines.append(f"{ANSI.DIM}{desc}{ANSI.RESET}")
                    if asset_type in ("music", "sfx"):
                        tempo = asset.get("tempo")
                        scale = asset.get("scale")
                        wave = asset.get("wave")
                        pattern = asset.get("pattern")
                        summary = []
                        if tempo is not None:
                            summary.append(f"tempo:{tempo}")
                        if scale:
                            summary.append(f"scale:{scale}")
                        if wave:
                            summary.append(f"wave:{wave}")
                        selected_wave = getattr(player, "asset_explorer_waveform", None)
                        if selected_wave:
                            summary.append(f"preview:{selected_wave}")
                        if pattern:
                            summary.append(f"pattern:{pattern}")
                        if summary:
                            right_lines.append(f"{ANSI.DIM}{' '.join(summary)}{ANSI.RESET}")
                    if getattr(player, "asset_explorer_show_art", True):
                        art = asset.get("art")
                        masks = asset.get("color_map") if asset_type == "opponents" else None
                        if isinstance(art, list):
                            right_lines.append("")
                            max_lines = max(0, (top_h - 2) - len(right_lines))
                            lines = [str(line) for line in art[:max_lines]]
                            if asset_type == "opponents" and isinstance(masks, list) and hasattr(ctx, "colors"):
                                colors = ctx.colors.all()
                                if isinstance(colors, dict):
                                    colored = []
                                    for line, mask in zip(lines, masks):
                                        mask_line = str(mask).ljust(len(line))
                                        out = []
                                        for idx, ch in enumerate(line):
                                            m = mask_line[idx] if idx < len(mask_line) else ""
                                            code = _color_code_for_key(colors, m) if m else ""
                                            if code and ch != " ":
                                                out.append(f"{code}{ch}{ANSI.RESET}")
                                            else:
                                                out.append(ch)
                                        colored.append("".join(out))
                                    lines = colored
                            right_lines.extend(lines)
                if asset_type == "music":
                    if isinstance(asset, list):
                        right_lines.append(f"{ANSI.DIM}steps:{len(asset)}{ANSI.RESET}")
                    elif isinstance(asset, dict):
                        steps = asset.get("steps", [])
                        repeat = asset.get("repeat")
                        summary = []
                        if repeat:
                            summary.append(f"repeat:{repeat}")
                        if isinstance(steps, list):
                            summary.append(f"steps:{len(steps)}")
                        if summary:
                            right_lines.append(f"{ANSI.DIM}{' '.join(summary)}{ANSI.RESET}")
                right_box = _box(right_w, top_h, right_lines)

                info_lines = []
                if isinstance(asset, dict) and getattr(player, "asset_explorer_show_stats", True):
                    stats = []
                    for key in ("level", "hp", "atk", "defense", "speed", "mp_cost", "price"):
                        if key in asset:
                            stats.append(f"{key}:{asset.get(key)}")
                    if stats:
                        info_lines.append("Stats: " + " ".join(stats))
                if getattr(player, "asset_explorer_show_json", False):
                    raw = json.dumps(asset, indent=2, ensure_ascii=True)
                    info_lines.extend(raw.splitlines())
                focus = getattr(player, "asset_explorer_focus", "list")
                if focus == "info":
                    info_lines.append(f"{ANSI.DIM}Up/Down scroll, Left to list, S to go back.{ANSI.RESET}")
                else:
                    info_lines.append(f"{ANSI.DIM}Right to info, Up/Down select, S to go back.{ANSI.RESET}")
                scroll = max(0, int(getattr(player, "asset_explorer_info_scroll", 0) or 0))
                inner_h = max(0, bottom_h - 2)
                if inner_h and len(info_lines) > inner_h:
                    scroll = max(0, min(scroll, len(info_lines) - inner_h))
                    info_lines = info_lines[scroll:scroll + inner_h]
                bottom_box = _box(right_w, bottom_h, info_lines)

            content_lines = []
            for i in range(left_h):
                if i < top_h:
                    right_line = right_box[i]
                else:
                    right_line = bottom_box[i - top_h] if (i - top_h) < len(bottom_box) else " " * right_w
                content_lines.append(left_box[i] + " " + right_line)

            raw_lines = []
            raw_lines.extend(content_lines[:SCREEN_HEIGHT])
            return Frame(
                title="Asset Explorer",
                body_lines=[],
                action_lines=[],
                stat_lines=[],
                footer_hint="",
                location="Asset Explorer",
                art_lines=[],
                art_color=ANSI.FG_WHITE,
                status_lines=[],
                raw_lines=raw_lines,
            )
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
            atlas = ctx.glyphs.get("element_atlas", {}) if ctx.glyphs else {}
            if isinstance(atlas, dict):
                atlas_lines = atlas.get("art", []) if isinstance(atlas.get("art"), list) else []

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

        atlas_colored = [
            ANSI.RESET + _colorize_element_atlas_line(
                line,
                digit_colors,
                flicker_digit,
                flicker_on,
                f"{ANSI.FG_WHITE}{ANSI.DIM}",
            )
            for line in atlas_lines
        ]
        if atlas_colored:
            atlas_width = max((len(strip_ansi(line)) for line in atlas_colored), default=0)
            atlas_colored = [pad_or_trim_ansi(line, atlas_width).ljust(atlas_width) for line in atlas_colored]

        follower_art_blocks = []
        if title_avatar_id and hasattr(ctx, "players"):
            avatar = ctx.players.get(str(title_avatar_id), {})
            if isinstance(avatar, dict):
                art = avatar.get("art", [])
                masks = avatar.get("color_map", [])
                if isinstance(art, list) and art:
                    if isinstance(masks, list) and masks and hasattr(ctx, "colors"):
                        colors = ctx.colors.all() if hasattr(ctx, "colors") else {}
                        if isinstance(colors, dict):
                            def _apply_mask_line(line: str, mask: str) -> str:
                                if not line:
                                    return line
                                out = []
                                padded_mask = mask.ljust(len(line))
                                for idx, ch in enumerate(line):
                                    mask_ch = padded_mask[idx] if idx < len(padded_mask) else ""
                                    code = _color_code_for_key(colors, mask_ch) if mask_ch else ""
                                    if code and ch != " ":
                                        out.append(f"{code}{ch}{ANSI.RESET}")
                                    else:
                                        out.append(ch)
                                return "".join(out)
                            colored = []
                            for line, mask in zip(art, masks):
                                colored.append(_apply_mask_line(str(line), str(mask)))
                            follower_art_blocks.append(colored)
                        else:
                            follower_art_blocks.append([str(line) for line in art])
                    else:
                        follower_art_blocks.append([str(line) for line in art])
        if title_followers and hasattr(ctx, "opponents"):
            opponent_ids = set(ctx.opponents.all().keys()) if hasattr(ctx.opponents, "all") else set()
            fallback_map = {
                "mushroom": "mushroom_miranda",
                "mushroom_mage": "mushroom_miranda",
                "fairy": "fairy",
                "wolf": "wolf",
            }
            colors = ctx.colors.all() if hasattr(ctx, "colors") else {}
            def _apply_mask_line(line: str, mask: str) -> str:
                if not line or not isinstance(colors, dict):
                    return line
                out = []
                padded_mask = mask.ljust(len(line))
                for idx, ch in enumerate(line):
                    mask_ch = padded_mask[idx] if idx < len(padded_mask) else ""
                    code = _color_code_for_key(colors, mask_ch) if mask_ch else ""
                    if code and ch != " ":
                        out.append(f"{code}{ch}{ANSI.RESET}")
                    else:
                        out.append(ch)
                return "".join(out)
            for follower in title_followers:
                if not isinstance(follower, dict):
                    continue
                f_type = str(follower.get("type", ""))
                opp_id = f_type if f_type in opponent_ids else fallback_map.get(f_type, "")
                if not opp_id:
                    continue
                opp = ctx.opponents.get(opp_id, {}) if hasattr(ctx.opponents, "get") else {}
                art = opp.get("art", []) if isinstance(opp, dict) else []
                masks = opp.get("color_map", []) if isinstance(opp, dict) else []
                if isinstance(art, list) and art:
                    if isinstance(masks, list) and masks and isinstance(colors, dict):
                        colored = []
                        for line, mask in zip(art, masks):
                            colored.append(_apply_mask_line(str(line), str(mask)))
                        follower_art_blocks.append(colored)
                    else:
                        follower_art_blocks.append(art)

        follower_lines = []
        follower_span_width = 0
        if follower_art_blocks:
            heights = [len(block) for block in follower_art_blocks]
            widths = [max((len(strip_ansi(line).rstrip()) for line in block), default=0) for block in follower_art_blocks]
            if widths:
                follower_span_width = sum(widths) + max(0, len(widths) - 1)
            total_height = max(heights, default=0)
            for row in range(total_height):
                parts = []
                for block, height, width in zip(follower_art_blocks, heights, widths):
                    start = total_height - height
                    idx = row - start
                    if 0 <= idx < height:
                        raw = block[idx].rstrip()
                        line = raw.ljust(width)
                    else:
                        line = " " * width
                    parts.append(pad_or_trim_ansi(line, width))
                follower_lines.append(" ".join(parts).ljust(follower_span_width))

        span_height = max(len(atlas_colored), len(follower_lines))
        if span_height:
            start_y = SCREEN_HEIGHT - span_height
            for row in range(span_height):
                atlas_idx = row - (span_height - len(atlas_colored))
                follower_idx = row - (span_height - len(follower_lines))
                left = atlas_colored[atlas_idx] if 0 <= atlas_idx < len(atlas_colored) else ""
                right = follower_lines[follower_idx] if 0 <= follower_idx < len(follower_lines) else ""
                if left and right:
                    line = f"{left} {right}"
                else:
                    line = left or right
                row_idx = start_y + row
                if 0 <= row_idx < SCREEN_HEIGHT and line:
                    base_cells = _ansi_cells(canvas[row_idx])
                    overlay_cells = _ansi_cells(pad_or_trim_ansi(line, SCREEN_WIDTH))
                    merged = []
                    for (base_ch, base_code), (over_ch, over_code) in zip(base_cells, overlay_cells):
                        if over_ch == " ":
                            merged.append(ANSI.RESET + base_code + base_ch)
                        else:
                            merged.append(ANSI.RESET + over_code + over_ch)
                    canvas[row_idx] = "".join(merged) + ANSI.RESET
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
