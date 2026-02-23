"""Quest progression helpers."""

import copy
from typing import Any, Callable, Dict, Iterable, List, Optional, TypedDict, Tuple

from app.models import Player


class ActionHandler(TypedDict, total=False):
    apply: Callable[[Player, dict, Dict[str, Any], dict], Optional[str]]


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


def _objective_config(objectives_data, obj_type: str) -> dict:
    if objectives_data is None or not hasattr(objectives_data, "get"):
        return {}
    config = objectives_data.get(obj_type, {})
    return config if isinstance(config, dict) else {}


def _objective_key(obj: dict, objectives_data) -> Optional[str]:
    obj_type = str(obj.get("type", ""))
    config = _objective_config(objectives_data, obj_type)
    template = config.get("key")
    if not isinstance(template, str) or "{" not in template:
        return None
    result = template
    for key, value in obj.items():
        token = "{" + str(key) + "}"
        if token in result:
            result = result.replace(token, str(value))
    return result if result != template else None


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


def requirement_summary(player: Player, quest: dict) -> str:
    requirements = quest.get("requirements", {})
    if not isinstance(requirements, dict):
        requirements = {}
    parts = []
    level_min = int(requirements.get("level_min", 0) or 0)
    if level_min and int(player.level) < level_min:
        parts.append(f"Player level {level_min} is required.")
    flags_required = requirements.get("flags_required", [])
    if not isinstance(flags_required, list):
        flags_required = []
    unmet = [str(flag) for flag in flags_required if not player.flags.get(str(flag), False)]
    if unmet:
        parts.append("Quest prerequisites are not met.")
    if parts:
        return "Requirement not met. " + " ".join(parts)
    return "Requirement not met."


def _objectives_met(player: Player, progress: dict, objectives: Iterable[dict], objectives_data) -> bool:
    for obj in objectives:
        if not isinstance(obj, dict):
            continue
        obj_type = str(obj.get("type", ""))
        config = _objective_config(objectives_data, obj_type)
        completion = config.get("completion")
        if completion == "equip_slots":
            if not _equip_slots_complete(player, obj):
                return False
            continue
        key = _objective_key(obj, objectives_data)
        if not key:
            continue
        needed = int(obj.get("count", 1) or 1)
        current = int(progress.get(key, 0) or 0)
        if current < needed:
            return False
    return True


def _equip_slots_complete(player: Player, obj: dict) -> bool:
    slots = obj.get("slots", [])
    if not isinstance(slots, list):
        slots = []
    needed = int(obj.get("count", 0) or 0)
    if not needed:
        needed = len(slots)
    equipment = player.equipment if isinstance(player.equipment, dict) else {}
    equipped = sum(1 for slot in slots if equipment.get(str(slot)))
    return equipped >= needed


def _follower_template(entry: dict, followers_data: Optional[object]) -> dict:
    follower_type = str(entry.get("type", "follower"))
    template = {}
    if followers_data is not None and hasattr(followers_data, "get"):
        template = followers_data.get(follower_type, {}) or {}
    if not isinstance(template, dict):
        template = {}
    base = dict(template)
    base_name = entry.get("name") or base.get("name")
    if not base_name:
        base_name = follower_type.replace("_", " ").title()
    base.setdefault("level", 1)
    base.setdefault("xp", 0)
    base.setdefault("max_level", 5)
    base.setdefault("atk", 4)
    base.setdefault("defense", 2)
    base.setdefault("hp", 12)
    base.setdefault("max_hp", base.get("hp", 12))
    base.setdefault("mp", 6)
    base.setdefault("max_mp", base.get("mp", 6))
    base.setdefault("equipment", {})
    base.setdefault("abilities", [])
    base.setdefault("active_ability", "")
    base["type"] = follower_type
    base["name"] = base_name
    overrides = entry.get("overrides", {})
    if isinstance(overrides, dict):
        base.update(overrides)
    return base


