# Command Schema

Commands are defined in JSON (global, scenes, venues, menus) and merged at runtime.

## Base Fields

- `key`: string displayed in the Actions panel (e.g., `"F"`, `"1"`)
- `label`: string shown next to the key (e.g., `"Shop"`)
- `command`: string command id dispatched by the router (the action to run)

## Optional Fields

- `target`: string target used by the command (e.g., `"forest"`, `"town_shop"`)
- `service_id`: string service id used by venue services (e.g., `"rest"`, `"meal"`)
- `when`: string condition for filtering (e.g., `"has_opponents"`, `"no_opponents"`, `"needs_rest"`, `"has_save"`)
- `type`: string categorizing the command (e.g., `"menu_open"`, `"combat"`, `"system"`)
- `anim`: string animation hint (e.g., `"flash"`, `"melt"`, `"battle_start"`, `"battle_end"`)
- `requires_target`: boolean to indicate a target is required
- `suppress_actions`: boolean to hide the action panel during a command

## Scene Object Entries (scenes.json)

When scenes use object composition (`objects`, `objects_left`, `objects_right`, `objects_bottom`), entries can be:

```json
{ "id": "house", "label": "Shop", "label_row": 2, "label_key": "o" }
```

Optional fields:
- `label`: text injected into the object art (centered within the row content).
- `label_row`: 0-based row index in the object art to place the label.
- `label_key`: color key used for the label mask.
- `label_variation`: jitter amount for label color.
- `label_jitter_stability`: whether label jitter is stable per tick.
- `scatter`: id of a dynamic object to scatter across a repeated base line (forest bottom).

## Scene Gap Ground (scenes.json)

When rendering a battle gap in a scene with left/right objects, you can add
ground lines beneath opponents:

```json
"gap_ground": ["grass", "grass", "grass"],
"gap_ground_scatter": "battle_ground"
```

`gap_ground` entries reference object ids. `gap_ground_scatter` points to a
dynamic object definition used to randomly place glyphs on those lines.

## Dynamic Objects (objects.json)

Objects can define a `dynamic` block for scatter behavior:

```json
"dynamic": {
  "mode": "scatter",
  "glyphs": ["o", "O"],
  "color_keys": ["z", "Z", "x", "X", "l", "L"],
  "scatter_chance": 0.2
}
```

These dynamic objects are referenced by `scatter` or `gap_ground_scatter`.

## Examples

```json
{
  "key": "F",
  "label": "Set out for the Forest",
  "command": "ENTER_SCENE",
  "target": "forest"
}
```

```json
{
  "key": "1",
  "label": "Buy Rations",
  "command": "NUM1"
}
```

```json
{
  "key": "S",
  "label": "Shop",
  "command": "ENTER_VENUE",
  "target": "town_shop"
}
```
