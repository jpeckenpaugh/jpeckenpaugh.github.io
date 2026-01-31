"""Command registry and dispatch helpers."""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from app.data_access.items_data import ItemsData
from app.data_access.spells_data import SpellsData
from app.models import Player, Opponent

CommandHandler = Callable[["CommandContext"], Optional[str]]


@dataclass
class CommandContext:
    player: Player
    opponents: List[Opponent]
    loot: dict
    spells_data: SpellsData
    items_data: ItemsData
    target_index: Optional[int] = None


class CommandRegistry:
    def __init__(self):
        self._handlers: Dict[str, CommandHandler] = {}

    def register(self, command_id: str, handler: CommandHandler):
        self._handlers[command_id] = handler

    def dispatch(self, command_id: str, ctx: CommandContext) -> Optional[str]:
        handler = self._handlers.get(command_id)
        if handler is None:
            return None
        return handler(ctx)


def dispatch_command(
    registry: CommandRegistry,
    command_id: str,
    ctx: CommandContext
) -> str:
    handled = registry.dispatch(command_id, ctx)
    if handled is not None:
        return handled
    return "Unknown action."
