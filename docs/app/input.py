"""Single-key input helpers with optional timeouts."""

import os
import sys
import time
from typing import Optional


_BROWSER_ENABLED = False
_BROWSER_QUEUE: list[str] = []


def enable_browser_input() -> None:
    global _BROWSER_ENABLED
    _BROWSER_ENABLED = True


def enqueue_key(key: str) -> None:
    if key:
        _BROWSER_QUEUE.append(key)


def _read_from_browser(timeout_sec: Optional[float] = None) -> Optional[str]:
    end = None if timeout_sec is None else time.monotonic() + timeout_sec
    while True:
        if _BROWSER_QUEUE:
            return _BROWSER_QUEUE.pop(0)
        if end is not None and time.monotonic() >= end:
            return None
        time.sleep(0.01)


def read_keypress() -> str:
    """
    Read a single keypress without requiring Enter (POSIX terminals).
    Returns a single-character string.
    """
    if _BROWSER_ENABLED:
        return _read_from_browser() or ""
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            key = msvcrt.getch()
            if key == b"K":
                return "LEFT"
            if key == b"M":
                return "RIGHT"
            if key == b"H":
                return "UP"
            if key == b"P":
                return "DOWN"
            return ""
        if ch == b"\r":
            return "ENTER"
        try:
            return ch.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    else:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)  # cbreak: immediate input, but still handles signals
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                if seq == "[D":
                    return "LEFT"
                if seq == "[C":
                    return "RIGHT"
                if seq == "[A":
                    return "UP"
                if seq == "[B":
                    return "DOWN"
                return ""
            if ch in ("\r", "\n"):
                return "ENTER"
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def read_keypress_timeout(timeout_sec: float) -> Optional[str]:
    if _BROWSER_ENABLED:
        return _read_from_browser(timeout_sec)
    if os.name == "nt":
        import msvcrt
        end = time.monotonic() + timeout_sec
        while time.monotonic() < end:
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch in (b"\x00", b"\xe0"):
                    key = msvcrt.getch()
                    if key == b"K":
                        return "LEFT"
                    if key == b"M":
                        return "RIGHT"
                    if key == b"H":
                        return "UP"
                    if key == b"P":
                        return "DOWN"
                    return ""
                if ch == b"\r":
                    return "ENTER"
                try:
                    return ch.decode("utf-8", errors="ignore")
                except Exception:
                    return ""
            time.sleep(0.01)
        return None
    else:
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            ready, _, _ = select.select([sys.stdin], [], [], timeout_sec)
            if ready:
                ch = sys.stdin.read(1)
                if ch == "\x1b":
                    seq = sys.stdin.read(2)
                    if seq == "[D":
                        return "LEFT"
                    if seq == "[C":
                        return "RIGHT"
                    if seq == "[A":
                        return "UP"
                    if seq == "[B":
                        return "DOWN"
                    return ""
                if ch in ("\r", "\n"):
                    return "ENTER"
                return ch
            return None
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
