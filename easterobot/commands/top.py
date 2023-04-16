from sqlalchemy.ext.asyncio import AsyncSession

from ..bot import embed
from ..config import agree
from .base import EasterbotContext, controled_command, egg_command_group


def record_top(rank: str, user_id: int, count: int) -> str:
    return (
        f"{rank} <@{user_id}>\n"
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
        egg_counts = await ctx.bot.get_rank(session, ctx.guild_id)
        morsels = []
        top_player = False
        if egg_counts:
            for user_id, rank, egg_count in egg_counts:
                if user_id == ctx.user.id:
                    top_player = True
                morsels.append(record_top(rank, user_id, egg_count))
            if not top_player:
                morsels.append("")
                user_egg_count = await ctx.bot.get_rank(
                    session, ctx.guild_id, ctx.user.id
                )
                if user_egg_count:
                    user_id, rank, egg_count = user_egg_count[0]
                    morsels.append(record_top(rank, user_id, egg_count))
                else:
                    morsels.append("\n:spider_web: Vous n'avez aucun œuf")
        else:
            morsels.append("\n:spider_web: Personne n'a d'œuf")
    text = "\n".join(morsels)
    await ctx.followup.send(
        embed=embed(
            title=f"Chasse aux œufs : {ctx.guild.name}",
            description=text,
            thumbnail=ctx.guild.icon.url,
        ),
        ephemeral=True,
    )
