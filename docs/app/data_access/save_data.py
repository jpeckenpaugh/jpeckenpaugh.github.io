"""Load and persist save data."""

import json
import os
from typing import Any, Dict, Optional

from app.models import Player


class SaveData:
    def __init__(self, path: str):
        self._path = path

    def load(self) -> Dict[str, Any]:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        data.setdefault("version", 1)
        data.setdefault("player", {})
        data.setdefault("quests", {})
        data.setdefault("flags", {})
        return data

    def save(self, data: Dict[str, Any]):
        payload = {
            "version": int(data.get("version", 1)),
            "player": data.get("player", {}),
            "quests": data.get("quests", {}),
            "flags": data.get("flags", {}),
        }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        if os.environ.get("LOKARTA_WEB") == "1":
            try:
                import js
                if hasattr(js, "syncSaves"):
                    js.syncSaves()
            except Exception:
                return

    def save_player(self, player: Player):
        self.save({"player": player.to_dict()})

    def load_player(self) -> Optional[Player]:
        data = self.load()
        if not data:
            return None
        return Player.from_dict(data.get("player", {}))

    def exists(self) -> bool:
        try:
            with open(self._path, "r", encoding="utf-8"):
                return True
        except OSError:
            return False

    def delete(self):
        try:
            import os
            os.remove(self._path)
        except OSError:
            return
