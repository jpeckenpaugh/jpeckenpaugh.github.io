import json
import time
from typing import Dict, List, Tuple

from app.scenes.base import Scene, SceneResult


class AssetExplorerScene(Scene):
    scene_id = "asset_explorer"

    def __init__(self) -> None:
        self._categories: List[Tuple[str, str]] = [
            ("Objects", "objects.json"),
            ("Opponents", "opponents.json"),
            ("NPCs", "npcs.json"),
            ("Venues", "venues.json"),
            ("SpellsArt", "spells_art.json"),
            ("Items", "items.json"),
            ("Scenes", "scenes.json"),
        ]
        self._category_idx = 0
        self._item_idx = 0
        self._preview_offset = 0
        self._message = ""
        self._screen_width = 100
        self._screen_height = 30
        self._ansi_reset = "\x1b[0m"
        self._last_spell_frame_key = -1

    def _current_category(self) -> Tuple[str, str]:
        return self._categories[self._category_idx]

    def _item_labels(self, app: "GameApp") -> List[str]:
        _, filename = self._current_category()
        try:
            labels = app.asset_repository.entry_labels(filename)
            return labels
        except Exception as exc:  # pragma: no cover - simple terminal fallback
            self._message = f"Load error: {exc}"
            return []

    def _clamp_item_cursor(self, labels: List[str]) -> None:
        if not labels:
            self._item_idx = 0
            return
        self._item_idx = max(0, min(self._item_idx, len(labels) - 1))

    def _move_category(self, delta: int) -> None:
        total = len(self._categories)
        self._category_idx = (self._category_idx + delta) % total
        self._item_idx = 0
        self._preview_offset = 0

    def _move_preview(self, delta: int, total_lines: int, view_lines: int) -> None:
        max_offset = max(0, total_lines - view_lines)
        self._preview_offset = max(0, min(self._preview_offset + delta, max_offset))

    def _selected_payload_lines(self, app: "GameApp", labels: List[str]) -> List[str]:
        _, filename = self._current_category()
        if not labels:
            return json.dumps({}, indent=2, ensure_ascii=True).splitlines()
        selected_label = labels[self._item_idx]
        _, payload = app.asset_repository.entry(filename, selected_label)
        return json.dumps(payload, indent=2, ensure_ascii=True).splitlines()

    def _box(self, width: int, height: int, content_lines: List[str]) -> List[str]:
        width = max(2, width)
        height = max(2, height)
        inner_w = width - 2
        inner_h = height - 2
        lines = ["+" + ("-" * inner_w) + "+"]
        for row in range(inner_h):
            content = content_lines[row] if row < len(content_lines) else ""
            lines.append("|" + content[:inner_w].ljust(inner_w) + "|")
        lines.append("+" + ("-" * inner_w) + "+")
        return lines

    def _payload_preview_lines(self, payload: object, height_budget: int) -> List[str]:
        lines: List[str] = []
        if isinstance(payload, dict):
            name = payload.get("name")
            if isinstance(name, str) and name:
                lines.append(name)
            desc = payload.get("description") or payload.get("desc")
            if isinstance(desc, str) and desc:
                lines.append(desc)
        elif isinstance(payload, list):
            lines.append(f"List entries: {len(payload)}")
        else:
            lines.append(str(type(payload).__name__))
        return lines[:height_budget]

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

    def _color_codes(self, app: "GameApp") -> Dict[str, str]:
        try:
            colors = app.asset_repository.load("colors.json")
        except Exception:
            return {}
        if not isinstance(colors, dict):
            return {}
        out: Dict[str, str] = {}
        for key, value in colors.items():
            if not isinstance(value, dict):
                continue
            code = self._hex_to_ansi(value.get("hex", ""))
            if code:
                out[str(key)] = code
        return out

    def _digit_fallback_codes(self) -> Dict[str, str]:
        return {
            "1": "\x1b[38;2;120;180;255m",
            "2": "\x1b[38;2;150;220;255m",
            "3": "\x1b[38;2;200;200;255m",
            "4": "\x1b[38;2;255;180;120m",
            "5": "\x1b[38;2;255;220;150m",
            "6": "\x1b[38;2;255;140;140m",
            "7": "\x1b[38;2;180;255;180m",
            "8": "\x1b[38;2;220;255;220m",
            "9": "\x1b[38;2;255;180;255m",
            "0": "\x1b[38;2;200;200;200m",
        }

    def _colorized_lines(
        self,
        app: "GameApp",
        art: List[str],
        mask: List[str],
        max_lines: int,
    ) -> List[str]:
        if not art:
            return []
        if max_lines <= 0:
            return []
        code_by_key = self._color_codes(app)
        code_by_key.update(self._digit_fallback_codes())
        if not mask:
            return [str(line) for line in art[:max_lines]]
        rendered: List[str] = []
        for row_idx, raw_line in enumerate(art[:max_lines]):
            line = str(raw_line)
            mask_line = str(mask[row_idx]) if row_idx < len(mask) else ""
            out: List[str] = []
            for col_idx, ch in enumerate(line):
                if ch == " ":
                    out.append(" ")
                    continue
                key = mask_line[col_idx] if col_idx < len(mask_line) else ""
                code = code_by_key.get(key, "")
                if code:
                    out.append(f"{code}{ch}{self._ansi_reset}")
                else:
                    out.append(ch)
            rendered.append("".join(out))
        return rendered

    def _object_art_mask(self, app: "GameApp", object_id: str) -> Tuple[List[str], List[str]]:
        try:
            objects = app.asset_repository.load("objects.json")
        except Exception:
            return ([], [])
        entry = objects.get(object_id, {}) if isinstance(objects, dict) else {}
        if not isinstance(entry, dict):
            return ([], [])
        art = entry.get("art", [])
        mask = entry.get("color_mask", [])
        if not isinstance(art, list):
            art = []
        if not isinstance(mask, list):
            mask = []
        return ([str(line) for line in art], [str(line) for line in mask])

    def _npc_art_mask(self, app: "GameApp", payload: object) -> Tuple[List[str], List[str]]:
        if not isinstance(payload, dict):
            return ([], [])
        parts = payload.get("parts", [])
        if not isinstance(parts, list) or not parts:
            return ([], [])
        try:
            npc_parts = app.asset_repository.load("npc_parts.json")
        except Exception:
            return ([], [])
        if not isinstance(npc_parts, dict):
            return ([], [])
        art_lines: List[str] = []
        mask_lines: List[str] = []
        for token in parts:
            if not isinstance(token, dict):
                continue
            part_id = str(token.get("id", "") or "")
            if not part_id:
                continue
            part = npc_parts.get(part_id, {})
            if not isinstance(part, dict):
                continue
            part_art = part.get("art", [])
            part_mask = part.get("color_mask", [])
            if not isinstance(part_art, list):
                part_art = []
            if not isinstance(part_mask, list):
                part_mask = []
            for row_idx, raw in enumerate(part_art):
                line = str(raw)
                art_lines.append(line)
                if row_idx < len(part_mask):
                    mask_lines.append(str(part_mask[row_idx]))
                else:
                    mask_lines.append(" " * len(line))
        return (art_lines, mask_lines)

    def _compose_pieces(self, pieces: List[Tuple[List[str], List[str]]], max_height: int, max_width: int) -> Tuple[List[str], List[str]]:
        if max_height <= 0 or max_width <= 0 or not pieces:
            return ([], [])
        piece_heights = [len(art) if art else 1 for art, _ in pieces]
        target_h = max(1, min(max_height, max(piece_heights)))
        out_art = ["" for _ in range(target_h)]
        out_mask = ["" for _ in range(target_h)]
        for art, mask in pieces:
            rows = [str(line) for line in art] if art else [""]
            masks = [str(line) for line in mask] if mask else []
            piece_w = max((len(row) for row in rows), default=0)
            if piece_w <= 0:
                continue
            padded_rows = [row.ljust(piece_w) for row in rows]
            padded_masks = []
            for idx in range(len(padded_rows)):
                if idx < len(masks):
                    padded_masks.append(str(masks[idx]).ljust(piece_w))
                else:
                    padded_masks.append(" " * piece_w)
            if len(padded_rows) > target_h:
                padded_rows = padded_rows[-target_h:]
                padded_masks = padded_masks[-target_h:]
            elif len(padded_rows) < target_h:
                pad = target_h - len(padded_rows)
                padded_rows = ([" " * piece_w] * pad) + padded_rows
                padded_masks = ([" " * piece_w] * pad) + padded_masks
            for y in range(target_h):
                out_art[y] += padded_rows[y]
                out_mask[y] += padded_masks[y]
                if len(out_art[y]) > max_width:
                    out_art[y] = out_art[y][:max_width]
                    out_mask[y] = out_mask[y][:max_width]
        return (out_art, out_mask)

    def _venue_art_mask(self, app: "GameApp", payload: object, width_budget: int, height_budget: int) -> Tuple[List[str], List[str]]:
        if not isinstance(payload, dict):
            return ([], [])
        objects = payload.get("objects", [])
        if not isinstance(objects, list) or not objects:
            return ([], [])
        npc_payload = {}
        npc_ids = payload.get("npc_ids", [])
        if isinstance(npc_ids, list) and npc_ids:
            npc_id = str(npc_ids[0])
            try:
                npcs = app.asset_repository.load("npcs.json")
            except Exception:
                npcs = {}
            if isinstance(npcs, dict):
                npc_payload = npcs.get(npc_id, {})
        npc_art, npc_mask = self._npc_art_mask(app, npc_payload)

        pieces: List[Tuple[List[str], List[str]]] = []
        for token in objects:
            if not isinstance(token, dict):
                continue
            object_id = str(token.get("id", "") or "")
            if not object_id:
                continue
            repeat = int(token.get("repeat", 1) or 1)
            repeat = max(1, min(repeat, 16))
            art: List[str]
            mask: List[str]
            if object_id == "space":
                width = max(1, int(token.get("width", 1) or 1))
                art = [" " * width]
                mask = [" " * width]
            elif object_id == "npc":
                art = npc_art if npc_art else [" " * 6]
                mask = npc_mask if npc_mask else [" " * len(art[0])]
            else:
                art, mask = self._object_art_mask(app, object_id)
                if not art:
                    continue
            for _ in range(repeat):
                pieces.append((art, mask))
        return self._compose_pieces(pieces, max_height=height_budget, max_width=width_budget)

    def _spell_frame_index(self, payload: object, now: float | None = None) -> int:
        if not isinstance(payload, dict):
            return 0
        frames = payload.get("frames", [])
        if not isinstance(frames, list) or not frames:
            return 0
        delay = float(payload.get("frame_delay", 0.1) or 0.1)
        delay = max(0.04, delay)
        moment = time.time() if now is None else now
        return int(moment / delay) % max(1, len(frames))

    def _spell_art_mask(self, payload: object, now: float | None = None) -> Tuple[List[str], List[str]]:
        if not isinstance(payload, dict):
            return ([], [])
        frames = payload.get("frames", [])
        if not isinstance(frames, list) or not frames:
            return ([], [])
        masks = payload.get("mask_frames", [])
        if not isinstance(masks, list):
            masks = []
        idx = self._spell_frame_index(payload, now=now)
        art = frames[idx] if idx < len(frames) else []
        mask = masks[idx] if idx < len(masks) else []
        if not isinstance(art, list):
            art = []
        if not isinstance(mask, list):
            mask = []
        return ([str(line) for line in art], [str(line) for line in mask])

    def _colorized_art_lines(
        self,
        app: "GameApp",
        category_name: str,
        payload: object,
        max_lines: int,
        width_budget: int,
    ) -> List[str]:
        if max_lines <= 0:
            return []
        art: List[str] = []
        mask: List[str] = []
        if isinstance(payload, dict):
            if category_name == "NPCs":
                art, mask = self._npc_art_mask(app, payload)
            elif category_name == "Venues":
                art, mask = self._venue_art_mask(app, payload, width_budget=width_budget, height_budget=max_lines)
            elif category_name == "SpellsArt":
                art, mask = self._spell_art_mask(payload)
            else:
                source_art = payload.get("art", [])
                source_mask = payload.get("color_mask")
                if not isinstance(source_mask, list):
                    source_mask = payload.get("color_map")
                if isinstance(source_art, list):
                    art = [str(line) for line in source_art]
                if isinstance(source_mask, list):
                    mask = [str(line) for line in source_mask]
        return self._colorized_lines(app, art, mask, max_lines=max_lines)

    def _ansi_cells(self, text: str, width: int) -> List[str]:
        cells: List[str] = []
        i = 0
        active = ""
        while i < len(text):
            ch = text[i]
            if ch == "\x1b" and i + 1 < len(text) and text[i + 1] == "[":
                j = i + 2
                while j < len(text) and text[j] != "m":
                    j += 1
                if j < len(text):
                    seq = text[i : j + 1]
                    if seq == self._ansi_reset:
                        active = ""
                    else:
                        active = seq
                    i = j + 1
                    continue
            if ch == " ":
                cells.append(" ")
            elif active:
                cells.append(f"{active}{ch}{self._ansi_reset}")
            else:
                cells.append(ch)
            i += 1
            if len(cells) >= width:
                break
        while len(cells) < width:
            cells.append(" ")
        return cells[:width]

    def render(self, app: "GameApp") -> str:
        category_name, filename = self._current_category()
        labels = self._item_labels(app)
        self._clamp_item_cursor(labels)

        selected_label = labels[self._item_idx] if labels else "-"
        selected_payload = {}
        if labels:
            _, selected_payload = app.asset_repository.entry(filename, selected_label)

        divider_x = 33
        right_w = self._screen_width - divider_x - 1
        top_h = 16
        bottom_h = self._screen_height - top_h

        payload_lines = json.dumps(selected_payload, indent=2, ensure_ascii=True).splitlines() if labels else ["{}"]
        json_view_lines = max(1, bottom_h - 6)
        max_offset = max(0, len(payload_lines) - json_view_lines)
        if self._preview_offset > max_offset:
            self._preview_offset = max_offset
        clipped_payload = payload_lines[self._preview_offset : self._preview_offset + json_view_lines]

        item_window = self._screen_height - 4
        start = max(0, self._item_idx - item_window // 2)
        end = min(len(labels), start + item_window)
        start = max(0, end - item_window)

        left_content: List[str] = [f"[ {category_name} ]", ""]
        if not labels:
            left_content.append("(no entries)")
        else:
            for i in range(start, end):
                cursor = ">" if i == self._item_idx else " "
                left_content.append(f"{cursor} {labels[i]}")

        top_content: List[str] = [
            f"[ Preview ] {filename}",
            "",
        ]
        if category_name != "Venues":
            top_content.extend(
                [
                    f"Selected: {selected_label}",
                    f"Entries: {len(labels)}",
                    "",
                ]
            )
        top_preview_budget = max(0, top_h - len(top_content) - 1)
        art_lines = self._colorized_art_lines(
            app,
            category_name=category_name,
            payload=selected_payload,
            max_lines=top_preview_budget,
            width_budget=right_w - 2,
        )
        if art_lines:
            top_content.extend(art_lines[:top_preview_budget])
            remaining = max(0, top_preview_budget - len(art_lines))
            if remaining > 0:
                top_content.append("")
                remaining -= 1
                if remaining > 0:
                    top_content.extend(self._payload_preview_lines(selected_payload, remaining))
        else:
            top_content.extend(self._payload_preview_lines(selected_payload, top_preview_budget))

        bottom_content: List[str] = [
            "[ Details ]",
            "Arrows nav  U/J json scroll",
            "R reload  S/Esc back  Enter options",
            "",
            f"JSON lines {self._preview_offset + 1}-{self._preview_offset + len(clipped_payload)}"
            f" / {max(1, len(payload_lines))}",
        ]
        bottom_content.extend(clipped_payload)
        if self._message:
            bottom_content.append("")
            bottom_content.append(self._message[: right_w - 2])
        # Shared-frame canvas: one outer frame + one vertical divider + one right horizontal divider.
        w = self._screen_width
        h = self._screen_height
        canvas = [[" " for _ in range(w)] for _ in range(h)]

        def put(x: int, y: int, ch: str) -> None:
            if 0 <= x < w and 0 <= y < h:
                canvas[y][x] = ch

        # Outer frame
        put(0, 0, "+")
        put(w - 1, 0, "+")
        put(0, h - 1, "+")
        put(w - 1, h - 1, "+")
        for x in range(1, w - 1):
            put(x, 0, "-")
            put(x, h - 1, "-")
        for y in range(1, h - 1):
            put(0, y, "|")
            put(w - 1, y, "|")

        # Vertical divider
        for y in range(0, h):
            put(divider_x, y, "|")
        put(divider_x, 0, "+")
        put(divider_x, h - 1, "+")

        # Right-side horizontal divider
        for x in range(divider_x, w):
            put(x, top_h, "-")
        put(divider_x, top_h, "+")
        put(w - 1, top_h, "+")

        # Left pane content
        left_inner_w = divider_x - 1
        left_inner_h = h - 2
        for i, line in enumerate(left_content[:left_inner_h]):
            y = 1 + i
            cells = self._ansi_cells(line, left_inner_w)
            for x, ch in enumerate(cells):
                put(1 + x, y, ch)

        # Right-top content
        right_inner_w = w - divider_x - 2
        top_inner_h = top_h - 1
        for i, line in enumerate(top_content[:top_inner_h]):
            y = 1 + i
            cells = self._ansi_cells(line, right_inner_w)
            for x, ch in enumerate(cells):
                put(divider_x + 1 + x, y, ch)

        # Right-bottom content
        bottom_inner_h = h - top_h - 2
        for i, line in enumerate(bottom_content[:bottom_inner_h]):
            y = top_h + 1 + i
            cells = self._ansi_cells(line, right_inner_w)
            for x, ch in enumerate(cells):
                put(divider_x + 1 + x, y, ch)

        lines: List[str] = ["".join(row) for row in canvas]
        return "\n".join(lines)

    def input_timeout_seconds(self) -> float | None:
        category_name, _ = self._current_category()
        if category_name == "SpellsArt":
            return 0.08
        return None

    def needs_redraw(self, app: "GameApp") -> bool:
        category_name, filename = self._current_category()
        if category_name != "SpellsArt":
            self._last_spell_frame_key = -1
            return False
        labels = self._item_labels(app)
        self._clamp_item_cursor(labels)
        if not labels:
            return False
        selected_label = labels[self._item_idx]
        _, payload = app.asset_repository.entry(filename, selected_label)
        frame_idx = self._spell_frame_index(payload, now=time.time())
        if frame_idx != self._last_spell_frame_key:
            self._last_spell_frame_key = frame_idx
            return True
        return False

    def handle_input(self, app: "GameApp", key: str) -> SceneResult:
        labels = self._item_labels(app)
        self._clamp_item_cursor(labels)

        if key == "back":
            return SceneResult(next_scene_id="title")
        if key == "options":
            app.options_return_scene_id = "asset_explorer"
            return SceneResult(next_scene_id="options")
        if key == "left":
            self._move_category(-1)
            self._message = ""
            return SceneResult()
        if key == "right":
            self._move_category(1)
            self._message = ""
            return SceneResult()
        if key == "up" and labels:
            self._item_idx = (self._item_idx - 1) % len(labels)
            self._preview_offset = 0
            return SceneResult()
        if key == "down" and labels:
            self._item_idx = (self._item_idx + 1) % len(labels)
            self._preview_offset = 0
            return SceneResult()
        if key == "u":
            payload_lines = self._selected_payload_lines(app, labels)
            self._move_preview(-3, len(payload_lines), 14)
            return SceneResult()
        if key == "j":
            payload_lines = self._selected_payload_lines(app, labels)
            self._move_preview(3, len(payload_lines), 14)
            return SceneResult()
        if key == "r":
            _, filename = self._current_category()
            try:
                app.asset_repository.reload(filename)
                self._message = f"Reloaded {filename}"
            except Exception as exc:  # pragma: no cover - simple terminal fallback
                self._message = f"Reload failed: {exc}"
            return SceneResult()

        return SceneResult()
