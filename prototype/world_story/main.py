from __future__ import annotations

import sys
import time

from .battle import BattleState, options_for, start_battle, take_turn
from .constants import ANSI_CLEAR, ANSI_HIDE_CURSOR, ANSI_HOME, ANSI_SHOW_CURSOR, TICK_SECONDS
from .dialog import STORY_DIALOG, DialogState
from .input import KeyReader, terminal_mode
from .dialog import DialogLine
from .story import StoryState, active_trigger, assign_hawking_feather, next_stage
from .travel import TravelState, move_player, render_world


def _start_trigger_dialog(dialog: DialogState, trigger_id: str) -> None:
    dialog.open(trigger_id, STORY_DIALOG.get(trigger_id, []))


def _post_dialog_action(story: StoryState, done_event: str, pending: dict) -> BattleState | None:
    trigger = pending.get(done_event)
    if trigger is None:
        return None
    if trigger.battle_stage is None:
        next_stage(story, trigger.id)
        return None
    _apply_pre_battle_join(story, trigger.id)
    return start_battle(trigger.battle_stage, story)


def _apply_pre_battle_join(story: StoryState, trigger_id: str) -> None:
    if trigger_id == "mushy_commotion":
        if "mushy" not in story.party:
            story.party.append("mushy")
        if "mycostaff" not in story.items:
            story.items.append("mycostaff")
    if trigger_id == "sharoom_house" and "sharoom" not in story.party:
        story.party.insert(0, "sharoom")


def _handle_battle_done(story: StoryState, battle: BattleState, pending_trigger_id: str | None) -> tuple[BattleState | None, str | None]:
    if not battle.victory:
        return start_battle(battle.stage, story), pending_trigger_id
    if pending_trigger_id == "hawking_crossroad":
        next_stage(story, pending_trigger_id)
        return None, "hawking_post"
    if pending_trigger_id:
        next_stage(story, pending_trigger_id)
    return None, None


def _assign_owner_for_index(story: StoryState, index: int) -> None:
    choices = list(story.party)
    if not choices:
        choices = ["player"]
    owner = choices[index % len(choices)]
    assign_hawking_feather(story, owner)


def main() -> None:
    story = StoryState()
    travel = TravelState()
    dialog = DialogState()
    keys = KeyReader()
    battle: BattleState | None = None
    pending: dict = {}
    pending_trigger_id: str | None = None
    assign_cursor = 0

    with terminal_mode():
        sys.stdout.write(ANSI_HIDE_CURSOR + ANSI_CLEAR)
        sys.stdout.flush()
        try:
            last = time.monotonic()
            while True:
                now = time.monotonic()
                if now - last < TICK_SECONDS:
                    time.sleep(max(0.0, TICK_SECONDS - (now - last)))
                last = time.monotonic()

                prompt = ""
                if story.stage == "assign_hawking_feather":
                    choices = [name.title() for name in story.party]
                    selected = choices[assign_cursor % len(choices)]
                    prompt = f"[A Assign {selected}]  Up/Down choose"

                sys.stdout.write(ANSI_HOME + render_world(travel, story, battle, prompt))
                sys.stdout.flush()
                if dialog.active:
                    _draw_dialog(dialog)

                key = keys.read(0.0)
                if key is None:
                    continue
                if key == "quit":
                    break

                if dialog.active:
                    if key == "confirm":
                        done = dialog.advance()
                        if done:
                            battle = _post_dialog_action(story, done, pending)
                            if battle is not None:
                                pending_trigger_id = done
                    _draw_dialog(dialog)
                    continue

                if story.stage == "assign_hawking_feather":
                    if key in ("up", "left"):
                        assign_cursor -= 1
                    elif key in ("down", "right"):
                        assign_cursor += 1
                    elif key == "confirm":
                        _assign_owner_for_index(story, assign_cursor)
                        dialog.open("hawking_victory", [DialogLine("System", "Hawking Feather assigned. Summon Hawking is now available on that actor's command menu.")])
                    continue

                if battle is not None:
                    if battle.finished:
                        if key == "confirm":
                            battle, post_dialog = _handle_battle_done(story, battle, pending_trigger_id)
                            if post_dialog:
                                dialog.open(post_dialog, STORY_DIALOG[post_dialog])
                            else:
                                pending_trigger_id = None
                        continue
                    actor = battle.active_actor
                    options = options_for(actor, story)
                    if key in ("up", "left"):
                        battle.cursor = (battle.cursor - 1) % len(options)
                    elif key in ("down", "right"):
                        battle.cursor = (battle.cursor + 1) % len(options)
                    elif key == "confirm":
                        take_turn(battle, story, options[battle.cursor % len(options)])
                        battle.cursor = 0
                    continue

                if key in ("left", "right", "up", "down"):
                    move_player(travel, key)
                elif key == "confirm":
                    trigger = active_trigger(story, travel.x, travel.y)
                    if trigger:
                        pending[trigger.id] = trigger
                        _start_trigger_dialog(dialog, trigger.id)
                        if not dialog.active:
                            battle = _post_dialog_action(story, trigger.id, pending)
                            pending_trigger_id = trigger.id if battle is not None else None
        finally:
            sys.stdout.write(ANSI_SHOW_CURSOR + ANSI_CLEAR + ANSI_HOME)
            sys.stdout.flush()


def _draw_dialog(dialog: DialogState) -> None:
    rendered = dialog.render_lines()
    if not rendered:
        return
    rows, top = rendered
    sys.stdout.write(ANSI_HOME)
    for y in range(top):
        sys.stdout.write(f"\x1b[{y + 1};1H")
    for idx, row in enumerate(rows):
        sys.stdout.write(f"\x1b[{top + idx + 1};1H{row}")
    sys.stdout.flush()
