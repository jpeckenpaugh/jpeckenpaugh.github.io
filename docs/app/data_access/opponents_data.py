"""Load and spawn opponent data from JSON."""

import json
import random
from typing import Dict, List, Optional

from app.models import Opponent


class OpponentsData:
    def __init__(self, path: str):
        self._path = path
        self._opponents: Dict[str, dict] = {}
        self._variants: Dict[str, dict] = {}
        self.load()

    def load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict) and "base_opponents" in data:
            self._opponents = data.get("base_opponents", {}) or {}
            self._variants = data.get("element_variants", {}) or {}
        else:
            self._opponents = data if isinstance(data, dict) else {}
            self._variants = {}

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

    def _variant_meta(self) -> dict:
        return self._variants.get("meta", {}) if isinstance(self._variants, dict) else {}

    def _variant_names(self) -> dict:
        return self._variants.get("names", {}) if isinstance(self._variants, dict) else {}

    def _variant_desc(self) -> dict:
        return self._variants.get("descriptions", {}) if isinstance(self._variants, dict) else {}

    def _colorize_map(self, color_map: dict, element: str) -> dict:
        if not isinstance(color_map, dict):
            return color_map
        meta = self._variant_meta()
        palette = meta.get("color_palettes", {}).get(element) if isinstance(meta, dict) else None
        # palette can be injected later; if missing, keep placeholders
        if not isinstance(palette, dict):
            return color_map
        mapped = {}
        for key, value in color_map.items():
            if str(value) in ("1", "2", "3"):
                mapped[key] = palette.get(str(value), value)
            else:
                mapped[key] = value
        return mapped

    def build_variant(self, base_id: str, element: str) -> dict:
        base = dict(self._opponents.get(base_id, {}))
        if not base:
            return {}
        meta = self._variant_meta()
        level_offsets = meta.get("level_offsets", {})
        multipliers = meta.get("stat_multipliers", {})
        offset = int(level_offsets.get(element, 0) or 0)
        mult = multipliers.get(element, {}) if isinstance(multipliers, dict) else {}
        hp_mult = float(mult.get("hp", 1.0) or 1.0)
        atk_mult = float(mult.get("atk", 1.0) or 1.0)
        def_mult = float(mult.get("defense", 1.0) or 1.0)
        spd_mult = float(mult.get("speed", 1.0) or 1.0)
        base["level"] = int(base.get("level", 1)) + offset
        base["hp"] = max(1, int(int(base.get("hp", 1)) * hp_mult))
        base["atk"] = max(1, int(int(base.get("atk", 1)) * atk_mult))
        base["defense"] = max(0, int(int(base.get("defense", 0)) * def_mult))
        base["action_chance"] = float(base.get("action_chance", 1.0)) * spd_mult
        base["element"] = element
        key = f"{base_id}_{element}"
        names = self._variant_names()
        descs = self._variant_desc()
        if key in names:
            base["name"] = names[key]
        if key in descs:
            base["desc"] = descs[key]
        return base

    def create(self, data: dict, art_color: str) -> Opponent:
        name = data.get("name", "Slime")
        element = data.get("element", "base")
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
        if element and self._variants:
            color_map = self._colorize_map(color_map, element)
        return Opponent(
            name=name,
            element=element,
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
        art_color: str,
        element: str = "base"
    ) -> List[Opponent]:
        if not self._opponents:
            return []
        base_ids = list(self._opponents.keys())
        candidates = [self.build_variant(base_id, element) for base_id in base_ids]
        candidates = [c for c in candidates if c]
        if not candidates:
            candidates = [self.build_variant(base_id, "base") for base_id in base_ids]
            candidates = [c for c in candidates if c]
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
