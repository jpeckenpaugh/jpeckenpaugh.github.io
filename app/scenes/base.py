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

    def input_timeout_seconds(self) -> Optional[float]:
        return None

    def needs_redraw(self, app: "GameApp") -> bool:
        return False

    def handle_input(self, app: "GameApp", key: str) -> SceneResult:
        raise NotImplementedError
