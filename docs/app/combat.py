"""Combat helpers for damage, targeting, and timing."""

import random
from typing import List, Optional, Tuple

from app.data_access.spells_data import SpellsData
from app.models import Player, Opponent


def roll_damage(attacker_atk: int, defender_def: int) -> Tuple[int, bool, bool]:
    crit = random.random() < 0.15
    miss = random.random() < 0.1
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
    spell_id: str,
    boosted: bool,
    loot: dict,
    spells_data: SpellsData,
    target_index: Optional[int] = None
) -> str:
    spell = spells_data.get(spell_id, {})
    name = spell.get("name", spell_id.title())
    mp_cost = int(spell.get("boosted_mp_cost", 4 if boosted else 2))
    if not boosted:
        mp_cost = int(spell.get("mp_cost", 2))
    if player.mp < mp_cost:
        return f"Not enough MP to cast {name}."

    if spell_id == "healing":
        if player.hp == player.max_hp:
            return "Your HP is already full."
        player.mp -= mp_cost
        heal_amount = int(spell.get("boosted_heal", 20 if boosted else 10))
        if not boosted:
            heal_amount = int(spell.get("heal", 10))
        heal = min(heal_amount, player.max_hp - player.hp)
        player.hp += heal
        return f"You cast {name} and restore {heal} HP."

    if spell_id == "spark":
        opponent = None
        if target_index is not None and 0 <= target_index < len(opponents):
            candidate = opponents[target_index]
            if candidate.hp > 0:
                opponent = candidate
        if opponent is None:
            opponent = primary_opponent(opponents)
        if not opponent:
            return "There is nothing to target."
        player.mp -= mp_cost
        atk_bonus = int(spell.get("atk_bonus", 2))
        damage, crit, miss = roll_damage(player.atk + atk_bonus, opponent.defense)
        if boosted:
            damage *= int(spell.get("boosted_multiplier", 2))
        if miss:
            return f"Your {name} misses the {opponent.name}."
        opponent.hp = max(0, opponent.hp - damage)
        if opponent.hp == 0:
            xp_gain = random.randint(opponent.max_hp // 2, opponent.max_hp)
            gold_gain = random.randint(opponent.max_hp // 2, opponent.max_hp)
            add_loot(loot, xp_gain, gold_gain)
            opponent.melted = False
            message = f"Your {name} fells the {opponent.name}."
            return message
        stun_chance = float(spell.get("boosted_stun_chance", 0.8 if boosted else 0.4))
        if not boosted:
            stun_chance = float(spell.get("stun_chance", 0.4))
        stunned_turns = try_stun(opponent, stun_chance)
        if crit:
            message = f"Critical {name}! You hit the {opponent.name} for {damage}."
        else:
            message = f"You hit the {opponent.name} with {name} for {damage}."
        if stunned_turns > 0:
            message += f" It is stunned for {stunned_turns} turn(s)."
        return message

    return f"{name} fizzles with no effect."
