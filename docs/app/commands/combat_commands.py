import random

from app.combat import add_loot, primary_opponent, roll_damage
from app.commands.registry import CommandRegistry, CommandContext


def register(registry: CommandRegistry):
    registry.register("ATTACK", _handle_attack)


def _handle_attack(ctx: CommandContext) -> str:
    opponent = None
    if ctx.target_index is not None and 0 <= ctx.target_index < len(ctx.opponents):
        candidate = ctx.opponents[ctx.target_index]
        if candidate.hp > 0:
            opponent = candidate
    if opponent is None:
        opponent = primary_opponent(ctx.opponents)
    if not opponent:
        return "There is nothing to attack."
    damage, crit, miss = roll_damage(ctx.player.atk, opponent.defense)
    if miss:
        return f"You miss the {opponent.name}."
    opponent.hp = max(0, opponent.hp - damage)
    if opponent.hp == 0:
        xp_gain = random.randint(opponent.max_hp // 2, opponent.max_hp)
        gold_gain = random.randint(opponent.max_hp // 2, opponent.max_hp)
        add_loot(ctx.loot, xp_gain, gold_gain)
        opponent.melted = False
        return f"You strike down the {opponent.name}."
    if crit:
        return f"Critical hit! You hit the {opponent.name} for {damage}."
    return f"You hit the {opponent.name} for {damage}."
