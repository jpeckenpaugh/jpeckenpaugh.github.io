"""Shop-related helpers for purchases."""

from app.data_access.items_data import ItemsData
from app.models import Player


def purchase_item(player: Player, items_data: ItemsData, key: str) -> str:
    item = items_data.get(key)
    if not item:
        return "That item is not available."
    price = int(item.get("price", 0))
    if player.gold < price:
        return "Not enough GP."
    player.gold -= price
    player.add_item(key, 1)
    return f"Purchased {item.get('name', key)}."
