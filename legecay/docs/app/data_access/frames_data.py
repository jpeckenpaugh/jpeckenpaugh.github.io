"""Load frame art data from JSON."""

import json
from typing import Dict, Optional


class FramesData:
    def __init__(self, path: str):
        self._path = path
        self._frames: Dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._frames = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._frames = {}

    def all(self) -> Dict[str, dict]:
        return self._frames

    def get(self, key: str, default: Optional[dict] = None) -> dict:
        if default is None:
            default = {}
        return self._frames.get(key, default)
