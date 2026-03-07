"""Load command definitions from JSON."""

import json
from typing import List


class CommandsData:
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

    def global_commands(self) -> List[dict]:
        commands = self._data.get("global", [])
        if isinstance(commands, list):
            return commands
        return []
