import time
from dataclasses import dataclass
from typing import List


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
    ) -> None:
        self.viewport_width = viewport_width
        self.height = height
        self.speed = speed
        base_forest_width = max(1, viewport_width // 2)
        self.forest_width = max(1, int(base_forest_width * max(0.1, min(1.0, forest_width_scale))))
        self.town_width = viewport_width
        self._map = self._build_map()

    def _build_map(self) -> TileMap:
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
        moment = time.time() if now is None else now
        start_x = int(moment * self.speed)
        return self._map.slice_wrap(start_x=start_x, width=self.viewport_width)

