"""Command router for stateful, data-driven actions."""

from dataclasses import dataclass
import random
from typing import List, Optional

from app.combat import cast_spell, primary_opponent
from app.data_access.commands_data import CommandsData
from app.data_access.items_data import ItemsData
from app.data_access.opponents_data import OpponentsData
from app.data_access.scenes_data import ScenesData
from app.data_access.venues_data import VenuesData
from app.data_access.menus_data import MenusData
from app.data_access.objects_data import ObjectsData
from app.data_access.save_data import SaveData
from app.models import Player, Opponent
from app.commands.registry import CommandContext, CommandRegistry, dispatch_command
from app.data_access.spells_data import SpellsData
from app.shop import purchase_item
from app.ui.ansi import ANSI
from app.ui.rendering import animate_battle_start
from app.ui.constants import SCREEN_WIDTH


@dataclass
class CommandState:
    player: Player
    opponents: List[Opponent]
    loot_bank: dict
    last_message: str
    shop_mode: bool
    inventory_mode: bool
    inventory_items: List[tuple[str, str]]
    hall_mode: bool
    hall_view: str
    inn_mode: bool
    spell_mode: bool
    action_cmd: Optional[str]
    target_index: Optional[int] = None


@dataclass
class RouterContext:
    items: ItemsData
    opponents_data: OpponentsData
    scenes: ScenesData
    commands: CommandsData
    venues: VenuesData
    save_data: SaveData
    spells: SpellsData
    menus: MenusData
    objects: ObjectsData
    registry: CommandRegistry


