"""Command router for stateful, data-driven actions."""

from dataclasses import dataclass
import random
from typing import List, Optional

from app.combat import cast_spell, primary_opponent
from app.data_access.commands_data import CommandsData
from app.data_access.continents_data import ContinentsData
from app.data_access.items_data import ItemsData
from app.data_access.glyphs_data import GlyphsData
from app.data_access.elements_data import ElementsData
from app.data_access.spells_art_data import SpellsArtData
from app.data_access.opponents_data import OpponentsData
from app.data_access.scenes_data import ScenesData
from app.data_access.venues_data import VenuesData
from app.data_access.menus_data import MenusData
from app.data_access.objects_data import ObjectsData
from app.data_access.save_data import SaveData
from app.data_access.quests_data import QuestsData
from app.data_access.stories_data import StoriesData
from app.models import Player, Opponent
from app.commands.registry import CommandContext, CommandRegistry, dispatch_command
from app.commands.scene_commands import command_is_enabled
from app.data_access.spells_data import SpellsData
from app.questing import handle_event
from app.venues import handle_venue_command, venue_id_from_state
from app.ui.ansi import ANSI
from app.ui.rendering import animate_battle_start
from app.ui.constants import SCREEN_WIDTH
from app.player_sync import sync_player_elements


@dataclass
class CommandState:
    player: Player
    opponents: List[Opponent]
    loot_bank: dict
    last_message: str
    current_venue_id: Optional[str]
    shop_mode: bool
    shop_view: str
    inventory_mode: bool
    inventory_items: List[tuple[str, str]]
    hall_mode: bool
    hall_view: str
    inn_mode: bool
    stats_mode: bool
    spell_mode: bool
    followers_mode: bool
    element_mode: bool
    alchemist_mode: bool
    alchemy_first: Optional[str]
    alchemy_selecting: bool
    temple_mode: bool
    smithy_mode: bool
    portal_mode: bool
    quest_mode: bool
    options_mode: bool
    action_cmd: Optional[str]
    quest_continent_index: int = 0
    quest_detail_mode: bool = False
    quest_detail_id: Optional[str] = None
    quest_detail_page: int = 0
    target_index: Optional[int] = None
    command_target_override: Optional[str] = None
    command_service_override: Optional[str] = None


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
    continents: ContinentsData
    elements: ElementsData
    abilities: object
    spells_art: SpellsArtData
    glyphs: GlyphsData
    objects: ObjectsData
    quests: QuestsData
    stories: StoriesData
    title_screen: object
    portal_screen: object
    spellbook_screen: object
    quests_screen: object
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
        state.current_venue_id = venue_id
        if venue_id == "town_shop":
            state.shop_mode = True
            state.shop_view = "menu"
            state.hall_mode = False
            state.inn_mode = False
            state.inventory_mode = False
            state.spell_mode = False
            state.element_mode = False
            state.alchemist_mode = False
            state.temple_mode = False
            state.smithy_mode = False
            state.portal_mode = False
        elif venue_id == "town_hall":
            state.hall_mode = True
            state.hall_view = "menu"
            state.shop_mode = False
            state.inn_mode = False
            state.inventory_mode = False
            state.spell_mode = False
            state.element_mode = False
            state.alchemist_mode = False
            state.temple_mode = False
            state.smithy_mode = False
            state.portal_mode = False
        elif venue_id == "town_inn":
            state.inn_mode = True
            state.shop_mode = False
            state.hall_mode = False
            state.inventory_mode = False
            state.spell_mode = False
            state.element_mode = False
            state.alchemist_mode = False
            state.temple_mode = False
            state.smithy_mode = False
            state.portal_mode = False
        elif venue_id == "town_alchemist":
            state.alchemist_mode = True
            state.alchemy_first = None
            state.shop_mode = False
            state.hall_mode = False
            state.inn_mode = False
            state.inventory_mode = False
            state.spell_mode = False
            state.element_mode = False
            state.temple_mode = False
            state.smithy_mode = False
            state.portal_mode = False
        elif venue_id == "town_temple":
            state.temple_mode = True
            state.shop_mode = False
            state.hall_mode = False
            state.inn_mode = False
            state.inventory_mode = False
            state.spell_mode = False
            state.element_mode = False
            state.alchemist_mode = False
            state.smithy_mode = False
            state.portal_mode = False
        elif venue_id == "town_smithy":
            state.smithy_mode = True
            state.shop_mode = False
            state.hall_mode = False
            state.inn_mode = False
            state.inventory_mode = False
            state.spell_mode = False
            state.element_mode = False
            state.alchemist_mode = False
            state.temple_mode = False
            state.portal_mode = False
        elif venue_id == "town_portal":
            state.portal_mode = True
            state.shop_mode = False
            state.hall_mode = False
            state.inn_mode = False
            state.inventory_mode = False
            state.spell_mode = False
            state.element_mode = False
            state.alchemist_mode = False
            state.temple_mode = False
            state.smithy_mode = False
        else:
            return False
        state.last_message = venue.get("welcome_message", state.last_message)
        return True

    if command_id == "PORTAL":
        menu = ctx.menus.get("portal", {})
        state.portal_mode = True
        state.current_venue_id = "town_portal"
        state.shop_mode = False
        state.hall_mode = False
        state.inn_mode = False
        state.inventory_mode = False
        state.spell_mode = False
        state.element_mode = False
        state.alchemist_mode = False
        state.temple_mode = False
        state.smithy_mode = False
        state.last_message = menu.get("open_message", "Select a continent.")
        return True

    if command_id == "QUEST":
        state.quest_mode = True
        state.quest_detail_mode = False
        state.quest_detail_id = None
        state.quest_detail_page = 0
        state.options_mode = False
        state.shop_mode = False
        state.hall_mode = False
        state.inn_mode = False
        state.inventory_mode = False
        state.spell_mode = False
        state.element_mode = False
        state.alchemist_mode = False
        state.temple_mode = False
        state.smithy_mode = False
        state.portal_mode = False
        elements = list(getattr(state.player, "elements", []) or [])
        if hasattr(ctx, "continents"):
            order = list(ctx.continents.order() or [])
            if order:
                elements = [e for e in order if e in elements] or elements
        current = getattr(state.player, "current_element", None)
        if current in elements:
            state.quest_continent_index = elements.index(current)
        else:
            state.quest_continent_index = 0
        state.last_message = "Your quests await."
        return True

    if command_id == "ENTER_SCENE":
        scene_id = _command_target(ctx.scenes, ctx.commands, state, command_id, key)
        if not scene_id:
            return False
        state.current_venue_id = None
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

    if command_id == "B_KEY" and state.element_mode:
        menu = ctx.menus.get("elements", {})
        state.element_mode = False
        state.last_message = menu.get("close_message", "Closed elements.")
        return True

    if command_id == "B_KEY" and state.quest_mode:
        state.quest_mode = False
        state.quest_detail_mode = False
        state.quest_detail_id = None
        state.quest_detail_page = 0
        state.last_message = "Closed quests."
        return True

    if command_id == "B_KEY" and state.options_mode:
        menu = ctx.menus.get("options", {})
        state.options_mode = False
        state.last_message = menu.get("close_message", "Closed options.")
        return True

    if command_id == "B_KEY" and state.followers_mode:
        menu = ctx.menus.get("followers", {})
        state.followers_mode = False
        state.last_message = menu.get("close_message", "Closed followers.")
        return True
    if command_id == "SPELLBOOK":
        menu = ctx.menus.get("spellbook", {})
        state.spell_mode = True
        state.shop_mode = False
        state.shop_view = "menu"
        state.inventory_mode = False
        state.hall_mode = False
        state.inn_mode = False
        state.options_mode = False
        state.followers_mode = False
        state.element_mode = False
        state.last_message = menu.get("open_message", "Open spellbook.")
        return True

    if command_id == "FOLLOWERS":
        menu = ctx.menus.get("followers", {})
        state.followers_mode = True
        state.options_mode = False
        state.menu_cursor = 0
        state.follower_dismiss_pending = None
        state.followers_focus = "list"
        state.followers_action_cursor = 0
        state.last_message = menu.get("open_message", "View your followers.")
        return True

    if command_id == "FOLLOWER_FUSE_AUTO":
        if state.current_venue_id != "town_temple":
            state.last_message = "Fusing is only possible at the temple."
            return True
        if state.player.gold < 100:
            state.last_message = "Not enough GP to fuse followers."
            return True
        followers = getattr(state.player, "followers", [])
        if not isinstance(followers, list):
            followers = []
        counts = {}
        for follower in followers:
            if not isinstance(follower, dict):
                continue
            f_type = str(follower.get("type", ""))
            if not f_type:
                continue
            counts[f_type] = counts.get(f_type, 0) + 1
        fuse_type = None
        for f_type, count in counts.items():
            if count >= 3:
                fuse_type = f_type
                break
        if not fuse_type:
            state.last_message = "Need three followers of the same type to fuse."
            return True
        fused = state.player.fuse_followers(fuse_type, 3)
        if not fused:
            state.last_message = "Need three followers of the same type to fuse."
            return True
        state.player.gold = max(0, state.player.gold - 100)
        state.last_message = f"{fused.get('name', 'Follower')} joins your party."
        if hasattr(ctx, "quests") and ctx.quests is not None:
            quest_messages = handle_event(
                state.player,
                ctx.quests,
                "fuse_followers",
                {"follower_type": fuse_type, "count": 3},
                ctx.items,
            )
            if quest_messages:
                state.last_message = f"{state.last_message} " + " ".join(quest_messages)
        ctx.save_data.save_player(state.player)
        return True

    if command_id == "ELEMENTS":
        menu = ctx.menus.get("elements", {})
        state.element_mode = True
        state.inventory_mode = False
        state.shop_mode = False
        state.hall_mode = False
        state.inn_mode = False
        state.spell_mode = False
        state.options_mode = False
        state.followers_mode = False
        state.last_message = menu.get("open_message", "Select an element.")
        return True

    if command_id == "OPTIONS":
        menu = ctx.menus.get("options", {})
        if state.options_mode:
            state.options_mode = False
            state.menu_cursor = 0
            state.last_message = menu.get("close_message", "Closed options.")
            return True
        actions = []
        available_spells = ctx.spells.available(state.player, ctx.items) if hasattr(ctx, "spells") else []
        for entry in menu.get("actions", []):
            if not entry.get("command"):
                continue
            cmd_entry = dict(entry)
            if not command_is_enabled(cmd_entry, state.player, state.opponents):
                cmd_entry["_disabled"] = True
            if cmd_entry.get("command") == "SPELLBOOK" and not available_spells:
                cmd_entry["_disabled"] = True
            actions.append(cmd_entry)
        enabled = [i for i, cmd in enumerate(actions) if not cmd.get("_disabled")]
        state.menu_cursor = enabled[0] if enabled else -1
        state.options_mode = True
        state.followers_mode = False
        state.last_message = menu.get("open_message", "Options menu.")
        return True

    if state.portal_mode and command_id.startswith("PORTAL:"):
        element_id = command_id.split(":", 1)[1]
        if element_id and element_id in getattr(state.player, "elements", []):
            state.player.current_element = element_id
            state.portal_mode = False
            ctx.save_data.save_player(state.player)
            state.last_message = f"Teleported to {element_id.title()} continent."
            return True

    if state.spell_mode and command_id:
        spell_entry = ctx.spells.by_command_id(command_id)
        if not spell_entry:
            return False
        _, spell = spell_entry
        in_battle = state.player.location == "Forest" and any(opp.hp > 0 for opp in state.opponents)
        state.spell_mode = not in_battle
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

    if command_id in ("B_KEY", "LEAVE") and (
        state.current_venue_id
        or state.hall_mode
        or state.inn_mode
        or state.shop_mode
        or state.alchemist_mode
        or state.temple_mode
        or state.smithy_mode
        or state.portal_mode
    ):
        venue_id = venue_id_from_state(state)
        if venue_id:
            return handle_venue_command(ctx, state, venue_id, command_id)
        state.shop_mode = False
        state.shop_view = "menu"
        state.hall_mode = False
        state.inn_mode = False
        state.alchemist_mode = False
        state.alchemy_first = None
        state.temple_mode = False
        state.smithy_mode = False
        state.portal_mode = False
        state.current_venue_id = None
        state.last_message = "You leave the venue."
        return True

    if state.shop_mode:
        venue_id = venue_id_from_state(state)
        if venue_id and handle_venue_command(ctx, state, venue_id, command_id):
            return True

    if state.alchemist_mode:
        venue_id = venue_id_from_state(state)
        if venue_id and handle_venue_command(ctx, state, venue_id, command_id):
            return True

    if command_id == "INVENTORY":
        menu = ctx.menus.get("inventory", {})
        state.inventory_items = state.player.list_inventory_items(ctx.items)
        if not state.inventory_items:
            state.last_message = menu.get("empty", "Inventory is empty.")
            return True
        state.inventory_mode = True
        state.stats_mode = False
        state.shop_mode = False
        state.hall_mode = False
        state.spell_mode = False
        state.options_mode = False
        state.last_message = menu.get("open_message", "Choose an item to use.")
        return True

    if command_id == "STATS":
        menu = ctx.menus.get("stats", {})
        state.stats_mode = True
        state.menu_cursor = 0
        state.inventory_mode = False
        state.shop_mode = False
        state.hall_mode = False
        state.spell_mode = False
        state.options_mode = False
        state.last_message = menu.get("open_message", "View stats and spend points.")
        return True

    if state.inventory_mode:
        menu = ctx.menus.get("inventory", {})
        if command_id == "B_KEY":
            state.inventory_mode = False
            state.last_message = menu.get("close_message", "Closed inventory.")
            return True
        if command_id == "NUM":
            state.last_message = menu.get("open_message", "Choose an item to use.")
            return True
        if command_id.startswith("NUM"):
            idx = int(command_id.replace("NUM", "")) - 1
            if 0 <= idx < len(state.inventory_items):
                item_id, _ = state.inventory_items[idx]
                target = None
                if state.player.followers:
                    item = ctx.items.get(item_id, {})
                    if isinstance(item, dict) and (int(item.get("hp", 0)) > 0 or int(item.get("mp", 0)) > 0):
                        target_type, target_ref = state.player.select_team_target(mode="combined")
                        if target_type == "follower":
                            target = target_ref
                state.last_message = state.player.use_item(item_id, ctx.items, target=target)
                ctx.save_data.save_player(state.player)
                state.inventory_items = state.player.list_inventory_items(ctx.items)
                if not state.inventory_items:
                    state.inventory_mode = False
            else:
                state.last_message = "Invalid item selection."
            return True

    if state.stats_mode:
        menu = ctx.menus.get("stats", {})
        if command_id == "B_KEY":
            state.stats_mode = False
            state.last_message = menu.get("close_message", "Closed stats.")
            return True
        if command_id in ("STAT_HP", "STAT_MP", "STAT_ATK", "STAT_DEF"):
            if state.player.stat_points <= 0:
                state.last_message = "No stat points to spend."
                return True
            mapping = {
                "STAT_HP": "HP",
                "STAT_MP": "MP",
                "STAT_ATK": "ATK",
                "STAT_DEF": "DEF",
            }
            stat = mapping.get(command_id)
            if stat:
                state.player.spend_stat_point(stat)
                ctx.save_data.save_player(state.player)
                state.last_message = f"{stat} increased by 1."
            return True
        if command_id == "STAT_BALANCED":
            if state.player.stat_points <= 0:
                state.last_message = "No stat points to spend."
                return True
            state.player.allocate_balanced()
            ctx.save_data.save_player(state.player)
            state.last_message = "Balanced allocation complete."
            return True
        if command_id == "STAT_RANDOM":
            if state.player.stat_points <= 0:
                state.last_message = "No stat points to spend."
                return True
            state.player.allocate_random()
            ctx.save_data.save_player(state.player)
            state.last_message = "Random allocation complete."
            return True
    if state.element_mode and command_id.startswith("ELEMENT:"):
        element_id = command_id.split(":", 1)[1]
        if element_id and element_id in getattr(state.player, "elements", []):
            state.player.current_element = element_id
            state.element_mode = False
            ctx.save_data.save_player(state.player)
            state.last_message = f"Element set to {element_id.title()}."
            return True

    if command_id == "USE_SERVICE":
        service_key = state.command_service_override or "rest"
        venue_id = state.command_target_override
        if state.inn_mode:
            venue = ctx.venues.get("town_inn", {})
            if not venue_id:
                for entry in venue.get("commands", []):
                    if entry.get("command") != command_id:
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
        if service_type not in ("rest", "meal", "overcharge"):
            return False
        if service_type != "overcharge":
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
        if service_type == "overcharge":
            if not state.player.equipment.get("wand"):
                state.last_message = service.get("no_wand_message", "You have no wand to charge.")
                return True
            state.player.recharge_wands(overcharge=True)
            state.last_message = service.get("message", "Your wand hums with power.")
        elif service_type == "meal":
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
            state.player.temp_atk_bonus = 0
            state.player.temp_def_bonus = 0
            state.player.temp_hp_bonus = 0
            state.last_message = service.get("message", "You rest at the inn and feel fully restored.")
        if service_type in ("rest", "meal"):
            state.player.recharge_wands()
            state.player.recharge_follower_wands()
            state.player.restore_follower_mp()
        ctx.save_data.save_player(state.player)
        return True

    ctx_data = CommandContext(
        player=state.player,
        opponents=state.opponents,
        loot=state.loot_bank,
        spells_data=ctx.spells,
        items_data=ctx.items,
        quests_data=ctx.quests,
        target_index=state.target_index,
    )
    if command_id in ("ATTACK", "SPARK", "HEAL", "DEFEND", "SOCIALIZE"):
        state.action_cmd = command_id
        return True

    message = dispatch_command(ctx.registry, command_id, ctx_data)
    if message != "Unknown action.":
        state.last_message = message
        if command_id in ("FLEE", "SOCIALIZE"):
            state.action_cmd = command_id
        return True

    return False


