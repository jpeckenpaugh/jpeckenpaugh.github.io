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

    def available(self, player_level: int) -> list[Tuple[str, dict]]:
        entries = []
        for spell_id, spell in self._spells.items():
            level_required = int(spell.get("level_required", 0) or 0)
            if player_level >= level_required:
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
