"""Load global color map data from JSON."""

import json
from typing import Dict, Optional


class ColorsData:
    def __init__(self, path: str):
        self._path = path
        self._colors: Dict[str, str] = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._colors = data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            self._colors = {}

    def all(self) -> Dict[str, str]:
        return self._colors

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._colors.get(key, default)
