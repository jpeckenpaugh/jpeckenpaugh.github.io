import json
import os
import tempfile
import unittest

from app.data_access.spells_data import SpellsData


class TestSpellsData(unittest.TestCase):
    def test_lookup_by_command_and_menu(self) -> None:
        payload = {
            "healing": {"command_id": "HEAL", "menu_key": "NUM1"},
            "spark": {"command_id": "SPARK", "menu_key": "NUM2"},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "spells.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            data = SpellsData(path)

        spell_id, spell = data.by_command_id("HEAL")
        self.assertEqual(spell_id, "healing")
        self.assertEqual(spell.get("menu_key"), "NUM1")

        spell_id, spell = data.by_menu_key("NUM2")
        self.assertEqual(spell_id, "spark")
        self.assertEqual(spell.get("command_id"), "SPARK")

        self.assertIsNone(data.by_command_id("UNKNOWN"))
        self.assertIsNone(data.by_menu_key("NUM9"))


if __name__ == "__main__":
    unittest.main()
