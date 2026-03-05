from app.scenes.base import Scene, SceneResult
from app.rendering.title_panorama import TitlePanorama
import time
import random


class TitleScene(Scene):
    scene_id = "title"
    _CLOUD_RGB_PALETTE = [
        (255, 255, 255),
        (236, 240, 246),
        (214, 222, 235),
        (198, 216, 246),
        (178, 204, 242),
    ]

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
        self._last_blink_phase = -1
        self._last_cloud_phase = -1
        self._cloud_rng = random.Random(int(time.time() * 1000) & 0xFFFFFFFF)
        self._clouds: list[dict] = []
        self._cloud_templates: dict[str, list[dict]] = {"small": [], "medium": [], "large": []}
        self._last_cloud_update = time.time()

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
        self._load_cloud_templates()
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

    def _load_cloud_templates(self) -> None:
        templates: dict[str, list[dict]] = {"small": [], "medium": [], "large": []}
        for object_id, payload in self._objects_data.items():
            if not isinstance(object_id, str) or not object_id.startswith("cloud_"):
                continue
            if not isinstance(payload, dict):
                continue
            if "_small_" in object_id:
                size = "small"
            elif "_medium_" in object_id:
                size = "medium"
            elif "_large_" in object_id:
                size = "large"
            else:
                continue
            art = payload.get("art", [])
            mask = payload.get("color_mask", [])
            if not isinstance(art, list) or not art:
                continue
            if not isinstance(mask, list):
                mask = []
            width = max((len(str(line)) for line in art), default=1)
            rows: list[list[str]] = []
            for y, raw_line in enumerate(art):
                line = str(raw_line).ljust(width)
                mask_line = str(mask[y]) if y < len(mask) else ""
                row: list[str] = []
                for x, ch in enumerate(line):
                    if ch == " ":
                        row.append(" ")
                        continue
                    key = mask_line[x] if x < len(mask_line) else "l"
                    code = self._cloud_color_code(object_id, y, x, key)
                    row.append(f"{code}{ch}\x1b[0m")
                rows.append(row)
            templates[size].append(
                {
                    "id": object_id,
                    "rows": rows,
                    "width": width,
                    "height": len(rows),
                    "size": size,
                }
            )
        self._cloud_templates = templates
        if not self._clouds:
            self._seed_initial_clouds()

    def _cloud_color_code(self, object_id: str, row: int, col: int, mask_key: str) -> str:
        seed = 2166136261
        for ch in f"{object_id}:{row}:{col}:{mask_key}":
            seed ^= ord(ch)
            seed = (seed * 16777619) & 0xFFFFFFFF
        idx = seed % len(self._CLOUD_RGB_PALETTE)
        r, g, b = self._CLOUD_RGB_PALETTE[idx]
        return f"\x1b[38;2;{r};{g};{b}m"

    def _seed_initial_clouds(self) -> None:
        total = 10
        for slot in range(total):
            self._spawn_cloud(initial=True, slot=slot, total_slots=total)

    def _cloud_phase(self) -> int:
        return int(time.time() * 10.0)

    def _cloud_speed(self, size: str, y: int) -> float:
        size_weight = {"large": 0.72, "medium": 1.0, "small": 1.28}.get(size, 1.0)
        height_norm = max(0.0, min(1.0, y / max(1, (self._screen_height // 2) - 1)))
        height_weight = 0.72 + (0.62 * height_norm)
        variance = 0.9 + (self._cloud_rng.random() * 0.2)
        return 1.0 * size_weight * height_weight * variance

    def _pick_cloud_size(self) -> str:
        weights = [("small", 0.30), ("medium", 0.45), ("large", 0.25)]
        total = sum(weight for _, weight in weights)
        roll = self._cloud_rng.random() * total
        acc = 0.0
        for size, weight in weights:
            acc += weight
            if roll <= acc:
                return size
        return "medium"

    def _spawn_cloud(self, initial: bool = False, slot: int = 0, total_slots: int = 1) -> None:
        size = self._pick_cloud_size()
        candidates = self._cloud_templates.get(size, [])
        if not candidates:
            for fallback in ("medium", "small", "large"):
                candidates = self._cloud_templates.get(fallback, [])
                if candidates:
                    size = fallback
                    break
        if not candidates:
            return
        template = candidates[self._cloud_rng.randrange(len(candidates))]
        h = int(template["height"])
        sky_height = self._screen_height // 2
        y_min = 0
        y_max = max(0, sky_height - h)
        if size == "large":
            y_min = min(y_max, 1)
            y_max = max(y_min, y_max)
        elif size == "small":
            y_max = max(y_min, sky_height - h)
        y = self._cloud_rng.randint(y_min, y_max) if y_max >= y_min else 0
        speed = self._cloud_speed(size, y)
        width = int(template.get("width", 1))
        if initial:
            segments = max(1, total_slots)
            seg_w = max(1, self._screen_width // segments)
            seg_start = slot * seg_w
            seg_end = self._screen_width - 1 if slot == segments - 1 else ((slot + 1) * seg_w - 1)
            min_x = seg_start - max(1, width // 2)
            max_x = max(min_x, seg_end)
            start_x = self._cloud_rng.randint(min_x, max_x)
        else:
            start_x = self._screen_width + self._cloud_rng.randint(2, 28)
        self._clouds.append(
            {
                "template": template,
                "x": float(start_x),
                "y": y,
                "speed": speed,
            }
        )

    def _update_clouds(self, now: float) -> None:
        dt = max(0.0, min(0.4, now - self._last_cloud_update))
        self._last_cloud_update = now
        for cloud in self._clouds:
            speed = float(cloud.get("speed", 1.0))
            cloud["x"] = float(cloud.get("x", 0.0)) - (speed * dt)
            width = int(cloud.get("template", {}).get("width", 0))
            if cloud["x"] + width < 0:
                cloud["x"] = self._screen_width + (cloud["x"] + width)

    def _overlay_clouds(self, lines: list[str]) -> None:
        sky_height = self._screen_height // 2
        composed_rows: dict[int, list[str]] = {}
        for cloud in self._clouds:
            template = cloud.get("template", {})
            rows = template.get("rows", [])
            if not isinstance(rows, list):
                continue
            x0 = int(float(cloud.get("x", 0.0)))
            y0 = int(cloud.get("y", 0))
            for row_idx, row_cells in enumerate(rows):
                y = y0 + row_idx
                if y < 0 or y >= len(lines):
                    continue
                # Keep clouds in the full top-half sky region above panorama anchor.
                if y >= sky_height:
                    continue
                if not isinstance(row_cells, list):
                    continue
                if y not in composed_rows:
                    composed_rows[y] = list(lines[y])
                base = composed_rows[y]
                for col_idx, cell in enumerate(row_cells):
                    x = x0 + col_idx
                    if x < 0 or x >= self._screen_width:
                        continue
                    if cell != " ":
                        base[x] = cell
        for y, cells in composed_rows.items():
            lines[y] = "".join(cells)

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
        return self._logo_gradient_code(x, y, self._screen_width, self._screen_height)

    def _white_code(self) -> str:
        return "\x1b[38;2;255;255;255m"

    def _colorize_menu_line(self, text: str, y: int, start_x: int) -> str:
        visible_text = self._strip_ansi(text)
        width = len(visible_text)
        is_top_bottom = width >= 2 and visible_text[0] == "o" and visible_text[-1] == "o"
        out: list[str] = []
        i = 0
        style_active = False
        visible_idx = 0
        while i < len(text):
            ch = text[i]
            if ch == "\x1b" and i + 1 < len(text) and text[i + 1] == "[":
                j = i + 2
                while j < len(text) and text[j] != "m":
                    j += 1
                if j < len(text):
                    seq = text[i : j + 1]
                    out.append(seq)
                    if seq == "\x1b[0m":
                        style_active = False
                    else:
                        style_active = True
                    i = j + 1
                    continue
            if ch == " ":
                out.append(" ")
            else:
                is_side_border = visible_idx == 0 or visible_idx == width - 1
                is_top_bottom_border = is_top_bottom and ch in ("o", "-")
                is_frame = is_side_border or is_top_bottom_border
                if style_active and not is_frame:
                    out.append(ch)
                else:
                    code = self._gradient_code(start_x + visible_idx, y) if is_frame else self._white_code()
                    out.append(f"{code}{ch}\x1b[0m")
            visible_idx += 1
            i += 1
        return "".join(out)

    def _strip_ansi(self, text: str) -> str:
        out: list[str] = []
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "\x1b" and i + 1 < len(text) and text[i + 1] == "[":
                j = i + 2
                while j < len(text) and text[j] != "m":
                    j += 1
                if j < len(text):
                    i = j + 1
                    continue
            out.append(ch)
            i += 1
        return "".join(out)

    def _button_row(self, inner: int) -> str:
        accept = "\x1b[30;42m[ A / Accept ]\x1b[0m"
        cancel = "\x1b[90m[ S / Cancel ]\x1b[0m"
        spacer = " " * 5
        body = accept + spacer + cancel
        visible = len(self._strip_ansi(body))
        pad_left = max(0, (inner - visible) // 2)
        pad_right = max(0, inner - visible - pad_left)
        return (" " * pad_left) + body + (" " * pad_right)

    def _blink_phase(self) -> int:
        return int(time.time() * 2.0)

    def _title_subheading(self, y: int, start_x: int) -> str:
        left = "*-----<{([  "
        mid = "AI World Engine"
        right = "  ])}>-----*"
        full = left + mid + right
        out: list[str] = []
        for i, ch in enumerate(full):
            if ch == " ":
                out.append(" ")
            elif len(left) <= i < len(left) + len(mid):
                out.append(f"{self._white_code()}{ch}\x1b[0m")
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

    def _menu_box_lines(self, app: "GameApp", blink_on: bool) -> list[str]:
        width = 46
        inner = width - 2
        lines: list[str] = []
        lines.append("o" + ("-" * inner) + "o")
        lines.append("|" + (" " * inner) + "|")
        for idx, label in enumerate(self._options):
            enabled = self._option_enabled(app, idx)
            suffix = "" if enabled else " (no save)"
            if idx == self._cursor:
                left_bracket = "[" if blink_on else " "
                right_bracket = "]" if blink_on else " "
                text = f" {left_bracket} {label}{suffix} {right_bracket}"
            else:
                text = f"   {label}{suffix}"
            lines.append("|" + text.ljust(inner)[:inner] + "|")
        lines.append("|" + (" " * inner) + "|")
        lines.append("|" + f" Slot: {app.session.selected_slot}".ljust(inner)[:inner] + "|")
        if app.session.last_message:
            lines.append("|" + f" {app.session.last_message}".ljust(inner)[:inner] + "|")
        else:
            lines.append("|" + (" " * inner) + "|")
        lines.append("|" + self._button_row(inner) + "|")
        lines.append("o" + ("-" * inner) + "o")
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
        if self._blink_phase() != self._last_blink_phase:
            return True
        if self._cloud_phase() != self._last_cloud_phase:
            return True
        if self._signature(app) != self._last_signature:
            return True
        return self._panorama.offset() != self._last_drawn_offset

    def render(self, app: "GameApp") -> str:
        self._ensure_panorama(app)
        continue_enabled = app.save_service.has_slot(app.session.selected_slot)
        offset = self._panorama.offset()
        blink_phase = self._blink_phase()
        blink_on = (blink_phase % 2) == 0
        self._last_blink_phase = blink_phase
        self._last_cloud_phase = self._cloud_phase()
        self._update_clouds(time.time())
        self._last_drawn_offset = offset
        self._last_signature = self._signature(app)
        lines = [" " * self._screen_width for _ in range(self._screen_height)]
        self._overlay_clouds(lines)

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

        subtitle_y = logo_start_y + logo_height + 1
        if 0 <= subtitle_y < self._screen_height:
            subtitle_width = len("*-----<{([  AI World Engine  ])}>-----*")
            start_x = max(0, (self._screen_width - subtitle_width) // 2)
            subtitle = self._title_subheading(subtitle_y, start_x)
            lines[subtitle_y] = (" " * start_x) + subtitle + (" " * max(0, self._screen_width - start_x - subtitle_width))

        menu_lines = self._menu_box_lines(app, blink_on=blink_on)
        menu_start_y = 8
        for idx, line in enumerate(menu_lines):
            y = menu_start_y + idx
            if 0 <= y < self._screen_height:
                visible_len = len(self._strip_ansi(line))
                start_x = max(0, (self._screen_width - visible_len) // 2)
                colored = self._colorize_menu_line(line, y, start_x)
                lines[y] = (" " * start_x) + colored + (" " * max(0, self._screen_width - start_x - visible_len))

        if not continue_enabled and self._cursor == 0:
            self._move(app, 1)
        return "\n".join(lines)

    def handle_input(self, app: "GameApp", key: str) -> SceneResult:
        if key == "up":
            self._move(app, -1)
            return SceneResult()
        if key == "down":
            self._move(app, 1)
            return SceneResult()
        if key == "back":
            return SceneResult(quit_game=True)
        if key == "options":
            app.options_return_scene_id = "title"
            return SceneResult(next_scene_id="options")
        if key != "confirm":
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
