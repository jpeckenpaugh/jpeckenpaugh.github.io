"""Load story arc data from JSON."""

import json
from typing import Dict, Optional


class StoriesData:
    def __init__(self, path: str):
        self._path = path
        self._stories: Dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._stories = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._stories = {}

    def all(self) -> Dict[str, dict]:
        return self._stories

    def get(self, key: str, default: Optional[dict] = None) -> dict:
        if default is None:
            default = {}
        return self._stories.get(key, default)
