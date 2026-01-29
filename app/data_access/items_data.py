"""Load and query item data from JSON."""

import json
from typing import Dict, List, Optional


class ItemsData:
    def __init__(self, path: str):
        self._path = path
        self._items: Dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._items = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._items = {}

    def all(self) -> Dict[str, dict]:
        return self._items

    def get(self, key: str, default: Optional[dict] = None) -> dict:
        if default is None:
            default = {}
        return self._items.get(key, default)

    def list_descriptions(self) -> List[str]:
        lines = []
        for data in self._items.values():
            name = data.get("name", "Unknown")
            desc = data.get("desc", "")
            lines.append(f"{name}: {desc}")
        return lines
