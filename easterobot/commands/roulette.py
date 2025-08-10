"""Roulette command module for Easter egg hunt bot.

This module implements the roulette command that allows users with manage
channels permission to launch a casino-style roulette game in text channels.
The command validates channel types and initializes the roulette manager
for game execution.
"""

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
    """Launch a casino roulette game in the current channel.

    Starts a roulette game session that users can participate in. The command
    validates that it's being used in a text channel and requires manage
    channels permission. Creates and runs a RouletteManager instance
    for the game.

    Args:
        ctx: Discord interaction context containing channel and client info.

    Returns:
        None. Sends appropriate response messages through Discord interaction.
    """
    # Validate channel type - roulette only works in text channels
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.response.send_message(
            "Salon invalide !",
            ephemeral=True,
        )
        return

    # Send confirmation message that roulette is starting
    await ctx.response.send_message(
        "Lancement de la roulette !",
        ephemeral=True,
    )

    # Initialize and start the roulette game
    roulette_manager = RouletteManager(ctx.client)
    await roulette_manager.run(ctx.channel)
