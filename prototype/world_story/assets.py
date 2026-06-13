from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEGACY_DATA = ROOT / "legacy" / "data"

PRESERVED_JSON_ASSETS = (
    "objects.json",
    "colors.json",
    "glyphs.json",
    "players.json",
    "opponents.json",
    "spells_art.json",
    "frames.json",
    "npc_parts.json",
)


@lru_cache(maxsize=None)
def load_legacy_json(name: str) -> object:
    if name not in PRESERVED_JSON_ASSETS and not name.endswith(".json"):
        raise ValueError(f"Unsupported legacy data file: {name}")
    path = LEGACY_DATA / name
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def preserved_asset_status() -> dict[str, bool]:
    return {name: (LEGACY_DATA / name).exists() for name in PRESERVED_JSON_ASSETS}
