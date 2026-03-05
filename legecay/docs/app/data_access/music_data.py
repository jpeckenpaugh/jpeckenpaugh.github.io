"""Load music data from JSON."""

import json


class MusicData:
    def __init__(self, path: str):
        self._path = path
        self._data: dict = {}
        self.load()

    def load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def all(self) -> dict:
        return self._data

    def songs(self) -> dict:
        data = self._data.get("songs", {})
        return data if isinstance(data, dict) else {}

    def sequences(self) -> dict:
        data = self._data.get("sequences", {})
        return data if isinstance(data, dict) else {}

    def patterns(self) -> dict:
        data = self._data.get("patterns", {})
        return data if isinstance(data, dict) else {}
