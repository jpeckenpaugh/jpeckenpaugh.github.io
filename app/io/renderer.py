import os
import sys


class Renderer:
    def __init__(self) -> None:
        self._initialized = False
        self._last_line_count = 0

    def clear(self) -> None:
        self._initialized = False
        self._last_line_count = 0
        os.system("cls" if os.name == "nt" else "clear")
        sys.stdout.write("\x1b[?25h")
        sys.stdout.flush()

    def render_text(self, frame: str) -> None:
        lines = frame.splitlines()
        if not self._initialized:
            self.clear()
            sys.stdout.write("\x1b[?25l")
            self._initialized = True
        sys.stdout.write("\x1b[H")
        for line in lines:
            sys.stdout.write(line + "\n")
        if self._last_line_count > len(lines):
            for _ in range(self._last_line_count - len(lines)):
                sys.stdout.write("\n")
        self._last_line_count = len(lines)
        sys.stdout.flush()
