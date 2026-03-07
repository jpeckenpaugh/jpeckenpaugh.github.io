#!/usr/bin/env bash
set -euo pipefail

LEGACY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$LEGACY_ROOT/.." && pwd)"
DOCS="$REPO_ROOT/docs"
WEB_SRC="$LEGACY_ROOT/docs"

mkdir -p "$DOCS"

# 1) Start from web shell/template files.
rsync -av --delete \
  --exclude ".git/" \
  --exclude "__pycache__/" \
  --exclude "tmp/" \
  --exclude "*.pyc" \
  "$WEB_SRC/" "$DOCS/"

rsync -av --delete \
  --exclude ".git/" \
  --exclude "__pycache__/" \
  --exclude "venv/" \
  --exclude "tmp/" \
  --exclude "tmp1.txt" \
  --exclude "saves/" \
  --exclude "docs/" \
  --exclude "*.pyc" \
  "$LEGACY_ROOT/app/" "$DOCS/app/"

rsync -av --delete \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  "$LEGACY_ROOT/data/" "$DOCS/data/"

# 2) Legacy runtime entrypoint modules.
rsync -av \
  "$LEGACY_ROOT/main.py" \
  "$LEGACY_ROOT/music.py" \
  "$LEGACY_ROOT/render.py" \
  "$LEGACY_ROOT/color_map.py" \
  "$DOCS/"

# 3) Demo battle scene files from repo root.
rsync -av \
  "$REPO_ROOT/battle_scene.py" \
  "$REPO_ROOT/ui_v07.py" \
  "$REPO_ROOT/ui_v07_esp.py" \
  "$REPO_ROOT/ui_v07_pt_br.py" \
  "$DOCS/"

# battle_scene.py imports app.rendering.title_panorama from root app package.
rsync -av --delete \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  "$REPO_ROOT/app/rendering/" "$DOCS/app/rendering/"

date "+%Y-%m-%d %H:%M:%S %Z" > "$DOCS/build-time.txt"

ROOT_PATH="$REPO_ROOT"
python3 - <<'PY'
import json
import os
import time
from pathlib import Path

root = Path(os.environ.get("ROOT_PATH", "")).resolve() / "docs"
files = []
for path in root.rglob("*"):
    if path.is_dir():
        continue
    rel = path.relative_to(root).as_posix()
    if rel.startswith(".git/"):
        continue
    if "/__pycache__/" in f"/{rel}/":
        continue
    if rel.startswith("saves/"):
        continue
    if rel.endswith(".pyc"):
        continue
    if rel.endswith(".DS_Store"):
        continue
    files.append(rel)
files = sorted(set(files))
manifest = {"version": int(time.time()), "files": files}
(root / "asset-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n")
PY
