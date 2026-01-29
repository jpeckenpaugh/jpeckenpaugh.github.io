"""Load scene data from JSON."""

import json
from typing import Dict, Optional


class ScenesData:
    def __init__(self, path: str):
        self._path = path
        self._scenes: Dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._scenes = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._scenes = {}
            return
        forest = self._scenes.get("forest")
        if isinstance(forest, dict):
            left = forest.get("left")
            right = forest.get("right")
            if isinstance(left, list) and left:
                max_left = max(len(line) for line in left)
                forest["left"] = [line.ljust(max_left) for line in left]
            if isinstance(right, list) and right:
                max_right = max(len(line) for line in right)
                forest["right"] = [line.ljust(max_right) for line in right]

    def all(self) -> Dict[str, dict]:
        return self._scenes

    def get(self, key: str, default: Optional[dict] = None) -> dict:
        if default is None:
            default = {}
        return self._scenes.get(key, default)
