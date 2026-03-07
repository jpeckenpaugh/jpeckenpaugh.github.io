"""Load NPC data and greetings from JSON."""

import json
from typing import Dict, Optional


class NpcsData:
    def __init__(self, path: str):
        self._path = path
        self._npcs: Dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._npcs = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._npcs = {}

    def all(self) -> Dict[str, dict]:
        return self._npcs

    def get(self, key: str, default: Optional[dict] = None) -> dict:
        if default is None:
            default = {}
        return self._npcs.get(key, default)

    def format_greeting(self, npc_id: str) -> list[str]:
        npc = self.get(npc_id, {})
        name = npc.get("name", "")
        role = npc.get("role", "")
        greeting = npc.get("greeting", "")
        if greeting:
            speaker = name or role
            if speaker:
                return [f"{speaker}: {greeting}"]
            return [greeting]
        return []
