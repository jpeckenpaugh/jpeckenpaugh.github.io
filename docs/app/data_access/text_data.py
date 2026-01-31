"""Load message templates from JSON."""

import json


class TextData:
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

    def get(self, section: str, key: str, default: str = "") -> str:
        section_data = self._data.get(section, {})
        if isinstance(section_data, dict):
            return str(section_data.get(key, default))
        return default
