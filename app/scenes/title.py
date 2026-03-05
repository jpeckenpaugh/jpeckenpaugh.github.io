from app.scenes.base import Scene, SceneResult
from app.rendering.title_panorama import TitlePanorama


class TitleScene(Scene):
    scene_id = "title"

    def __init__(self) -> None:
        self._options = ["Continue", "New Game", "Asset Explorer", "Quit"]
        self._cursor = 0
        self._panorama = TitlePanorama(
            viewport_width=100,
            height=10,
            speed=1.0,
            forest_width_scale=0.5,
        )

    def input_timeout_seconds(self) -> float:
        return 0.1

    def _option_enabled(self, app: "GameApp", index: int) -> bool:
        label = self._options[index]
        if label == "Continue":
            return app.save_service.has_slot(app.session.selected_slot)
        return True

    def _move(self, app: "GameApp", delta: int) -> None:
        total = len(self._options)
        for _ in range(total):
            self._cursor = (self._cursor + delta) % total
            if self._option_enabled(app, self._cursor):
                return

    def render(self, app: "GameApp") -> str:
        continue_enabled = app.save_service.has_slot(app.session.selected_slot)
        lines = self._panorama.viewport()
        lines.extend([
            "-" * 100,
            "L O K A R T A".center(100),
            "Terminal RPG Rebuild".center(100),
            "-" * 100,
            "Use W/S or Arrow keys. Press Enter to confirm.".center(100),
            "",
        ])
        for idx, label in enumerate(self._options):
            enabled = self._option_enabled(app, idx)
            cursor = ">" if idx == self._cursor else " "
            suffix = "" if enabled else " (no save)"
            lines.append(f" {cursor} {label}{suffix}".center(100))
        lines.extend([
            "",
            f"Slot: {app.session.selected_slot}".center(100),
            app.session.last_message.center(100) if app.session.last_message else "",
            "",
            "Press Q any time to quit.".center(100),
        ])
        if not continue_enabled and self._cursor == 0:
            self._move(app, 1)
        return "\n".join(lines)

    def handle_input(self, app: "GameApp", key: str) -> SceneResult:
        if key in ("up", "w"):
            self._move(app, -1)
            return SceneResult()
        if key in ("down", "s"):
            self._move(app, 1)
            return SceneResult()
        if key == "q":
            return SceneResult(quit_game=True)
        if key != "enter":
            return SceneResult()

        choice = self._options[self._cursor]
        if choice == "Continue":
            loaded = app.save_service.load(app.session.selected_slot)
            if loaded is None:
                app.session.with_message("No save found in slot 1.")
                return SceneResult()
            app.session = loaded
            app.session.with_message("Save loaded. Gameplay scene not wired yet.")
            return SceneResult(save_now=False)

        if choice == "New Game":
            app.session = app.new_session()
            app.session.with_message("New game created. Gameplay scene not wired yet.")
            return SceneResult(save_now=True)

        if choice == "Asset Explorer":
            app.session.with_message("")
            return SceneResult(next_scene_id="asset_explorer")

        return SceneResult(quit_game=True)
