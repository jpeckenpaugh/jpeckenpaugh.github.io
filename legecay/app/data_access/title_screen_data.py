"""Load title screen data from JSON."""

import json
from typing import Dict, Optional


class TitleScreenData:
    def __init__(self, path: str):
        self._path = path
        self._data: Dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def all(self) -> Dict[str, dict]:
        return self._data

    def get(self, key: str, default: Optional[dict] = None) -> dict:
        if default is None:
            default = {}
        value = self._data.get(key, default)
        return value if isinstance(value, dict) else default
