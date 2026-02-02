#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS="$ROOT/docs"

rsync -av --delete \
  --exclude ".git/" \
  --exclude "__pycache__/" \
  --exclude "venv/" \
  --exclude "tmp/" \
  --exclude "tmp1.txt" \
  --exclude "saves/" \
  --exclude "docs/" \
  --exclude "*.pyc" \
  "$ROOT/app/" "$DOCS/app/"

rsync -av --delete \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  "$ROOT/data/" "$DOCS/data/"

rsync -av \
  "$ROOT/main.py" \
  "$ROOT/music.py" \
  "$ROOT/render.py" \
  "$ROOT/color_map.py" \
  "$DOCS/"

ROOT_PATH="$ROOT"
python3 - <<'PY'
import json
import os
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
    if rel.endswith(".pyc"):
        continue
    if rel.endswith(".DS_Store"):
        continue
    files.append(rel)
files = sorted(set(files))
manifest = {"files": files}
(root / "asset-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n")
PY
