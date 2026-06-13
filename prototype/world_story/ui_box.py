from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import List


ANSI_RESET = "\x1b[0m"


@dataclass(frozen=True)
class UIBoxBorderGlyphs:
    tl: str
    tr: str
    bl: str
    br: str
    h: str
    v: str


@dataclass
class UIBoxSpec:
    role: str
    border_style: str
    body_text: str
    title: str = ""
    actions: List[str] | None = None
    center_x: int | None = None
    center_y: int | None = None
    x: int | None = None
    y: int | None = None
    max_body_width: int = 56
    padding_x: int = 1
    padding_y: int = 1
    body_align: str = "left"
    wrap_mode: str = "balanced"
    border_gradient: bool = True
    anchor: str = "center"
    preserve_body_whitespace: bool = False
    blink_body_rows: List[int] | None = None
    dim_body_rows: List[int] | None = None


@dataclass(frozen=True)
class UIBoxLayout:
    spec: UIBoxSpec
    lines: List[str]
    x0: int
    y0: int
    box_w: int
    box_h: int
    title_start: int
    title_end: int
    action_row_index: int
    blink_line_indices: set[int]
    dim_line_indices: set[int]
    screen_w: int
    screen_h: int


def ui_border_gradient_code(x: int, y: int, width: int, height: int) -> str:
    if width <= 1 and height <= 1:
        return "\x1b[38;2;192;192;192m"
    t = ((x / max(1, width - 1)) + (y / max(1, height - 1))) / 2.0
    if t <= 0.5:
        tt = t / 0.5
        start = (192, 192, 192)
        end = (77, 77, 255)
    else:
        tt = (t - 0.5) / 0.5
        start = (77, 77, 255)
        end = (96, 96, 96)
    r = int(start[0] + (end[0] - start[0]) * tt)
    g = int(start[1] + (end[1] - start[1]) * tt)
    b = int(start[2] + (end[2] - start[2]) * tt)
    return f"\x1b[38;2;{r};{g};{b}m"


def _ui_border_glyphs(style: str) -> UIBoxBorderGlyphs:
    key = str(style).strip().lower()
    if key == "double":
        return UIBoxBorderGlyphs(tl="╔", tr="╗", bl="╚", br="╝", h="═", v="║")
    if key == "heavy":
        return UIBoxBorderGlyphs(tl="┏", tr="┓", bl="┗", br="┛", h="━", v="┃")
    return UIBoxBorderGlyphs(tl="┌", tr="┐", bl="└", br="┘", h="─", v="│")


def _balanced_wrap_lines(text: str, width: int) -> List[str]:
    lines = textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)
    if len(lines) < 2:
        return lines or [text[:width]]
    while len(lines) >= 2:
        tail_words = lines[-1].split()
        prev_words = lines[-2].split()
        if len(tail_words) > 2 or len(prev_words) <= 2:
            break
        moved = prev_words[-1]
        cand_tail = f"{moved} {lines[-1]}".strip()
        cand_prev = " ".join(prev_words[:-1]).strip()
        if not cand_prev or len(cand_tail) > width:
            break
        lines[-2] = cand_prev
        lines[-1] = cand_tail
    return lines


def _wrap_ui_body(text: str, width: int, mode: str, preserve_whitespace: bool = False) -> List[str]:
    out: List[str] = []
    wrap_mode = str(mode).strip().lower()
    for para in str(text).splitlines():
        line = str(para).rstrip("\n")
        test_line = line if preserve_whitespace else line.strip()
        if not preserve_whitespace:
            line = test_line
        if not test_line:
            out.append("")
            continue
        if wrap_mode == "balanced":
            out.extend(_balanced_wrap_lines(line, width))
        else:
            out.extend(textwrap.wrap(line, width=width, break_long_words=False, break_on_hyphens=False))
    return out or [""]


def _format_ui_body_line(text: str, width: int, align: str) -> str:
    mode = str(align).strip().lower()
    if mode == "center":
        return text.center(width)
    if mode == "right":
        return text.rjust(width)
    return text.ljust(width)


