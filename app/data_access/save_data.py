"""Load and persist save data."""

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from app.models import Player


MAX_SAVE_SLOTS = 100


class SaveData:
    def __init__(self, base_dir: str):
        self._base_dir = base_dir
        self._current_slot = 1
        self._last_slot_path = os.path.join(base_dir, "last_slot.json")
        os.makedirs(base_dir, exist_ok=True)

    def _slot_path(self, slot: int) -> str:
        slot_num = max(1, min(MAX_SAVE_SLOTS, int(slot)))
        return os.path.join(self._base_dir, f"slot{slot_num}.json")

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    def _load_last_slot(self) -> Optional[int]:
        try:
            with open(self._last_slot_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        slot = data.get("last_slot")
        if isinstance(slot, int) and 1 <= slot <= MAX_SAVE_SLOTS:
            return slot
        return None

    def last_played_slot(self) -> Optional[int]:
        return self._load_last_slot()

    def set_current_slot(self, slot: int) -> None:
        self._current_slot = max(1, min(MAX_SAVE_SLOTS, int(slot)))
        try:
            with open(self._last_slot_path, "w", encoding="utf-8") as f:
                json.dump({"last_slot": self._current_slot}, f, indent=2)
        except OSError:
            return

    def load(self, slot: Optional[int] = None) -> Dict[str, Any]:
        path = self._slot_path(slot or self._current_slot)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        data.setdefault("version", 1)
        data.setdefault("player", {})
        data.setdefault("quests", {})
        data.setdefault("flags", {})
        data.setdefault("meta", {})
        return data

    def save(self, data: Dict[str, Any], slot: Optional[int] = None):
        path = self._slot_path(slot or self._current_slot)
        payload = {
            "version": int(data.get("version", 1)),
            "player": data.get("player", {}),
            "quests": data.get("quests", {}),
            "flags": data.get("flags", {}),
            "meta": data.get("meta", {}),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        if os.environ.get("LOKARTA_WEB") == "1":
            try:
                import js
                if hasattr(js, "syncSaves"):
                    js.syncSaves()
            except Exception:
                return

    def save_player(self, player: Player, slot: Optional[int] = None):
        data = self.load(slot)
        meta = data.get("meta", {}) if isinstance(data, dict) else {}
        if not isinstance(meta, dict):
            meta = {}
        if not meta.get("created_at"):
            meta["created_at"] = self._now()
        meta["last_played"] = self._now()
        self.save({"player": player.to_dict(), "meta": meta}, slot)
        self.set_current_slot(slot or self._current_slot)

    def load_player(self, slot: Optional[int] = None) -> Optional[Player]:
        data = self.load(slot)
        if not data:
            return None
        self.set_current_slot(slot or self._current_slot)
        return Player.from_dict(data.get("player", {}))

    def exists(self, slot: Optional[int] = None) -> bool:
        if slot is None:
            return any(self.exists(idx) for idx in range(1, MAX_SAVE_SLOTS + 1))
        try:
            with open(self._slot_path(slot), "r", encoding="utf-8"):
                return True
        except OSError:
            return False

    def delete(self, slot: Optional[int] = None):
        path = self._slot_path(slot or self._current_slot)
        try:
            os.remove(path)
        except OSError:
            return

    def slot_summary(self, slot: int) -> dict:
        path = self._slot_path(slot)
        if not os.path.exists(path):
            return {"slot": slot, "empty": True}
        data = self.load(slot)
        player = data.get("player", {}) if isinstance(data, dict) else {}
        meta = data.get("meta", {}) if isinstance(data, dict) else {}
        return {
            "slot": slot,
            "empty": False,
            "level": int(player.get("level", 1)),
            "gold": int(player.get("gold", 0)),
            "location": str(player.get("location", "Town")),
            "created_at": str(meta.get("created_at") or "Unknown"),
            "last_played": str(meta.get("last_played") or "Unknown"),
        }

    def slot_summaries(self) -> list[dict]:
        return [self.slot_summary(idx) for idx in range(1, MAX_SAVE_SLOTS + 1)]

    def _slot_numbers(self, max_slots: Optional[int] = None) -> list[int]:
        limit = max(1, min(MAX_SAVE_SLOTS, int(max_slots or MAX_SAVE_SLOTS)))
        slots = []
        try:
            for entry in os.listdir(self._base_dir):
                if not entry.startswith("slot") or not entry.endswith(".json"):
                    continue
                raw = entry[len("slot"):-len(".json")]
                if not raw.isdigit():
                    continue
                slot = int(raw)
                if 1 <= slot <= limit:
                    slots.append(slot)
        except OSError:
            return []
        return sorted(set(slots))

    def _parse_timestamp(self, value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError:
            return None

    def slot_summaries_sorted(self, max_slots: Optional[int] = None, include_empty: bool = False) -> list[dict]:
        limit = max(1, min(MAX_SAVE_SLOTS, int(max_slots or MAX_SAVE_SLOTS)))
        if include_empty:
            slots = list(range(1, limit + 1))
        else:
            slots = self._slot_numbers(limit)
        summaries = [self.slot_summary(slot) for slot in slots]

        def sort_key(summary: dict) -> tuple[int, float]:
            if summary.get("empty"):
                return (0, 0.0)
            last_played = self._parse_timestamp(str(summary.get("last_played") or ""))
            if last_played:
                return (1, last_played.timestamp())
            path = self._slot_path(int(summary.get("slot", 0) or 0))
            try:
                return (1, os.path.getmtime(path))
            except OSError:
                return (1, 0.0)

        summaries.sort(key=sort_key, reverse=True)
        return summaries

    def next_empty_slot(self, max_slots: Optional[int] = None) -> Optional[int]:
        limit = max(1, min(MAX_SAVE_SLOTS, int(max_slots or MAX_SAVE_SLOTS)))
        for slot in range(1, limit + 1):
            if not self.exists(slot):
                return slot
        return None
