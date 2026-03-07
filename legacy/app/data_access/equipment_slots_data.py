"""Load and query equipment slot rules from JSON."""

import json
from typing import Dict, List, Optional


class EquipmentSlotsData:
    def __init__(self, path: str):
        self._path = path
        self._data: Dict[str, object] = {}
        self.load()

    def load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def all(self) -> Dict[str, object]:
        return self._data

    def slots(self) -> List[dict]:
        slots = self._data.get("slots", [])
        return slots if isinstance(slots, list) else []

    def order(self) -> List[str]:
        order = self._data.get("order", [])
        return order if isinstance(order, list) else []

    def slot_meta(self, slot_id: str) -> dict:
        slot_id = str(slot_id or "")
        for slot in self.slots():
            if isinstance(slot, dict) and str(slot.get("id", "")) == slot_id:
                return slot
        return {}

    def slot_label(self, slot_id: str) -> str:
        meta = self.slot_meta(slot_id)
        label = str(meta.get("label", "") or "").strip()
        return label or slot_id.title()

    def slot_hand(self, slot_id: str) -> str:
        meta = self.slot_meta(slot_id)
        return str(meta.get("hand", "") or "")

    def slot_requires_flag(self, slot_id: str) -> str:
        meta = self.slot_meta(slot_id)
        return str(meta.get("requires_flag", "") or "")
