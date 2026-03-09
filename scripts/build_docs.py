#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"


def should_include(rel: str) -> bool:
    if rel.startswith(".git/"):
        return False
    if rel.startswith("saves/"):
        return False
    if "/__pycache__/" in f"/{rel}/":
        return False
    if rel.endswith(".pyc"):
        return False
    if rel.endswith(".DS_Store"):
        return False
    return True


def write_build_time() -> None:
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    (DOCS_ROOT / "build-time.txt").write_text(f"{stamp}\n", encoding="utf-8")


def write_manifest() -> None:
    files: list[str] = []
    for path in DOCS_ROOT.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(DOCS_ROOT).as_posix()
        if should_include(rel):
            files.append(rel)

    manifest = {
        "version": int(time.time()),
        "files": sorted(set(files)),
    }
    (DOCS_ROOT / "asset-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    if not DOCS_ROOT.exists():
        raise SystemExit(f"docs folder not found: {DOCS_ROOT}")
    write_build_time()
    write_manifest()
    print(f"Updated {DOCS_ROOT / 'build-time.txt'}")
    print(f"Updated {DOCS_ROOT / 'asset-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