def _resolve_ui_box_origin(box_w: int, box_h: int, spec: UIBoxSpec, screen_w: int, screen_h: int) -> tuple[int, int]:
    if spec.x is not None and spec.y is not None:
        return (max(0, min(screen_w - box_w, int(spec.x))), max(0, min(screen_h - box_h, int(spec.y))))

    cx = screen_w // 2 if spec.center_x is None else int(spec.center_x)
    cy = screen_h // 2 if spec.center_y is None else int(spec.center_y)
    anchor = str(spec.anchor).strip().lower()
    if anchor == "left":
        x0 = cx
        y0 = cy - (box_h // 2)
    elif anchor == "right":
        x0 = cx - box_w
        y0 = cy - (box_h // 2)
    elif anchor == "top":
        x0 = cx - (box_w // 2)
        y0 = cy
    elif anchor == "bottom":
        x0 = cx - (box_w // 2)
        y0 = cy - box_h
    else:
        x0 = cx - (box_w // 2)
        y0 = cy - (box_h // 2)
    return (max(0, min(screen_w - box_w, x0)), max(0, min(screen_h - box_h, y0)))


def build_ui_box_layout(spec: UIBoxSpec, screen_w: int = 100, screen_h: int = 30) -> UIBoxLayout:
    glyphs = _ui_border_glyphs(spec.border_style)
    max_w = max(8, min(screen_w - 4, int(spec.max_body_width)))
    wrapped = _wrap_ui_body(spec.body_text, max_w, spec.wrap_mode, bool(spec.preserve_body_whitespace))
    body_w = max((len(line) for line in wrapped), default=0)
    actions = spec.actions if isinstance(spec.actions, list) else []
    action_row = "  ".join(str(item).strip() for item in actions if str(item).strip())
    title = str(spec.title).strip()
    title_token = f"[ {title} ]" if title else ""
    inner_w = body_w + (max(0, int(spec.padding_x)) * 2)
    if title_token:
        inner_w = max(inner_w, len(title_token) + 4)
    if action_row:
        inner_w = max(inner_w, len(action_row) + 4)

    lines: List[str] = []
    title_left = max(0, (inner_w - len(title_token)) // 2) if title_token else 0
    title_right = max(0, inner_w - len(title_token) - title_left) if title_token else 0
    if title_token:
        lines.append(glyphs.tl + (glyphs.h * title_left) + title_token + (glyphs.h * title_right) + glyphs.tr)
    else:
        lines.append(glyphs.tl + (glyphs.h * inner_w) + glyphs.tr)

    for _ in range(max(0, int(spec.padding_y))):
        lines.append(glyphs.v + (" " * inner_w) + glyphs.v)
    for line in wrapped:
        body = _format_ui_body_line(line, body_w, spec.body_align)
        content = (" " * max(0, int(spec.padding_x))) + body + (" " * max(0, int(spec.padding_x)))
        lines.append(glyphs.v + content.ljust(inner_w)[:inner_w] + glyphs.v)
    for _ in range(max(0, int(spec.padding_y))):
        lines.append(glyphs.v + (" " * inner_w) + glyphs.v)

    action_row_index = -1
    if action_row:
        action_row_index = len(lines)
        lines.append(glyphs.v + action_row.center(inner_w)[:inner_w] + glyphs.v)
    lines.append(glyphs.bl + (glyphs.h * inner_w) + glyphs.br)

    box_w = inner_w + 2
    box_h = len(lines)
    x0, y0 = _resolve_ui_box_origin(box_w, box_h, spec, screen_w, screen_h)
    blink_lines: set[int] = set()
    dim_lines: set[int] = set()
    body_start = 1 + max(0, int(spec.padding_y))
    for row in spec.blink_body_rows or []:
        line_idx = body_start + int(row)
        if 0 <= line_idx < box_h:
            blink_lines.add(line_idx)
    for row in spec.dim_body_rows or []:
        line_idx = body_start + int(row)
        if 0 <= line_idx < box_h:
            dim_lines.add(line_idx)
    return UIBoxLayout(
        spec=spec,
        lines=lines,
        x0=x0,
        y0=y0,
        box_w=box_w,
        box_h=box_h,
        title_start=1 + title_left,
        title_end=1 + title_left + len(title_token),
        action_row_index=action_row_index,
        blink_line_indices=blink_lines,
        dim_line_indices=dim_lines,
        screen_w=screen_w,
        screen_h=screen_h,
    )


def _paint(canvas: List[List[str]], x: int, y: int, cell: str) -> None:
    if 0 <= y < len(canvas) and 0 <= x < len(canvas[y]):
        canvas[y][x] = cell


def draw_ui_box(canvas: List[List[str]], spec: UIBoxSpec, blink_on: bool = True) -> None:
    layout = build_ui_box_layout(spec, len(canvas[0]) if canvas else 100, len(canvas))
    _draw_ui_box_layout(canvas, layout, blink_on=blink_on)


def _draw_ui_box_layout(canvas: List[List[str]], layout: UIBoxLayout, blink_on: bool = True) -> None:
    spec = layout.spec
    text_color = "\x1b[38;2;245;245;245m"
    title_color = "\x1b[38;2;255;255;255m"
    key_green = "\x1b[38;2;56;186;72m"
    key_red = "\x1b[38;2;220;70;70m"
    dim_text = "\x1b[38;2;150;150;150m"
    border_flat = "\x1b[38;2;210;210;210m"
    for dy, raw in enumerate(layout.lines):
        y = layout.y0 + dy
        for dx, ch in enumerate(raw):
            x = layout.x0 + dx
            is_border = dy == 0 or dy == layout.box_h - 1 or dx == 0 or dx == layout.box_w - 1
            if is_border and ch != " ":
                border_code = ui_border_gradient_code(dx, dy, layout.box_w, layout.box_h) if spec.border_gradient else border_flat
                if dy == 0 and layout.title_start <= dx < layout.title_end:
                    _paint(canvas, x, y, f"{title_color}{ch}{ANSI_RESET}")
                else:
                    _paint(canvas, x, y, f"{border_code}{ch}{ANSI_RESET}")
            elif ch == " ":
                _paint(canvas, x, y, " ")
            elif dy == layout.action_row_index and ch == "A":
                _paint(canvas, x, y, f"{key_green}A{ANSI_RESET}")
            elif dy == layout.action_row_index and ch == "S":
                _paint(canvas, x, y, f"{key_red}S{ANSI_RESET}")
            else:
                if dy in layout.dim_line_indices:
                    color = dim_text
                elif dy in layout.blink_line_indices and not blink_on:
                    color = dim_text
                else:
                    color = text_color
                _paint(canvas, x, y, f"{color}{ch}{ANSI_RESET}")


def draw_ui_box_animated(canvas: List[List[str]], spec: UIBoxSpec, progress: float, blink_on: bool = True) -> None:
    layout = build_ui_box_layout(spec, len(canvas[0]) if canvas else 100, len(canvas))
    raw_p = max(0.0, min(1.0, float(progress)))
    p = raw_p * raw_p * (3.0 - (2.0 * raw_p))
    h_steps = max(0, layout.box_h - 2)
    w_steps = max(0, layout.box_w - 2)
    h_ticks = max(0, (h_steps + 1) // 2)
    w_ticks = max(0, (w_steps + 1) // 2)
    total_ticks = max(1, h_ticks + w_ticks)
    tick = max(0, min(total_ticks, int(round(total_ticks * p))))
    if tick <= h_ticks:
        vh = 2 + min(h_steps, tick * 2)
        vw = 2
    else:
        vh = layout.box_h
        vw = 2 + min(w_steps, (tick - h_ticks) * 2)

    ax0 = layout.x0 + ((layout.box_w - vw) // 2)
    ay0 = layout.y0 + ((layout.box_h - vh) // 2)
    ax1 = ax0 + vw - 1
    ay1 = ay0 + vh - 1
    glyphs = _ui_border_glyphs(spec.border_style)
    border_flat = "\x1b[38;2;210;210;210m"
    for dy in range(vh):
        y = ay0 + dy
        for dx in range(vw):
            x = ax0 + dx
            border = dy == 0 or dy == vh - 1 or dx == 0 or dx == vw - 1
            if not border:
                _paint(canvas, x, y, " ")
                continue
            if dy == 0 and dx == 0:
                ch = glyphs.tl
            elif dy == 0 and dx == vw - 1:
                ch = glyphs.tr
            elif dy == vh - 1 and dx == 0:
                ch = glyphs.bl
            elif dy == vh - 1 and dx == vw - 1:
                ch = glyphs.br
            elif dy == 0 or dy == vh - 1:
                ch = glyphs.h
            else:
                ch = glyphs.v
            border_code = ui_border_gradient_code(dx, dy, vw, vh) if spec.border_gradient else border_flat
            _paint(canvas, x, y, f"{border_code}{ch}{ANSI_RESET}")

    text_color = "\x1b[38;2;245;245;245m"
    key_green = "\x1b[38;2;56;186;72m"
    key_red = "\x1b[38;2;220;70;70m"
    dim_text = "\x1b[38;2;150;150;150m"
    for dy, raw in enumerate(layout.lines):
        y = layout.y0 + dy
        if y < ay0 or y > ay1:
            continue
        for dx, ch in enumerate(raw):
            x = layout.x0 + dx
            if x < ax0 or x > ax1:
                continue
            on_anim_border = y == ay0 or y == ay1 or x == ax0 or x == ax1
            if on_anim_border or ch == " ":
                continue
            final_border = dy == 0 or dy == layout.box_h - 1 or dx == 0 or dx == layout.box_w - 1
            if final_border:
                continue
            if dy == layout.action_row_index and ch == "A":
                _paint(canvas, x, y, f"{key_green}A{ANSI_RESET}")
            elif dy == layout.action_row_index and ch == "S":
                _paint(canvas, x, y, f"{key_red}S{ANSI_RESET}")
            else:
                if dy in layout.dim_line_indices:
                    color = dim_text
                elif dy in layout.blink_line_indices and not blink_on:
                    color = dim_text
                else:
                    color = text_color
                _paint(canvas, x, y, f"{color}{ch}{ANSI_RESET}")
