"""Shop-related helpers for purchases."""

from typing import Optional

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


def shop_sell_inventory(player: Player, items_data: ItemsData) -> list[dict]:
    entries = []
    idx = 0
    for key in sorted(player.inventory.keys()):
        count = int(player.inventory.get(key, 0))
        if count <= 0:
            continue
        item = items_data.get(key, {})
        name = item.get("name", key)
        price = int(item.get("price", 0))
        sell_price = price // 2
        label = f"{name} x{count}"
        entries.append({
            "key": f"item:{key}",
            "label": label,
            "price": sell_price,
            "command": f"SELL_{idx + 1}",
        })
        idx += 1
    for gear in player.gear_inventory:
        if not isinstance(gear, dict):
            continue
        gear_id = gear.get("id", "")
        name = gear.get("name", "Gear")
        price = int(gear.get("price", 0))
        sell_price = price // 2
        label = name
        entries.append({
            "key": f"gear:{gear_id}",
            "label": label,
            "price": sell_price,
            "command": f"SELL_{idx + 1}",
        })
        idx += 1
    return entries


def shop_commands(venue: dict, items_data: ItemsData, element: str, view: str, player: Optional[Player] = None) -> list[dict]:
    commands = []
    if view == "menu":
        commands = [
            {"label": "Purchase", "command": "SHOP_BUY"},
            {"label": "Sell", "command": "SHOP_SELL"},
        ]
    elif view == "buy":
        inventory = shop_inventory(venue, items_data, element)
        for entry in inventory:
            commands.append({
                "label": f"Buy {entry.get('label', '')}".strip(),
                "command": entry.get("command"),
            })
    elif view == "sell" and player is not None:
        inventory = shop_sell_inventory(player, items_data)
        for entry in inventory:
            commands.append({
                "label": f"Sell {entry.get('label', '')}".strip(),
                "command": entry.get("command"),
            })
    commands.append({"label": "Leave", "command": "B_KEY"})
    return commands


def purchase_item(player: Player, items_data: ItemsData, key: str) -> str:
    item = items_data.get(key)
    if not item:
        return "That item is not available."
    price = int(item.get("price", 0))
    if player.gold < price:
        return "Not enough GP."
    player.gold -= price
    if item.get("type") == "gear":
        player.add_gear(key, items_data)
    else:
        player.add_item(key, 1)
    return f"Purchased {item.get('name', key)}."


def sell_item(player: Player, items_data: ItemsData, key: str) -> str:
    if key.startswith("item:"):
        item_id = key.split(":", 1)[1]
        item = items_data.get(item_id)
        if not item:
            return "That item cannot be sold."
        if int(player.inventory.get(item_id, 0)) <= 0:
            return "You do not have that item."
        price = int(item.get("price", 0))
        player.inventory[item_id] = int(player.inventory.get(item_id, 0)) - 1
        if player.inventory[item_id] <= 0:
            player.inventory.pop(item_id, None)
        player.gold += price // 2
        return f"Sold {item.get('name', item_id)}."
    if key.startswith("gear:"):
        gear_id = key.split(":", 1)[1]
        gear = player.gear_instance(gear_id)
        if not gear:
            return "That item cannot be sold."
        price = int(gear.get("price", 0))
        for slot, equipped_id in list(player.equipment.items()):
            if equipped_id == gear_id:
                player.equipment.pop(slot, None)
        player.gear_inventory = [
            g for g in player.gear_inventory
            if not (isinstance(g, dict) and g.get("id") == gear_id)
        ]
        player._recalc_gear()
        player.gold += price // 2
        return f"Sold {gear.get('name', 'gear')}."
    return "That item cannot be sold."
