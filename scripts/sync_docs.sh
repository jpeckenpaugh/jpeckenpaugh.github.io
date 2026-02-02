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
