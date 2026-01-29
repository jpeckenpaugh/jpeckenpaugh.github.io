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
