"""Shop-related helpers for purchases."""

from app.data_access.items_data import ItemsData
from app.models import Player


def _format_shop_label(item: dict) -> str:
    name = item.get("name", "Item")
    if item.get("type") == "gear":
        atk = int(item.get("atk", 0))
        defense = int(item.get("defense", 0))
        bonus = []
        if atk:
            bonus.append(f"ATK+{atk}")
        if defense:
            bonus.append(f"DEF+{defense}")
        detail = ", ".join(bonus) if bonus else "No bonuses"
        return f"{name} ({detail})"
    hp = int(item.get("hp", 0))
    mp = int(item.get("mp", 0))
    if hp or mp:
        return f"{name} (+{hp} HP/+{mp} MP)"
    return name


def shop_inventory(venue: dict, items_data: ItemsData, element: str) -> list[dict]:
    inventory_sets = venue.get("inventory_sets")
    if isinstance(inventory_sets, dict):
        entries = inventory_sets.get(element) or inventory_sets.get("base") or []
    else:
        entries = venue.get("inventory_items", [])
    output = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        item_id = entry.get("item_id")
        if not item_id:
            continue
        item = items_data.get(item_id, {})
        label = entry.get("label") or _format_shop_label(item)
        command = entry.get("command") or f"SHOP_{idx + 1}"
        output.append({"item_id": item_id, "label": label, "command": command})
    return output


def shop_commands(venue: dict, items_data: ItemsData, element: str) -> list[dict]:
    commands = []
    inventory = shop_inventory(venue, items_data, element)
    for entry in inventory:
        commands.append({
            "label": f"Buy {entry.get('label', '')}".strip(),
            "command": entry.get("command"),
        })
    for cmd in venue.get("commands", []):
        if cmd.get("command") == "B_KEY":
            commands.append(cmd)
            break
    return commands


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
