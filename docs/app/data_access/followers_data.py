"""Load follower templates from JSON."""

import json
from typing import Dict, Optional


class FollowersData:
    def __init__(self, path: str):
        self._path = path
        self._followers: Dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._followers = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._followers = {}

    def all(self) -> Dict[str, dict]:
        return self._followers

    def get(self, key: str, default: Optional[dict] = None) -> dict:
        if default is None:
            default = {}
        return self._followers.get(key, default)
