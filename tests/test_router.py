import json
import os
import tempfile
import unittest

from app.commands.router import CommandState, RouterContext, handle_command
from app.data_access.commands_data import CommandsData
from app.data_access.items_data import ItemsData
from app.data_access.menus_data import MenusData
from app.data_access.opponents_data import OpponentsData
from app.data_access.save_data import SaveData
from app.data_access.scenes_data import ScenesData
from app.data_access.spells_data import SpellsData
from app.data_access.venues_data import VenuesData
from app.models import Player
from app.commands import build_registry


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.data_dir = self.tmpdir.name
        self._write_json(
            "scenes.json",
            {
                "town": {
                    "commands": [
                        {"key": "F", "command": "ENTER_SCENE", "target": "forest"},
                        {"key": "S", "command": "ENTER_VENUE", "target": "town_shop"},
                    ]
                },
                "forest": {"commands": []},
            },
        )
        self._write_json("commands.json", {"global": []})
        self._write_json("venues.json", {"town_shop": {"welcome_message": "Welcome to the shop."}})
        self._write_json("opponents.json", {})
        self._write_json("items.json", {})
        self._write_json("menus.json", {})
        self._write_json("spells.json", {})

        self.items = ItemsData(os.path.join(self.data_dir, "items.json"))
        self.opponents = OpponentsData(os.path.join(self.data_dir, "opponents.json"))
        self.scenes = ScenesData(os.path.join(self.data_dir, "scenes.json"))
        self.commands = CommandsData(os.path.join(self.data_dir, "commands.json"))
        self.venues = VenuesData(os.path.join(self.data_dir, "venues.json"))
        self.menus = MenusData(os.path.join(self.data_dir, "menus.json"))
        self.spells = SpellsData(os.path.join(self.data_dir, "spells.json"))
        self.save_data = SaveData(os.path.join(self.data_dir, "save.json"))
        self.registry = build_registry()

        self.ctx = RouterContext(
            items=self.items,
            opponents_data=self.opponents,
            scenes=self.scenes,
            commands=self.commands,
            venues=self.venues,
            save_data=self.save_data,
            spells=self.spells,
            menus=self.menus,
            registry=self.registry,
        )

    def _write_json(self, name: str, payload: dict):
        with open(os.path.join(self.data_dir, name), "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def test_enter_scene_forest(self):
        player = Player.from_dict({})
        player.location = "Town"
        state = CommandState(
            player=player,
            opponents=[],
            loot_bank={"xp": 0, "gold": 0},
            last_message="",
            shop_mode=False,
            inventory_mode=False,
            inventory_items=[],
            hall_mode=False,
            hall_view="menu",
            inn_mode=False,
            spell_mode=False,
            action_cmd=None,
        )
        handled = handle_command("ENTER_SCENE", state, self.ctx, key="F")
        self.assertTrue(handled)
        self.assertEqual(state.player.location, "Forest")

    def test_enter_venue_shop(self):
        player = Player.from_dict({})
        player.location = "Town"
        state = CommandState(
            player=player,
            opponents=[],
            loot_bank={"xp": 0, "gold": 0},
            last_message="",
            shop_mode=False,
            inventory_mode=False,
            inventory_items=[],
            hall_mode=False,
            hall_view="menu",
            inn_mode=False,
            spell_mode=False,
            action_cmd=None,
        )
        handled = handle_command("ENTER_VENUE", state, self.ctx, key="S")
        self.assertTrue(handled)
        self.assertTrue(state.shop_mode)
        self.assertEqual(state.last_message, "Welcome to the shop.")


if __name__ == "__main__":
    unittest.main()
