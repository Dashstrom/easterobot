from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..bot import embed
from ..config import agree
from ..models import Egg
from .base import EasterbotContext, controled_command, egg_command_group

RANK_MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}


def record_top(rank: int, user_id: int, count: int) -> str:
    return (
        f"{RANK_MEDAL.get(rank, f'`#{rank}`')} <@{user_id}>\n"
        f"\u2004\u2004\u2004\u2004\u2004"
        f"➥ {agree('{0} œuf', '{0} œufs', count)}"
    )


@egg_command_group.command(
    name="top", description="Classement des chasseurs d'œufs"
)
@controled_command(cooldown=True)
async def top_command(ctx: EasterbotContext) -> None:
    await ctx.defer(ephemeral=True)
    async with AsyncSession(ctx.bot.engine) as session:
        base = (
            select(
                Egg.user_id,
                func.rank().over(order_by=func.count().desc()).label("row"),
                func.count().label("count"),
            )
            .where(Egg.guild_id == ctx.guild_id)
            .group_by(Egg.user_id)
            .order_by(func.count().desc())
        )
        egg_counts = (await session.execute(base.limit(5))).all()
        morsels = []
        top_player = False

        for user_id, rank, egg_count in egg_counts:
            if user_id == ctx.user.id:
                top_player = True
            morsels.append(record_top(rank, user_id, egg_count))
        if not top_player:
            morsels.append("")
            subq = base.subquery()
            user_egg_count = (
                await session.execute(
                    select(subq).where(subq.c.user_id == ctx.user.id)
                )
            ).first()
            if user_egg_count:
                user_id, rank, egg_count = user_egg_count
                morsels.append(record_top(rank, user_id, egg_count))
            else:
                morsels.append("\n:spider_web: Vous n'avez aucun œuf")
    text = "\n".join(morsels)
    await ctx.followup.send(
        embed=embed(
            title=f"Chasse aux œufs : {ctx.guild.name}",
            description=text,
            thumbnail=ctx.guild.icon.url,
        ),
        ephemeral=True,
    )
