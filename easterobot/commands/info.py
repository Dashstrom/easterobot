"""Command basket."""

import asyncio
from typing import Optional

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
    ctx: Context, user: Optional[discord.Member] = None
) -> None:
    """Show current user basket."""
    # Delay the response
    await ctx.response.defer(ephemeral=True)

    # Set the user of the basket
    hunter = user or ctx.user

    async with AsyncSession(ctx.client.engine) as session:
        ranking, member_luck = await asyncio.gather(
            Ranking.from_guild(session, ctx.guild_id),
            ctx.client.hunt.get_luck(
                session=session,
                guild_id=hunter.guild.id,
                user_id=hunter.id,
                sleep_hours=False,
            ),
        )
        hunter_rank = ranking.get(hunter.id)

        await ctx.followup.send(
            embed=embed(
                title=f"Informations sur {hunter.display_name}",
                description=(
                    f"Classement : {hunter_rank.badge}\n"
                    f"Nombre d'oeufs : `{hunter_rank.eggs}`\n"
                    f"Chance brute : `{member_luck.luck:.0%}`\n"
                    f"Chance de trouver un oeuf : `{member_luck.discovered:.0%}`\n"
                    f"Chance de se faire voler : `{member_luck.spotted:.0%}`"
                ),
            ),
            ephemeral=True,
        )
