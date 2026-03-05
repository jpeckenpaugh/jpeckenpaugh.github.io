from dataclasses import dataclass
from typing import Optional


@dataclass
class SceneResult:
    next_scene_id: Optional[str] = None
    quit_game: bool = False
    save_now: bool = False


class Scene:
    scene_id: str = "base"

    def render(self, app: "GameApp") -> str:
        raise NotImplementedError

    def handle_input(self, app: "GameApp", key: str) -> SceneResult:
        raise NotImplementedError