def handle_command(command_id: str, state: CommandState, ctx: RouterContext, key: Optional[str] = None) -> bool:
    if command_id is None:
        return False

    if state.player.location == "Title":
        return _handle_title(command_id, state, ctx, key)

    if command_id == "ENTER_VENUE":
        venue_id = _command_target(ctx.scenes, ctx.commands, state, command_id, key)
        if not venue_id:
            return False
        venue = ctx.venues.get(venue_id, {})
        if venue_id == "town_shop":
            state.shop_mode = True
            state.hall_mode = False
            state.inn_mode = False
            state.inventory_mode = False
            state.spell_mode = False
        elif venue_id == "town_hall":
            state.hall_mode = True
            state.hall_view = "menu"
            state.shop_mode = False
            state.inn_mode = False
            state.inventory_mode = False
            state.spell_mode = False
        elif venue_id == "town_inn":
            state.inn_mode = True
            state.shop_mode = False
            state.hall_mode = False
            state.inventory_mode = False
            state.spell_mode = False
        else:
            return False
        state.last_message = venue.get("welcome_message", state.last_message)
        return True

    if command_id == "ENTER_SCENE":
        scene_id = _command_target(ctx.scenes, ctx.commands, state, command_id, key)
        if not scene_id:
            return False
        return _enter_scene(scene_id, state, ctx)

    if command_id == "B_KEY" and state.inventory_mode:
        menu = ctx.menus.get("inventory", {})
        state.inventory_mode = False
        state.last_message = menu.get("close_message", "Closed inventory.")
        return True

    if command_id == "B_KEY" and state.spell_mode:
        menu = ctx.menus.get("spellbook", {})
        state.spell_mode = False
        state.last_message = menu.get("close_message", "Closed spellbook.")
        return True
    if command_id == "SPELLBOOK":
        menu = ctx.menus.get("spellbook", {})
        state.spell_mode = True
        state.shop_mode = False
        state.inventory_mode = False
        state.hall_mode = False
        state.inn_mode = False
        state.last_message = menu.get("open_message", "Open spellbook.")
        return True

    if state.spell_mode and command_id.startswith("NUM"):
        spell_entry = ctx.spells.by_menu_key(command_id)
        if not spell_entry:
            return False
        _, spell = spell_entry
        state.spell_mode = False
        state.action_cmd = spell.get("command_id")
        return True

    if command_id in ("NUM1", "NUM2") and state.hall_mode:
        venue = ctx.venues.get("town_hall", {})
        info_sections = venue.get("info_sections", [])
        selected = next(
            (entry for entry in info_sections if entry.get("command") == command_id),
            None
        )
        if selected:
            state.hall_view = selected.get("key", state.hall_view)
            state.last_message = selected.get("message", state.last_message)
            return True
        return False

    if command_id == "B_KEY" and state.hall_mode:
        venue = ctx.venues.get("town_hall", {})
        state.hall_mode = False
        state.last_message = venue.get("leave_message", "You leave the hall.")
        return True

    if command_id == "B_KEY" and state.inn_mode:
        venue = ctx.venues.get("town_inn", {})
        state.inn_mode = False
        state.last_message = venue.get("leave_message", "You leave the inn.")
        return True

    if command_id == "B_KEY" and state.shop_mode:
        venue = ctx.venues.get("town_shop", {})
        state.shop_mode = False
        state.last_message = venue.get("leave_message", "You leave the shop.")
        return True

    if state.shop_mode:
        venue = ctx.venues.get("town_shop", {})
        selection = next(
            (entry for entry in venue.get("inventory_items", []) if entry.get("command") == command_id),
            None
        )
        if selection:
            item_id = selection.get("item_id")
            if item_id:
                state.last_message = purchase_item(state.player, ctx.items, item_id)
                ctx.save_data.save_player(state.player)
            return True
        return False

    if command_id == "INVENTORY":
        menu = ctx.menus.get("inventory", {})
        state.inventory_items = state.player.list_inventory_items(ctx.items)
        if not state.inventory_items:
            state.last_message = menu.get("empty", "Inventory is empty.")
            return True
        state.inventory_mode = True
        state.shop_mode = False
        state.hall_mode = False
        state.spell_mode = False
        state.last_message = menu.get("open_message", "Choose an item to use.")
        return True

    if state.inventory_mode:
        menu = ctx.menus.get("inventory", {})
        if command_id == "B_KEY":
            state.inventory_mode = False
            state.last_message = menu.get("close_message", "Closed inventory.")
            return True
        if command_id.startswith("NUM"):
            idx = int(command_id.replace("NUM", "")) - 1
            if 0 <= idx < len(state.inventory_items):
                item_id, _ = state.inventory_items[idx]
                state.last_message = state.player.use_item(item_id, ctx.items)
                ctx.save_data.save_player(state.player)
                state.inventory_items = state.player.list_inventory_items(ctx.items)
                if not state.inventory_items:
                    state.inventory_mode = False
            else:
                state.last_message = "Invalid item selection."
            return True

    if command_id == "USE_SERVICE":
        service_key = "rest"
        venue_id = None
        if state.inn_mode:
            venue = ctx.venues.get("town_inn", {})
            for entry in venue.get("commands", []):
                if entry.get("command") != command_id:
                    continue
                cmd_key = str(entry.get("key", "")).lower()
                if key and cmd_key and cmd_key != key.lower():
                    continue
                venue_id = entry.get("target", "town_inn")
                service_key = entry.get("service_id", service_key)
                break
        if not venue_id:
            venue_id = _command_target(ctx.scenes, ctx.commands, state, command_id, key)
        if not venue_id:
            return False
        venue = ctx.venues.get(venue_id, {})
        services = venue.get("services")
        if isinstance(services, dict):
            service = services.get(service_key, {})
        else:
            service = venue.get("service", {})
        service_type = service.get("type")
        if service_type not in ("rest", "meal"):
            return False
        if not (state.player.hp < state.player.max_hp or state.player.mp < state.player.max_mp):
            state.last_message = service.get("full_message", "You're already fully rested.")
            return True
        if state.player.location != "Town":
            state.last_message = service.get("location_message", "The inn is only in town.")
            return True
        cost = int(service.get("cost", 0))
        if state.player.gold < cost:
            state.last_message = service.get("insufficient_message", "Not enough GP to rest at the inn.")
            return True
        state.player.gold -= cost
        if service_type == "meal":
            item_id = service.get("item_id")
            item = ctx.items.get(item_id, {}) if item_id else {}
            hp_gain = int(item.get("hp", service.get("hp", 0)))
            mp_gain = int(item.get("mp", service.get("mp", 0)))
            state.player.hp = min(state.player.max_hp, state.player.hp + hp_gain)
            state.player.mp = min(state.player.max_mp, state.player.mp + mp_gain)
            state.last_message = service.get("message", "You enjoy a hot meal.")
        else:
            if service.get("heal_full", True):
                state.player.hp = state.player.max_hp
                state.player.mp = state.player.max_mp
            state.last_message = service.get("message", "You rest at the inn and feel fully restored.")
        ctx.save_data.save_player(state.player)
        return True

    ctx_data = CommandContext(
        player=state.player,
        opponents=state.opponents,
        loot=state.loot_bank,
        spells_data=ctx.spells,
        items_data=ctx.items,
        target_index=state.target_index,
    )
    if command_id in ("ATTACK", "SPARK", "HEAL"):
        state.action_cmd = command_id
        return True

    message = dispatch_command(ctx.registry, command_id, ctx_data)
    if message != "Unknown action.":
        state.last_message = message
        return True

    return False


