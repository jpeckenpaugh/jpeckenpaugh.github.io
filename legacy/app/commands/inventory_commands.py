from app.commands.registry import CommandRegistry, CommandContext


def register(registry: CommandRegistry):
    registry.register("INVENTORY", _handle_inventory)


def _handle_inventory(ctx: CommandContext) -> str:
    return ctx.player.format_inventory(ctx.items_data)
