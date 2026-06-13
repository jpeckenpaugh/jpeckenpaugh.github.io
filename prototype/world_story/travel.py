from __future__ import annotations

import random
import textwrap
from dataclasses import dataclass

from .battle import BattleState, options_for
from .constants import (
    ANSI_BLUE,
    ANSI_BOLD,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_MAGENTA,
    ANSI_RED,
    ANSI_RESET,
    ANSI_ROAD,
    ANSI_YELLOW,
    SCREEN_H,
    SCREEN_W,
    WORLD_H,
    WORLD_W,
)
from .story import StoryState, Trigger, active_trigger
from .story import TRIGGERS


@dataclass
class TravelState:
    x: int = 12
    y: int = 15
    facing: str = "right"


HOUSES = [
    (62, 8, "#3 Ave A", "Sharoom"),
    (119, 21, "#9 Ave A", "Roomy"),
    (31, 21, "#1 Ave A", ""),
    (86, 8, "#5 Ave A", ""),
    (101, 22, "#7 Ave A", ""),
    (151, 9, "Watch Post", ""),
]


def can_walk(x: int, y: int) -> bool:
    if x < 1 or y < 1 or x >= WORLD_W - 1 or y >= WORLD_H - 1:
        return False
    if 12 <= y <= 18:
        return True
    for road_x in (45, 75, 105, 135, 165):
        if road_x - 4 <= x <= road_x + 4 and 6 <= y <= 25:
            return True
    for cx, cy in ((50, 15), (145, 15), (166, 15)):
        if abs(x - cx) <= 10 and abs(y - cy) <= 5:
            return True
    return False


def move_player(travel: TravelState, key: str) -> None:
    dx, dy = 0, 0
    if key == "left":
        dx = -1
        travel.facing = "left"
    elif key == "right":
        dx = 1
        travel.facing = "right"
    elif key == "up":
        dy = -1
        travel.facing = "up"
    elif key == "down":
        dy = 1
        travel.facing = "down"
    nx, ny = travel.x + dx, travel.y + dy
    if can_walk(nx, ny):
        travel.x, travel.y = nx, ny


