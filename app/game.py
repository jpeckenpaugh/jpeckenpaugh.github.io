from app.io.input_adapter import InputAdapter
from app.io.renderer import Renderer
from app.scenes.asset_explorer import AssetExplorerScene
from app.scenes.base import SceneResult
from app.scenes.title import TitleScene
from app.services.asset_repository import AssetRepository
from app.services.save_service import SaveGameService
from app.session import GameSession, Player


class GameApp:
    def __init__(self) -> None:
        self.renderer = Renderer()
        self.input = InputAdapter()
        self.save_service = SaveGameService()
        self.asset_repository = AssetRepository()
        self.session = self.new_session()
        self.scenes = {
            "title": TitleScene(),
            "asset_explorer": AssetExplorerScene(),
        }
        self.running = True

    def new_session(self) -> GameSession:
        return GameSession(player=Player())

    def active_scene(self):
        return self.scenes.get(self.session.current_scene_id, self.scenes["title"])

    def apply_result(self, result: SceneResult) -> None:
        if result.next_scene_id:
            self.session.current_scene_id = result.next_scene_id
        if result.save_now:
            self.save_service.save(self.session, self.session.selected_slot)
        if result.quit_game:
            self.running = False

    def run(self) -> None:
        force_render = True
        while self.running:
            scene = self.active_scene()
            timeout = scene.input_timeout_seconds()
            if force_render or scene.needs_redraw(self):
                frame = scene.render(self)
                self.renderer.render_text(frame)
                force_render = False
            if timeout is None:
                key = self.input.read_key()
            else:
                key = self.input.read_key_timeout(timeout)
                if key is None:
                    continue
            result = scene.handle_input(self, key)
            previous_scene_id = self.session.current_scene_id
            self.apply_result(result)
            force_render = True
            if self.session.current_scene_id != previous_scene_id:
                force_render = True
        self.renderer.clear()
        print("Exited game.")
