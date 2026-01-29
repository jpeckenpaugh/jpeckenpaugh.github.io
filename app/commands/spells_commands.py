from app.combat import cast_spell
from app.commands.registry import CommandRegistry, CommandContext


def register(registry: CommandRegistry):
    registry.register("HEAL", _handle_heal)
    registry.register("SPARK", _handle_spark)


def _handle_heal(ctx: CommandContext) -> str:
    return cast_spell(
        ctx.player,
        ctx.opponents,
        "healing",
        boosted=False,
        loot=ctx.loot,
        spells_data=ctx.spells_data,
        target_index=ctx.target_index,
    )


def _handle_spark(ctx: CommandContext) -> str:
    return cast_spell(
        ctx.player,
        ctx.opponents,
        "spark",
        boosted=False,
        loot=ctx.loot,
        spells_data=ctx.spells_data,
        target_index=ctx.target_index,
    )
