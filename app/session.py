from dataclasses import dataclass
from typing import Optional


@dataclass
class Player:
    name: str = "Hero"
    level: int = 1
    hp: int = 20
    max_hp: int = 20
    gold: int = 0
    avatar_id: str = "player_01"
    location: str = "Town"


@dataclass
class GameSession:
    player: Player
    current_scene_id: str = "title"
    selected_slot: int = 1
    last_message: str = ""

    def with_message(self, message: Optional[str]) -> None:
        self.last_message = message or ""
