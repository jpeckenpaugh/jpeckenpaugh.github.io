import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


ANSI_RESET = "\x1b[0m"


def _hex_to_ansi_fg(hex_code: str) -> str:
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


def _unit_hash(value: int) -> float:
    x = int(value) & 0xFFFFFFFF
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= (x >> 17)
    x ^= (x << 5) & 0xFFFFFFFF
    return (x & 0xFFFFFFFF) / 4294967295.0


@dataclass
class TileMap:
    cells: List[List[str]]

    @property
    def height(self) -> int:
        return len(self.cells)

    @property
    def width(self) -> int:
        return len(self.cells[0]) if self.cells else 0

    def slice_wrap(self, start_x: int, width: int) -> List[str]:
        if not self.cells:
            return []
        out: List[str] = []
        total = max(1, self.width)
        start = start_x % total
        for row in self.cells:
            normalized = row if len(row) >= total else row + ([" "] * (total - len(row)))
            if start + width <= total:
                view = normalized[start : start + width]
            else:
                first = normalized[start:]
                second = normalized[: width - len(first)]
                view = first + second
            out.append("".join(view))
        return out


class TitlePanorama:
    def __init__(
        self,
        viewport_width: int = 100,
        height: int = 10,
        speed: float = 1.0,
        forest_width_scale: float = 0.5,
        scenes_data: Optional[dict] = None,
        objects_data: Optional[dict] = None,
        colors_data: Optional[dict] = None,
        opponents_data: Optional[dict] = None,
    ) -> None:
        self.viewport_width = viewport_width
        self.height = height
        self.content_height = 10
        self.speed = speed
        self.scenes_data = scenes_data if isinstance(scenes_data, dict) else {}
        self.objects_data = objects_data if isinstance(objects_data, dict) else {}
        self.colors_data = colors_data if isinstance(colors_data, dict) else {}
        self.opponents_data = opponents_data if isinstance(opponents_data, dict) else {}
        self._color_code_cache: Dict[str, str] = {}
        base_forest_width = max(1, viewport_width // 2)
        self.forest_width = max(1, int(base_forest_width * max(0.1, min(1.0, forest_width_scale))))
        self.town_width = viewport_width
        self._start_time = time.time()
        self._map = self._build_map()

    def _color_code_for_key(self, key: str) -> str:
        if not key:
            return ""
        # Reserved: opaque/no-tint mask key.
        if key == "!":
            return ""
        if key in self._color_code_cache:
            return self._color_code_cache[key]
        entry = self.colors_data.get(key, {})
        hex_code = entry.get("hex", "") if isinstance(entry, dict) else ""
        code = _hex_to_ansi_fg(hex_code)
        self._color_code_cache[key] = code
        return code

    def _colorize(self, char: str, mask_char: str) -> str:
        if char == " ":
            return " "
        code = self._color_code_for_key(mask_char)
        if not code:
            return char
        return f"{code}{char}{ANSI_RESET}"

    def _object_art(self, object_id: str) -> List[str]:
        obj = self.objects_data.get(object_id, {})
        art = obj.get("art", []) if isinstance(obj, dict) else []
        if not isinstance(art, list):
            return []
        return [str(line) for line in art]

    def _object_mask(self, object_id: str) -> List[str]:
        obj = self.objects_data.get(object_id, {})
        mask = obj.get("color_mask", []) if isinstance(obj, dict) else []
        if not isinstance(mask, list):
            return []
        return [str(line) for line in mask]

    def _object_variation(self, object_id: str) -> float:
        obj = self.objects_data.get(object_id, {})
        if not isinstance(obj, dict):
            return 0.0
        try:
            return max(0.0, min(1.0, float(obj.get("variation", 0.0) or 0.0)))
        except (TypeError, ValueError):
            return 0.0

    def _opponent_entry(self, opponent_id: str) -> dict:
        base = self.opponents_data.get("base_opponents", {})
        if not isinstance(base, dict):
            return {}
        entry = base.get(opponent_id, {})
        return entry if isinstance(entry, dict) else {}

    def _opponent_art(self, opponent_id: str) -> List[str]:
        entry = self._opponent_entry(opponent_id)
        art = entry.get("art", [])
        if not isinstance(art, list):
            return []
        return [str(line) for line in art]

    def _opponent_mask(self, opponent_id: str) -> List[str]:
        entry = self._opponent_entry(opponent_id)
        mask = entry.get("color_map", [])
        if not isinstance(mask, list):
            return []
        return [str(line) for line in mask]

    def _first_non_space(self, value: str) -> int:
        for idx, ch in enumerate(value):
            if ch != " ":
                return idx
        return -1

    def _align_mask_line(self, art_line: str, mask_line: str, width: int) -> str:
        if not mask_line:
            return " " * width
        out = mask_line
        art_first = self._first_non_space(art_line)
        mask_first = self._first_non_space(mask_line)
        if art_first >= 0 and mask_first >= 0 and mask_first < art_first:
            out = (" " * (art_first - mask_first)) + out
        return out.ljust(width)[:width]

    def _normalize_layers(self, art: List[str], mask: List[str]) -> tuple[List[str], List[str]]:
        if not art:
            art = [" "]
        width = max((len(line) for line in art), default=1)
        art_rows = [line.ljust(width) for line in art]
        mask_rows = [line for line in mask] if mask else ([" " * width] * len(art_rows))

        if len(mask_rows) < len(art_rows):
            mask_rows = ([" " * width] * (len(art_rows) - len(mask_rows))) + mask_rows
        if len(mask_rows) > len(art_rows):
            mask_rows = mask_rows[-len(art_rows) :]
        mask_rows = [
            self._align_mask_line(art_rows[idx], mask_rows[idx] if idx < len(mask_rows) else "", width)
            for idx in range(len(art_rows))
        ]

        if len(art_rows) > self.content_height:
            art_rows = art_rows[-self.content_height :]
            mask_rows = mask_rows[-self.content_height :]
        if len(art_rows) < self.content_height:
            pad_count = self.content_height - len(art_rows)
            art_rows = ([" " * width] * pad_count) + art_rows
            mask_rows = ([" " * width] * pad_count) + mask_rows
        return art_rows, mask_rows

    def _overlay_label(
        self,
        rows: List[List[str]],
        start_x: int,
        piece_width: int,
        source_art_height: int,
        label: str,
        label_row: int,
        label_key: str,
    ) -> None:
        text = f"[ {label} ]"
        if not text or not rows:
            return
        visible_h = min(self.content_height, max(1, source_art_height))
        top_pad = self.content_height - visible_h
        clipped_from_top = max(0, source_art_height - self.content_height)
        local_row = max(0, int(label_row) - clipped_from_top)
        y = top_pad + local_row
        if y < 0 or y >= len(rows):
            return
        x = start_x + max(0, (piece_width - len(text)) // 2)
        for idx, ch in enumerate(text):
            pos = x + idx
            if 0 <= pos < len(rows[y]):
                if ch == " ":
                    rows[y][pos] = " "
                else:
                    rows[y][pos] = self._colorize(ch, label_key)

    def _compose_strip(self, object_ids: List[str], target_width: int) -> List[List[str]]:
        rows: List[List[str]] = [[] for _ in range(self.content_height)]
        for object_id in object_ids:
            art_rows, mask_rows = self._normalize_layers(self._object_art(object_id), self._object_mask(object_id))
            for y in range(self.content_height):
                art_line = art_rows[y]
                mask_line = mask_rows[y]
                for x, ch in enumerate(art_line):
                    mask_char = mask_line[x] if x < len(mask_line) else " "
                    rows[y].append(self._colorize(ch, mask_char))
        if target_width <= 0:
            return rows
        trimmed: List[List[str]] = []
        for row in rows:
            if len(row) >= target_width:
                trimmed.append(row[:target_width])
            else:
                trimmed.append(row + ([" "] * (target_width - len(row))))
        return trimmed

    def _append_piece(self, rows: List[List[str]], art: List[str], mask: List[str]) -> int:
        art_rows, mask_rows = self._normalize_layers(art, mask)
        width = len(art_rows[0]) if art_rows else 0
        for y in range(self.content_height):
            art_line = art_rows[y]
            mask_line = mask_rows[y]
            for x, ch in enumerate(art_line):
                mask_char = mask_line[x] if x < len(mask_line) else " "
                rows[y].append(self._colorize(ch, mask_char))
        return width

    def _strip_ansi(self, value: str) -> str:
        out: List[str] = []
        i = 0
        while i < len(value):
            if value[i] == "\x1b" and i + 1 < len(value) and value[i + 1] == "[":
                j = i + 2
                while j < len(value) and value[j] != "m":
                    j += 1
                i = j + 1 if j < len(value) else len(value)
                continue
            out.append(value[i])
            i += 1
        return "".join(out)

    def _add_vertical_padding(self, cells: List[List[str]]) -> List[List[str]]:
        if not cells:
            return cells
        width = len(cells[0])
        extra = max(0, self.height - len(cells))
        if extra <= 0:
            return cells[-self.height :]

        top_count = min(4, extra)
        remaining = extra - top_count
        bottom_count = min(1, remaining)
        trailing_blank_count = max(0, remaining - bottom_count)

        top_rows = [[" " for _ in range(width)] for _ in range(top_count)]
        bottom_rows: List[List[str]] = []
        if bottom_count:
            source_row = cells[-1]
            water_art = self._object_art("water")
            water_mask = self._object_mask("water")
            grass_art = self._object_art("grass")
            grass_mask = self._object_mask("grass")
            water_pattern = water_art[0] if water_art else "~"
            water_pattern_mask = water_mask[0] if water_mask else "b"
            grass_pattern = grass_art[0] if grass_art else "~"
            grass_pattern_mask = grass_mask[0] if grass_mask else "g"
            water_variation = self._object_variation("water")
            grass_variation = self._object_variation("grass")
            bottom: List[str] = []
            blue_codes = {
                self._color_code_for_key("b"),
                self._color_code_for_key("B"),
            }
            for cell in source_row:
                glyph = self._strip_ansi(cell)
                is_blue_water = glyph == "~" and any(code and code in cell for code in blue_codes)
                pattern = water_pattern if is_blue_water else grass_pattern
                pattern_mask = water_pattern_mask if is_blue_water else grass_pattern_mask
                variation = water_variation if is_blue_water else grass_variation
                x = len(bottom)
                ch = pattern[x % max(1, len(pattern))] if pattern else "~"
                mask_char = pattern_mask[x % max(1, len(pattern_mask))] if pattern_mask else ("b" if is_blue_water else "g")
                if mask_char.isalpha() and variation > 0.0:
                    unit = _unit_hash((x + 1) * 1315423911)
                    if unit < variation:
                        mask_char = mask_char.swapcase()
                bottom.append(self._colorize(ch, mask_char))
            bottom_rows.append(bottom)
        trailing_rows = [[" " for _ in range(width)] for _ in range(trailing_blank_count)]
        return top_rows + cells + bottom_rows + trailing_rows

    def _town_from_assets(self, width: int) -> List[List[str]]:
        scene = self.scenes_data.get("town", {})
        objects = scene.get("objects", []) if isinstance(scene, dict) else []
        rows: List[List[str]] = [[] for _ in range(self.content_height)]
        if isinstance(objects, list):
            for token in objects:
                if not isinstance(token, dict):
                    continue
                object_id = str(token.get("id", "") or "")
                if not object_id:
                    continue
                repeat = int(token.get("repeat", 1) or 1)
                repeat = max(1, min(repeat, 12))
                for _ in range(repeat):
                    source_art = self._object_art(object_id)
                    source_mask = self._object_mask(object_id)
                    art_rows, mask_rows = self._normalize_layers(source_art, source_mask)
                    piece_width = len(art_rows[0]) if art_rows else 0
                    start_x = len(rows[0]) if rows else 0
                    for y in range(self.content_height):
                        art_line = art_rows[y]
                        mask_line = mask_rows[y]
                        for x, ch in enumerate(art_line):
                            mask_char = mask_line[x] if x < len(mask_line) else " "
                            rows[y].append(self._colorize(ch, mask_char))
                    if token.get("label"):
                        label = str(token.get("label"))
                        label_row = int(token.get("label_row", 0) or 0)
                        label_key = str(token.get("label_key", "w") or "w")
                        self._overlay_label(
                            rows,
                            start_x=start_x,
                            piece_width=piece_width,
                            source_art_height=max(1, len(source_art)),
                            label=label,
                            label_row=label_row,
                            label_key=label_key,
                        )
        if not rows or not rows[0]:
            sequence = ["water", "town_wall", "grass", "house", "grass", "sign_small", "grass", "town_wall", "water"]
            return self._compose_strip(sequence, width)
        if width <= 0:
            return rows
        trimmed: List[List[str]] = []
        for row in rows:
            if len(row) >= width:
                trimmed.append(row[:width])
            else:
                trimmed.append(row + ([" "] * (width - len(row))))
        return trimmed

    def _forest_from_assets(self, width: int, seed: int) -> List[List[str]]:
        tree_options = [
            "tree_large",
            "tree_large_2",
            "tree_large_3",
            "bush_large",
            "bush_large_2",
            "bush_large_3",
        ]
        tree_options = [obj_id for obj_id in tree_options if self._object_art(obj_id)]
        if not tree_options:
            tree_options = ["tree_large", "bush_large", "grass_1"]
        rng = random.Random(seed)
        companion_ids = ["mushroom_baby", "wolf_pup", "fairy_baby", "baby_ogre"]
        has_all_companions = all(self._opponent_art(companion_id) for companion_id in companion_ids)
        if has_all_companions:
            rows: List[List[str]] = [[] for _ in range(self.content_height)]
            for idx, companion_id in enumerate(companion_ids):
                self._append_piece(rows, self._opponent_art(companion_id), self._opponent_mask(companion_id))
                if idx == len(companion_ids) - 1:
                    continue
                tree_count = rng.randint(1, 2)
                for _ in range(tree_count):
                    tree_id = tree_options[rng.randrange(len(tree_options))]
                    self._append_piece(rows, self._object_art(tree_id), self._object_mask(tree_id))
            if width > 0:
                trimmed: List[List[str]] = []
                for row in rows:
                    if len(row) >= width:
                        trimmed.append(row[:width])
                    else:
                        trimmed.append(row + ([" "] * (width - len(row))))
                return trimmed
            return rows

        sequence: List[str] = []
        current_width = 0
        while current_width < width and tree_options:
            object_id = tree_options[rng.randrange(len(tree_options))]
            art_rows, _ = self._normalize_layers(self._object_art(object_id), self._object_mask(object_id))
            piece_width = len(art_rows[0]) if art_rows else 0
            sequence.append(object_id)
            current_width += piece_width
            if piece_width <= 0:
                break
        return self._compose_strip(sequence, width)

    def _build_map(self) -> TileMap:
        if self.scenes_data and self.objects_data:
            town = self._town_from_assets(0)
            forest = self._forest_from_assets(0, seed=4242)
        else:
            town = self._plain_rows(self.town_width, fill="=")
            forest = self._plain_rows(self.forest_width, fill=".")
        cells = [
            town[y] + forest[y]
            for y in range(self.content_height)
        ]
        return TileMap(cells=self._add_vertical_padding(cells))

    def _plain_rows(self, width: int, fill: str = " ") -> List[List[str]]:
        ch = fill[0] if fill else " "
        return [[ch for _ in range(width)] for _ in range(self.content_height)]

    def viewport(self, now: float | None = None) -> List[str]:
        start_x = self.offset(now)
        return self._map.slice_wrap(start_x=start_x, width=self.viewport_width)

    def offset(self, now: float | None = None) -> int:
        moment = time.time() if now is None else now
        return int(max(0.0, moment - self._start_time) * self.speed)
