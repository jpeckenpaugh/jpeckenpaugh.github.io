"""Load venue data and art from JSON."""

import json
from typing import Dict, Optional


class VenuesData:
    def __init__(self, path: str):
        self._path = path
        self._venues: Dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._venues = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._venues = {}

    def all(self) -> Dict[str, dict]:
        return self._venues

    def get(self, key: str, default: Optional[dict] = None) -> dict:
        if default is None:
            default = {}
        return self._venues.get(key, default)
