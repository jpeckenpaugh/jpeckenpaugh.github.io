from __future__ import annotations

from dataclasses import dataclass
import random
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from app.game import GameApp


@dataclass
class NewGameView:
    step: str
    heading: str
    detail: str
    options: List[str]
    cursor: int


@dataclass
class NewGameOutcome:
    save_now: bool = False


class NewGameWorkflow:
    _NAME_KEYBOARD = [
        ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
        ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        ["K", "L", "M", "N", "O", "P", "Q", "R", "S", "T"],
        ["U", "V", "W", "X", "Y", "Z", "-", "'", "SPACE", "DEL"],
        ["SHIFT", "DONE", "CANCEL"],
    ]
    _FORTUNE_VALUES = {
        "Poor (10 GP)": 10,
        "Well-Off (100 GP)": 100,
        "Royalty (1000 GP)": 1000,
    }

    def __init__(self) -> None:
        self._rng = random.Random()
        self._active = False
        self._step = "idle"
        self._cursor = 0
        self._pending_slot = 1
        self._pending_avatar_id = "player_01"
        self._pending_avatar_label = ""
        self._pending_name = ""
        self._pending_fortune = "Well-Off (100 GP)"
        self._player_ids: list[str] = []
        self._player_labels: list[str] = []
        self._player_cursor = 0
        self._name_choices: list[str] = []
        self._name_cursor = 0
        self._name_key_row = 0
        self._name_key_col = 0
        self._name_shift = True

    def is_active(self) -> bool:
        return self._active

    def start(self, app: "GameApp") -> None:
        self._active = True
        self._step = "idle"
        self._cursor = 0
        self._pending_name = ""
        self._pending_fortune = "Well-Off (100 GP)"
        self._load_players(app)
        next_slot = app.save_service.next_empty_slot(max_slots=100)
        if next_slot is None:
            self._pending_slot = app.save_service.last_played_slot(max_slots=100) or 1
            self._step = "overwrite_confirm"
            return
        self._pending_slot = next_slot
        self._step = "player_select"

    def cancel(self) -> None:
        self._active = False
        self._step = "idle"
        self._cursor = 0

    def move_cursor(self, delta: int) -> None:
        options = self._options_for_step()
        if not options:
            return
        self._cursor = (self._cursor + delta) % len(options)

    def view(self) -> NewGameView:
        heading = ""
        detail = ""
        options = self._options_for_step()
        if self._step == "overwrite_confirm":
            heading = "New Game"
            detail = f"Slot {self._pending_slot} has data. Overwrite?"
        elif self._step == "player_select":
            heading = "Choose Adventurer"
            label = self._current_player_label()
            detail = f"Slot {self._pending_slot}  Avatar: {label}"
        elif self._step == "name_select":
            heading = "Say Your Name"
            detail = ""
        elif self._step == "name_input":
            heading = "Custom Name"
            detail = f"Name: {(self._pending_name or '')[:16]}_"
        elif self._step == "fortune":
            heading = "Choose Fortune"
            detail = ""
        elif self._step == "start_confirm":
            heading = "Being Your Adventure"
            detail = ""
        return NewGameView(step=self._step, heading=heading, detail=detail, options=options, cursor=self._cursor)

    def step(self) -> str:
        return self._step

    def player_choices(self) -> list[tuple[str, str, bool]]:
        out: list[tuple[str, str, bool]] = []
        for idx, player_id in enumerate(self._player_ids):
            label = self._player_labels[idx] if idx < len(self._player_labels) else player_id
            out.append((player_id, label, idx == self._player_cursor))
        return out

    def name_input_state(self) -> tuple[str, list[list[str]], tuple[int, int]]:
        rows = self._display_keyboard_rows()
        return ((self._pending_name or "")[:16], rows, (self._name_key_row, self._name_key_col))

    def handle_key(self, app: "GameApp", key: str) -> NewGameOutcome:
        if not self._active:
            return NewGameOutcome()

        if self._step == "player_select":
            if key in ("left", "up"):
                self._move_player(-1)
                return NewGameOutcome()
            if key in ("right", "down"):
                self._move_player(1)
                return NewGameOutcome()
            if key == "back":
                self.cancel()
                return NewGameOutcome()
            if key == "confirm":
                self._pending_avatar_id = self._current_player_id()
                self._pending_avatar_label = self._current_player_label()
                self._prepare_name_choices(app)
                self._step = "name_select"
                self._cursor = 0
                return NewGameOutcome()
            return NewGameOutcome()

        if self._step == "name_select":
            if key == "left":
                self._cycle_name(-1)
                return NewGameOutcome()
            if key == "right":
                self._cycle_name(1)
                return NewGameOutcome()

        if self._step == "name_input":
            if key in ("up", "down", "left", "right"):
                self._move_name_key_cursor(key)
                return NewGameOutcome()
            if key == "back":
                self._step = "name_select"
                self._cursor = 1
                return NewGameOutcome()
            if key == "confirm":
                self._press_name_key()
                return NewGameOutcome()
            if key in ("\x08", "\x7f"):
                self._pending_name = self._pending_name[:-1]
                return NewGameOutcome()
            if len(key) == 1 and key.isprintable() and key not in ("\r", "\n"):
                if len(self._pending_name) < 16:
                    self._pending_name += key
            return NewGameOutcome()

        if self._step == "start_confirm":
            if key == "back":
                self._step = "fortune"
                self._cursor = 1
                return NewGameOutcome()
            if key == "confirm":
                self._create_session(app)
                self.cancel()
                return NewGameOutcome(save_now=True)
            return NewGameOutcome()

        if key == "up":
            self.move_cursor(-1)
            return NewGameOutcome()
        if key == "down":
            self.move_cursor(1)
            return NewGameOutcome()

        if key == "back":
            self._handle_back()
            return NewGameOutcome()
        if key != "confirm":
            return NewGameOutcome()

        return self._handle_confirm(app)

    def _handle_back(self) -> None:
        if self._step == "overwrite_confirm":
            self.cancel()
            return
        if self._step == "name_select":
            self._step = "player_select"
            self._cursor = 0
            return
        if self._step == "fortune":
            self._step = "name_select"
            self._cursor = 0
            return
        if self._step == "start_confirm":
            self._step = "fortune"
            self._cursor = 1

    def _handle_confirm(self, app: "GameApp") -> NewGameOutcome:
        options = self._options_for_step()
        if not options:
            return NewGameOutcome()
        choice = options[self._cursor]

        if self._step == "overwrite_confirm":
            if choice.startswith("Yes"):
                app.save_service.delete(self._pending_slot)
                self._step = "player_select"
                self._cursor = 0
            else:
                self.cancel()
            return NewGameOutcome()

        if self._step == "name_select":
            if self._cursor == 0:
                self._pending_name = self._current_name_choice()
                self._step = "fortune"
                self._cursor = 1
            elif choice == "Custom...":
                self._step = "name_input"
                self._name_key_row = 0
                self._name_key_col = 0
                self._name_shift = True
                self._cursor = 0
            return NewGameOutcome()

        if self._step == "fortune":
            self._pending_fortune = choice
            self._step = "start_confirm"
            self._cursor = 0
            return NewGameOutcome()

        return NewGameOutcome()

    def _create_session(self, app: "GameApp") -> None:
        from app.session import GameSession, Player

        gold = self._FORTUNE_VALUES.get(self._pending_fortune, 100)
        player = Player(
            name=(self._pending_name or "WARRIOR")[:16],
            level=1,
            hp=20,
            max_hp=20,
            gold=gold,
            avatar_id=(self._pending_avatar_id or "player_01"),
            location="Town",
        )
        app.session = GameSession(
            player=player,
            current_scene_id="title",
            selected_slot=self._pending_slot,
            last_message="New game created.",
        )

    def _options_for_step(self) -> list[str]:
        if self._step == "overwrite_confirm":
            return [f"Yes, overwrite slot {self._pending_slot}", "No, go back"]
        if self._step == "player_select":
            return ["Confirm Avatar", "Back"]
        if self._step == "name_select":
            return [f"< {self._current_name_choice()} >", "Custom..."]
        if self._step == "name_input":
            return ["Type then press A", "S to cancel"]
        if self._step == "fortune":
            return ["Poor (10 GP)", "Well-Off (100 GP)", "Royalty (1000 GP)"]
        if self._step == "start_confirm":
            return []
        return []

    def _load_players(self, app: "GameApp") -> None:
        try:
            payload = app.asset_repository.load("players.json")
        except Exception:
            payload = {}
        ids: list[str] = []
        labels: list[str] = []
        if isinstance(payload, dict):
            for player_id in sorted(payload.keys()):
                entry = payload.get(player_id, {})
                label = player_id
                if isinstance(entry, dict):
                    label = str(entry.get("label", player_id) or player_id)
                ids.append(str(player_id))
                labels.append(label)
        if not ids:
            ids = ["player_01"]
            labels = ["Adventurer"]
        self._player_ids = ids
        self._player_labels = labels
        self._player_cursor = self._rng.randint(0, len(self._player_ids) - 1)
        self._pending_avatar_id = self._current_player_id()
        self._pending_avatar_label = self._current_player_label()

    def _move_player(self, delta: int) -> None:
        if not self._player_ids:
            return
        self._player_cursor = (self._player_cursor + delta) % len(self._player_ids)

    def _current_player_id(self) -> str:
        if not self._player_ids:
            return "player_01"
        return self._player_ids[self._player_cursor]

    def _current_player_label(self) -> str:
        if not self._player_labels:
            return "Adventurer"
        return self._player_labels[self._player_cursor]

    def _random_name(self, app: "GameApp") -> str:
        try:
            players = app.asset_repository.load("players.json")
        except Exception:
            players = {}
        choices: list[str] = []
        entry = players.get(self._pending_avatar_id, {}) if isinstance(players, dict) else {}
        if isinstance(entry, dict):
            raw_names = entry.get("names", [])
            if isinstance(raw_names, list):
                choices = [str(n).strip() for n in raw_names if str(n).strip()]
        if not choices:
            choices = ["WARRIOR"]

        existing = set()
        for slot in range(1, 101):
            if not app.save_service.has_slot(slot):
                continue
            loaded = app.save_service.load(slot)
            if loaded and loaded.player.name:
                existing.add(str(loaded.player.name).strip().lower())

        self._rng.shuffle(choices)
        for base in choices:
            candidate = base[:16]
            if candidate.lower() not in existing:
                return candidate
        base = choices[0][:12] or "WARRIOR"
        suffix = 2
        while True:
            candidate = f"{base}{suffix}"[:16]
            if candidate.lower() not in existing:
                return candidate
            suffix += 1

    def _prepare_name_choices(self, app: "GameApp") -> None:
        try:
            players = app.asset_repository.load("players.json")
        except Exception:
            players = {}
        choices: list[str] = []
        entry = players.get(self._pending_avatar_id, {}) if isinstance(players, dict) else {}
        if isinstance(entry, dict):
            raw_names = entry.get("names", [])
            if isinstance(raw_names, list):
                seen: set[str] = set()
                for raw in raw_names:
                    name = str(raw).strip()[:16]
                    if not name:
                        continue
                    low = name.lower()
                    if low in seen:
                        continue
                    seen.add(low)
                    choices.append(name)
        if not choices:
            choices = ["WARRIOR"]
        self._rng.shuffle(choices)
        self._name_choices = choices
        self._name_cursor = 0

    def _current_name_choice(self) -> str:
        if not self._name_choices:
            return "WARRIOR"
        idx = max(0, min(self._name_cursor, len(self._name_choices) - 1))
        return self._name_choices[idx]

    def _cycle_name(self, delta: int) -> None:
        if not self._name_choices:
            return
        self._name_cursor = (self._name_cursor + delta) % len(self._name_choices)

    def _display_keyboard_rows(self) -> list[list[str]]:
        rows: list[list[str]] = []
        for row in self._NAME_KEYBOARD:
            display_row: list[str] = []
            for key in row:
                if len(key) == 1 and key.isalpha():
                    display_row.append(key.upper() if self._name_shift else key.lower())
                else:
                    display_row.append(key)
            rows.append(display_row)
        return rows

    def _move_name_key_cursor(self, direction: str) -> None:
        row = self._name_key_row
        col = self._name_key_col
        if direction == "up":
            row = (row - 1) % len(self._NAME_KEYBOARD)
            col = min(col, len(self._NAME_KEYBOARD[row]) - 1)
        elif direction == "down":
            row = (row + 1) % len(self._NAME_KEYBOARD)
            col = min(col, len(self._NAME_KEYBOARD[row]) - 1)
        elif direction == "left":
            col = (col - 1) % len(self._NAME_KEYBOARD[row])
        elif direction == "right":
            col = (col + 1) % len(self._NAME_KEYBOARD[row])
        self._name_key_row = row
        self._name_key_col = col

    def _press_name_key(self) -> None:
        row = max(0, min(self._name_key_row, len(self._NAME_KEYBOARD) - 1))
        col = max(0, min(self._name_key_col, len(self._NAME_KEYBOARD[row]) - 1))
        key = self._NAME_KEYBOARD[row][col]
        if key == "SHIFT":
            self._name_shift = not self._name_shift
            return
        if key == "DEL":
            self._pending_name = self._pending_name[:-1]
            return
        if key == "CANCEL":
            self._step = "name_select"
            self._cursor = 1
            return
        if key == "DONE":
            if self._pending_name.strip():
                self._pending_name = self._pending_name.strip()[:16]
                self._step = "fortune"
                self._cursor = 1
            return
        if len(self._pending_name) >= 16:
            return
        if key == "SPACE":
            self._pending_name += " "
            return
        if len(key) == 1 and key.isalpha():
            self._pending_name += key.upper() if self._name_shift else key.lower()
            return
        self._pending_name += key[:1]