def _handle_title(command_id: str, state: CommandState, ctx: RouterContext, key: Optional[str]) -> bool:
    if command_id == "QUIT":
        state.action_cmd = "QUIT"
        return True
    if command_id == "TITLE_CONFIRM_YES":
        pending_slot = getattr(state.player, "title_pending_slot", None)
        if pending_slot:
            ctx.save_data.delete(pending_slot)
        state.player.title_confirm = False
        state.player.title_name_select = True
        state.player.title_slot_select = False
        return True
    if command_id == "TITLE_CONFIRM_NO":
        state.player.title_confirm = False
        state.player.title_slot_select = False
        state.player.title_pending_slot = None
        return True
    if command_id == "TITLE_NEW":
        state.player.title_confirm = False
        state.player.title_fortune = False
        state.player.title_slot_select = False
        state.player.title_slot_mode = None
        state.player.title_start_confirm = False
        state.player.title_pending_name = None
        state.player.title_pending_fortune = None
        state.player.title_name_shift = True
        next_slot = ctx.save_data.next_empty_slot(max_slots=100)
        if next_slot is None:
            fallback_slot = ctx.save_data.last_played_slot() or 1
            state.player.title_confirm = True
            state.player.title_pending_slot = fallback_slot
            return True
        state.player.title_pending_slot = next_slot
        state.player.title_name_select = True
        return True
    if command_id == "TITLE_NAME_CUSTOM":
        state.player.title_name_select = False
        state.player.title_name_input = True
        state.player.title_pending_name = ""
        state.player.title_name_cursor = (0, 0)
        state.player.title_name_shift = True
        return True
    if command_id == "TITLE_NAME_RANDOM":
        name_choices = [
            "Arin", "Bram", "Cora", "Dain", "Elow",
            "Fenn", "Garen", "Hira", "Ivo", "Jora",
            "Kael", "Lyra", "Mira", "Nox", "Orin",
            "Pella", "Quin", "Rook", "Sera", "Taro",
        ]
        existing = ctx.save_data.existing_player_names(max_slots=100)
        available = [name for name in name_choices if name not in existing]
        max_len = 16
        if available:
            chosen = random.choice(available)
        else:
            def to_roman(num: int) -> str:
                numerals = [
                    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
                    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
                    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"),
                    (1, "I"),
                ]
                out = []
                value = num
                for val, symbol in numerals:
                    while value >= val:
                        out.append(symbol)
                        value -= val
                return "".join(out)

            base = random.choice(name_choices)
            suffix = 2
            while True:
                roman = to_roman(suffix)
                allowed = max_len - (len(roman) + 1)
                base_trim = base[:allowed] if allowed > 0 else ""
                candidate = f"{base_trim} {roman}".strip()
                if candidate and candidate not in existing:
                    chosen = candidate
                    break
                suffix += 1
        state.player.title_pending_name = chosen[:16]
        state.player.title_name_select = False
        state.player.title_fortune = True
        return True
    if command_id == "TITLE_NAME_BACK":
        state.player.title_name_select = False
        return True
    if command_id.startswith("TITLE_NAME:"):
        name = command_id.split(":", 1)[1].strip()
        if name:
            state.player.title_pending_name = name[:16]
        state.player.title_name_select = False
        state.player.title_fortune = True
        return True
    if command_id == "TITLE_FORTUNE_BACK":
        state.player.title_fortune = False
        state.player.title_name_select = True
        return True
    if command_id == "TITLE_SLOT_BACK":
        state.player.title_slot_select = False
        state.player.title_slot_mode = None
        state.player.title_pending_slot = None
        return True
    if command_id.startswith("TITLE_SLOT_"):
        slot_raw = command_id.replace("TITLE_SLOT_", "")
        if not slot_raw.isdigit():
            return False
        slot = int(slot_raw)
        mode = getattr(state.player, "title_slot_mode", "continue")
        if mode == "continue":
            if not ctx.save_data.exists(slot):
                state.last_message = "That slot is empty."
                return True
            loaded = ctx.save_data.load_player(slot)
            state.player = loaded if loaded else Player.from_dict({})
            state.player.sync_items(ctx.items)
            sync_player_elements(ctx, state.player)
            state.player.location = "Town"
            state.player.title_confirm = False
            state.player.title_fortune = False
            state.player.title_slot_select = False
            state.player.title_slot_mode = None
            state.player.title_pending_slot = None
            state.player.has_save = True
            state.opponents = []
            state.loot_bank = {"xp": 0, "gold": 0}
            state.shop_mode = False
            state.inventory_mode = False
            state.hall_mode = False
            state.inn_mode = False
            state.spell_mode = False
            state.last_message = "You arrive in town."
            return True
        if ctx.save_data.exists(slot):
            state.player.title_confirm = True
            state.player.title_pending_slot = slot
            return True
        state.player.title_pending_slot = slot
        state.player.title_name_select = True
        state.player.title_slot_select = False
        return True
    if command_id == "TITLE_START_CONFIRM_NO":
        state.player.title_start_confirm = False
        state.player.title_fortune = True
        return True
    if command_id == "TITLE_START_CONFIRM_YES":
        fortune_gold = {
            "FORTUNE_POOR": 10,
            "FORTUNE_WELL_OFF": 100,
            "FORTUNE_ROYALTY": 1000,
        }
        pending_slot = getattr(state.player, "title_pending_slot", None) or 1
        pending_name = str(getattr(state.player, "title_pending_name", "") or "WARRIOR")
        pending_fortune = str(getattr(state.player, "title_pending_fortune", "") or "FORTUNE_POOR")
        ctx.save_data.set_current_slot(pending_slot)
        state.player = Player.from_dict({
            "gold": fortune_gold.get(pending_fortune, 10),
            "name": pending_name[:16],
        })
        state.player.sync_items(ctx.items)
        sync_player_elements(ctx, state.player)
        state.player.location = "Town"
        state.player.title_confirm = False
        state.player.title_fortune = False
        state.player.title_start_confirm = False
        state.player.title_slot_select = False
        state.player.title_slot_mode = None
        state.player.title_pending_slot = None
        state.player.title_pending_name = None
        state.player.title_pending_fortune = None
        state.player.title_name_select = False
        state.player.title_name_input = False
        state.player.has_save = False
        state.opponents = []
        state.loot_bank = {"xp": 0, "gold": 0}
        state.shop_mode = False
        state.inventory_mode = False
        state.hall_mode = False
        state.inn_mode = False
        state.spell_mode = False
        state.element_mode = False
        state.alchemist_mode = False
        state.alchemy_first = None
        state.temple_mode = False
        state.smithy_mode = False
        state.portal_mode = False
        state.last_message = "You arrive in town."
        ctx.save_data.save_player(state.player)
        return True
    if command_id in ("FORTUNE_POOR", "FORTUNE_WELL_OFF", "FORTUNE_ROYALTY"):
        state.player.title_pending_fortune = command_id
        state.player.title_fortune = False
        state.player.title_start_confirm = True
        return True
    if command_id == "TITLE_CONTINUE":
        if not ctx.save_data.exists():
            return True
        state.player.title_slot_select = True
        state.player.title_slot_mode = "continue"
        state.player.title_confirm = False
        state.player.title_fortune = False
        return True
    return False


