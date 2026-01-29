from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Frame:
    title: str
    body_lines: List[str]
    action_lines: List[str]
    stat_lines: List[str]
    footer_hint: str  # shows available keys
    location: str
    art_lines: List[str]
    art_color: str
    status_lines: List[str]
    art_anchor_x: Optional[int] = None


@dataclass
class Player:
    name: str
    level: int
    xp: int
    stat_points: int
    gold: int
    battle_speed: str
    hp: int
    max_hp: int
    mp: int
    max_mp: int
    atk: int
    defense: int
    location: str
    inventory: dict

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "level": self.level,
            "xp": self.xp,
            "stat_points": self.stat_points,
            "gold": self.gold,
            "battle_speed": self.battle_speed,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "mp": self.mp,
            "max_mp": self.max_mp,
            "atk": self.atk,
            "defense": self.defense,
            "location": self.location,
            "inventory": self.inventory,
        }

    @staticmethod
    def from_dict(data: dict) -> "Player":
        return Player(
            name=data.get("name", "WARRIOR"),
            level=int(data.get("level", 1)),
            xp=int(data.get("xp", 0)),
            stat_points=int(data.get("stat_points", 0)),
            gold=int(data.get("gold", 10)),
            battle_speed=data.get("battle_speed", "normal"),
            hp=int(data.get("hp", 10)),
            max_hp=int(data.get("max_hp", 10)),
            mp=int(data.get("mp", 10)),
            max_mp=int(data.get("max_mp", 10)),
            atk=int(data.get("atk", 10)),
            defense=int(data.get("defense", 10)),
            location="Town",
            inventory=data.get("inventory", {}),
        )

    def add_item(self, key: str, amount: int = 1):
        self.inventory[key] = int(self.inventory.get(key, 0)) + amount

    def format_inventory(self, items_data) -> str:
        if not self.inventory:
            return "Inventory is empty."
        parts = []
        for key, count in self.inventory.items():
            item = items_data.get(key, {"name": key})
            parts.append(f"{item.get('name', key)} x{count}")
        return "Inventory: " + ", ".join(parts)

    def list_inventory_items(self, items_data) -> List[tuple[str, str]]:
        entries = []
        for key in sorted(self.inventory.keys()):
            count = int(self.inventory.get(key, 0))
            if count <= 0:
                continue
            item = items_data.get(key, {"name": key})
            name = item.get("name", key)
            hp = int(item.get("hp", 0))
            mp = int(item.get("mp", 0))
            entries.append((key, f"{name} x{count} (+{hp} HP/+{mp} MP)"))
        return entries

    def use_item(self, key: str, items_data) -> str:
        item = items_data.get(key)
        if not item:
            return "That item is not available."
        if int(self.inventory.get(key, 0)) <= 0:
            return "You do not have that item."
        if self.hp == self.max_hp and self.mp == self.max_mp:
            return "HP and MP are already full."
        hp_gain = int(item.get("hp", 0))
        mp_gain = int(item.get("mp", 0))
        self.hp = min(self.max_hp, self.hp + hp_gain)
        self.mp = min(self.max_mp, self.mp + mp_gain)
        self.inventory[key] = int(self.inventory.get(key, 0)) - 1
        if self.inventory[key] <= 0:
            self.inventory.pop(key, None)
        return f"Used {item.get('name', key)}."

    def gain_xp(self, amount: int) -> int:
        self.xp += amount
        levels_gained = 0
        while self.xp >= self.level * 50:
            self.level += 1
            self.stat_points += 10
            levels_gained += 1
        return levels_gained

    def needs_level_up(self) -> bool:
        return self.stat_points > 0

    def apply_stat_point(self, stat: str):
        if stat == "HP":
            self.max_hp += 1
            self.hp += 1
        elif stat == "MP":
            self.max_mp += 1
            self.mp += 1
        elif stat == "ATK":
            self.atk += 1
        elif stat == "DEF":
            self.defense += 1

    def spend_stat_point(self, stat: str) -> bool:
        if self.stat_points <= 0:
            return False
        self.stat_points -= 1
        self.apply_stat_point(stat)
        return True

    def allocate_balanced(self):
        points = self.stat_points
        if points <= 0:
            return
        per_stat = points // 4
        remainder = points % 4
        if per_stat > 0:
            self.max_hp += per_stat
            self.hp += per_stat
            self.max_mp += per_stat
            self.mp += per_stat
            self.atk += per_stat
            self.defense += per_stat
        for stat in ["HP", "MP", "ATK", "DEF"][:remainder]:
            self.apply_stat_point(stat)
        self.stat_points = 0

    def allocate_random(self):
        import random
        stats = ["HP", "MP", "ATK", "DEF"]
        while self.stat_points > 0:
            self.apply_stat_point(random.choice(stats))
            self.stat_points -= 1

    def finish_level_up(self):
        self.hp = self.max_hp
        self.mp = self.max_mp

    def handle_level_up_input(self, cmd: str) -> Tuple[str, bool]:
        if cmd == "B_KEY":
            self.allocate_balanced()
            message = "Balanced allocation complete."
        elif cmd == "X_KEY":
            self.allocate_random()
            message = "Random allocation complete."
        elif cmd in ("NUM1", "NUM2", "NUM3", "NUM4"):
            if self.stat_points <= 0:
                message = "No stat points to spend."
            else:
                if cmd == "NUM1":
                    self.spend_stat_point("HP")
                    message = "HP increased by 1."
                elif cmd == "NUM2":
                    self.spend_stat_point("MP")
                    message = "MP increased by 1."
                elif cmd == "NUM3":
                    self.spend_stat_point("ATK")
                    message = "ATK increased by 1."
                else:
                    self.spend_stat_point("DEF")
                    message = "DEF increased by 1."
        else:
            return "Spend all stat points to continue.", False

        if self.stat_points == 0:
            self.finish_level_up()
            return "Level up complete.", True
        return message, False


@dataclass
class Opponent:
    name: str
    level: int
    hp: int
    max_hp: int
    atk: int
    defense: int
    stunned_turns: int
    action_chance: float
    melted: bool
    art_lines: List[str]
    art_color: str
    color_map: List[str]
    arrival: str
    variation: float = 0.0
    jitter_stability: bool = True
