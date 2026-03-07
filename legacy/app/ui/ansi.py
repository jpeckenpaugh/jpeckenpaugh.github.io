"""ANSI color helpers for the terminal UI."""


class ANSI:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    FG_WHITE = "\033[37m"
    FG_CYAN = "\033[36m"
    FG_GREEN = "\033[32m"
    FG_YELLOW = "\033[33m"
    FG_RED = "\033[31m"
    FG_BLUE = "\033[34m"
    FG_MAGENTA = "\033[35m"

    CURSOR_HIDE = "\033[?25l"
    CURSOR_SHOW = "\033[?25h"
    BG_LIGHT_GRAY = "\033[48;2;220;220;220m"


def color(text: str, *codes: str) -> str:
    styled = "".join(codes) + text + ANSI.RESET
    return styled
