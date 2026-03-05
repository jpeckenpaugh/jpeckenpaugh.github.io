from app.scenes.base import Scene, SceneResult


class OptionsScene(Scene):
    scene_id = "options"

    def __init__(self) -> None:
        self._screen_width = 100
        self._screen_height = 30

    def _render_line(self, text: str, width: int) -> str:
        return "|" + text.center(width - 2)[: width - 2] + "|"

    def render(self, app: "GameApp") -> str:
        w = self._screen_width
        h = self._screen_height
        lines: list[str] = []
        lines.append("+" + ("-" * (w - 2)) + "+")
        lines.append(self._render_line("Options", w))
        lines.append("+" + ("-" * (w - 2)) + "+")
        body = [
            "",
            "Legacy Controls",
            "Arrow keys: move/select",
            "A: confirm / yes",
            "S or Esc: back / no",
            "Enter: options menu",
            "",
            "Press S or Esc to return.",
        ]
        for row in range(h - 4):
            text = body[row] if row < len(body) else ""
            lines.append(self._render_line(text, w))
        lines.append("+" + ("-" * (w - 2)) + "+")
        return "\n".join(lines[:h])

    def handle_input(self, app: "GameApp", key: str) -> SceneResult:
        if key in ("back",):
            return SceneResult(next_scene_id=getattr(app, "options_return_scene_id", "title"))
        if key in ("options",):
            return SceneResult(next_scene_id=getattr(app, "options_return_scene_id", "title"))
        return SceneResult()
