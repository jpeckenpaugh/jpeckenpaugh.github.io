from __future__ import annotations

import os
import select
import sys
import termios
import tty
from contextlib import contextmanager
from typing import Iterator


class KeyReader:
    def _read_escape(self, fd: int) -> str | None:
        seq = ""
        while len(seq) < 8:
            ready, _, _ = select.select([fd], [], [], 0.02)
            if not ready:
                break
            chunk = os.read(fd, 1).decode("utf-8", errors="ignore")
            if not chunk:
                break
            seq += chunk
            if chunk.isalpha() or chunk == "~":
                break
        if not seq:
            return None
        return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(seq[-1])

    def read(self, timeout: float = 0.0) -> str | None:
        if os.name == "nt":
            import msvcrt

            if not msvcrt.kbhit():
                return None
            ch = msvcrt.getch()
            if ch in (b"\x00", b"\xe0"):
                ext = msvcrt.getch()
                return {b"H": "up", b"P": "down", b"K": "left", b"M": "right"}.get(ext)
            if ch in (b"a", b"A", b"\r"):
                return "confirm"
            if ch in (b"s", b"S", b"\x1b"):
                return "back"
            if ch in (b"q", b"Q"):
                return "quit"
            return ch.decode("utf-8", errors="ignore").lower()[:1] or None

        fd = sys.stdin.fileno()
        ready, _, _ = select.select([fd], [], [], max(0.0, timeout))
        if not ready:
            return None
        ch = os.read(fd, 1).decode("utf-8", errors="ignore")
        if ch == "\x1b":
            return self._read_escape(fd) or "back"
        if ch in ("\r", "\n", "a", "A"):
            return "confirm"
        if ch in ("s", "S"):
            return "back"
        if ch in ("q", "Q"):
            return "quit"
        return ch.lower()[:1] if ch else None


@contextmanager
def terminal_mode() -> Iterator[None]:
    if os.name == "nt" or not sys.stdin.isatty():
        yield
        return
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        raw = termios.tcgetattr(fd)
        raw[3] &= ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSADRAIN, raw)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
