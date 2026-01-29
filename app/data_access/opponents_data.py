"""Load and spawn opponent data from JSON."""

import json
import random
from typing import Dict, List, Optional

from app.models import Opponent


class OpponentsData:
    def __init__(self, path: str):
        self._path = path
        self._opponents: Dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._opponents = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._opponents = {}

    def all(self) -> Dict[str, dict]:
        return self._opponents

    def get(self, key: str, default: Optional[dict] = None) -> dict:
        if default is None:
            default = {}
        return self._opponents.get(key, default)

    def list_descriptions(self) -> List[str]:
        lines = []
        for data in self._opponents.values():
            name = data.get("name", "Unknown")
            desc = data.get("desc", "")
            lines.append(f"{name}: {desc}")
        return lines

    def create(self, data: dict, art_color: str) -> Opponent:
        name = data.get("name", "Slime")
        level = int(data.get("level", 1))
        hp = int(data.get("hp", 10))
        atk = int(data.get("atk", 5))
        defense = int(data.get("defense", 5))
        action_chance = float(data.get("action_chance", 1.0))
        art_lines = data.get("art", [])
        color_map = data.get("color_map", [])
        arrival = data.get("arrival", "appears")
        variation = data.get("variation", 0.0)
        jitter_stability = data.get("jitter_stability", True)
        return Opponent(
            name=name,
            level=level,
            hp=hp,
            max_hp=hp,
            atk=atk,
            defense=defense,
            stunned_turns=0,
            action_chance=action_chance,
            melted=False,
            art_lines=art_lines,
            art_color=art_color,
            color_map=color_map,
            arrival=arrival,
            variation=variation,
            jitter_stability=bool(jitter_stability)
        )

    def spawn(
        self,
        player_level: int,
        art_color: str
    ) -> List[Opponent]:
        if not self._opponents:
            return []
        candidates = list(self._opponents.values())
        total_level = 0
        spawned = []
        attempts = 0
        while len(spawned) < 3 and attempts < 10:
            attempts += 1
            remaining = max(1, player_level - total_level)
            choices = [
                m for m in candidates
                if int(m.get("level", 1)) <= remaining
            ]
            if not choices:
                break
            data = random.choice(choices)
            spawned.append(self.create(data, art_color))
            total_level += int(data.get("level", 1))
            if total_level >= player_level:
                break
        if not spawned:
            spawned.append(self.create(candidates[0], art_color))
        return spawned
