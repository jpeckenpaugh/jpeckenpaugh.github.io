import os
import select
import sys
import time
from typing import Optional


class InputAdapter:
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

        import select

        ready, _, _ = select.select([sys.stdin], [], [], timeout_seconds)
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

        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ready, _, _ = select.select([sys.stdin], [], [], 0.01)
                if not ready:
                    return "back"
                n1 = sys.stdin.read(1)
                if n1 == "[":
                    ready, _, _ = select.select([sys.stdin], [], [], 0.01)
                    if not ready:
                        return "back"
                    n2 = sys.stdin.read(1)
                    if n2 == "A":
                        return "up"
                    if n2 == "B":
                        return "down"
                    if n2 == "D":
                        return "left"
                    if n2 == "C":
                        return "right"
                return "back"
            if ch in ("\r", "\n"):
                return "options"
            if ch in ("a", "A"):
                return "confirm"
            if ch in ("s", "S"):
                return "back"
            return ch.lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
