import random

from app.combat import add_loot, primary_opponent, roll_damage
from app.commands.registry import CommandRegistry, CommandContext
from app.questing import handle_event


def register(registry: CommandRegistry):
    registry.register("ATTACK", _handle_attack)
    registry.register("DEFEND", _handle_defend)
    registry.register("FLEE", _handle_flee)
    registry.register("SOCIALIZE", _handle_socialize)


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
    sword_points = ctx.player.gear_points_by_slot("sword")
    elem_bonus = sum(int(v) for v in sword_points.values()) if isinstance(sword_points, dict) else 0
    damage, crit, miss = roll_damage(ctx.player.total_atk() + elem_bonus, opponent.defense)
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


def _handle_defend(ctx: CommandContext) -> str:
    return "You brace for impact."


def _handle_flee(ctx: CommandContext) -> str:
    alive = [opp for opp in ctx.opponents if opp.hp > 0]
    if not alive:
        return "There is nothing to flee from."
    highest = max(opp.level for opp in alive)
    diff = ctx.player.level - highest
    chance = 0.5 + (diff * 0.08)
    chance = max(0.1, min(0.9, chance))
    if random.random() > chance:
        return "You fail to flee."
    ctx.opponents.clear()
    ctx.loot["xp"] = 0
    ctx.loot["gold"] = 0
    return "You flee to safety."


def _handle_socialize(ctx: CommandContext) -> str:
    opponent = None
    if ctx.target_index is not None and 0 <= ctx.target_index < len(ctx.opponents):
        candidate = ctx.opponents[ctx.target_index]
        if candidate.hp > 0:
            opponent = candidate
    if opponent is None:
        opponent = primary_opponent(ctx.opponents)
    if not opponent:
        return "There is no one to socialize with."
    recruit_only_types = None
    if isinstance(getattr(ctx.player, "flags", None), dict):
        recruit_only_types = ctx.player.flags.get("recruit_only_types")
    if isinstance(recruit_only_types, list) and recruit_only_types:
        if getattr(opponent, "follower_type", "") not in recruit_only_types:
            return "Why would I want to join your group?"
    if not getattr(opponent, "recruitable", False):
        return f"The {opponent.name} shows no interest."
    if getattr(ctx.player, "follower_slots_remaining", lambda: 0)() <= 0:
        return "You cannot lead more followers."
    cost = int(getattr(opponent, "recruit_cost", 0) or 0)
    if ctx.player.gold < cost:
        return "Not enough GP."
    ctx.player.gold -= cost
    chance = float(getattr(opponent, "recruit_chance", 0.0) or 0.0)
    if random.random() > chance:
        return f"The {opponent.name} refuses your offer."
    follower_type = getattr(opponent, "follower_type", "") or opponent.name.lower()
    names = getattr(opponent, "follower_names", []) or []
    name = random.choice(names) if names else opponent.name
    follower = {
        "type": follower_type,
        "name": name,
        "level": 1,
        "xp": 0,
        "max_level": 5,
        "atk": int(getattr(opponent, "atk", 4) or 4),
        "defense": int(getattr(opponent, "defense", 2) or 2),
        "mp": 6 + int(getattr(opponent, "level", 1) or 1) * 2,
        "max_mp": 6 + int(getattr(opponent, "level", 1) or 1) * 2,
        "hp": int(getattr(opponent, "max_hp", 12) or 12),
        "max_hp": int(getattr(opponent, "max_hp", 12) or 12),
        "equipment": {},
        "abilities": ["fairy_heal", "fairy_mana"] if follower_type == "fairy" else [],
        "active_ability": "fairy_heal" if follower_type == "fairy" else "",
    }
    if follower_type == "wolf":
        follower["abilities"] = ["wolf_meat_toss"]
        follower["active_ability"] = "wolf_meat_toss"
    if follower_type == "mushroom_mage":
        follower["spells"] = ["life_boost", "strength"]
        follower["abilities"] = ["mushroom_tea_brew"]
        wand_pool = ["fire_wand", "water_wand", "wind_wand", "earth_wand"]
        wand_item = random.choice(wand_pool)
        gear = ctx.player.add_gear(wand_item, ctx.items_data, auto_equip=False)
        ctx.player.assign_gear_to_follower(follower, gear.get("id"))
    if not ctx.player.add_follower(follower):
        return "You cannot lead more followers."
    opponent.hp = 0
    opponent.melted = True
    message = f"{name} joins your party."
    if ctx.quests_data is not None:
        quest_messages = handle_event(
            ctx.player,
            ctx.quests_data,
            "recruit_follower",
            {"follower_type": follower_type, "count": 1},
            ctx.items_data,
        )
        if quest_messages:
            message = f"{message} " + " ".join(quest_messages)
    return message
