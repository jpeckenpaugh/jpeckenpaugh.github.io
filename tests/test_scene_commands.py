import json
import os
import tempfile
import unittest

from app.commands.scene_commands import scene_commands
from app.data_access.commands_data import CommandsData
from app.data_access.scenes_data import ScenesData
from app.models import Player


class TestSceneCommands(unittest.TestCase):
    def test_title_excludes_global_commands(self) -> None:
        scenes_payload = {
            "title": {
                "commands": [
                    {"key": "N", "label": "New", "command": "TITLE_NEW"}
                ]
            }
        }
        commands_payload = {
            "global": [
                {"key": "M", "label": "Magic", "command": "SPELLBOOK"}
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            scenes_path = os.path.join(temp_dir, "scenes.json")
            commands_path = os.path.join(temp_dir, "commands.json")
            with open(scenes_path, "w", encoding="utf-8") as f:
                json.dump(scenes_payload, f)
            with open(commands_path, "w", encoding="utf-8") as f:
                json.dump(commands_payload, f)

            scenes = ScenesData(scenes_path)
            commands = CommandsData(commands_path)
            player = Player.from_dict({})
            results = scene_commands(scenes, commands, "title", player, [])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].get("command"), "TITLE_NEW")


if __name__ == "__main__":
    unittest.main()
