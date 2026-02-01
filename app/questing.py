"""Quest progression helpers."""

from typing import Any, Dict, Iterable, List, Optional

from app.models import Player


def _ensure_player_quest_state(player: Player) -> None:
    if not isinstance(getattr(player, "flags", None), dict):
        player.flags = {}
    if not isinstance(getattr(player, "quests", None), dict):
        player.quests = {}


def _quest_state(player: Player, quest_id: str) -> dict:
    _ensure_player_quest_state(player)
    entry = player.quests.get(quest_id)
    if not isinstance(entry, dict):
        entry = {"status": "active", "progress": {}}
        player.quests[quest_id] = entry
    if entry.get("status") not in ("active", "complete"):
        entry["status"] = "active"
    if not isinstance(entry.get("progress"), dict):
        entry["progress"] = {}
    return entry


def _objective_key(obj: dict) -> Optional[str]:
    obj_type = str(obj.get("type", ""))
    if obj_type == "recruit_follower":
        follower_type = str(obj.get("follower_type", ""))
        return f"recruit_follower:{follower_type}"
    if obj_type == "fuse_followers":
        follower_type = str(obj.get("follower_type", ""))
        return f"fuse_followers:{follower_type}"
    if obj_type == "visit_scene":
        scene_id = str(obj.get("id", ""))
        return f"visit_scene:{scene_id}"
    return None


def _requirements_met(player: Player, quest: dict) -> bool:
    requirements = quest.get("requirements", {})
    if not isinstance(requirements, dict):
        requirements = {}
    level_min = int(requirements.get("level_min", 0) or 0)
    if int(player.level) < level_min:
        return False
    flags_required = requirements.get("flags_required", [])
    if not isinstance(flags_required, list):
        flags_required = []
    for flag in flags_required:
        if not player.flags.get(str(flag), False):
            return False
    return True


def _objectives_met(progress: dict, objectives: Iterable[dict]) -> bool:
    for obj in objectives:
        if not isinstance(obj, dict):
            continue
        key = _objective_key(obj)
        if not key:
            continue
        needed = int(obj.get("count", 1) or 1)
        current = int(progress.get(key, 0) or 0)
        if current < needed:
            return False
    return True


def _build_follower(entry: dict) -> dict:
    follower_type = str(entry.get("type", "follower"))
    base_name = entry.get("name")
    if not base_name:
        base_name = follower_type.replace("_", " ").title()
    abilities = []
    active = ""
    if follower_type == "fairy":
        abilities = ["fairy_heal", "fairy_mana"]
        active = "fairy_heal"
    if follower_type.startswith("mushroom"):
        abilities = ["mushroom_tea_brew"]
    if not active and abilities:
        active = abilities[0]
    return {
        "type": follower_type,
        "name": base_name,
        "level": 1,
        "xp": 0,
        "max_level": 5,
        "atk": 4,
        "defense": 2,
        "hp": 12,
        "max_hp": 12,
        "mp": 6,
        "max_mp": 6,
        "equipment": {},
        "abilities": abilities,
        "active_ability": active,
    }


def _apply_rewards(player: Player, quest_id: str, quest: dict, items_data: Optional[object] = None) -> None:
    rewards = quest.get("rewards", {})
    if not isinstance(rewards, dict):
        rewards = {}
    flags_set = rewards.get("flags_set", [])
    if not isinstance(flags_set, list):
        flags_set = []
    for flag in flags_set:
        player.flags[str(flag)] = True
    items = rewards.get("items", [])
    if not isinstance(items, list):
        items = []
    for item_id in items:
        if not item_id:
            continue
        player.add_item(str(item_id), 1)
    followers_add = rewards.get("followers_add", [])
    if isinstance(followers_add, list):
        for follower_entry in followers_add:
            if not isinstance(follower_entry, dict):
                continue
            follower = _build_follower(follower_entry)
            player.add_follower(follower)


def build_follower_from_entry(entry: dict) -> Optional[dict]:
    if not isinstance(entry, dict):
        return None
    return _build_follower(entry)


def start_quest(player: Player, quest_id: str) -> bool:
    _ensure_player_quest_state(player)
    entry = player.quests.get(quest_id)
    if isinstance(entry, dict) and entry.get("status") == "complete":
        return False
    qstate = _quest_state(player, quest_id)
    qstate["status"] = "active"
    return True


def quest_entries(player: Player, quests_data) -> List[dict]:
    _ensure_player_quest_state(player)
    entries: List[dict] = []
    if not quests_data:
        return entries
    for quest_id, quest in quests_data.all().items():
        if not isinstance(quest, dict):
            continue
        qstate = player.quests.get(quest_id)
        status = qstate.get("status") if isinstance(qstate, dict) else None
        if status == "complete":
            entries.append({"id": quest_id, "quest": quest, "status": "complete"})
            continue
        if status == "active":
            entries.append({"id": quest_id, "quest": quest, "status": "active"})
            continue
        if _requirements_met(player, quest):
            entries.append({"id": quest_id, "quest": quest, "status": "available"})
    return entries


def evaluate_quests(player: Player, quests_data, items_data: Optional[object] = None) -> List[str]:
    _ensure_player_quest_state(player)
    messages: List[str] = []
    changed = True
    while changed:
        changed = False
        for quest_id, quest in quests_data.all().items():
            if not isinstance(quest, dict):
                continue
            qstate = _quest_state(player, quest_id)
            if qstate.get("status") == "complete":
                continue
            if not _requirements_met(player, quest):
                continue
            objectives = quest.get("objectives", [])
            if not isinstance(objectives, list):
                objectives = []
            if not _objectives_met(qstate.get("progress", {}), objectives):
                continue
            qstate["status"] = "complete"
            _apply_rewards(player, quest_id, quest, items_data)
            title = quest.get("title", quest_id)
            messages.append(f"Quest complete: {title}.")
            changed = True
    return messages


def record_event(
    player: Player,
    quests_data,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    _ensure_player_quest_state(player)
    payload = payload or {}
    for quest_id, quest in quests_data.all().items():
        if not isinstance(quest, dict):
            continue
        objectives = quest.get("objectives", [])
        if not isinstance(objectives, list):
            continue
        for obj in objectives:
            if not isinstance(obj, dict):
                continue
            obj_type = str(obj.get("type", ""))
            if obj_type != event_type:
                continue
            if event_type in ("recruit_follower", "fuse_followers"):
                follower_type = str(obj.get("follower_type", ""))
                if follower_type and follower_type != str(payload.get("follower_type", "")):
                    continue
            if event_type == "visit_scene":
                scene_id = str(obj.get("id", ""))
                if scene_id and scene_id != str(payload.get("scene_id", "")):
                    continue
            key = _objective_key(obj)
            if not key:
                continue
            qstate = _quest_state(player, quest_id)
            progress = qstate.get("progress", {})
            current = int(progress.get(key, 0) or 0)
            progress[key] = current + int(payload.get("count", 1) or 1)
            qstate["progress"] = progress


def handle_event(
    player: Player,
    quests_data,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    items_data: Optional[object] = None,
) -> List[str]:
    record_event(player, quests_data, event_type, payload)
    return evaluate_quests(player, quests_data, items_data)
