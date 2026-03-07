# RPG Rebuild (OO Skeleton)

This is a clean restart of the project with an object-oriented architecture.

## Run

```bash
python main.py
```

## Current Scope

- `GameApp` bootstraps runtime dependencies and runs the loop.
- `GameSession` is the saveable root state object.
- `TitleScene` includes `Continue`, `New Game`, `Asset Explorer`, and `Quit`.
- `TitleScene` now includes a legacy-style top panorama tilemap (`forest + town + forest`) that scrolls over a 100x10 viewport.
  - The panorama is assembled from legacy `scenes.json` + `objects.json` assets with `color_mask` + `colors.json` ANSI coloring.
- `AssetExplorerScene` browses JSON assets from `legacy/data`.
- `SaveGameService` handles JSON save/load (`saves/slot1.json`).
- `Renderer` and `InputAdapter` isolate terminal IO.

## Asset Explorer Controls

- `Left/Right` or `A/D`: switch category
- `Up/Down` or `W/S`: select asset entry
- `U/J`: scroll JSON preview
- `R`: reload current asset file
- `Q`: return to title

## Next Steps

- Add a `TownScene` and transition from `TitleScene` to `TownScene`.
- Introduce command objects for actions.
- Add encounter and battle domain classes.