def _command_target(
    scenes_data: ScenesData,
    commands_data: CommandsData,
    state: CommandState,
    command_id: str,
    key: Optional[str]
) -> Optional[str]:
    if state.command_target_override:
        return state.command_target_override
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
        state.element_mode = False
        state.alchemist_mode = False
        state.alchemy_first = None
        state.temple_mode = False
        state.smithy_mode = False
        state.portal_mode = False
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
            state.shop_view = "menu"
            state.inventory_mode = False
            state.hall_mode = False
            state.inn_mode = False
            state.spell_mode = False
            state.element_mode = False
            state.alchemist_mode = False
            state.alchemy_first = None
            state.temple_mode = False
            state.smithy_mode = False
            state.portal_mode = False
            ctx.save_data.save_player(state.player)
            return True

        primary = primary_opponent(state.opponents)
        if primary:
            state.last_message = f"You are already facing a {primary.name}."
            ctx.save_data.save_player(state.player)
            return True

        state.opponents = ctx.opponents_data.spawn(
            state.player.level,
            ANSI.FG_WHITE,
            element=getattr(state.player, "current_element", "base")
        )
        state.loot_bank = {"xp": 0, "gold": 0}
        if state.opponents:
            state.last_message = f"A {state.opponents[0].name} appears."
        else:
            state.last_message = "All is quiet. No enemies in sight."
        ctx.save_data.save_player(state.player)
        return True
    return False
