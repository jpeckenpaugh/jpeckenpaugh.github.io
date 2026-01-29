"""Screen composition helpers for game UI states."""

import random
import textwrap
import time
from dataclasses import dataclass
from typing import List, Optional

from app.commands.scene_commands import scene_commands
from app.data_access.commands_data import CommandsData
from app.data_access.colors_data import ColorsData
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
    format_player_stats,
    render_scene_art,
    render_venue_art,
    render_venue_objects,
)
from app.ui.text import format_text


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


def generate_frame(
    ctx: ScreenContext,
    player: Player,
    opponents: List[Opponent],
    message: str = "",
    leveling_mode: bool = False,
    shop_mode: bool = False,
    inventory_mode: bool = False,
    inventory_items: Optional[List[tuple[str, str]]] = None,
    hall_mode: bool = False,
    hall_view: str = "menu",
    inn_mode: bool = False,
    spell_mode: bool = False,
    suppress_actions: bool = False
) -> Frame:
    """Build a screen frame from game state and UI data."""
    healing = ctx.spells.get("healing", {})
    spark = ctx.spells.get("spark", {})
    heal_name = healing.get("name", "Healing")
    spark_name = spark.get("name", "Spark")
    display_location = player.location
    art_anchor_x = None
    if leveling_mode:
        body = [
            "Level Up!",
            "",
            f"You reached level {player.level}.",
            "",
            f"Stat points available: {player.stat_points}",
            "",
            "Choose how to spend your points:",
            "  [1] +HP",
            "  [2] +MP",
            "  [3] +ATK",
            "  [4] +DEF",
            "",
            "  [B] Balanced allocation",
            "  [X] Random allocation",
        ]
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
        for entry in venue.get("inventory_items", []):
            item_id = entry.get("item_id")
            if not item_id:
                continue
            item = ctx.items.get(item_id, {})
            label = entry.get("label", item.get("name", item_id))
            price = item.get("price", 0)
            body.append(f"{label}  {price} GP")
        body.append("")
        body += venue.get("narrative", [])
        art_anchor_x = None
        if venue.get("objects"):
            art_lines, art_color, art_anchor_x = render_venue_objects(venue, npc, ctx.objects, ctx.colors.all())
        else:
            art_lines, art_color = render_venue_art(venue, npc, ctx.colors.all())
        actions = format_command_lines(venue.get("commands", []))
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
        actions = format_command_lines(venue.get("commands", []))
        art_anchor_x = None
        if venue.get("objects"):
            art_lines, art_color, art_anchor_x = render_venue_objects(venue, npc, ctx.objects, ctx.colors.all())
        else:
            art_lines, art_color = render_venue_art(venue, npc, ctx.colors.all())
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
        actions = format_command_lines(venue.get("commands", []))
        art_anchor_x = None
        if venue.get("objects"):
            art_lines, art_color, art_anchor_x = render_venue_objects(venue, npc, ctx.objects, ctx.colors.all())
        else:
            art_lines, art_color = render_venue_art(venue, npc, ctx.colors.all())
    elif inventory_mode:
        inventory_menu = ctx.menus.get("inventory", {})
        items = inventory_items or []
        title = inventory_menu.get("title", "Inventory")
        body = [title, ""]
        if items:
            for i, (_, label) in enumerate(items[:9], start=1):
                body.append(f"{i}. {label}")
        else:
            body.append(inventory_menu.get("empty", "Inventory is empty."))
        actions = format_menu_actions(inventory_menu)
        art_lines = []
        art_color = ANSI.FG_WHITE
    elif spell_mode:
        spell_menu = ctx.menus.get("spellbook", {})
        heal_cost = int(healing.get("mp_cost", 2))
        spark_cost = int(spark.get("mp_cost", 2))
        body = [
            spell_menu.get("title", "Spellbook"),
            "",
            f"{heal_name} ({heal_cost} MP)",
            f"{spark_name} ({spark_cost} MP)",
        ]
        actions = format_menu_actions(
            spell_menu,
            replacements={
                "{heal_name}": heal_name,
                "{spark_name}": spark_name,
            },
        )
        art_lines = []
        art_color = ANSI.FG_WHITE
    elif player.location == "Town":
        scene_data = ctx.scenes.get("town", {})
        art_lines, art_color = render_scene_art(
            scene_data,
            opponents,
            objects_data=ctx.objects,
            color_map_override=ctx.colors.all(),
        )
        if not art_lines:
            art_lines = scene_data.get("art", [])
            art_color = COLOR_BY_NAME.get(scene_data.get("color", "yellow").lower(), ANSI.FG_WHITE)
        body = scene_data.get("narrative", [])
        actions = format_command_lines(
            scene_commands(ctx.scenes, ctx.commands, "town", player, opponents)
        )
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
                color_map_override=ctx.colors.all(),
            )
        if getattr(player, "title_confirm", False):
            body = scene_data.get("confirm_narrative", [])
            actions = format_command_lines(scene_data.get("confirm_commands", []))
        else:
            body = scene_data.get("narrative", [])
            actions = format_command_lines(
                scene_commands(ctx.scenes, ctx.commands, "title", player, opponents)
            )
        display_location = "Lokarta - World Maker"
    else:
        scene_data = ctx.scenes.get("forest", {})
        forest_art, art_color = render_scene_art(
            scene_data,
            opponents,
            objects_data=ctx.objects,
            color_map_override=ctx.colors.all(),
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
            scene_commands(ctx.scenes, ctx.commands, "forest", player, opponents)
        )
        art_lines = forest_art
        art_anchor_x = None

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

    return Frame(
        title="Lokarta - World Maker — PROTOTYPE",
        body_lines=body,
        action_lines=(format_action_lines([]) if suppress_actions else actions),
        stat_lines=format_player_stats(player),
        footer_hint=(
            "Keys: 1-4=Assign  B=Balanced  X=Random  Q=Quit"
            if leveling_mode
            else "Keys: use the action panel"
        ),
        location=display_location,
        art_lines=art_lines,
        art_color=art_color,
        status_lines=status_lines,
        art_anchor_x=art_anchor_x,
    )
