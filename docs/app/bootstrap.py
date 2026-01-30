"""Application bootstrap helpers."""

from dataclasses import dataclass

from app.commands import build_registry
from app.commands.router import RouterContext
from app.commands.scene_commands import command_ids_by_anim, command_ids_by_type
from app.config import DATA_DIR, SAVE_PATH
from app.data_access.commands_data import CommandsData
from app.data_access.colors_data import ColorsData
from app.data_access.continents_data import ContinentsData
from app.data_access.frames_data import FramesData
from app.data_access.spells_art_data import SpellsArtData
from app.data_access.elements_data import ElementsData
from app.data_access.items_data import ItemsData
from app.data_access.menus_data import MenusData
from app.data_access.npcs_data import NpcsData
from app.data_access.objects_data import ObjectsData
from app.data_access.opponents_data import OpponentsData
from app.data_access.save_data import SaveData
from app.data_access.scenes_data import ScenesData
from app.data_access.spells_data import SpellsData
from app.data_access.text_data import TextData
from app.data_access.venues_data import VenuesData
from app.ui.screens import ScreenContext


@dataclass
class AppContext:
    items: ItemsData
    opponents: OpponentsData
    scenes: ScenesData
    npcs: NpcsData
    objects: ObjectsData
    venues: VenuesData
    spells: SpellsData
    commands_data: CommandsData
    menus: MenusData
    texts: TextData
    colors: ColorsData
    frames: FramesData
    continents: ContinentsData
    elements: ElementsData
    spells_art: SpellsArtData
    save_data: SaveData
    registry: object
    router_ctx: RouterContext
    screen_ctx: ScreenContext
    spell_commands: set
    targeted_spell_commands: set
    flash_spell_commands: set
    combat_actions: set
    offensive_actions: set
    battle_end_commands: set


def _load_items() -> ItemsData:
    return ItemsData(f"{DATA_DIR}/items.json")


def _load_opponents() -> OpponentsData:
    return OpponentsData(f"{DATA_DIR}/opponents.json")


def _load_scenes() -> ScenesData:
    return ScenesData(f"{DATA_DIR}/scenes.json")


def _load_npcs() -> NpcsData:
    return NpcsData(f"{DATA_DIR}/npcs.json")


def _load_objects() -> ObjectsData:
    return ObjectsData(f"{DATA_DIR}/objects.json")


def _load_venues() -> VenuesData:
    return VenuesData(f"{DATA_DIR}/venues.json")


def _load_spells() -> SpellsData:
    return SpellsData(f"{DATA_DIR}/spells.json")


def _load_commands() -> CommandsData:
    return CommandsData(f"{DATA_DIR}/commands.json")


def _load_menus() -> MenusData:
    return MenusData(f"{DATA_DIR}/menus.json")


def _load_texts() -> TextData:
    return TextData(f"{DATA_DIR}/text.json")


def _load_colors() -> ColorsData:
    return ColorsData(f"{DATA_DIR}/colors.json")


def _load_frames() -> FramesData:
    return FramesData(f"{DATA_DIR}/frames.json")


def _load_elements() -> ElementsData:
    return ElementsData(f"{DATA_DIR}/elements.json")


def _load_spells_art() -> SpellsArtData:
    return SpellsArtData(f"{DATA_DIR}/spells_art.json")


def _load_continents() -> ContinentsData:
    return ContinentsData(f"{DATA_DIR}/continents.json")


def _load_save() -> SaveData:
    return SaveData(SAVE_PATH)


def _spell_command_sets(spells: SpellsData) -> tuple[set, set, set]:
    spell_commands = {
        spell.get("command_id")
        for spell in spells.all().values()
        if isinstance(spell, dict) and spell.get("command_id")
    }
    targeted_spell_commands = {
        spell.get("command_id")
        for spell in spells.all().values()
        if isinstance(spell, dict) and spell.get("command_id") and spell.get("requires_target")
    }
    flash_spell_commands = {
        spell.get("command_id")
        for spell in spells.all().values()
        if isinstance(spell, dict) and spell.get("command_id") and spell.get("anim") == "flash_melt"
    }
    return spell_commands, targeted_spell_commands, flash_spell_commands


def create_app() -> AppContext:
    items = _load_items()
    opponents = _load_opponents()
    scenes = _load_scenes()
    npcs = _load_npcs()
    objects = _load_objects()
    venues = _load_venues()
    spells = _load_spells()
    commands_data = _load_commands()
    menus = _load_menus()
    texts = _load_texts()
    colors = _load_colors()
    frames = _load_frames()
    elements = _load_elements()
    spells_art = _load_spells_art()
    continents = _load_continents()
    save_data = _load_save()

    spell_commands, targeted_spell_commands, flash_spell_commands = _spell_command_sets(spells)
    combat_actions = command_ids_by_type(scenes, "combat") | spell_commands
    offensive_actions = command_ids_by_anim(scenes, "flash_melt") | flash_spell_commands
    battle_end_commands = {"BATTLE_END"}

    registry = build_registry()
    router_ctx = RouterContext(
        items=items,
        opponents_data=opponents,
        scenes=scenes,
        commands=commands_data,
        venues=venues,
        save_data=save_data,
        spells=spells,
        menus=menus,
        continents=continents,
        elements=elements,
        spells_art=spells_art,
        objects=objects,
        registry=registry,
    )
    screen_ctx = ScreenContext(
        items=items,
        opponents=opponents,
        scenes=scenes,
        npcs=npcs,
        objects=objects,
        venues=venues,
        menus=menus,
        commands=commands_data,
        spells=spells,
        text=texts,
        colors=colors,
        frames=frames,
        continents=continents,
        elements=elements,
        spells_art=spells_art,
    )

    return AppContext(
        items=items,
        opponents=opponents,
        scenes=scenes,
        npcs=npcs,
        objects=objects,
        venues=venues,
        spells=spells,
        commands_data=commands_data,
        menus=menus,
        texts=texts,
        colors=colors,
        frames=frames,
        continents=continents,
        elements=elements,
        spells_art=spells_art,
        save_data=save_data,
        registry=registry,
        router_ctx=router_ctx,
        screen_ctx=screen_ctx,
        spell_commands=spell_commands,
        targeted_spell_commands=targeted_spell_commands,
        flash_spell_commands=flash_spell_commands,
        combat_actions=combat_actions,
        offensive_actions=offensive_actions,
        battle_end_commands=battle_end_commands,
    )
