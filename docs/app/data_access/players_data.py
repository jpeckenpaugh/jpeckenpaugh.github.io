"""Load player portrait data from JSON."""

import json
from typing import Dict, Optional


class PlayersData:
    def __init__(self, path: str):
        self._path = path
        self._players: Dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._players = data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            self._players = {}

    def all(self) -> Dict[str, dict]:
        return self._players

    def get(self, key: str, default: Optional[dict] = None) -> dict:
        if default is None:
            default = {}
        return self._players.get(key, default)
