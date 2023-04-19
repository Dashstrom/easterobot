from typing import Dict

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
    you = ctx.user == hunter
    async with AsyncSession(ctx.bot.engine) as session:
        morsels = []
        missings = []
        user_egg_count = await ctx.bot.get_rank(
            session, ctx.guild_id, hunter.id
        )
        if user_egg_count:
            rank = user_egg_count[1]
        else:
            rank = None
        res = await session.execute(
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
        egg_counts: Dict[int, int] = dict(res.all())  # type: ignore
        egg_count = 0
        for emoji in ctx.bot.config.emojis():
            try:
                type_count = egg_counts.pop(emoji.id)  # type: ignore
                egg_count += type_count
                morsels.append(f"{emoji} \xd7 {type_count}")
            except KeyError:
                missings.append(emoji)

        absent_count = sum(egg_counts.values())
        if absent_count:
            egg_count += absent_count
            morsels.insert(0, f"🥚 \xd7 {absent_count}")

        if rank is not None:
            il = ctx.bot.config.conjugate("{Iel} est", hunter)
            morsels.insert(
                0,
                f"**{'Tu es' if you else il} au rang** {rank}\n",
            )

        if missings:
            morsels.append(
                f"\nIl {'te' if you else 'lui'} "
                f"manque : {''.join(map(str, missings))}"
            )

        text = "\n".join(morsels).strip()
        await ctx.followup.send(
            embed=embed(
                title=f"Contenu du panier de {hunter.nick or hunter.name}",
                description=text,
                egg_count=egg_count,
            ),
            ephemeral=True,
        )
