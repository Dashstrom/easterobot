import logging
from typing import Any, cast

import discord
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..bot import embed
from ..config import RAND, agree
from ..models import Egg, Hunt
from .base import EasterbotContext, controled_command, egg_command_group

logger = logging.getLogger("easterobot")


@egg_command_group.command(name="search", description="Rechercher un œuf")
@controled_command(cooldown=True)
async def search_command(ctx: EasterbotContext) -> None:
    with Session(ctx.bot.engine) as session:
        hunt = session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )
        if hunt is None:
            await ctx.respond(
                "La chasse aux œufs n'est pas activée dans ce salon",
                ephemeral=True,
            )
            return

    name = ctx.user.nick or ctx.user.name
    discovered: float = ctx.bot.config.command_attr("search", "discovered")
    spotted: float = ctx.bot.config.command_attr("search", "spotted")
    n1, n2 = RAND.random(), RAND.random()
    if discovered > n1:
        if spotted > n2:

            async def send_method(
                *args: Any, **kwargs: Any
            ) -> discord.Message:
                interaction = cast(
                    discord.Interaction, await ctx.respond(*args, **kwargs)
                )
                return await interaction.original_response()

            await ctx.bot.start_hunt(
                ctx.channel_id,
                ctx.bot.config.spotted(ctx.user),
                member_id=ctx.user.id,
                send_method=send_method,
            )
        else:
            emoji = ctx.bot.config.emoji()
            with Session(ctx.bot.engine) as session:
                session.add(
                    Egg(
                        channel_id=ctx.channel.id,
                        guild_id=ctx.channel.guild.id,
                        user_id=ctx.user.id,
                        emoji_id=emoji.id,
                    )
                )
                egg_count = session.scalar(
                    select(func.count(Egg.user_id).label("count"),).where(
                        and_(
                            Egg.guild_id == ctx.guild.id,
                            Egg.user_id == ctx.user.id,
                        )
                    )
                )
                session.commit()

            logger.info(
                "%s (%s) à obtenu un oeuf pour un total %s in %s",
                ctx.user,
                ctx.user.id,
                agree("{0} egg", "{0} eggs", egg_count),
                ctx.channel.jump_url,
            )
            await ctx.respond(
                embed=embed(
                    title=f"{name} récupère un œuf",
                    description=ctx.bot.config.hidden(ctx.user),
                    thumbnail=emoji.url,
                    egg_count=egg_count,
                )
            )
    else:
        await ctx.respond(
            embed=embed(
                title=f"{name} repart bredouille",
                description=ctx.bot.config.failed(ctx.user),
            )
        )
