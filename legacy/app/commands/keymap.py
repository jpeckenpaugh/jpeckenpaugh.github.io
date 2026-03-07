"""Key-to-command mapping, with optional data-driven overrides."""

from typing import Optional, Sequence


def map_key_to_command(ch: str, commands: Optional[Sequence[dict]] = None) -> Optional[str]:
    c = ch.lower()
    if c == "1":
        return "NUM1"
    if c == "2":
        return "NUM2"
    if c == "3":
        return "NUM3"
    if c == "4":
        return "NUM4"
    if c == "5":
        return "NUM5"
    if c == "6":
        return "NUM6"
    if c == "7":
        return "NUM7"
    if c == "8":
        return "NUM8"
    if c == "9":
        return "NUM9"
    if commands is not None:
        for command in commands:
            key = str(command.get("key", "")).lower()
            if key == c:
                return command.get("command")
        return None
    if c == "a":
        return "ATTACK"
    if c == "b":
        return "B_KEY"
    if c == "i":
        return "REST"
    if c == "o":
        return "INVENTORY"
    if c == "s":
        return "S_KEY"
    if c == "t":
        return "TOWN"
    if c == "f":
        return "F_KEY"
    if c == "h":
        return "HALL"
    if c == "m":
        return "SPELLBOOK"
    if c == "p":
        return "SPELLBOOK"
    if c == "x":
        return "X_KEY"
    if c == "q":
        return "QUIT"
    return None
