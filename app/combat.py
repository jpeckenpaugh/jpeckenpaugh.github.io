"""Combat helpers for damage, targeting, and timing."""

import random
from typing import List, Optional, Tuple

from app.models import Player, Opponent


def roll_damage(
    attacker_atk: int,
    defender_def: int,
    miss_chance: float = 0.1,
    crit_chance: float = 0.15
) -> Tuple[int, bool, bool]:
    crit = random.random() < crit_chance
    miss = random.random() < miss_chance
    if miss:
        return 0, False, True
    base = max(1, attacker_atk - defender_def)
    if crit:
        base *= 2
    damage = random.randint(max(1, base // 2), base)
    return damage, crit, False


def try_stun(opponent: Opponent, chance: float) -> int:
    if random.random() < chance:
        turns = random.randint(1, 3)
        opponent.stunned_turns = max(opponent.stunned_turns, turns)
        return turns
    return 0


def primary_opponent(opponents: List[Opponent]) -> Optional[Opponent]:
    for opponent in opponents:
        if opponent.hp > 0:
            return opponent
    return None


def primary_opponent_index(opponents: List[Opponent]) -> Optional[int]:
    for idx, opponent in enumerate(opponents):
        if opponent.hp > 0:
            return idx
    return None


def battle_action_delay(player: Player) -> float:
    speeds = {
        "fast": 0.2,
        "normal": 0.45,
        "slow": 0.75,
    }
    return speeds.get(player.battle_speed, speeds["normal"])


def add_loot(loot: dict, xp: int, gold: int):
    loot["xp"] = loot.get("xp", 0) + xp
    loot["gold"] = loot.get("gold", 0) + gold


def cast_spell(
    player: Player,
    opponents: List[Opponent],
    spell: dict,
    effect: dict,
    loot: dict,
    target_index: Optional[int] = None,
    rank: int = 1
) -> str:
    name = spell.get("name", "Spell")
    mp_cost = int(spell.get("mp_cost", 2)) * max(1, rank)
    element = spell.get("element")
    used_charge = False
    if element:
        used_charge = player.consume_wand_charge(str(element))
    if not used_charge and player.mp < mp_cost:
        return f"Not enough MP to cast {name}."

    if effect.get("kind") == "damage":
        targets: List[Opponent] = []
        threshold = int(effect.get("rank_all_threshold", 2) or 2)
        if rank >= threshold:
            targets = [opp for opp in opponents if opp.hp > 0]
        else:
            opponent = None
            if target_index is not None and 0 <= target_index < len(opponents):
                candidate = opponents[target_index]
                if candidate.hp > 0:
                    opponent = candidate
            if opponent is None:
                opponent = primary_opponent(opponents)
            if opponent:
                targets = [opponent]
        if not targets:
            return "There is nothing to target."
        if not used_charge:
            player.mp -= mp_cost
        atk_bonus_key = str(effect.get("atk_bonus_key", "atk_bonus") or "atk_bonus")
        atk_bonus = int(spell.get(atk_bonus_key, 2))
        if element:
            ring_bonus = player.element_points_total(str(element), slots=["ring"])
            atk_bonus += int(ring_bonus)
        rank3_mult_key = str(effect.get("rank3_damage_mult_key", "rank3_damage_mult") or "rank3_damage_mult")
        damage_mult = float(spell.get(rank3_mult_key, 1.0)) if rank >= 3 else 1.0
        messages = []
        for opponent in targets:
            damage, crit, miss = roll_damage(player.total_atk() + atk_bonus, opponent.defense)
            damage = int(damage * damage_mult)
            if miss:
                messages.append(f"Your {name} misses the {opponent.name}.")
                continue
            opponent.hp = max(0, opponent.hp - damage)
            if opponent.hp == 0:
                xp_gain = random.randint(opponent.max_hp // 2, opponent.max_hp)
                gold_gain = random.randint(opponent.max_hp // 2, opponent.max_hp)
                add_loot(loot, xp_gain, gold_gain)
                opponent.melted = False
                messages.append(f"Your {name} fells the {opponent.name}.")
                continue
            stun_chance_key = str(effect.get("stun_chance_key", "stun_chance") or "stun_chance")
            stun_chance = float(spell.get(stun_chance_key, 0.0))
            if rank >= 3:
                rank3_stun_key = str(effect.get("rank3_stun_bonus_key", "rank3_stun_bonus") or "rank3_stun_bonus")
                stun_chance = min(0.95, stun_chance + float(spell.get(rank3_stun_key, 0.0)))
            stunned_turns = try_stun(opponent, stun_chance)
            if crit:
                message = f"Critical {name}! You hit the {opponent.name} for {damage}."
            else:
                message = f"You hit the {opponent.name} with {name} for {damage}."
            if stunned_turns > 0:
                message += f" It is stunned for {stunned_turns} turn(s)."
            messages.append(message)
        return " ".join(messages)

    return f"{name} fizzles with no effect."
