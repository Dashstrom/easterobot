"""Command basket."""

import discord

from easterobot.casino.roulette import RouletteManager
from easterobot.commands.base import (
    Context,
    controlled_command,
    egg_command_group,
)


@egg_command_group.command(
    name="roulette",
    description="Lancer la roulette",
)
@controlled_command(cooldown=True, manage_channels=True)
async def roulette_command(
    ctx: Context,
) -> None:
    """Show current user basket."""
    # Delay the response
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.response.send_message(
            "Salon invalide !",
            ephemeral=True,
        )
        return
    await ctx.response.send_message(
        "Lancement de la roulette !",
        ephemeral=True,
    )
    roulette = RouletteManager(ctx.client)
    await roulette.run(ctx.channel)
