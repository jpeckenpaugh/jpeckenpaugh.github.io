from __future__ import annotations

from dataclasses import dataclass, field
import random

from .story import StoryState


NAMES = {
    "player": "Player",
    "mushy": "Mushy",
    "sharoom": "Sharoom",
    "roomy": "Roomy",
}


@dataclass
class Actor:
    key: str
    name: str
    hp: int
    max_hp: int
    mp: int = 0
    max_mp: int = 0
    atk: int = 2
    defense: int = 1


@dataclass
class BattleState:
    stage: int
    party: list[Actor]
    enemies: list[Actor]
    actor_index: int = 0
    cursor: int = 0
    log: list[str] = field(default_factory=list)
    finished: bool = False
    victory: bool = False

    @property
    def active_actor(self) -> Actor:
        living = [a for a in self.party if a.hp > 0]
        if not living:
            return self.party[0]
        self.actor_index %= len(living)
        return living[self.actor_index]


def _party_for_story(story: StoryState) -> list[Actor]:
    party = []
    for key in story.party:
        if key == "player":
            party.append(Actor("player", "Player", 20, 20, story.player_max_mp, story.player_max_mp, 2, 1))
        elif key == "mushy":
            party.append(Actor("mushy", "Mushy", 10, 10, 6, 6, 2, 2))
        elif key == "sharoom":
            party.append(Actor("sharoom", "Sharoom", 10, 10, 8, 8, 2, 2))
        elif key == "roomy":
            party.append(Actor("roomy", "Roomy", 11, 11, 8, 8, 2, 2))
    if story.hawking_feather_owner:
        for actor in party:
            if actor.key == story.hawking_feather_owner:
                actor.max_hp += 4
                actor.hp += 4
                actor.max_mp += 4
                actor.mp += 4
    return party


def _enemies_for_stage(stage: int) -> list[Actor]:
    if stage == 1:
        return [Actor("crow", "Baby Crow", 10, 10, atk=3, defense=0)]
    if stage == 2:
        return [Actor(f"crow{i}", "Baby Crow", 10, 10, atk=3, defense=0) for i in range(1, 3)]
    if stage == 3:
        return [Actor(f"crow{i}", "Baby Crow", 10, 10, atk=3, defense=0) for i in range(1, 4)]
    if stage == 4:
        return [Actor("hawking", "Hawking", 28, 28, atk=4, defense=1)]
    return [Actor(f"fairy{i}", "Baby Fairy", 12, 12, atk=3, defense=1) for i in range(1, 6)]


def start_battle(stage: int, story: StoryState) -> BattleState:
    battle = BattleState(stage=stage, party=_party_for_story(story), enemies=_enemies_for_stage(stage))
    names = ", ".join(a.name for a in battle.party)
    foes = ", ".join(e.name for e in battle.enemies)
    battle.log.append(f"Battle begins: {names} vs {foes}.")
    return battle


def options_for(actor: Actor, story: StoryState) -> list[str]:
    options = ["Attack", "Defend"]
    if actor.key == "player":
        options.insert(1, "Magic Spark")
    if actor.key == "mushy":
        options.insert(1, "Mushroom Tea")
    if actor.key == "sharoom":
        options.insert(1, "Healing Touch")
    if actor.key == "roomy":
        options.insert(1, "Concentric")
    if story.summon_hawking_unlocked and actor.key == story.hawking_feather_owner:
        options.insert(1, "Summon Hawking")
    return options


def living_enemies(battle: BattleState) -> list[Actor]:
    return [enemy for enemy in battle.enemies if enemy.hp > 0]


def living_party(battle: BattleState) -> list[Actor]:
    return [actor for actor in battle.party if actor.hp > 0]


def _damage(attacker: Actor, defender: Actor, bonus: int = 0) -> int:
    return max(1, attacker.atk + bonus + random.randint(0, 2) - defender.defense)


def _hit(attacker: Actor, defender: Actor, amount: int, log: list[str]) -> None:
    defender.hp = max(0, defender.hp - amount)
    log.append(f"{attacker.name} hits {defender.name} for {amount}.")
    if defender.hp <= 0:
        log.append(f"{defender.name} is defeated.")


def take_turn(battle: BattleState, story: StoryState, action: str) -> None:
    actor = battle.active_actor
    if actor.hp <= 0:
        battle.actor_index += 1
        return
    enemies = living_enemies(battle)
    if not enemies:
        _finish(battle, True)
        return
    target = enemies[0]
    if action == "Magic Spark" and actor.mp >= 2:
        actor.mp -= 2
        targets = enemies if story.magic_spark_level >= 2 else [target]
        for enemy in targets:
            _hit(actor, enemy, random.randint(5, 8), battle.log)
    elif action == "Summon Hawking" and actor.mp >= 0:
        _hit(actor, target, target.hp, battle.log)
        battle.log.append("Hawking swoops through the street.")
    elif action == "Mushroom Tea" and actor.mp >= 2:
        actor.mp -= 2
        actor.atk += 2
        actor.defense += 1
        battle.log.append("Mushy drinks Mushroom Tea. Attack and defense rise.")
    elif action == "Healing Touch" and actor.mp >= 2:
        actor.mp -= 2
        ally = min(living_party(battle), key=lambda item: item.hp / max(1, item.max_hp))
        old = ally.hp
        ally.hp = min(ally.max_hp, ally.hp + 6)
        battle.log.append(f"Sharoom restores {ally.name}: {old} -> {ally.hp} HP.")
    elif action == "Concentric" and actor.mp >= 2:
        actor.mp -= 2
        for ally in battle.party:
            if ally.key != "roomy":
                ally.mp = min(ally.max_mp, ally.mp + 1)
        battle.log.append("Roomy restores a little MP to the team.")
    elif action == "Defend":
        actor.defense += 1
        battle.log.append(f"{actor.name} defends.")
    else:
        _hit(actor, target, _damage(actor, target), battle.log)

    if not living_enemies(battle):
        _finish(battle, True)
        return

    battle.actor_index += 1
    if battle.actor_index >= len(living_party(battle)):
        battle.actor_index = 0
        enemy_phase(battle)


def enemy_phase(battle: BattleState) -> None:
    for enemy in living_enemies(battle):
        targets = living_party(battle)
        if not targets:
            _finish(battle, False)
            return
        target = random.choice(targets)
        _hit(enemy, target, _damage(enemy, target), battle.log)
    if not living_party(battle):
        _finish(battle, False)


def _finish(battle: BattleState, victory: bool) -> None:
    battle.finished = True
    battle.victory = victory
    battle.log.append("Victory!" if victory else "The party falls. Press A to retry.")
