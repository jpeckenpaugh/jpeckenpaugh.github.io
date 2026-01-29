"""Scene command composition and filtering."""

from typing import List, Set

from app.data_access.commands_data import CommandsData
from app.data_access.scenes_data import ScenesData
from app.models import Player, Opponent


def filter_commands(commands: List[dict], player: Player, opponents: List[Opponent]) -> List[dict]:
    has_opponents = any(opponent.hp > 0 for opponent in opponents)
    has_save = bool(getattr(player, "has_save", False))
    filtered = []
    for command in commands:
        when = command.get("when")
        if when == "has_opponents" and not has_opponents:
            continue
        if when == "no_opponents" and has_opponents:
            continue
        if when == "needs_rest":
            if not (player.hp < player.max_hp or player.mp < player.max_mp):
                continue
        if when == "has_save" and not has_save:
            continue
        filtered.append(command)
    return filtered


def scene_commands(
    scenes_data: ScenesData,
    commands_data: CommandsData,
    scene_id: str,
    player: Player,
    opponents: List[Opponent],
    include_hidden: bool = False,
) -> List[dict]:
    scene_data = scenes_data.get(scene_id, {})
    scene_list = scene_data.get("commands", [])
    if not isinstance(scene_list, list):
        scene_list = []
    scene_list = filter_commands(scene_list, player, opponents)
    if scene_id == "title":
        global_list = []
    else:
        global_list = filter_commands(commands_data.global_commands(), player, opponents)
    merged = []
    seen = set()
    for command in scene_list + global_list:
        if not include_hidden and command.get("key") == "_":
            continue
        key = str(command.get("key", "")).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(command)
    return merged


def format_commands(commands: List[dict]) -> List[str]:
    actions = []
    for command in commands:
        key = str(command.get("key", "")).upper()
        label = str(command.get("label", "")).strip()
        if not key or not label:
            continue
        actions.append(f"  [{key}] {label}")
    return actions


def command_ids_by_type(scenes_data: ScenesData, command_type: str) -> Set[str]:
    ids: Set[str] = set()
    for scene in scenes_data.all().values():
        if not isinstance(scene, dict):
            continue
        for command in scene.get("commands", []):
            if command.get("type") != command_type:
                continue
            cmd_id = command.get("command")
            if cmd_id:
                ids.add(cmd_id)
    return ids


def command_ids_by_anim(scenes_data: ScenesData, anim: str) -> Set[str]:
    ids: Set[str] = set()
    for scene in scenes_data.all().values():
        if not isinstance(scene, dict):
            continue
        for command in scene.get("commands", []):
            if command.get("anim") != anim:
                continue
            cmd_id = command.get("command")
            if cmd_id:
                ids.add(cmd_id)
    return ids
