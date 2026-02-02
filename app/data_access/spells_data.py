"""Load spell data from JSON."""

import json
from typing import Dict, Optional, Tuple


class SpellsData:
    def __init__(self, path: str):
        self._path = path
        self._spells: Dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._spells = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._spells = {}

    def all(self) -> Dict[str, dict]:
        return self._spells

    def get(self, key: str, default: Optional[dict] = None) -> dict:
        if default is None:
            default = {}
        return self._spells.get(key, default)

    def by_command_id(self, command_id: str) -> Optional[Tuple[str, dict]]:
        for spell_id, spell in self._spells.items():
            if spell.get("command_id") == command_id:
                return spell_id, spell
        return None

    def by_menu_key(self, menu_key: str) -> Optional[Tuple[str, dict]]:
        for spell_id, spell in self._spells.items():
            if spell.get("menu_key") == menu_key:
                return spell_id, spell
        return None

    def available(self, player, items_data: Optional[object] = None) -> list[Tuple[str, dict]]:
        entries = []
        player_level = int(getattr(player, "level", 0) or 0) if not isinstance(player, int) else int(player)
        flags = getattr(player, "flags", {}) if not isinstance(player, int) else {}
        if not isinstance(flags, dict):
            flags = {}
        equipped_ids = set()
        granted_spells = set()
        if not isinstance(player, int) and items_data is not None:
            equipment = getattr(player, "equipment", {}) if hasattr(player, "equipment") else {}
            if isinstance(equipment, dict):
                for gear_id in equipment.values():
                    gear = getattr(player, "gear_instance", lambda _id: None)(gear_id)
                    if not isinstance(gear, dict):
                        continue
                    item_id = gear.get("item_id")
                    if item_id:
                        equipped_ids.add(str(item_id))
                        item = items_data.get(str(item_id), {}) if hasattr(items_data, "get") else {}
                        grants = item.get("grants_spells", [])
                        if isinstance(grants, list):
                            granted_spells.update(str(spell_id) for spell_id in grants)
                    grants = gear.get("grants_spells", [])
                    if isinstance(grants, list):
                        granted_spells.update(str(spell_id) for spell_id in grants)
        for spell_id, spell in self._spells.items():
            level_required = int(spell.get("level_required", 0) or 0)
            if player_level < level_required:
                continue
            unlock = spell.get("unlock")
            if not isinstance(player, int):
                flags_any = []
                items_any = []
                if isinstance(unlock, dict):
                    flags_any = unlock.get("flags_any", [])
                    if not isinstance(flags_any, list):
                        flags_any = []
                    items_any = unlock.get("items_any", [])
                    if not isinstance(items_any, list):
                        items_any = []
                allowed = False
                if flags_any and any(flags.get(str(flag), False) for flag in flags_any):
                    allowed = True
                if items_any and any(str(item_id) in equipped_ids for item_id in items_any):
                    allowed = True
                if str(spell_id) in granted_spells:
                    allowed = True
                if not allowed:
                    continue
            entries.append((spell_id, spell))
        entries.sort(key=lambda item: (int(item[1].get("level_required", 0) or 0), item[0]))
        return entries

    def rank_for(self, spell: dict, player_level: int) -> int:
        level_required = int(spell.get("level_required", 0) or 0)
        if player_level < level_required:
            return 0
        rank = 1 + max(0, (player_level - level_required) // 2)
        return min(3, rank)

    def element_unlocks(self) -> dict:
        unlocks = {}
        for spell in self._spells.values():
            if not isinstance(spell, dict):
                continue
            element = spell.get("element")
            if not element:
                continue
            level_required = int(spell.get("level_required", 0) or 0)
            unlocks[element] = min(unlocks.get(element, level_required), level_required)
        return unlocks
