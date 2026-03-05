import json
from typing import List, Tuple

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

    def render(self, app: "GameApp") -> str:
        category_name, filename = self._current_category()
        labels = self._item_labels(app)
        self._clamp_item_cursor(labels)

        selected_label = labels[self._item_idx] if labels else "-"
        selected_payload = {}
        if labels:
            _, selected_payload = app.asset_repository.entry(filename, selected_label)

        payload_lines = json.dumps(selected_payload, indent=2, ensure_ascii=True).splitlines()
        max_payload_lines = 14
        max_offset = max(0, len(payload_lines) - max_payload_lines)
        if self._preview_offset > max_offset:
            self._preview_offset = max_offset
        clipped_payload = payload_lines[self._preview_offset : self._preview_offset + max_payload_lines]

        item_window = 10
        start = max(0, self._item_idx - item_window // 2)
        end = min(len(labels), start + item_window)
        start = max(0, end - item_window)

        lines = [
            "=" * 100,
            "ASSET EXPLORER".center(100),
            "=" * 100,
            "Left/Right: category  Up/Down: item  U/J: preview scroll  R: reload  Q: back",
            f"Category: {category_name} ({filename})",
            f"Entries: {len(labels)}  Selected: {selected_label}",
            "-" * 100,
            "Items:",
        ]

        if not labels:
            lines.append("  (no entries)")
        else:
            for i in range(start, end):
                cursor = ">" if i == self._item_idx else " "
                lines.append(f" {cursor} {labels[i]}")

        lines.append("-" * 100)
        lines.append(
            f"JSON Preview: line {self._preview_offset + 1}-{self._preview_offset + len(clipped_payload)}"
            f" of {max(1, len(payload_lines))}"
        )
        lines.extend(clipped_payload)
        if self._preview_offset + len(clipped_payload) < len(payload_lines):
            lines.append("...")
        lines.append("-" * 100)
        if self._message:
            lines.append(self._message)
        else:
            lines.append("")

        return "\n".join(lines)

    def handle_input(self, app: "GameApp", key: str) -> SceneResult:
        labels = self._item_labels(app)
        self._clamp_item_cursor(labels)

        if key in ("q",):
            return SceneResult(next_scene_id="title")
        if key in ("left", "a"):
            self._move_category(-1)
            self._message = ""
            return SceneResult()
        if key in ("right", "d"):
            self._move_category(1)
            self._message = ""
            return SceneResult()
        if key in ("up", "w") and labels:
            self._item_idx = (self._item_idx - 1) % len(labels)
            self._preview_offset = 0
            return SceneResult()
        if key in ("down", "s") and labels:
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
