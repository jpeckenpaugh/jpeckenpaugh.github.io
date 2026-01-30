"""Load continent data from JSON."""

import json
from typing import Dict, List


class ContinentsData:
    def __init__(self, path: str):
        self._path = path
        self._data: Dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def order(self) -> List[str]:
        order = self._data.get("order")
        if isinstance(order, list):
            return [str(item) for item in order if isinstance(item, str)]
        return []

    def continents(self) -> Dict[str, dict]:
        continents = self._data.get("continents")
        if isinstance(continents, dict):
            return continents
        return {}

    def unlocks(self) -> Dict[str, int]:
        unlocks: Dict[str, int] = {}
        for element_id, entry in self.continents().items():
            if not isinstance(entry, dict):
                continue
            level_required = int(entry.get("level_required", 0) or 0)
            unlocks[element_id] = level_required
        return unlocks

    def name_for(self, element_id: str) -> str:
        entry = self.continents().get(element_id, {})
        return entry.get("name", element_id.title())
