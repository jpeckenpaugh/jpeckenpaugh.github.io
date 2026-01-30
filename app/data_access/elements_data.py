"""Load element data from JSON."""

import json
from typing import Dict, List


class ElementsData:
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

    def all(self) -> Dict[str, dict]:
        return self._data

    def get(self, key: str, default: dict | None = None) -> dict:
        if default is None:
            default = {}
        return self._data.get(key, default)

    def colors_for(self, element_id: str) -> List[str]:
        entry = self._data.get(element_id, {})
        colors = entry.get("colors")
        if isinstance(colors, list):
            return [str(c) for c in colors if isinstance(c, str)]
        return []
