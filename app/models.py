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
    location_gradient: Optional[Tuple[int, int, int, int, int, int]] = None


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
    gear_inventory: List[dict]
    equipment: dict
    gear_atk: int
    gear_defense: int
    elements: List[str]
    current_element: str
    temp_atk_bonus: int = 0
    temp_def_bonus: int = 0
    temp_hp_bonus: int = 0

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
            "gear_inventory": self.gear_inventory,
            "equipment": self.equipment,
            "gear_atk": self.gear_atk,
            "gear_defense": self.gear_defense,
            "elements": list(self.elements),
            "current_element": self.current_element,
        }

    @staticmethod
    def from_dict(data: dict) -> "Player":
        elements = data.get("elements")
        if not isinstance(elements, list):
            elements = []
        if not elements:
            elements = ["base"]
        order = ["base", "earth", "wind", "fire", "water", "light", "lightning", "dark", "ice"]
        elements = [e for e in order if e in elements] or elements
        current_element = data.get("current_element", "base")
        if current_element not in elements:
            current_element = elements[0]
        equipment = data.get("equipment", {})
        if not isinstance(equipment, dict):
            equipment = {}
        gear_inventory = data.get("gear_inventory", [])
        if not isinstance(gear_inventory, list):
            gear_inventory = []
        return Player(
            name=data.get("name", "WARRIOR"),
            level=int(data.get("level", 1)),
            xp=int(data.get("xp", 0)),
            stat_points=int(data.get("stat_points", 0)),
            gold=int(data.get("gold", 10)),
            battle_speed=data.get("battle_speed", "normal"),
            hp=int(data.get("hp", 50)),
            max_hp=int(data.get("max_hp", 50)),
            mp=int(data.get("mp", 10)),
            max_mp=int(data.get("max_mp", 10)),
            atk=int(data.get("atk", 5)),
            defense=int(data.get("defense", 5)),
            location="Town",
            inventory=data.get("inventory", {}),
            gear_inventory=gear_inventory,
            equipment=equipment,
            gear_atk=int(data.get("gear_atk", 0)),
            gear_defense=int(data.get("gear_defense", 0)),
            elements=elements,
            current_element=current_element,
            temp_atk_bonus=0,
            temp_def_bonus=0,
            temp_hp_bonus=0,
        )

    def add_item(self, key: str, amount: int = 1):
        self.inventory[key] = int(self.inventory.get(key, 0)) + amount

    def add_gear(self, item_id: str, items_data) -> dict:
        gear = self._create_gear_instance(item_id, items_data)
        self.gear_inventory.append(gear)
        self.auto_equip_if_best(gear.get("id"))
        return gear

    def _next_gear_id(self) -> str:
        current = 0
        for gear in self.gear_inventory:
            if not isinstance(gear, dict):
                continue
            gear_id = str(gear.get("id", ""))
            if gear_id.startswith("g") and gear_id[1:].isdigit():
                current = max(current, int(gear_id[1:]))
        return f"g{current + 1}"

    def _normalize_elem_points(self, elem_points: Optional[dict]) -> dict:
        output = {}
        if not isinstance(elem_points, dict):
            return output
        for key, value in elem_points.items():
            try:
                output[str(key)] = max(0, int(value))
            except (TypeError, ValueError):
                continue
        return output

    def _charges_from_points(self, elem_points: dict) -> dict:
        charges = {}
        for element, points in elem_points.items():
            value = max(0, int(points))
            if value > 0:
                charges[element] = max(1, value // 3)
            else:
                charges[element] = 0
        return charges

    def _fusion_rank(self, gear: Optional[dict]) -> int:
        if not isinstance(gear, dict):
            return 0
        try:
            return int(gear.get("fuse_rank", 0))
        except (TypeError, ValueError):
            return 0

    def _fusion_base_name(self, name: str) -> str:
        if not name:
            return "Gear"
        prefixes = (
            "Fused ",
            "Empowered ",
            "Mythic ",
            "Legendary ",
            "Godly ",
            "Omnipotent ",
        )
        for prefix in prefixes:
            if name.startswith(prefix):
                return name[len(prefix):].strip() or "Gear"
        return name

    def _create_gear_instance(self, item_id: str, items_data, overrides: Optional[dict] = None) -> dict:
        item = items_data.get(item_id, {})
        elem_points = self._normalize_elem_points(item.get("elem_points"))
        if not elem_points:
            element = item.get("element")
            if element:
                elem_points = {str(element): 1}
        instance = {
            "id": self._next_gear_id(),
            "item_id": item_id,
            "name": item.get("name", item_id),
            "slot": item.get("slot", ""),
            "atk": int(item.get("atk", 0)),
            "defense": int(item.get("defense", 0)),
            "elem_points": elem_points,
            "price": int(item.get("price", 0)),
        }
        if overrides:
            instance.update(overrides)
        if instance.get("slot") == "wand":
            charges = self._charges_from_points(instance.get("elem_points", {}))
            instance["charges"] = charges.copy()
            instance["max_charges"] = charges.copy()
        return instance

    def gear_instance(self, gear_id: str) -> Optional[dict]:
        for gear in self.gear_inventory:
            if isinstance(gear, dict) and gear.get("id") == gear_id:
                return gear
        return None

    def equip_gear(self, gear_id: str) -> str:
        gear = self.gear_instance(gear_id)
        if not gear:
            return "That gear is not available."
        slot = gear.get("slot")
        if not slot:
            return "That item cannot be equipped."
        if self.equipment.get(slot) == gear_id:
            self.equipment.pop(slot, None)
            self._recalc_gear()
            return f"Unequipped {gear.get('name', 'gear')}."
        self.equipment[slot] = gear_id
        self._recalc_gear()
        return f"Equipped {gear.get('name', 'gear')}."

    def _gear_score(self, gear: dict) -> int:
        if not isinstance(gear, dict):
            return 0
        atk = int(gear.get("atk", 0))
        defense = int(gear.get("defense", 0))
        elem_points = self._normalize_elem_points(gear.get("elem_points", {}))
        elem_total = sum(int(value) for value in elem_points.values())
        return atk + defense + elem_total

    def auto_equip_if_best(self, gear_id: Optional[str]) -> bool:
        if not gear_id:
            return False
        gear = self.gear_instance(str(gear_id))
        if not gear:
            return False
        slot = gear.get("slot")
        if not slot:
            return False
        if not isinstance(self.equipment, dict):
            self.equipment = {}
        current_id = self.equipment.get(slot)
        current = self.gear_instance(current_id) if current_id else None
        new_score = self._gear_score(gear)
        current_score = self._gear_score(current) if current else -1
        if current and new_score < current_score:
            return False
        self.equipment[slot] = gear.get("id")
        self._recalc_gear()
        return True

    def total_atk(self) -> int:
        return self.atk + int(self.gear_atk) + int(self.temp_atk_bonus)

    def total_defense(self) -> int:
        return self.defense + int(self.gear_defense) + int(self.temp_def_bonus)

    def total_max_hp(self) -> int:
        return self.max_hp + int(self.temp_hp_bonus)

    def _recalc_gear(self) -> None:
        atk_bonus = 0
        def_bonus = 0
        equipment = self.equipment if isinstance(self.equipment, dict) else {}
        for slot, gear_id in equipment.items():
            gear = self.gear_instance(gear_id)
            if not gear:
                continue
            if gear.get("slot") != slot:
                continue
            atk_bonus += int(gear.get("atk", 0))
            def_bonus += int(gear.get("defense", 0))
        self.gear_atk = atk_bonus
        self.gear_defense = def_bonus

    def sync_items(self, items_data) -> None:
        if not isinstance(self.equipment, dict):
            self.equipment = {}
        if not isinstance(self.inventory, dict):
            self.inventory = {}
        if not isinstance(self.gear_inventory, list):
            self.gear_inventory = []
        migrated = []
        for item_id, count in list(self.inventory.items()):
            item = items_data.get(item_id, {})
            if item.get("type") != "gear":
                continue
            count_int = int(count)
            if count_int <= 0:
                continue
            for _ in range(count_int):
                migrated.append(self._create_gear_instance(item_id, items_data))
            self.inventory.pop(item_id, None)
        self.gear_inventory.extend(migrated)
        for gear in self.gear_inventory:
            if not isinstance(gear, dict):
                continue
            if gear.get("slot") != "wand":
                continue
            if not isinstance(gear.get("charges"), dict):
                points = self._normalize_elem_points(gear.get("elem_points", {}))
                charges = self._charges_from_points(points)
                gear["charges"] = charges.copy()
                gear["max_charges"] = charges.copy()
        cleaned = {}
        for slot, gear_id in self.equipment.items():
            if isinstance(gear_id, str) and gear_id.startswith("g"):
                gear = self.gear_instance(gear_id)
                if gear and gear.get("slot") == slot:
                    cleaned[slot] = gear_id
                    continue
            item = items_data.get(str(gear_id), {})
            if item.get("type") == "gear" and item.get("slot") == slot:
                gear = self._create_gear_instance(str(gear_id), items_data)
                self.gear_inventory.append(gear)
                cleaned[slot] = gear.get("id")
        self.equipment = cleaned
        self._recalc_gear()

    def format_inventory(self, items_data) -> str:
        if not self.inventory:
            if not self.gear_inventory:
                return "Inventory is empty."
        parts = []
        for key, count in self.inventory.items():
            item = items_data.get(key, {"name": key})
            parts.append(f"{item.get('name', key)} x{count}")
        if self.gear_inventory:
            parts.append(f"Gear x{len(self.gear_inventory)}")
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
            entries.append((f"item:{key}", f"{name} x{count} (+{hp} HP/+{mp} MP)"))
        for gear in self.gear_inventory:
            if not isinstance(gear, dict):
                continue
            gear_id = gear.get("id", "")
            name = gear.get("name", "Gear")
            slot = gear.get("slot", "")
            atk = int(gear.get("atk", 0))
            defense = int(gear.get("defense", 0))
            elem_points = gear.get("elem_points", {})
            elem_total = sum(int(v) for v in elem_points.values()) if isinstance(elem_points, dict) else 0
            bonus = []
            if atk:
                bonus.append(f"ATK+{atk}")
            if defense:
                bonus.append(f"DEF+{defense}")
            if elem_total:
                bonus.append(f"Elem+{elem_total}")
            detail = ", ".join(bonus) if bonus else "No bonuses"
            slot_text = slot.title() if slot else "Gear"
            equipped = " (equipped)" if self.equipment.get(slot) == gear_id else ""
            entries.append((f"gear:{gear_id}", f"{name} ({slot_text} {detail}){equipped}"))
        return entries

    def use_item(self, key: str, items_data) -> str:
        if key.startswith("gear:"):
            gear_id = key.split(":", 1)[1]
            return self.equip_gear(gear_id)
        if key.startswith("item:"):
            key = key.split(":", 1)[1]
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

    def gear_points_by_slot(self, slot: str) -> dict:
        gear_id = self.equipment.get(slot)
        if not gear_id:
            return {}
        gear = self.gear_instance(gear_id)
        if not gear:
            return {}
        return self._normalize_elem_points(gear.get("elem_points", {}))

    def element_points_total(self, element: str, slots: Optional[List[str]] = None) -> int:
        total = 0
        if slots is None:
            slots = list(self.equipment.keys())
        for slot in slots:
            points = self.gear_points_by_slot(slot)
            total += int(points.get(element, 0))
        return total

    def wand_charges(self) -> dict:
        gear_id = self.equipment.get("wand")
        if not gear_id:
            return {}
        gear = self.gear_instance(gear_id)
        if not gear:
            return {}
        charges = gear.get("charges", {})
        return charges if isinstance(charges, dict) else {}

    def consume_wand_charge(self, element: str) -> bool:
        gear_id = self.equipment.get("wand")
        if not gear_id:
            return False
        gear = self.gear_instance(gear_id)
        if not gear:
            return False
        charges = gear.get("charges", {})
        if not isinstance(charges, dict):
            return False
        current = int(charges.get(element, 0))
        if current <= 0:
            return False
        charges[element] = current - 1
        gear["charges"] = charges
        return True

    def recharge_wands(self, overcharge: bool = False) -> None:
        gear_id = self.equipment.get("wand")
        if not gear_id:
            return
        gear = self.gear_instance(gear_id)
        if not gear:
            return
        points = self._normalize_elem_points(gear.get("elem_points", {}))
        max_charges = self._charges_from_points(points)
        if overcharge:
            charges = {k: int(v * 1.5) for k, v in max_charges.items()}
        else:
            charges = dict(max_charges)
        gear["charges"] = charges
        gear["max_charges"] = max_charges

    def fuse_gear(self, gear_a: str, gear_b: str) -> Optional[dict]:
        first = self.gear_instance(gear_a)
        second = self.gear_instance(gear_b)
        if not first or not second:
            return None
        rank = max(self._fusion_rank(first), self._fusion_rank(second)) + 1
        ranks = ["Fused", "Empowered", "Mythic", "Legendary", "Godly", "Omnipotent"]
        title = ranks[min(rank - 1, len(ranks) - 1)]
        base_name = self._fusion_base_name(first.get("name", "Gear"))
        merged_points = {}
        for points in (first.get("elem_points", {}), second.get("elem_points", {})):
            if not isinstance(points, dict):
                continue
            for element, value in points.items():
                merged_points[element] = int(merged_points.get(element, 0)) + int(value)
        fused = {
            "id": self._next_gear_id(),
            "item_id": first.get("item_id") or second.get("item_id"),
            "name": f"{title} {base_name}",
            "slot": first.get("slot") or second.get("slot"),
            "atk": int(first.get("atk", 0)) + int(second.get("atk", 0)),
            "defense": int(first.get("defense", 0)) + int(second.get("defense", 0)),
            "elem_points": merged_points,
            "price": int(first.get("price", 0)) + int(second.get("price", 0)),
            "fuse_rank": rank,
        }
        if fused.get("slot") == "wand":
            charges = self._charges_from_points(merged_points)
            fused["charges"] = charges.copy()
            fused["max_charges"] = charges.copy()
        self.gear_inventory = [
            gear for gear in self.gear_inventory
            if not (isinstance(gear, dict) and gear.get("id") in {gear_a, gear_b})
        ]
        for slot, gear_id in list(self.equipment.items()):
            if gear_id in {gear_a, gear_b}:
                self.equipment.pop(slot, None)
        self.gear_inventory.append(fused)
        self._recalc_gear()
        self.auto_equip_if_best(fused.get("id"))
        return fused

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
        elif cmd == "BANK":
            self.finish_level_up()
            return "Stat points banked.", True
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
    element: str
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
