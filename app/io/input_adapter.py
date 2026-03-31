import os
import select
import sys
import time
from typing import Optional


class InputAdapter:
    def _read_posix_escape_sequence(self, fd: int, timeout_seconds: float = 0.015) -> Optional[str]:
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        seq = ""
        while len(seq) < 3:
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                break
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                break
            try:
                chunk = os.read(fd, 1).decode("utf-8", errors="ignore")
            except Exception:
                break
            if not chunk:
                break
            seq += chunk
            if chunk.isalpha() or chunk == "~":
                break
        if not seq:
            return None
        tail = seq[-1]
        if tail == "A":
            return "up"
        if tail == "B":
            return "down"
        if tail == "C":
            return "right"
        if tail == "D":
            return "left"
        return None

    def read_key_timeout(self, timeout_seconds: Optional[float]) -> Optional[str]:
        if timeout_seconds is None:
            return self.read_key()
        timeout_seconds = max(0.0, float(timeout_seconds))
        if os.name == "nt":
            import msvcrt

            end = time.monotonic() + timeout_seconds
            while time.monotonic() < end:
                if msvcrt.kbhit():
                    return self.read_key()
                time.sleep(0.01)
            return None

        fd = sys.stdin.fileno()
        ready, _, _ = select.select([fd], [], [], timeout_seconds)
        if ready:
            return self.read_key()
        return None

    def read_key(self) -> str:
        if os.name == "nt":
            import msvcrt

            ch = msvcrt.getch()
            if ch in (b"\x00", b"\xe0"):
                ext = msvcrt.getch()
                if ext == b"H":
                    return "up"
                if ext == b"P":
                    return "down"
                if ext == b"K":
                    return "left"
                if ext == b"M":
                    return "right"
                return "unknown"
            if ch == b"\r":
                return "options"
            if ch == b"\x1b":
                return "back"
            if ch in (b"a", b"A"):
                return "confirm"
            if ch in (b"s", b"S"):
                return "back"
            try:
                return ch.decode("utf-8").lower()
            except UnicodeDecodeError:
                return "unknown"

        fd = sys.stdin.fileno()
        try:
            ch = os.read(fd, 1).decode("utf-8", errors="ignore")
        except Exception:
            return "unknown"
        if not ch:
            return "unknown"
        if ch == "\x1b":
            arrow = self._read_posix_escape_sequence(fd)
            if arrow is not None:
                return arrow
            return "back"
        if ch in ("\r", "\n"):
            return "options"
        if ch in ("a", "A"):
            return "confirm"
        if ch in ("s", "S"):
            return "back"
        return ch.lower()
