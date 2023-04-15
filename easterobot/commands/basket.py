import discord
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..bot import embed
from ..models import Egg
from .base import EasterbotContext, controled_command, egg_command_group


@egg_command_group.command(
    name="basket", description="Regarder le contenu d'un panier"
)
@discord.option(  # type: ignore
    "user",
    input_type=discord.Member,
    required=False,
    default=None,
    description="Membre possèdant le panier à inspecter",
)
@controled_command(cooldown=True)
async def basket_command(ctx: EasterbotContext, user: discord.Member) -> None:
    await ctx.defer(ephemeral=True)
    hunter = user or ctx.user
    async with AsyncSession(ctx.bot.engine) as session:
        egg_counts = (
            await session.execute(
                select(
                    Egg.emoji_id,
                    func.count().label("count"),
                )
                .where(
                    and_(
                        Egg.guild_id == ctx.guild.id,
                        Egg.user_id == hunter.id,
                    )
                )
                .group_by(Egg.emoji_id)
            )
        ).all()
        none_emoji = 0
        morsels = []
        for egg in egg_counts:
            emoji = ctx.bot.get_emoji(egg[0])
            if emoji is None:
                none_emoji += egg[1]
            else:
                morsels.append(f"{emoji} \xd7 {egg[1]}")
        if none_emoji:
            morsels.append(f"🥚 \xd7 {none_emoji}")
        if morsels:
            text = "\n".join(morsels)
        else:
            if hunter == ctx.user:
                text = ":spider_web: Vous n'avez aucun œuf"
            else:
                text = ctx.bot.config.conjugate(
                    ":spider_web: {Iel} n'a aucun œuf", hunter
                )
        await ctx.followup.send(
            embed=embed(
                title=f"Contenu du panier de {hunter.nick or hunter.name}",
                description=text,
                egg_count=sum(egg[1] for egg in egg_counts),
            ),
            ephemeral=True,
        )
