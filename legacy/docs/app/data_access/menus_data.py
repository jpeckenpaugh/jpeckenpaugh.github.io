"""Load menu UI copy and actions from JSON."""

import json


class MenusData:
    def __init__(self, path: str):
        self._path = path
        self._data = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def get(self, key: str, default=None) -> dict:
        if default is None:
            default = {}
        return self._data.get(key, default)