def _action_handlers() -> Dict[str, ActionHandler]:
    return {
        "show_message": {"apply": _apply_show_message},
        "set_flags": {"apply": _apply_set_flags},
        "set_flag": {"apply": _apply_set_flag},
        "set_flag_values": {"apply": _apply_set_flag_values},
        "set_recruit_only_types": {"apply": _apply_set_recruit_only},
        "clear_recruit_only_types": {"apply": _apply_clear_recruit_only},
        "set_follower_cap": {"apply": _apply_set_follower_cap},
        "set_follower_cap_extra": {"apply": _apply_set_follower_cap_extra},
        "clear_follower_cap": {"apply": _apply_clear_follower_cap},
        "spend_gold": {"apply": _apply_spend_gold},
        "grant_follower": {"apply": _apply_grant_follower},
        "grant_items": {"apply": _apply_grant_items},
        "grant_xp": {"apply": _apply_grant_xp},
        "grant_mp_bonus": {"apply": _apply_grant_mp_bonus},
        "grant_spell_rank_up": {"apply": _apply_grant_spell_rank_up},
        "grant_followers": {"apply": _apply_grant_followers},
    }


def _apply_set_flags(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    flags = action.get("flags", [])
    if not isinstance(flags, list):
        return None
    for flag in flags:
        if flag:
            player.flags[str(flag)] = True
    return None


def _apply_show_message(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    message = str(action.get("message", "") or "").strip()
    if message:
        effects["messages"] = effects.get("messages", []) + [message]
    return None


def _apply_set_flag(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    key = action.get("key")
    if not key:
        return None
    value = action.get("value", True)
    player.flags[str(key)] = value
    return None


def _apply_set_flag_values(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    values = action.get("values", {})
    if not isinstance(values, dict):
        return None
    for key, value in values.items():
        if key:
            player.flags[str(key)] = value
    return None


def _apply_set_recruit_only(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    types = action.get("types", [])
    if not isinstance(types, list):
        return None
    player.flags["recruit_only_types"] = [str(t) for t in types if t]
    return None


def _apply_clear_recruit_only(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    player.flags.pop("recruit_only_types", None)
    return None


def _apply_set_follower_cap(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    value = action.get("value")
    if isinstance(value, int) and value > 0:
        player.flags["follower_cap"] = value
    return None


def _apply_set_follower_cap_extra(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    extra = action.get("value")
    if not isinstance(extra, int) or extra <= 0:
        return None
    pending = int(ctx.get("pending_grants", 0) or 0)
    followers = getattr(player, "followers", [])
    base_count = len(followers) if isinstance(followers, list) else 0
    player.flags["follower_cap"] = base_count + pending + extra
    return None


def _apply_clear_follower_cap(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    player.flags.pop("follower_cap", None)
    return None


def _apply_spend_gold(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    amount = int(action.get("amount", 0) or 0)
    if amount <= 0:
        return None
    gold = int(getattr(player, "gold", 0) or 0)
    if gold < amount:
        return "Not enough GP."
    player.gold = gold - amount
    return None


def _apply_grant_follower(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    entry = action.get("follower")
    if not isinstance(entry, dict):
        return None
    follower = build_follower_from_entry(entry, ctx.get("followers_data"))
    if not follower:
        return None
    if not player.add_follower(follower):
        if action.get("required"):
            return "No room for another follower."
        return None
    if entry.get("count_as_recruit") and ctx.get("quests_data") is not None:
        emit_quest_events(
            player,
            ctx["quests_data"],
            ctx.get("events_data"),
            "recruit_follower",
            [{"follower_type": follower.get("type", ""), "count": 1}],
            ctx.get("items_data"),
            ctx.get("spells_data"),
            ctx.get("followers_data"),
            ctx.get("objectives_data"),
        )
    return None


def _apply_grant_items(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    items = action.get("items", [])
    if not isinstance(items, list):
        return None
    for item_id in items:
        if item_id:
            player.add_item(str(item_id), 1)
    return None


def _apply_grant_xp(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    amount = int(action.get("amount", 0) or 0)
    if amount <= 0:
        return None
    effects["xp_gain"] = effects.get("xp_gain", 0) + amount
    effects["levels_gained"] = effects.get("levels_gained", 0) + player.gain_xp(amount)
    return None


def _apply_grant_mp_bonus(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    bonus = int(action.get("amount", 0) or 0)
    if bonus <= 0:
        return None
    player.max_mp += bonus
    player.mp += bonus
    return None


def _apply_grant_spell_rank_up(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    amount = int(action.get("amount", 0) or 0)
    spells_data = ctx.get("spells_data")
    items_data = ctx.get("items_data")
    if amount <= 0 or spells_data is None:
        return None
    ranks = player.flags.get("spell_ranks")
    if not isinstance(ranks, dict):
        ranks = {}
    available = spells_data.available(player, items_data) if hasattr(spells_data, "available") else []
    for spell_id, _spell in available:
        current = ranks.get(str(spell_id))
        if not isinstance(current, int) or current < 1:
            current = 1
        ranks[str(spell_id)] = min(3, current + amount)
    player.flags["spell_ranks"] = ranks
    return None


def _apply_grant_followers(player: Player, action: dict, ctx: Dict[str, Any], effects: dict) -> Optional[str]:
    entries = action.get("followers", [])
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        follower = build_follower_from_entry(entry, ctx.get("followers_data"))
        if follower:
            player.add_follower(follower)
    return None


def _action_context(
    actions: List[dict],
    *,
    items_data: Optional[object] = None,
    spells_data: Optional[object] = None,
    followers_data: Optional[object] = None,
    quests_data: Optional[object] = None,
    objectives_data: Optional[object] = None,
    events_data: Optional[object] = None,
) -> Dict[str, Any]:
    pending_grants = 0
    for action in actions:
        if not isinstance(action, dict):
            continue
        if action.get("type") == "grant_follower":
            pending_grants += 1
    return {
        "items_data": items_data,
        "spells_data": spells_data,
        "followers_data": followers_data,
        "quests_data": quests_data,
        "objectives_data": objectives_data,
        "events_data": events_data,
        "pending_grants": pending_grants,
    }


def apply_actions(
    player: Player,
    actions: List[dict],
    *,
    items_data: Optional[object] = None,
    spells_data: Optional[object] = None,
    followers_data: Optional[object] = None,
    quests_data: Optional[object] = None,
    objectives_data: Optional[object] = None,
    events_data: Optional[object] = None,
    dry_run: bool = False,
) -> Tuple[bool, Optional[str], dict]:
    if not actions:
        return True, None, {"xp_gain": 0, "levels_gained": 0}
    target = copy.deepcopy(player) if dry_run else player
    _ensure_player_quest_state(target)
    effects = {"xp_gain": 0, "levels_gained": 0, "messages": []}
    ctx = _action_context(
        actions,
        items_data=items_data,
        spells_data=spells_data,
        followers_data=followers_data,
        quests_data=quests_data,
        objectives_data=objectives_data,
        events_data=events_data,
    )
    handlers = _action_handlers()
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = str(action.get("type", "") or "")
        handler = handlers.get(action_type)
        if not handler or "apply" not in handler:
            continue
        error = handler["apply"](target, action, ctx, effects)
        if error:
            return False, error, effects
    return True, None, effects


def _start_actions_for(quest: dict) -> List[dict]:
    actions = []
    start_actions = quest.get("on_start_actions", [])
    if isinstance(start_actions, list) and start_actions:
        return [a for a in start_actions if isinstance(a, dict)]
    return actions


def _complete_actions_for(quest: dict) -> List[dict]:
    actions = []
    complete_actions = quest.get("on_complete_actions", [])
    if isinstance(complete_actions, list) and complete_actions:
        actions.extend([a for a in complete_actions if isinstance(a, dict)])
    return actions


def _apply_rewards(
    player: Player,
    quest_id: str,
    quest: dict,
    items_data: Optional[object] = None,
    spells_data: Optional[object] = None,
    followers_data: Optional[object] = None,
    quests_data: Optional[object] = None,
    objectives_data: Optional[object] = None,
    events_data: Optional[object] = None,
) -> tuple[int, int]:
    actions = _complete_actions_for(quest)
    if not actions:
        return 0, 0
    ok, _error, effects = apply_actions(
        player,
        actions,
        items_data=items_data,
        spells_data=spells_data,
        followers_data=followers_data,
        quests_data=quests_data,
        objectives_data=objectives_data,
        events_data=events_data,
    )
    if not ok:
        return 0, 0
    return int(effects.get("xp_gain", 0) or 0), int(effects.get("levels_gained", 0) or 0)


def build_follower_from_entry(entry: dict, followers_data: Optional[object] = None) -> Optional[dict]:
    if not isinstance(entry, dict):
        return None
    return _follower_template(entry, followers_data)


def apply_quest_start_actions(
    player: Player,
    quest: dict,
    *,
    items_data: Optional[object] = None,
    spells_data: Optional[object] = None,
    followers_data: Optional[object] = None,
    quests_data: Optional[object] = None,
    objectives_data: Optional[object] = None,
    events_data: Optional[object] = None,
) -> Tuple[bool, Optional[str], List[str]]:
    actions = _start_actions_for(quest)
    if not actions:
        return True, None, []
    ok, error, _effects = apply_actions(
        player,
        actions,
        items_data=items_data,
        spells_data=spells_data,
        followers_data=followers_data,
        quests_data=quests_data,
        objectives_data=objectives_data,
        events_data=events_data,
        dry_run=True,
    )
    if not ok:
        return False, error, []
    ok, error, effects = apply_actions(
        player,
        actions,
        items_data=items_data,
        spells_data=spells_data,
        followers_data=followers_data,
        quests_data=quests_data,
        objectives_data=objectives_data,
        events_data=events_data,
    )
    messages = effects.get("messages", [])
    return ok, error, messages if isinstance(messages, list) else []


def start_quest(player: Player, quest_id: str) -> bool:
    _ensure_player_quest_state(player)
    entry = player.quests.get(quest_id)
    if isinstance(entry, dict) and entry.get("status") == "complete":
        return False
    qstate = _quest_state(player, quest_id)
    qstate["status"] = "active"
    return True


def ordered_quest_ids(stories_data, quests_data, continent: Optional[str] = None) -> List[str]:
    ordered: List[str] = []
    if hasattr(stories_data, "all"):
        for story in stories_data.all().values():
            if not isinstance(story, dict):
                continue
            quest_ids = story.get("quests", [])
            if not isinstance(quest_ids, list):
                continue
            for quest_id in quest_ids:
                quest_id = str(quest_id)
                if quest_id in ordered:
                    continue
                quest = quests_data.get(quest_id, {}) if hasattr(quests_data, "get") else {}
                if continent:
                    quest_continent = str(quest.get("continent", "") or "")
                    if quest_continent and quest_continent != continent:
                        continue
                ordered.append(quest_id)
    return ordered


def quest_entries(
    player: Player,
    quests_data,
    items_data: Optional[object] = None,
    *,
    continent: Optional[str] = None,
    include_locked_next: bool = False,
    ordered_ids: Optional[List[str]] = None,
    objectives_data: Optional[object] = None,
    events_data: Optional[object] = None,
) -> List[dict]:
    _ensure_player_quest_state(player)
    entries: List[dict] = []
    if not quests_data:
        return entries
    evaluate_quests(player, quests_data, items_data, objectives_data=objectives_data, events_data=events_data)
    quest_items = []
    if ordered_ids:
        for quest_id in ordered_ids:
            quest = quests_data.get(quest_id, {}) if hasattr(quests_data, "get") else {}
            if isinstance(quest, dict):
                quest_items.append((quest_id, quest))
    else:
        quest_items = list(quests_data.all().items())

    shown_next = False
    for quest_id, quest in quest_items:
        if not isinstance(quest, dict):
            continue
        if continent:
            quest_continent = str(quest.get("continent", "") or "")
            if quest_continent and quest_continent != continent:
                continue
        qstate = player.quests.get(quest_id)
        status = qstate.get("status") if isinstance(qstate, dict) else None
        if status == "complete":
            entries.append({"id": quest_id, "quest": quest, "status": "complete"})
            continue
        if status == "active":
            entries.append({"id": quest_id, "quest": quest, "status": "active"})
            shown_next = True
            break
        if _requirements_met(player, quest):
            entries.append({"id": quest_id, "quest": quest, "status": "available"})
            shown_next = True
            break
        if include_locked_next and not shown_next:
            entries.append({"id": quest_id, "quest": quest, "status": "locked"})
            break
    return entries


def evaluate_quests(
    player: Player,
    quests_data,
    items_data: Optional[object] = None,
    spells_data: Optional[object] = None,
    followers_data: Optional[object] = None,
    objectives_data: Optional[object] = None,
    events_data: Optional[object] = None,
) -> List[str]:
    _ensure_player_quest_state(player)
    messages: List[str] = []
    changed = True
    while changed:
        changed = False
        for quest_id, quest in quests_data.all().items():
            if not isinstance(quest, dict):
                continue
            qstate = player.quests.get(quest_id)
            if not isinstance(qstate, dict):
                continue
            if qstate.get("status") == "complete":
                continue
            if not _requirements_met(player, quest):
                continue
            objectives = quest.get("objectives", [])
            if not isinstance(objectives, list):
                objectives = []
            progress = qstate.get("progress", {})
            if not _objectives_met(player, qstate.get("progress", {}), objectives, objectives_data):
                continue
            qstate["status"] = "complete"
            xp_gain, _levels_gained = _apply_rewards(
                player,
                quest_id,
                quest,
                items_data,
                spells_data,
                followers_data,
                quests_data,
                objectives_data,
                events_data,
            )
            title = quest.get("title", quest_id)
            messages.append(f"Quest complete: {title}.")
            if xp_gain > 0:
                messages.append(f"You gain {xp_gain} XP.")
            changed = True
    return messages


def record_event(
    player: Player,
    quests_data,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    objectives_data: Optional[object] = None,
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
            config = _objective_config(objectives_data, obj_type)
            event_name = str(config.get("event", "") or "")
            if not event_name or event_name != event_type:
                continue
            qstate = player.quests.get(quest_id)
            if not isinstance(qstate, dict) or qstate.get("status") != "active":
                continue
            match = config.get("match", {})
            if not isinstance(match, dict):
                match = {}
            object_key = str(match.get("object_key", "") or "")
            payload_key = str(match.get("payload_key", "") or "")
            if object_key and payload_key:
                obj_value = str(obj.get(object_key, "") or "")
                payload_value = str(payload.get(payload_key, "") or "")
                if obj_value and obj_value != payload_value:
                    continue
            key = _objective_key(obj, objectives_data)
            if not key:
                continue
            progress = qstate.get("progress", {})
            current = int(progress.get(key, 0) or 0)
            update = config.get("update", {})
            if not isinstance(update, dict):
                update = {}
            mode = str(update.get("mode", "add") or "add")
            count_key = update.get("count_key", "count")
            count_value = 1
            if isinstance(count_key, list):
                for key_name in count_key:
                    if key_name in payload:
                        count_value = int(payload.get(key_name, 1) or 1)
                        break
            else:
                count_value = int(payload.get(str(count_key), 1) or 1)
            if mode == "max":
                progress[key] = max(current, count_value)
            else:
                progress[key] = current + count_value
            qstate["progress"] = progress


def handle_event(
    player: Player,
    quests_data,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    items_data: Optional[object] = None,
    spells_data: Optional[object] = None,
    followers_data: Optional[object] = None,
    objectives_data: Optional[object] = None,
    events_data: Optional[object] = None,
) -> List[str]:
    record_event(player, quests_data, event_type, payload, objectives_data)
    return evaluate_quests(player, quests_data, items_data, spells_data, followers_data, objectives_data, events_data)


def emit_quest_events(
    player: Player,
    quests_data,
    events_data,
    trigger: str,
    payloads: List[Dict[str, Any]],
    items_data: Optional[object] = None,
    spells_data: Optional[object] = None,
    followers_data: Optional[object] = None,
    objectives_data: Optional[object] = None,
) -> List[str]:
    if not events_data or not hasattr(events_data, "all"):
        return []
    messages: List[str] = []
    for _name, rule in events_data.all().items():
        if not isinstance(rule, dict):
            continue
        if str(rule.get("trigger", "")) != trigger:
            continue
        event_name = str(rule.get("event", "") or "")
        if not event_name:
            continue
        payload_template = rule.get("payload", {})
        if not isinstance(payload_template, dict):
            payload_template = {}
        for payload in payloads:
            event_payload: Dict[str, Any] = {}
            for key, value in payload_template.items():
                if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
                    token = value[1:-1]
                    event_payload[key] = payload.get(token, "")
                else:
                    event_payload[key] = value
            if not event_payload:
                continue
            messages.extend(handle_event(
                player,
                quests_data,
                event_name,
                event_payload,
                items_data,
                spells_data,
                followers_data,
                objectives_data,
                events_data,
            ))
    return messages
