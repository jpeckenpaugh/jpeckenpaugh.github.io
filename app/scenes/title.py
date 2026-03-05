from app.scenes.base import Scene, SceneResult


class TitleScene(Scene):
    scene_id = "title"

    def __init__(self) -> None:
        self._options = ["Continue", "New Game", "Asset Explorer", "Quit"]
        self._cursor = 0

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
        lines = [
            "=" * 60,
            "                     L O K A R T A",
            "                 Terminal RPG Rebuild",
            "=" * 60,
            "",
            "Use W/S or Arrow keys. Press Enter to confirm.",
            "",
        ]
        for idx, label in enumerate(self._options):
            enabled = self._option_enabled(app, idx)
            cursor = ">" if idx == self._cursor else " "
            suffix = "" if enabled else " (no save)"
            lines.append(f" {cursor} {label}{suffix}")
        lines.extend([
            "",
            f"Slot: {app.session.selected_slot}",
            app.session.last_message,
            "",
            "Press Q any time to quit.",
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