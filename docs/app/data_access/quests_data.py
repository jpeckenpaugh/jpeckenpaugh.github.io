"""Load quest data from JSON."""

import json
from typing import Dict, Optional


class QuestsData:
    def __init__(self, path: str):
        self._path = path
        self._quests: Dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._quests = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._quests = {}

    def all(self) -> Dict[str, dict]:
        return self._quests

    def get(self, key: str, default: Optional[dict] = None) -> dict:
        if default is None:
            default = {}
        return self._quests.get(key, default)
