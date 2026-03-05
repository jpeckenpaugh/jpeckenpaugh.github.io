from dataclasses import asdict
import json
import os
from typing import Optional

from app.session import GameSession, Player


class SaveGameService:
    def __init__(self, save_dir: str = "saves") -> None:
        self.save_dir = save_dir
        os.makedirs(self.save_dir, exist_ok=True)

    def _slot_path(self, slot: int) -> str:
        return os.path.join(self.save_dir, f"slot{slot}.json")

    def has_slot(self, slot: int) -> bool:
        return os.path.isfile(self._slot_path(slot))

    def delete(self, slot: int) -> None:
        path = self._slot_path(slot)
        if os.path.isfile(path):
            os.remove(path)

    def next_empty_slot(self, max_slots: int = 100) -> Optional[int]:
        for slot in range(1, max(1, int(max_slots)) + 1):
            if not self.has_slot(slot):
                return slot
        return None

    def last_played_slot(self, max_slots: int = 100) -> Optional[int]:
        latest_mtime = -1.0
        latest_slot: Optional[int] = None
        for slot in range(1, max(1, int(max_slots)) + 1):
            path = self._slot_path(slot)
            if not os.path.isfile(path):
                continue
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_slot = slot
        return latest_slot

    def save(self, session: GameSession, slot: int) -> None:
        payload = {
            "player": asdict(session.player),
            "current_scene_id": session.current_scene_id,
            "selected_slot": session.selected_slot,
            "last_message": session.last_message,
        }
        with open(self._slot_path(slot), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def load(self, slot: int) -> Optional[GameSession]:
        path = self._slot_path(slot)
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        player_payload = payload.get("player", {})
        player = Player(
            name=str(player_payload.get("name", "Hero")),
            level=int(player_payload.get("level", 1)),
            hp=int(player_payload.get("hp", 20)),
            max_hp=int(player_payload.get("max_hp", 20)),
            gold=int(player_payload.get("gold", 0)),
            avatar_id=str(player_payload.get("avatar_id", "player_01")),
            location=str(player_payload.get("location", "Town")),
        )
        return GameSession(
            player=player,
            current_scene_id=str(payload.get("current_scene_id", "title")),
            selected_slot=int(payload.get("selected_slot", slot)),
            last_message=str(payload.get("last_message", "")),
        )
