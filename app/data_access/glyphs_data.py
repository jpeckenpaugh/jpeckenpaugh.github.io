"""Load glyph data from JSON."""

import json
from typing import Dict, Optional


class GlyphsData:
    def __init__(self, path: str):
        self._path = path
        self._glyphs: Dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._glyphs = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._glyphs = {}

    def get(self, key: str, default: Optional[dict] = None) -> dict:
        if default is None:
            default = {}
        return self._glyphs.get(key, default)
