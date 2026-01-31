"""Load follower abilities data from JSON."""

import json
from typing import Dict, Optional


class AbilitiesData:
    def __init__(self, path: str):
        self._path = path
        self._data: Dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {}
        self._data = data if isinstance(data, dict) else {}

    def get(self, ability_id: str, default: Optional[dict] = None) -> dict:
        if default is None:
            default = {}
        return self._data.get(ability_id, default)

    def all(self) -> Dict[str, dict]:
        return self._data
