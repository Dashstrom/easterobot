import logging
from typing import Any, Dict

import discord
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..bot import embed
from ..config import RAND, agree
from ..models import Egg, Hunt
from .base import (
    EasterbotContext,
    InteruptedCommandError,
    controled_command,
    egg_command_group,
)

logger = logging.getLogger("easterobot")


@egg_command_group.command(name="search", description="Rechercher un œuf")
@controled_command(cooldown=True)
async def search_command(ctx: EasterbotContext) -> None:
    config = ctx.bot.config
    async with AsyncSession(ctx.bot.engine) as session:
        hunt = await session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )
        if hunt is None:
            await ctx.respond(
                "La chasse aux œufs n'est pas activée dans ce salon",
                ephemeral=True,
            )
            return
    try:
        await ctx.defer(ephemeral=False)
    except discord.errors.NotFound as err:
        raise InteruptedCommandError() from err
    name = ctx.user.nick or ctx.user.name

    async with AsyncSession(ctx.bot.engine) as session:
        egg_max = await session.scalar(
            select(
                func.count().label("max"),
            )
            .where(Egg.guild_id == ctx.guild_id)
            .group_by(Egg.user_id)
            .order_by(func.count().label("max").desc())
            .limit(1)
        )
        egg_max = egg_max or 0
        egg_count = await session.scalar(
            select(func.count().label("count"),).where(
                and_(
                    Egg.guild_id == ctx.guild.id,
                    Egg.user_id == ctx.user.id,
                )
            )
        )
    ratio = egg_count / egg_max if egg_max != 0 else 1.0

    conf_d: Dict[str, float] = config.command_attr("search", "discovered")
    prob_d = (conf_d["max"] - conf_d["min"]) * (1 - ratio) + conf_d["min"]

    sample_d = RAND.random()
    if prob_d > sample_d or egg_count < conf_d["shield"]:
        sample_s = RAND.random()
        conf_s: Dict[str, float] = config.command_attr("search", "spotted")
        prob_s = (conf_s["max"] - conf_s["min"]) * ratio + conf_s["min"]
        logger.info("discovered: %.2f > %.2f", prob_d, sample_d)
        if prob_s > sample_s and egg_count > conf_s["shield"]:
            logger.info("spotted: %.2f > %.2f", prob_s, sample_s)

            async def send_method(
                *args: Any, **kwargs: Any
            ) -> discord.Message:
                return await ctx.followup.send(*args, **kwargs)

            await ctx.bot.start_hunt(
                ctx.channel_id,
                config.spotted(ctx.user),
                member_id=ctx.user.id,
                send_method=send_method,
            )
        else:
            logger.info("found: %.2f > %.2f", prob_s, sample_s)
            emoji = config.emoji()
            async with AsyncSession(ctx.bot.engine) as session:
                session.add(
                    Egg(
                        channel_id=ctx.channel.id,
                        guild_id=ctx.channel.guild.id,
                        user_id=ctx.user.id,
                        emoji_id=emoji.id,
                    )
                )
                await session.commit()

            logger.info(
                "%s (%s) got an egg for a total %s in %s",
                ctx.user,
                ctx.user.id,
                agree("{0} egg", "{0} eggs", egg_count),
                ctx.channel.jump_url,
            )
            await ctx.followup.send(
                embed=embed(
                    title=f"{name} récupère un œuf",
                    description=config.hidden(ctx.user),
                    thumbnail=emoji.url,
                    egg_count=egg_count + 1,
                )
            )
    else:
        logger.info("failed: %.2f > %.2f", prob_d, sample_d)
        await ctx.followup.send(
            embed=embed(
                title=f"{name} repart bredouille",
                description=config.failed(ctx.user),
                egg_count=egg_count,
            )
        )
