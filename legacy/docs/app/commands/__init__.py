from app.commands.registry import CommandRegistry
from app.commands import combat_commands, inventory_commands, spells_commands


def build_registry() -> CommandRegistry:
    registry = CommandRegistry()
    combat_commands.register(registry)
    inventory_commands.register(registry)
    spells_commands.register(registry)
    return registry
