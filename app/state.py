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
    shop_mode: bool
    inventory_mode: bool
    inventory_items: List[tuple[str, str]]
    hall_mode: bool
    hall_view: str
    inn_mode: bool
    spell_mode: bool
    quit_confirm: bool
    title_mode: bool
    shop_view: str = "menu"
    element_mode: bool = False
    alchemist_mode: bool = False
    alchemy_first: Optional[str] = None
    temple_mode: bool = False
    smithy_mode: bool = False
    portal_mode: bool = False
    options_mode: bool = False
    target_select: bool = False
    target_index: Optional[int] = None
    target_command: Optional[str] = None
    battle_log: list[str] = field(default_factory=list)
    action_cursor: int = 0
    menu_cursor: int = 0
    spell_cursor: int = 0
    battle_cursor: int = 0
    level_cursor: int = 0
    defend_active: bool = False
    defend_bonus: int = 0
    defend_evasion: float = 0.0
    action_effect_override: Optional[dict] = None
    level_up_notes: list[str] = field(default_factory=list)
    last_spell_targets: list[int] = field(default_factory=list)
    current_venue_id: Optional[str] = None
