from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot


@dataclass(frozen=True)
class Trigger:
    id: str
    stage: str
    x: int
    y: int
    radius: int
    prompt: str
    objective: str
    battle_stage: int | None = None


@dataclass
class StoryState:
    stage: str = "find_mushy"
    completed_triggers: set[str] = field(default_factory=set)
    party: list[str] = field(default_factory=lambda: ["player"])
    items: list[str] = field(default_factory=list)
    current_objective: str = "Follow Main Street and investigate the commotion."
    hawking_feather_owner: str = ""
    summon_hawking_unlocked: bool = False
    magic_spark_level: int = 1
    player_max_mp: int = 6


TRIGGERS: list[Trigger] = [
    Trigger("mushy_commotion", "find_mushy", 30, 18, 4, "[A Talk]", "Help Mushy with the crow.", 1),
    Trigger("second_crow_ambush", "find_more_crows", 50, 15, 4, "[A Investigate]", "Deal with the next crow ambush.", 2),
    Trigger("sharoom_house", "find_sharoom", 66, 10, 5, "[A Talk]", "Recruit Sharoom at #3 Ave A.", 3),
    Trigger("roomy_house", "find_roomy", 120, 22, 5, "[A Talk]", "Recruit Roomy at #9 Ave A.", None),
    Trigger("hawking_crossroad", "find_hawking", 145, 15, 6, "[A Challenge]", "Face Hawking at the wide crossroad.", 4),
    Trigger("fairy_roadblock", "find_fairies", 166, 15, 6, "[A Battle]", "Break through the fairy roadblock.", 5),
]


STAGE_ORDER = [
    "find_mushy",
    "find_more_crows",
    "find_sharoom",
    "find_roomy",
    "find_hawking",
    "assign_hawking_feather",
    "find_fairies",
    "complete",
]


def active_trigger(story: StoryState, player_x: int, player_y: int) -> Trigger | None:
    for trigger in TRIGGERS:
        if trigger.stage != story.stage or trigger.id in story.completed_triggers:
            continue
        if hypot(trigger.x - player_x, trigger.y - player_y) <= trigger.radius:
            return trigger
    return None


def next_stage(story: StoryState, trigger_id: str) -> None:
    story.completed_triggers.add(trigger_id)
    if trigger_id == "mushy_commotion":
        if "mushy" not in story.party:
            story.party.append("mushy")
        if "mycostaff" not in story.items:
            story.items.append("mycostaff")
        story.player_max_mp = 8
        story.stage = "find_more_crows"
        story.current_objective = "Continue down Main Street to the next crossroad."
    elif trigger_id == "second_crow_ambush":
        story.magic_spark_level = 2
        story.stage = "find_sharoom"
        story.current_objective = "Find Sharoom near #3 Ave A."
    elif trigger_id == "sharoom_house":
        if "sharoom" not in story.party:
            story.party.insert(0, "sharoom")
        story.stage = "find_roomy"
        story.current_objective = "Find Roomy near #9 Ave A."
    elif trigger_id == "roomy_house":
        if "roomy" not in story.party:
            story.party.append("roomy")
        story.stage = "find_hawking"
        story.current_objective = "Travel east to the wide crossroad and confront Hawking."
    elif trigger_id == "hawking_crossroad":
        story.stage = "assign_hawking_feather"
        story.current_objective = "Assign Hawking Feather to one party member."
    elif trigger_id == "fairy_roadblock":
        story.stage = "complete"
        story.current_objective = "Prototype route complete. Explore or press Q to quit."


def assign_hawking_feather(story: StoryState, owner: str) -> None:
    story.hawking_feather_owner = owner
    story.summon_hawking_unlocked = True
    if "hawking_feather" not in story.items:
        story.items.append("hawking_feather")
    story.stage = "find_fairies"
    story.current_objective = "Continue east and stop the fairy roadblock."
