"""Load and query object art data from JSON."""

import json
from typing import Dict, Optional


class ObjectsData:
    def __init__(self, path: str):
        self._path = path
        self._objects: Dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._objects = data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            self._objects = {}

    def all(self) -> Dict[str, dict]:
        return self._objects

    def get(self, key: str, default: Optional[dict] = None) -> dict:
        if default is None:
            default = {}
        return self._objects.get(key, default)
