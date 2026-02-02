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
    stats_mode: bool
    spell_mode: bool
    followers_mode: bool = False
    quit_confirm: bool = False
    title_mode: bool = False
    shop_view: str = "menu"
    element_mode: bool = False
    alchemist_mode: bool = False
    alchemy_first: Optional[str] = None
    alchemy_selecting: bool = False
    temple_mode: bool = False
    smithy_mode: bool = False
    portal_mode: bool = False
    quest_mode: bool = False
    quest_detail_mode: bool = False
    options_mode: bool = False
    target_select: bool = False
    target_index: Optional[int] = None
    target_command: Optional[str] = None
    battle_log: list[str] = field(default_factory=list)
    action_cursor: int = 0
    menu_cursor: int = 0
    spell_cursor: int = 0
    spell_cast_rank: int = 1
    spell_target_mode: bool = False
    spell_target_cursor: int = 0
    spell_target_command: Optional[str] = None
    battle_cursor: int = 0
    level_cursor: int = 0
    defend_active: bool = False
    defend_bonus: int = 0
    defend_evasion: float = 0.0
    action_effect_override: Optional[dict] = None
    level_up_notes: list[str] = field(default_factory=list)
    last_spell_targets: list[int] = field(default_factory=list)
    team_target_index: Optional[int] = None
    last_team_target_player: Optional[bool] = None
    current_venue_id: Optional[str] = None
    follower_dismiss_pending: Optional[int] = None
    followers_focus: str = "list"
    followers_action_cursor: int = 0
    follower_equip_mode: bool = False
    follower_equip_target: Optional[int] = None
    title_menu_stack: list[str] = field(default_factory=list)
    quest_continent_index: int = 0
    quest_detail_id: Optional[str] = None
    quest_detail_page: int = 0
    quest_audio_played: bool = False
    quest_detail_audio_key: Optional[str] = None
    screen_audio_key: Optional[str] = None
    asset_explorer_type: Optional[str] = None
    asset_explorer_show_art: bool = True
    asset_explorer_show_stats: bool = True
    asset_explorer_show_json: bool = True
    asset_explorer_focus: str = "list"
    asset_explorer_info_scroll: int = 0
    asset_explorer_preview_key: Optional[str] = None
    prev_follower_count: int = 0
