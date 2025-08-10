"""Player information command module for Easter egg hunt bot.

This module implements the info command that displays detailed statistics about
a player's Easter egg hunting performance, including their ranking, egg count,
and various luck probabilities within the current guild.
"""

import asyncio

import discord
from discord import app_commands
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.commands.base import (
    Context,
    controlled_command,
    egg_command_group,
)
from easterobot.hunts.hunt import embed
from easterobot.hunts.rank import Ranking


@egg_command_group.command(
    name="info",
    description="Avoir des informations sur la chance d'un joueur",
)
@app_commands.describe(
    user="Joueur a inspecter",
)
@controlled_command(cooldown=True)
async def info_command(
    ctx: Context, user: discord.Member | None = None
) -> None:
    """Display detailed Easter egg hunting statistics for a player.

    Shows comprehensive information about a player's hunt performance including
    their guild ranking, total egg count, base luck percentage, discovery chance,
    and theft probability. If no user is specified, shows info for the command user.

    Args:
        ctx: Discord interaction context containing guild and user info.
        user: Optional Discord member to inspect. Defaults to command invoker.

    Returns:
        None. Sends player statistics embed through Discord interaction.
    """
    # Defer response to allow time for database queries
    await ctx.response.defer(ephemeral=True)

    # Use specified user or default to command invoker
    target_hunter = user or ctx.user

    # Fetch ranking data and luck statistics concurrently
    async with AsyncSession(ctx.client.engine) as database_session:
        guild_ranking, hunter_luck_stats = await asyncio.gather(
            Ranking.from_guild(database_session, ctx.guild_id),
            ctx.client.hunt.get_luck(
                session=database_session,
                guild_id=target_hunter.guild.id,
                user_id=target_hunter.id,
                sleep_hours=False,
            ),
        )

        # Get the hunter's position and stats from guild ranking
        hunter_ranking_info = guild_ranking.get(target_hunter.id)

        # Send comprehensive player information embed
        await ctx.followup.send(
            embed=embed(
                title=f"Informations sur {target_hunter.display_name}",
                description=(
                    f"Classement : {hunter_ranking_info.badge}\n"
                    f"Nombre d'œufs : `{hunter_ranking_info.eggs}`\n"
                    f"Chance brute : `{hunter_luck_stats.luck:.0%}`\n"
                    f"Chance de trouver un œuf : `{hunter_luck_stats.discovered:.0%}`\n"
                    f"Chance de se faire voler : `{hunter_luck_stats.spotted:.0%}`"
                ),
            ),
            ephemeral=True,
        )
