"""Module for edit command."""

import discord
from discord import app_commands
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.config import RAND, agree
from easterobot.hunts.hunt import embed
from easterobot.models import Egg

from .base import Context, controlled_command, egg_command_group


@egg_command_group.command(
    name="edit", description="Editer le nombre d'œufs d'un membre"
)
@controlled_command(cooldown=True, administrator=True)
async def edit_command(
    ctx: Context,
    user: discord.Member,
    oeufs: app_commands.Range[int, 0, 10_000],
) -> None:
    """Edit command."""
    await ctx.response.defer(ephemeral=True)
    async with AsyncSession(ctx.client.engine) as session:
        eggs: list[Egg] = list(
            (
                await session.scalars(
                    select(Egg).where(
                        and_(
                            Egg.guild_id == ctx.guild_id,
                            Egg.user_id == user.id,
                        )
                    )
                )
            ).all()
        )
        diff = len(eggs) - oeufs
        if diff > 0:
            to_delete = []
            for _ in range(diff):
                egg = RAND.choice(eggs)
                eggs.remove(egg)
                to_delete.append(egg.id)
            await session.execute(delete(Egg).where(Egg.id.in_(to_delete)))
            await session.commit()
        elif diff < 0:
            for _ in range(-diff):
                session.add(
                    Egg(
                        guild_id=ctx.guild_id,
                        channel_id=ctx.channel_id,
                        user_id=user.id,
                        emoji_id=ctx.client.egg_emotes.rand().id,
                    )
                )
            await session.commit()
    await ctx.followup.send(
        embed=embed(
            title="Edition terminée",
            description=(
                f"{user.mention} a maintenant "
                f"{agree('{0} œuf', '{0} œufs', oeufs)}"
            ),
        ),
        ephemeral=True,
    )
