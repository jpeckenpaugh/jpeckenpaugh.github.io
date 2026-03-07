"""Sync player state against data-driven unlocks."""

from typing import List


def _ordered_elements(order: List[str], elements: List[str]) -> List[str]:
    if order:
        return [element for element in order if element in elements] or elements
    return elements


def sync_player_elements(ctx, player) -> None:
    order = []
    unlocks = {}
    if hasattr(ctx, "continents"):
        order = list(ctx.continents.order() or [])
        unlocks = ctx.continents.unlocks() if hasattr(ctx.continents, "unlocks") else {}
    elements = list(getattr(player, "elements", []) or [])
    if unlocks:
        elements = [element for element in order if unlocks.get(element, 0) <= player.level]
    elements = _ordered_elements(order, elements)
    if not elements:
        elements = [order[0]] if order else ["base"]
    if player.current_element not in elements:
        player.current_element = elements[0]
    player.elements = elements
