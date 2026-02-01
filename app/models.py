from dataclasses import dataclass, field
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
    raw_lines: Optional[List[str]] = None
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
    followers: List[dict] = field(default_factory=list)
    temp_atk_bonus: int = 0
    temp_def_bonus: int = 0
    temp_hp_bonus: int = 0
    flags: dict = field(default_factory=dict)
    quests: dict = field(default_factory=dict)

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
            "followers": self.followers,
            "flags": self.flags,
            "quests": self.quests,
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
        followers = data.get("followers", [])
        if not isinstance(followers, list):
            followers = []
        flags = data.get("flags", {})
        if not isinstance(flags, dict):
            flags = {}
        quests = data.get("quests", {})
        if not isinstance(quests, dict):
            quests = {}
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
            followers=followers,
            temp_atk_bonus=0,
            temp_def_bonus=0,
            temp_hp_bonus=0,
            flags=flags,
            quests=quests,
        )

    def add_item(self, key: str, amount: int = 1):
        self.inventory[key] = int(self.inventory.get(key, 0)) + amount

    def add_gear(self, item_id: str, items_data, *, auto_equip: bool = True) -> dict:
        gear = self._create_gear_instance(item_id, items_data)
        self.gear_inventory.append(gear)
        if auto_equip:
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

    def follower_limit(self) -> int:
        base_limit = 5
        if isinstance(getattr(self, "quests", None), dict):
            qstate = self.quests.get("intro_spellcraft")
            if isinstance(qstate, dict) and qstate.get("status") == "active":
                if not self.flags.get("quest_intro_spellcraft_complete", False):
                    return 3
        return base_limit

    def follower_slots_remaining(self) -> int:
        return max(0, self.follower_limit() - len(self.followers))

    def add_follower(self, follower: dict) -> bool:
        if self.follower_slots_remaining() <= 0:
            return False
        if not isinstance(self.followers, list):
            self.followers = []
        self._ensure_follower_id(follower)
        self.followers.append(follower)
        return True

    def _next_follower_id(self) -> str:
        current = 0
        for follower in self.followers:
            if not isinstance(follower, dict):
                continue
            follower_id = str(follower.get("id", ""))
            if follower_id.startswith("f") and follower_id[1:].isdigit():
                current = max(current, int(follower_id[1:]))
        return f"f{current + 1}"

    def _ensure_follower_id(self, follower: dict) -> None:
        if not isinstance(follower, dict):
            return
        if follower.get("id"):
            return
        follower["id"] = self._next_follower_id()

    def follower_by_id(self, follower_id: str) -> Optional[dict]:
        if not follower_id:
            return None
        for follower in self.followers:
            if isinstance(follower, dict) and follower.get("id") == follower_id:
                return follower
        return None

    def gear_owner(self, gear_id: str) -> tuple[Optional[str], Optional[str]]:
        if not gear_id:
            return None, None
        gear = self.gear_instance(gear_id)
        slot = gear.get("slot") if isinstance(gear, dict) else ""
        if slot and self.equipment.get(slot) == gear_id:
            return "player", None
        for follower in self.followers:
            if not isinstance(follower, dict):
                continue
            equip = follower.get("equipment", {})
            if not isinstance(equip, dict):
                continue
            if gear_id in equip.values():
                return "follower", str(follower.get("id", ""))
        return None, None

    def gear_owner_label(self, gear_id: str) -> str:
        if not gear_id:
            return ""
        gear = self.gear_instance(gear_id)
        slot = gear.get("slot") if isinstance(gear, dict) else ""
        if slot and self.equipment.get(slot) == gear_id:
            return "Player"
        for follower in self.followers:
            if not isinstance(follower, dict):
                continue
            equipment = follower.get("equipment", {})
            if not isinstance(equipment, dict):
                continue
            if gear_id in equipment.values():
                return follower.get("name", "Follower")
        return ""

    def follower_equipment(self, follower: dict) -> dict:
        if not isinstance(follower, dict):
            return {}
        equipment = follower.get("equipment", {})
        if not isinstance(equipment, dict):
            equipment = {}
            follower["equipment"] = equipment
        return equipment

    def follower_gear_instance(self, follower: dict, slot: str) -> Optional[dict]:
        equipment = self.follower_equipment(follower)
        gear_id = equipment.get(slot)
        if not gear_id:
            return None
        return self.gear_instance(gear_id)

    def assign_gear_to_follower(self, follower: dict, gear_id: str) -> bool:
        if not isinstance(follower, dict) or not gear_id:
            return False
        gear = self.gear_instance(gear_id)
        if not gear:
            return False
        slot = gear.get("slot")
        if not slot:
            return False
        self._ensure_follower_id(follower)
        # remove from player equipment if needed
        for eq_slot, eq_id in list(self.equipment.items()):
            if eq_id == gear_id:
                self.equipment.pop(eq_slot, None)
        self._recalc_gear()
        # remove from other followers
        for other in self.followers:
            if not isinstance(other, dict):
                continue
            equip = self.follower_equipment(other)
            for eq_slot, eq_id in list(equip.items()):
                if eq_id == gear_id:
                    equip.pop(eq_slot, None)
        equip = self.follower_equipment(follower)
        equip[slot] = gear_id
        return True

    def unequip_follower_slot(self, follower: dict, slot: str) -> bool:
        if not isinstance(follower, dict):
            return False
        equip = self.follower_equipment(follower)
        if slot in equip:
            equip.pop(slot, None)
            return True
        return False

    def follower_total_atk(self, follower: dict) -> int:
        base = int(follower.get("atk", 2) or 2)
        temp = int(follower.get("temp_atk_bonus", 0) or 0)
        equip = self.follower_equipment(follower)
        bonus = 0
        for gear_id in equip.values():
            gear = self.gear_instance(gear_id)
            if not isinstance(gear, dict):
                continue
            bonus += int(gear.get("atk", 0) or 0)
        return base + bonus + temp

    def follower_total_defense(self, follower: dict) -> int:
        base = int(follower.get("defense", 1) or 1)
        temp = int(follower.get("temp_def_bonus", 0) or 0)
        equip = self.follower_equipment(follower)
        bonus = 0
        for gear_id in equip.values():
            gear = self.gear_instance(gear_id)
            if not isinstance(gear, dict):
                continue
            bonus += int(gear.get("defense", 0) or 0)
        return base + bonus + temp

    def follower_total_max_hp(self, follower: dict) -> int:
        base = int(follower.get("max_hp", 0) or 0)
        temp = int(follower.get("temp_hp_bonus", 0) or 0)
        return base + temp

    def team_missing_total(self, follower: Optional[dict] = None, *, mode: str = "combined") -> int:
        if follower is None:
            max_hp = self.total_max_hp()
            max_mp = int(self.max_mp)
            missing_hp = max_hp - int(self.hp)
            missing_mp = max_mp - int(self.mp)
        else:
            if not isinstance(follower, dict):
                return 0
            max_hp = self.follower_total_max_hp(follower)
            max_mp = int(follower.get("max_mp", 0) or 0)
            hp = int(follower.get("hp", max_hp) or max_hp)
            mp = int(follower.get("mp", max_mp) or max_mp)
            missing_hp = max(0, max_hp - hp)
            missing_mp = max(0, max_mp - mp)
        if mode == "hp":
            return missing_hp
        return missing_hp + missing_mp

    def select_team_target(self, *, mode: str = "combined") -> tuple[str, Optional[dict]]:
        candidates: list[tuple[str, Optional[dict], int]] = [("player", None, self.team_missing_total(mode=mode))]
        for follower in self.followers:
            if not isinstance(follower, dict):
                continue
            candidates.append(("follower", follower, self.team_missing_total(follower, mode=mode)))
        target_type, target_ref, missing = max(candidates, key=lambda entry: entry[2])
        if missing <= 0:
            return "none", None
        return target_type, target_ref

    def follower_element_points_total(self, follower: dict, element: str) -> int:
        total = 0
        equip = self.follower_equipment(follower)
        for gear_id in equip.values():
            gear = self.gear_instance(gear_id)
            if not isinstance(gear, dict):
                continue
            points = gear.get("elem_points", {})
            if not isinstance(points, dict):
                continue
            total += int(points.get(element, 0) or 0)
        return total

    def follower_wand_charges(self, follower: dict) -> dict:
        gear = self.follower_gear_instance(follower, "wand")
        if not gear:
            return {}
        charges = gear.get("charges", {})
        return charges if isinstance(charges, dict) else {}

    def consume_follower_wand_charge(self, follower: dict, element: str) -> bool:
        gear = self.follower_gear_instance(follower, "wand")
        if not gear:
            return False
        charges = gear.get("charges", {})
        if not isinstance(charges, dict):
            return False
        current = int(charges.get(element, 0) or 0)
        if current <= 0:
            return False
        charges[element] = current - 1
        gear["charges"] = charges
        return True

    def recharge_follower_wands(self) -> None:
        for follower in self.followers:
            if not isinstance(follower, dict):
                continue
            gear = self.follower_gear_instance(follower, "wand")
            if not gear:
                continue
            points = self._normalize_elem_points(gear.get("elem_points", {}))
            max_charges = self._charges_from_points(points)
            gear["charges"] = dict(max_charges)
            gear["max_charges"] = dict(max_charges)

    def restore_follower_mp(self) -> None:
        for follower in self.followers:
            if not isinstance(follower, dict):
                continue
            max_mp = int(follower.get("max_mp", 0) or 0)
            if max_mp > 0:
                follower["mp"] = max_mp

    def list_gear_items(self) -> List[tuple[str, str]]:
        entries: List[tuple[str, str]] = []
        for gear in self.gear_inventory:
            if not isinstance(gear, dict):
                continue
            gear_id = str(gear.get("id", ""))
            if not gear_id:
                continue
            name = gear.get("name", "Gear")
            slot = gear.get("slot", "")
            owner = self.gear_owner_label(gear_id)
            suffix = f" ({slot})" if slot else ""
            if owner:
                suffix += f" [{owner}]"
            entries.append((gear_id, f"{name}{suffix}"))
        return entries

    def fuse_followers(self, follower_type: str, count: int = 3) -> Optional[dict]:
        if count <= 0:
            return None
        if not isinstance(self.followers, list):
            return None
        matches = [idx for idx, follower in enumerate(self.followers) if isinstance(follower, dict) and follower.get("type") == follower_type]
        if len(matches) < count:
            return None
        remove_indices = set(matches[:count])
        kept_names = []
        kept = []
        for idx, follower in enumerate(self.followers):
            if idx in remove_indices:
                if isinstance(follower, dict):
                    kept_names.append(str(follower.get("name", "")))
                continue
            kept.append(follower)
        fused_type = follower_type
        if follower_type == "mushroom_baby":
            fused_type = "mushroom_teen"
        base_name = fused_type.replace("_", " ").title() or "Follower"
        abilities = []
        active = ""
        if fused_type == "fairy":
            abilities = ["fairy_heal", "fairy_mana"]
            active = "fairy_heal"
        if fused_type.startswith("mushroom"):
            abilities = ["mushroom_tea_brew"]
        fused_name = f"Fused {base_name}"
        if follower_type == "mushroom_baby":
            fused_name = "Mushroom Teen"
            if any(name == "Mushy" for name in kept_names):
                fused_name = "Mushy"
        fused = {
            "type": fused_type,
            "name": fused_name,
            "level": 1,
            "xp": 0,
            "max_level": 5,
            "hp": 14,
            "max_hp": 14,
            "mp": 6,
            "max_mp": 6,
            "abilities": abilities,
            "active_ability": active,
            "fusion_rank": 1,
            "equipment": {},
        }
        self._ensure_follower_id(fused)
        kept.append(fused)
        self.followers = kept
        return fused

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

    def use_item(self, key: str, items_data, *, target: Optional[dict] = None) -> str:
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
        hp_gain = int(item.get("hp", 0))
        mp_gain = int(item.get("mp", 0))
        if target is None:
            if self.hp == self.max_hp and self.mp == self.max_mp:
                return "HP and MP are already full."
            self.hp = min(self.max_hp, self.hp + hp_gain)
            self.mp = min(self.max_mp, self.mp + mp_gain)
        else:
            max_hp = int(target.get("max_hp", 0) or 0)
            max_mp = int(target.get("max_mp", 0) or 0)
            hp = int(target.get("hp", max_hp) or max_hp)
            mp = int(target.get("mp", max_mp) or max_mp)
            if hp >= max_hp and mp >= max_mp:
                return "That follower is already full."
            target["hp"] = min(max_hp, hp + hp_gain)
            target["mp"] = min(max_mp, mp + mp_gain)
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

    def fuse_gear(self, gear_a: str, gear_b: str, *, auto_equip: bool = True) -> Optional[dict]:
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
        for follower in self.followers:
            if not isinstance(follower, dict):
                continue
            equip = follower.get("equipment", {})
            if not isinstance(equip, dict):
                continue
            for slot, gear_id in list(equip.items()):
                if gear_id in {gear_a, gear_b}:
                    equip.pop(slot, None)
        self.gear_inventory.append(fused)
        self._recalc_gear()
        if auto_equip:
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
    recruitable: bool = False
    recruit_cost: int = 0
    recruit_chance: float = 0.0
    follower_type: str = ""
    follower_names: List[str] = field(default_factory=list)
    variation: float = 0.0
    jitter_stability: bool = True
    ai: Optional[dict] = None
