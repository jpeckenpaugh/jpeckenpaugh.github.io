from app.scenes.base import Scene, SceneResult
from app.rendering.title_panorama import TitlePanorama


class TitleScene(Scene):
    scene_id = "title"

    def __init__(self) -> None:
        self._options = ["Continue", "New Game", "Asset Explorer", "Quit"]
        self._cursor = 0
        self._last_drawn_offset = -1
        self._last_signature = ""
        self._panorama = None
        self._objects_data = {}
        self._colors_data = {}
        self._screen_width = 100
        self._screen_height = 30

    def _ensure_panorama(self, app: "GameApp") -> None:
        if self._panorama is not None:
            return
        scenes_data = {}
        objects_data = {}
        colors_data = {}
        opponents_data = {}
        try:
            scenes_data = app.asset_repository.load("scenes.json")
            objects_data = app.asset_repository.load("objects.json")
            colors_data = app.asset_repository.load("colors.json")
            opponents_data = app.asset_repository.load("opponents.json")
        except Exception:
            scenes_data = {}
            objects_data = {}
            colors_data = {}
            opponents_data = {}
        self._objects_data = objects_data if isinstance(objects_data, dict) else {}
        self._colors_data = colors_data if isinstance(colors_data, dict) else {}
        self._panorama = TitlePanorama(
            viewport_width=100,
            height=15,
            speed=1.0,
            forest_width_scale=0.5,
            scenes_data=scenes_data,
            objects_data=objects_data,
            colors_data=colors_data,
            opponents_data=opponents_data,
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

    def _hex_to_ansi(self, hex_code: str) -> str:
        value = str(hex_code or "").strip().lstrip("#")
        if len(value) != 6:
            return ""
        try:
            r = int(value[0:2], 16)
            g = int(value[2:4], 16)
            b = int(value[4:6], 16)
        except ValueError:
            return ""
        return f"\x1b[38;2;{r};{g};{b}m"

    def _color_code_for_key(self, key: str) -> str:
        entry = self._colors_data.get(key, {})
        if not isinstance(entry, dict):
            return ""
        return self._hex_to_ansi(entry.get("hex", ""))

    def _gradient_code(self, x: int, y: int) -> str:
        width = max(1, self._screen_width - 1)
        height = max(1, self._screen_height - 1)
        t = (x / width + y / height) / 2.0
        start = (180, 180, 210)
        mid = (95, 140, 235)
        end = (80, 90, 120)
        if t <= 0.5:
            tt = t / 0.5
            r = int(start[0] + (mid[0] - start[0]) * tt)
            g = int(start[1] + (mid[1] - start[1]) * tt)
            b = int(start[2] + (mid[2] - start[2]) * tt)
        else:
            tt = (t - 0.5) / 0.5
            r = int(mid[0] + (end[0] - mid[0]) * tt)
            g = int(mid[1] + (end[1] - mid[1]) * tt)
            b = int(mid[2] + (end[2] - mid[2]) * tt)
        return f"\x1b[38;2;{r};{g};{b}m"

    def _colorize_text_line(self, text: str, y: int, start_x: int) -> str:
        out: list[str] = []
        for i, ch in enumerate(text):
            if ch == " ":
                out.append(" ")
            else:
                code = self._gradient_code(start_x + i, y)
                out.append(f"{code}{ch}\x1b[0m")
        return "".join(out)

    def _logo_gradient_code(self, x: int, y: int, width: int, height: int) -> str:
        if width <= 1 and height <= 1:
            r, g, b = (192, 192, 192)
            return f"\x1b[38;2;{r};{g};{b}m"
        t = ((x / max(1, width - 1)) + (y / max(1, height - 1))) / 2.0
        if t <= 0.5:
            tt = t / 0.5
            start = (192, 192, 192)
            end = (77, 77, 255)
        else:
            tt = (t - 0.5) / 0.5
            start = (77, 77, 255)
            end = (96, 96, 96)
        r = int(start[0] + (end[0] - start[0]) * tt)
        g = int(start[1] + (end[1] - start[1]) * tt)
        b = int(start[2] + (end[2] - start[2]) * tt)
        return f"\x1b[38;2;{r};{g};{b}m"

    def _logo_lines(self) -> tuple[list[str], str]:
        logo = self._objects_data.get("lokarta_logo", {})
        art = logo.get("art", []) if isinstance(logo, dict) else []
        blocking = str(logo.get("blocking_space", "#")) if isinstance(logo, dict) else "#"
        if not isinstance(art, list) or not art:
            return [], "#"
        return [str(line) for line in art], (blocking if len(blocking) == 1 else "#")

    def _menu_box_lines(self, app: "GameApp") -> list[str]:
        width = 46
        inner = width - 2
        lines: list[str] = []
        lines.append("+" + ("-" * inner) + "+")
        lines.append("|" + " Main Menu ".center(inner, " ") + "|")
        lines.append("|" + (" " * inner) + "|")
        for idx, label in enumerate(self._options):
            enabled = self._option_enabled(app, idx)
            cursor = ">" if idx == self._cursor else " "
            suffix = "" if enabled else " (no save)"
            text = f" {cursor} {label}{suffix}"
            lines.append("|" + text.ljust(inner)[:inner] + "|")
        lines.append("|" + (" " * inner) + "|")
        lines.append("|" + f" Slot: {app.session.selected_slot}".ljust(inner)[:inner] + "|")
        if app.session.last_message:
            lines.append("|" + f" {app.session.last_message}".ljust(inner)[:inner] + "|")
        else:
            lines.append("|" + (" " * inner) + "|")
        lines.append("|" + " W/S move  Enter confirm  Q quit ".ljust(inner)[:inner] + "|")
        lines.append("+" + ("-" * inner) + "+")
        return lines

    def _signature(self, app: "GameApp") -> str:
        return "|".join(
            [
                str(self._cursor),
                str(app.session.selected_slot),
                str(app.session.last_message),
                str(app.save_service.has_slot(app.session.selected_slot)),
            ]
        )

    def needs_redraw(self, app: "GameApp") -> bool:
        self._ensure_panorama(app)
        if self._signature(app) != self._last_signature:
            return True
        return self._panorama.offset() != self._last_drawn_offset

    def render(self, app: "GameApp") -> str:
        self._ensure_panorama(app)
        continue_enabled = app.save_service.has_slot(app.session.selected_slot)
        offset = self._panorama.offset()
        self._last_drawn_offset = offset
        self._last_signature = self._signature(app)
        lines = [" " * self._screen_width for _ in range(self._screen_height)]

        pano_lines = self._panorama.viewport()
        pano_start_y = self._screen_height - len(pano_lines)
        for idx, line in enumerate(pano_lines):
            y = pano_start_y + idx
            if 0 <= y < self._screen_height:
                lines[y] = line

        logo_lines, blocking_char = self._logo_lines()
        logo_start_y = 1
        logo_height = max(1, len(logo_lines))
        logo_width = max((len(line) for line in logo_lines), default=1)
        for idx, line in enumerate(logo_lines):
            y = logo_start_y + idx
            if 0 <= y < self._screen_height:
                start_x = max(0, (self._screen_width - logo_width) // 2)
                rendered: list[str] = []
                for col in range(logo_width):
                    ch = line[col] if col < len(line) else " "
                    if ch == blocking_char:
                        rendered.append(" ")
                    elif ch == " ":
                        rendered.append(" ")
                    else:
                        code = self._logo_gradient_code(col, idx, logo_width, logo_height)
                        rendered.append(f"{code}{ch}\x1b[0m")
                row = "".join(rendered)
                lines[y] = (" " * start_x) + row + (" " * max(0, self._screen_width - start_x - logo_width))

        menu_lines = self._menu_box_lines(app)
        menu_start_y = 8
        for idx, line in enumerate(menu_lines):
            y = menu_start_y + idx
            if 0 <= y < self._screen_height:
                plain_len = len(line)
                start_x = max(0, (self._screen_width - plain_len) // 2)
                colored = self._colorize_text_line(line, y, start_x)
                lines[y] = (" " * start_x) + colored + (" " * max(0, self._screen_width - start_x - plain_len))

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