def camera_for(travel: TravelState) -> tuple[int, int]:
    cam_x = max(0, min(WORLD_W - SCREEN_W, travel.x - SCREEN_W // 2))
    cam_y = max(0, min(WORLD_H - SCREEN_H, travel.y - SCREEN_H // 2))
    return cam_x, cam_y


def _put(canvas: list[list[str]], x: int, y: int, text: str) -> None:
    if y < 0 or y >= SCREEN_H:
        return
    for i, ch in enumerate(text):
        if 0 <= x + i < SCREEN_W:
            canvas[y][x + i] = ch


def _world_cell(x: int, y: int) -> str:
    if can_walk(x, y):
        rng = random.Random((x * 928371 + y * 13337) & 0xFFFFFFFF)
        road_glyph = rng.choice([".", ",", "`", "'"])
        return f"{ANSI_ROAD}{road_glyph}{ANSI_RESET}"
    rng = random.Random((x * 1103515245 + y * 12345) & 0xFFFFFFFF)
    return f"{ANSI_GREEN}{rng.choice(['.', '.', ',', '~'])}{ANSI_RESET}"


def _draw_house(canvas: list[list[str]], cam_x: int, cam_y: int, hx: int, hy: int, label: str, resident: str) -> None:
    sx, sy = hx - cam_x, hy - cam_y
    art = ["  /\\  ", " /##\\ ", "|_[]_|"]
    for row, line in enumerate(art):
        _put(canvas, sx, sy + row, f"{ANSI_YELLOW}{line}{ANSI_RESET}")
    _put(canvas, sx - 1, sy + 3, f"{ANSI_DIM}{label}{ANSI_RESET}")
    if resident:
        _put(canvas, sx + 1, sy + 4, f"{ANSI_MAGENTA}{resident}{ANSI_RESET}")


def _draw_trigger(canvas: list[list[str]], cam_x: int, cam_y: int, trigger: Trigger) -> None:
    sx, sy = trigger.x - cam_x, trigger.y - cam_y
    glyph = "?"
    if "crow" in trigger.id or "fairy" in trigger.id:
        glyph = "!"
    if "hawking" in trigger.id:
        glyph = "H"
    _put(canvas, sx, sy, f"{ANSI_RED}{ANSI_BOLD}{glyph}{ANSI_RESET}")


def render_world(
    travel: TravelState,
    story: StoryState,
    battle: BattleState | None = None,
    prompt: str | None = None,
) -> str:
    cam_x, cam_y = camera_for(travel)
    canvas = [[_world_cell(cam_x + x, cam_y + y) for x in range(SCREEN_W)] for y in range(SCREEN_H)]

    for hx, hy, label, resident in HOUSES:
        _draw_house(canvas, cam_x, cam_y, hx, hy, label, resident)

    trigger = active_trigger(story, travel.x, travel.y)
    for candidate in [item for item in TRIGGERS if item.stage == story.stage]:
        _draw_trigger(canvas, cam_x, cam_y, candidate)

    _put(canvas, travel.x - cam_x, travel.y - cam_y, f"{ANSI_BLUE}{ANSI_BOLD}@{ANSI_RESET}")

    if battle is not None:
        _draw_battle(canvas, battle, story)

    _draw_hud(canvas, travel, story, prompt or (trigger.prompt if trigger else ""))
    return "\n".join("".join(row) for row in canvas)


def _draw_hud(canvas: list[list[str]], travel: TravelState, story: StoryState, prompt: str) -> None:
    top = f" Objective: {story.current_objective} "
    party = "Party: " + ", ".join(name.title() for name in story.party)
    loc = f"Loc: ({travel.x},{travel.y})  {prompt}"
    _put(canvas, 0, 0, f"{ANSI_BOLD}{top[:SCREEN_W]:<{SCREEN_W}}{ANSI_RESET}")
    _put(canvas, 0, 1, f"{party[:56]:<56}{loc[:43]:>43}")
    _put(canvas, 0, SCREEN_H - 1, f"{ANSI_DIM}Arrows move  A interact/confirm  S back  Q quit{ANSI_RESET}")


def _draw_bar(value: int, total: int, width: int = 10) -> str:
    total = max(1, total)
    filled = max(0, min(width, round((value / total) * width)))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _draw_battle(canvas: list[list[str]], battle: BattleState, story: StoryState) -> None:
    _put(canvas, 27, 3, f"{ANSI_RED}{ANSI_BOLD}ON-STREET BATTLE{ANSI_RESET}")
    for idx, enemy in enumerate(battle.enemies):
        x = 60 + idx * 6
        y = 9 + (idx % 2)
        if enemy.hp > 0:
            _put(canvas, x, y, f"{ANSI_RED}E{idx + 1}{ANSI_RESET}")
        _put(canvas, x - 3, y + 1, f"{enemy.name[:8]:<8}")
        _put(canvas, x - 3, y + 2, _draw_bar(enemy.hp, enemy.max_hp, 8))
    for idx, actor in enumerate(battle.party):
        x = 18 + idx * 8
        y = 18 + (idx % 2)
        marker = "@" if actor.key == "player" else actor.name[0]
        if actor.hp > 0:
            _put(canvas, x, y, f"{ANSI_BLUE}{marker}{ANSI_RESET}")
        _put(canvas, x - 4, y + 1, f"{actor.name[:9]:<9}")
        _put(canvas, x - 4, y + 2, _draw_bar(actor.hp, actor.max_hp, 8))
        _put(canvas, x - 4, y + 3, f"MP {actor.mp:>2}/{actor.max_mp:<2}")

    panel_x, panel_y = 2, 4
    _put(canvas, panel_x, panel_y, "+----------------------+")
    if battle.finished:
        _put(canvas, panel_x, panel_y + 1, "| A continue/retry     |")
    else:
        actor = battle.active_actor
        options = options_for(actor, story)
        _put(canvas, panel_x, panel_y + 1, f"| {actor.name:<20} |")
        for i, option in enumerate(options[:5]):
            cursor = ">" if i == battle.cursor % len(options) else " "
            _put(canvas, panel_x, panel_y + 2 + i, f"|{cursor} {option:<19}|")
    _put(canvas, panel_x, panel_y + 8, "+----------------------+")

    log_lines = battle.log[-6:]
    for i, line in enumerate(log_lines):
        for j, wrapped in enumerate(textwrap.wrap(line, width=42)[:2]):
            _put(canvas, 54, 20 + i + j, wrapped[:42])
