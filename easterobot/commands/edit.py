from typing import List

import discord
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..bot import embed
from ..config import RAND, agree
from ..models import Egg
from .base import EasterbotContext, controled_command, egg_command_group


@egg_command_group.command(
    name="edit", description="Editer le nombre d'œufs d'un membre"
)
@discord.option(  # type: ignore
    "user",
    input_type=discord.Member,
    required=True,
    description="Membre voulant editer",
)
@discord.option(  # type: ignore
    "oeufs",
    input_type=int,
    required=True,
    description="Nouveau nombre d'œufs",
)
@controled_command(cooldown=True, administrator=True)
async def edit_command(
    ctx: EasterbotContext,
    user: discord.Member,
    oeufs: int,
) -> None:
    oeufs = min(max(oeufs, 0), 100_000)
    await ctx.defer(ephemeral=True)
    async with AsyncSession(ctx.bot.engine) as session:
        eggs: List[Egg] = (
            await session.scalars(
                select(Egg).where(
                    and_(
                        Egg.guild_id == ctx.guild.id,
                        Egg.user_id == user.id,
                    )
                )
            )
        ).all()
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
                        emoji_id=ctx.bot.config.emoji().id,
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
