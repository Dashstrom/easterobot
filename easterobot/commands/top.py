from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..bot import embed
from ..config import agree
from ..models import Egg
from .base import EasterbotContext, controled_command, egg_command_group


@egg_command_group.command(
    name="top", description="Classement des chasseurs d'œufs"
)
@controled_command(cooldown=True)
async def top_command(ctx: EasterbotContext) -> None:
    with Session(ctx.bot.engine) as session:
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
        egg_counts = session.execute(base.limit(3)).all()
        morsels = []
        top_player = False
        rank_medal = {1: "🥇", 2: "🥈", 3: "🥉"}
        for user_id, rank, count in egg_counts:
            if user_id == ctx.user.id:
                top_player = True
            morsels.append(
                f"{rank_medal.get(rank, rank)} <@{user_id}>\n"
                f"\u2004\u2004\u2004\u2004\u2004"
                f"➥ {agree('{0} œuf', '{0} œufs', count)}"
            )
        if not top_player:
            subq = base.subquery()
            user_egg_count = session.execute(
                select(subq).where(subq.c.user_id == ctx.user.id)
            ).first()
            if user_egg_count:
                user_id, rank, egg_count = user_egg_count
                morsels.append(
                    f"\n{rank_medal.get(rank, f'`#{rank}`')} "
                    f"<@{user_id}>\n"
                    f"\u2004\u2004\u2004\u2004\u2004"
                    f"➥ {agree('{0} œuf', '{0} œufs', egg_count)}"
                )
            else:
                morsels.append("\n:spider_web: Vous n'avez aucun œuf")
    text = "\n".join(morsels)
    await ctx.respond(
        embed=embed(
            title=f"Chasse aux œufs : {ctx.guild.name}",
            description=text,
            thumbnail=ctx.guild.icon.url,
        ),
        ephemeral=True,
    )
