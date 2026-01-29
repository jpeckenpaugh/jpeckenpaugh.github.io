"""Layout helpers for action panels and ANSI-safe text width."""

from typing import Optional

from app.commands.scene_commands import format_commands
from app.ui.constants import ACTION_LINES, SCREEN_WIDTH


def strip_ansi(s: str) -> str:
    # Minimal ANSI stripping for accurate padding when we add colors inside lines.
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def pad_or_trim_ansi(text: str, width: int) -> str:
    # Pad based on visible length, not raw length.
    visible = strip_ansi(text)
    if len(visible) > width:
        # Trim by visible characters while keeping ANSI sequences intact.
        out = []
        vis_idx = 0
        i = 0
        while i < len(text) and vis_idx < width:
            ch = text[i]
            if ch == "\x1b" and i + 1 < len(text) and text[i + 1] == "[":
                j = i + 2
                while j < len(text) and text[j] != "m":
                    j += 1
                if j < len(text):
                    out.append(text[i:j + 1])
                    i = j + 1
                    continue
            out.append(ch)
            vis_idx += 1
            i += 1
        return "".join(out)
    return text + (" " * (width - len(visible)))


def pad_ansi(text: str, width: int) -> str:
    # Pad based on visible length, never trim ANSI sequences.
    visible = strip_ansi(text)
    if len(visible) >= width:
        return text
    return text + (" " * (width - len(visible)))


def center_ansi(text: str, width: int) -> str:
    visible_len = len(strip_ansi(text))
    if visible_len > width:
        return pad_or_trim_ansi(text, width)
    if visible_len == width:
        return text
    left = (width - visible_len) // 2
    right = width - visible_len - left
    return (" " * left) + text + (" " * right)


def center_crop_ansi(text: str, width: int, anchor_x: Optional[int] = None) -> str:
    visible = strip_ansi(text)
    visible_len = len(visible)
    if visible_len <= width:
        return center_ansi(text, width)
    if anchor_x is None:
        start = (visible_len - width) // 2
    else:
        try:
            anchor = int(anchor_x)
        except (TypeError, ValueError):
            anchor = visible_len // 2
        anchor = max(0, min(anchor, max(visible_len - 1, 0)))
        start = anchor - (width // 2)
        start = max(0, min(start, visible_len - width))
    end = start + width
    out = []
    vis_idx = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\x1b" and i + 1 < len(text) and text[i + 1] == "[":
            j = i + 2
            while j < len(text) and text[j] != "m":
                j += 1
            if j < len(text):
                seq = text[i:j + 1]
                if start <= vis_idx < end:
                    out.append(seq)
                i = j + 1
                continue
        if start <= vis_idx < end:
            out.append(ch)
        vis_idx += 1
        i += 1
    return "".join(out)


def format_action_lines(actions: list[str]) -> list[str]:
    clean = [a for a in actions if a.strip()]
    count = len(clean)
    if count <= 3:
        cols = 1
    elif count <= 6:
        cols = 2
    else:
        cols = 3
    content_width = SCREEN_WIDTH - 2
    gap = 2
    col_width = (content_width - gap * (cols - 1)) // cols
    rows = ACTION_LINES
    lines = []
    for r in range(rows):
        parts = []
        for c in range(cols):
            idx = r + c * rows
            if idx < count:
                parts.append(pad_or_trim_ansi(clean[idx], col_width))
            else:
                parts.append(" " * col_width)
        lines.append((" " * gap).join(parts))
    return lines


def format_command_lines(commands: list[dict]) -> list[str]:
    return format_action_lines(format_commands(commands))


def format_menu_actions(menu_data: dict, replacements: Optional[dict] = None) -> list[str]:
    actions = []
    replacements = replacements or {}
    for command in menu_data.get("actions", []):
        key = str(command.get("key", "")).upper()
        label = str(command.get("label", "")).strip()
        if not key or not label:
            continue
        for token, value in replacements.items():
            label = label.replace(token, value)
        actions.append(f"  [{key}] {label}")
    return format_action_lines(actions)