def _handle_title(command_id: str, state: CommandState, ctx: RouterContext, key: Optional[str]) -> bool:
    if command_id == "QUIT":
        state.action_cmd = "QUIT"
        return True
    if command_id == "TITLE_CONFIRM_YES":
        ctx.save_data.delete()
        state.player = Player.from_dict({})
        state.player.location = "Town"
        state.player.title_confirm = False
        state.player.has_save = False
        state.opponents = []
        state.loot_bank = {"xp": 0, "gold": 0}
        state.shop_mode = False
        state.inventory_mode = False
        state.hall_mode = False
        state.inn_mode = False
        state.spell_mode = False
        state.last_message = "You arrive in town."
        return True
    if command_id == "TITLE_CONFIRM_NO":
        state.player.title_confirm = False
        return True
    if command_id == "TITLE_NEW":
        if ctx.save_data.exists():
            state.player.title_confirm = True
            return True
        state.player = Player.from_dict({})
        state.player.location = "Town"
        state.player.title_confirm = False
        state.player.has_save = False
        state.opponents = []
        state.loot_bank = {"xp": 0, "gold": 0}
        state.shop_mode = False
        state.inventory_mode = False
        state.hall_mode = False
        state.inn_mode = False
        state.spell_mode = False
        state.last_message = "You arrive in town."
        return True
    if command_id == "TITLE_CONTINUE":
        if not ctx.save_data.exists():
            return True
        loaded = ctx.save_data.load_player()
        state.player = loaded if loaded else Player.from_dict({})
        state.player.location = "Town"
        state.player.title_confirm = False
        state.player.has_save = ctx.save_data.exists()
        state.opponents = []
        state.loot_bank = {"xp": 0, "gold": 0}
        state.shop_mode = False
        state.inventory_mode = False
        state.hall_mode = False
        state.inn_mode = False
        state.spell_mode = False
        state.last_message = "You arrive in town."
        return True
    return False


def handle_boost_confirm(
    state: CommandState,
    ctx: RouterContext,
    spell_id: str,
    boosted: bool
) -> None:
    state.last_message = cast_spell(
        state.player,
        state.opponents,
        spell_id,
        boosted,
        state.loot_bank,
        ctx.spells,
        target_index=state.target_index,
    )
    spell = ctx.spells.get(spell_id, {})
    state.action_cmd = spell.get("command_id")


def _command_target(
    scenes_data: ScenesData,
    commands_data: CommandsData,
    state: CommandState,
    command_id: str,
    key: Optional[str]
) -> Optional[str]:
    from app.commands.scene_commands import scene_commands
    scene_id = "town" if state.player.location == "Town" else "forest"
    commands_list = scene_commands(
        scenes_data,
        commands_data,
        scene_id,
        state.player,
        state.opponents,
    )
    for command in commands_list:
        if command.get("command") != command_id:
            continue
        if key:
            cmd_key = str(command.get("key", "")).lower()
            if cmd_key and cmd_key != key.lower():
                continue
        return command.get("target")
    return None


def _enter_scene(scene_id: str, state: CommandState, ctx: RouterContext) -> bool:
    def _build_forest_objects() -> None:
        scene = ctx.scenes.get("forest", {})
        objects_data = ctx.objects
        if not objects_data:
            return
        scene["layout_seed"] = random.randint(0, 2**31 - 1)
        gap_min = int(scene.get("gap_min", 0) or 0)
        target_width = max(0, (SCREEN_WIDTH - 2 - gap_min) // 2)
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
        def build_strip() -> list[dict]:
            strip = []
            width = 0
            while width < target_width:
                obj_id = random.choice(options)
                strip.append({"id": obj_id})
                width += obj_width(obj_id)
                if obj_width(obj_id) == 0:
                    break
                if width < target_width and objects_data.get("grass_1", {}).get("art"):
                    strip.append({"id": "grass_1"})
                    width += obj_width("grass_1")
            return strip
        scene["objects_left"] = build_strip()
        scene["objects_right"] = build_strip()
        scene["gap_min"] = 0

    if scene_id == "town":
        if state.player.location == "Town":
            state.last_message = "You are already in town."
            return True
        state.player.location = "Town"
        state.opponents = []
        state.loot_bank = {"xp": 0, "gold": 0}
        state.shop_mode = False
        state.inventory_mode = False
        state.hall_mode = False
        state.inn_mode = False
        state.spell_mode = False
        state.last_message = "You return to town."
        ctx.save_data.save_player(state.player)
        return True
    if scene_id == "forest":
        if state.player.location != "Forest":
            _build_forest_objects()
            state.player.location = "Forest"
            state.opponents = []
            state.loot_bank = {"xp": 0, "gold": 0}
            state.last_message = "All is quiet. No enemies in sight."
            state.shop_mode = False
            state.inventory_mode = False
            state.hall_mode = False
            state.inn_mode = False
            state.spell_mode = False
            ctx.save_data.save_player(state.player)
            return True

        primary = primary_opponent(state.opponents)
        if primary:
            state.last_message = f"You are already facing a {primary.name}."
            ctx.save_data.save_player(state.player)
            return True

        state.opponents = ctx.opponents_data.spawn(state.player.level, ANSI.FG_WHITE)
        state.loot_bank = {"xp": 0, "gold": 0}
        if state.opponents:
            state.last_message = f"A {state.opponents[0].name} appears."
        else:
            state.last_message = "All is quiet. No enemies in sight."
        ctx.save_data.save_player(state.player)
        return True
    return False
