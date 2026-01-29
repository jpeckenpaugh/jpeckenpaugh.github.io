"""State container for the main game loop."""

from dataclasses import dataclass, field
from typing import List, Optional

from app.models import Player, Opponent


@dataclass
class GameState:
    player: Player
    opponents: List[Opponent]
    loot_bank: dict
    last_message: str
    leveling_mode: bool
    boost_prompt: Optional[str]
    shop_mode: bool
    inventory_mode: bool
    inventory_items: List[tuple[str, str]]
    hall_mode: bool
    hall_view: str
    inn_mode: bool
    spell_mode: bool
    quit_confirm: bool
    title_mode: bool
    target_select: bool = False
    target_index: Optional[int] = None
    target_command: Optional[str] = None
    battle_log: list[str] = field(default_factory=list)
