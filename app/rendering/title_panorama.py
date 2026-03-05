import time
import random
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TileMap:
    rows: List[str]

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def width(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    def slice_wrap(self, start_x: int, width: int) -> List[str]:
        if not self.rows:
            return []
        out: List[str] = []
        total = max(1, self.width)
        start = start_x % total
        for row in self.rows:
            if len(row) < total:
                row = row.ljust(total)
            if start + width <= total:
                out.append(row[start : start + width])
            else:
                first = row[start:]
                second = row[: width - len(first)]
                out.append(first + second)
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
    ) -> None:
        self.viewport_width = viewport_width
        self.height = height
        self.speed = speed
        self.scenes_data = scenes_data if isinstance(scenes_data, dict) else {}
        self.objects_data = objects_data if isinstance(objects_data, dict) else {}
        base_forest_width = max(1, viewport_width // 2)
        self.forest_width = max(1, int(base_forest_width * max(0.1, min(1.0, forest_width_scale))))
        self.town_width = viewport_width
        self._map = self._build_map()

    def _object_art(self, object_id: str) -> List[str]:
        obj = self.objects_data.get(object_id, {})
        art = obj.get("art", []) if isinstance(obj, dict) else []
        if not isinstance(art, list):
            return []
        return [str(line) for line in art]

    def _normalize_art(self, art: List[str]) -> List[str]:
        if not art:
            return [" "]
        width = max((len(line) for line in art), default=1)
        rows = [line.ljust(width) for line in art]
        if len(rows) > self.height:
            return rows[-self.height :]
        if len(rows) < self.height:
            padding = [" " * width for _ in range(self.height - len(rows))]
            return padding + rows
        return rows

    def _compose_strip(self, object_ids: List[str], target_width: int) -> List[str]:
        rows = [""] * self.height
        for object_id in object_ids:
            art = self._normalize_art(self._object_art(object_id))
            for y in range(self.height):
                rows[y] += art[y]
        if target_width <= 0:
            return rows
        return [row[:target_width].ljust(target_width) for row in rows]

    def _town_from_assets(self, width: int) -> List[str]:
        scene = self.scenes_data.get("town", {})
        objects = scene.get("objects", []) if isinstance(scene, dict) else []
        sequence: List[str] = []
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
                    sequence.append(object_id)
        if not sequence:
            sequence = ["water", "town_wall", "grass", "house", "grass", "sign_small", "grass", "town_wall", "water"]
        return self._compose_strip(sequence, width)

    def _forest_from_assets(self, width: int, seed: int) -> List[str]:
        options = [
            "tree_large",
            "tree_large_2",
            "tree_large_3",
            "bush_large",
            "bush_large_2",
            "bush_large_3",
        ]
        options = [obj_id for obj_id in options if self._object_art(obj_id)]
        if not options:
            options = ["tree_large", "bush_large", "grass_1"]
        separator = "grass_1" if self._object_art("grass_1") else ""
        rng = random.Random(seed)
        sequence: List[str] = []
        current_width = 0
        while current_width < width and options:
            object_id = options[rng.randrange(len(options))]
            art = self._normalize_art(self._object_art(object_id))
            piece_width = len(art[0]) if art else 0
            sequence.append(object_id)
            current_width += piece_width
            if separator and current_width < width:
                sep_art = self._normalize_art(self._object_art(separator))
                current_width += len(sep_art[0]) if sep_art else 0
                sequence.append(separator)
            if piece_width <= 0:
                break
        return self._compose_strip(sequence, width)

    def _build_map(self) -> TileMap:
        if self.scenes_data and self.objects_data:
            forest_a = self._forest_from_assets(self.forest_width, seed=4242)
            town = self._town_from_assets(self.town_width)
            forest_b = self._forest_from_assets(self.forest_width, seed=6262)
        else:
            forest_a = self._forest_rows(self.forest_width, phase=0)
            town = self._town_rows(self.town_width)
            forest_b = self._forest_rows(self.forest_width, phase=7)
        rows = [
            forest_a[y] + town[y] + forest_b[y]
            for y in range(self.height)
        ]
        return TileMap(rows=rows)

    def _forest_rows(self, width: int, phase: int) -> List[str]:
        rows: List[str] = []
        for y in range(self.height):
            chars: List[str] = []
            for x in range(width):
                p = x + phase
                ch = " "
                if y == 0:
                    ch = "." if (p % 17 == 0) else " "
                elif y in (1, 2):
                    ch = "^" if (p % 6 in (0, 1, 2)) else " "
                elif y in (3, 4):
                    ch = "M" if (p % 8 in (0, 1, 2)) else ("^" if p % 5 == 0 else " ")
                elif y in (5, 6, 7):
                    if p % 8 == 1:
                        ch = "|"
                    elif p % 11 == 0:
                        ch = '"'
                    else:
                        ch = " "
                elif y == 8:
                    ch = "," if p % 3 else "."
                else:
                    ch = "_" if p % 2 else "."
                chars.append(ch)
            rows.append("".join(chars))
        return rows

    def _town_rows(self, width: int) -> List[str]:
        rows: List[str] = []
        for y in range(self.height):
            chars: List[str] = []
            for x in range(width):
                ch = " "
                if y == 0:
                    ch = " "
                elif y == 1:
                    ch = "." if x % 23 == 0 else " "
                elif y == 2:
                    ch = "~" if x < 7 or x > width - 8 else " "
                elif y == 3:
                    ch = "=" if x < 9 or x > width - 10 else "#"
                elif y == 4:
                    if x in (12, 26, 40, 54, 68, 82):
                        ch = "^"
                    elif x in (13, 25, 27, 39, 41, 53, 55, 67, 69, 81, 83):
                        ch = "/"
                    else:
                        ch = " "
                elif y in (5, 6):
                    if x in (12, 26, 40, 54, 68, 82):
                        ch = "|"
                    elif x in (18, 32, 46, 60, 74, 88):
                        ch = "|"
                    elif x in (15, 29, 43, 57, 71, 85):
                        ch = "+"
                    else:
                        ch = " "
                elif y == 7:
                    ch = "-" if 10 <= x <= width - 11 else " "
                elif y == 8:
                    ch = "," if x % 3 else "."
                else:
                    ch = "_" if x % 2 else "."
                chars.append(ch)
            rows.append("".join(chars))
        return rows

    def viewport(self, now: float | None = None) -> List[str]:
        start_x = self.offset(now)
        return self._map.slice_wrap(start_x=start_x, width=self.viewport_width)

    def offset(self, now: float | None = None) -> int:
        moment = time.time() if now is None else now
        return int(moment * self.speed)
