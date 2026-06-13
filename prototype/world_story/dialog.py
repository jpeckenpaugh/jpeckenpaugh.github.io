from __future__ import annotations

from dataclasses import dataclass
import textwrap
from typing import Iterable

from .constants import ANSI_BOLD, ANSI_RESET, ANSI_YELLOW, SCREEN_H, SCREEN_W


@dataclass(frozen=True)
class DialogLine:
    title: str
    body: str


STORY_DIALOG: dict[str, list[DialogLine]] = {
    "mushy_commotion": [
        DialogLine("Story", "One day as you are walking home you hear a commotion. You stumble upon a small magic mushroom and a crow who appear to be fighting."),
        DialogLine("Mushy", "Hey you! You seem like a nice person. Would you come help me deal with this pesky crow?"),
        DialogLine("Mushy", "I have a Magic Staff embued with the Magic Spark spell. If you can figure out how to use it, we can get rid of this crow together."),
        DialogLine("Mushy", "Great! Now let's show this crow who is boss around here."),
    ],
    "second_crow_ambush": [
        DialogLine("Mushy", "Your Mycostaff holds 3 charge of the Magic Spark spell. It will automatically recharge after each battle."),
        DialogLine("Mushy", "We can also use my Mushroom Tea to temporarily boost our Attack and Defense points, giving us an edge in battle."),
        DialogLine("Mushy", "Watch out, here come some more crows!"),
    ],
    "sharoom_house": [
        DialogLine("Mushy", "Your Mana Points are increasing. That means you can use MP to cast spells in battle when your items run out of charges."),
        DialogLine("Mushy", "I have a friend Sharoom who knows some healing magic. She would be a good addition to our little team."),
        DialogLine("Mushy", "Sharoom, the time has come! Crow war is on. Come join our fight..."),
        DialogLine("Sharoom", "Sure I will join your team. I think we can work well together."),
        DialogLine("Sharoom", "Let me know when you need a Healing Touch, as that is my specialty."),
    ],
    "roomy_house": [
        DialogLine("Mushy", "Next we should seek out Roomie. I think he is looking for a place to stay..."),
        DialogLine("Mushy", "Roomie! Over here. We need your support in this crow war."),
        DialogLine("Roomie", "I have been working on my Concentric spell."),
        DialogLine("Roomie", "It is a spell to recover MP, and it can come in handy in longer battles, when we need extra magic points."),
        DialogLine("Mushy", "If we combine that with our other spells, we can really compound our punch power."),
    ],
    "hawking_crossroad": [
        DialogLine("Hawking", "I am the Hawk King. I've finally found you bird bashing bozos."),
        DialogLine("Hawking", "Why don't you try picking on someone your own size?"),
        DialogLine("Sharoom", "Our own size? You must be at least 10 times as big as us."),
        DialogLine("Sharoom", "But we've got teamwork, and you are all by yourself!"),
        DialogLine("Hawking", "Oh you think so, huh?"),
    ],
    "hawking_post": [
        DialogLine("Hawking", "Fine, you win. I guess we can be friends, since you apparently aren't a weakling."),
        DialogLine("Hawking", "Here, take one of my feathers. Just call when you need a hand and I will swoop in."),
        DialogLine("Hawking", "Just assign my feather to whoever should call me in battle."),
    ],
    "fairy_roadblock": [
        DialogLine("Roomy", "Uh oh, here come those fairies..."),
    ],
}


class DialogState:
    def __init__(self) -> None:
        self.lines: list[DialogLine] = []
        self.index = 0
        self.done_event: str | None = None

    @property
    def active(self) -> bool:
        return bool(self.lines)

    def open(self, event_id: str, lines: Iterable[DialogLine]) -> None:
        self.lines = list(lines)
        self.index = 0
        self.done_event = event_id

    def advance(self) -> str | None:
        if not self.lines:
            return None
        self.index += 1
        if self.index < len(self.lines):
            return None
        done = self.done_event
        self.lines = []
        self.index = 0
        self.done_event = None
        return done

    def render_lines(self) -> list[str]:
        if not self.lines:
            return []
        line = self.lines[min(self.index, len(self.lines) - 1)]
        width = 66
        body = textwrap.wrap(line.body, width=width) or [""]
        box_w = width + 4
        rows = [f"+{'-' * (box_w - 2)}+"]
        title = f" {line.title} "
        rows.append("|" + f"{ANSI_YELLOW}{ANSI_BOLD}{title:<{box_w - 2}}{ANSI_RESET}" + "|")
        rows.append("|" + " " * (box_w - 2) + "|")
        for text in body[:5]:
            rows.append("| " + f"{text:<{width}}" + " |")
        rows.append("|" + " " * (box_w - 2) + "|")
        rows.append("|" + f"{'[A Continue]':>{box_w - 3}} " + "|")
        rows.append(f"+{'-' * (box_w - 2)}+")
        top = max(2, SCREEN_H - len(rows) - 2)
        left = max(0, (SCREEN_W - box_w) // 2)
        return [(" " * left) + row for row in rows], top
