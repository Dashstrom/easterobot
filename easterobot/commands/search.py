"""Module for search command."""

import logging
from typing import Any

import discord
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.config import RAND, agree
from easterobot.hunts.hunt import embed
from easterobot.models import Egg, Hunt

from .base import (
    Context,
    InterruptedCommandError,
    controlled_command,
    egg_command_group,
)

logger = logging.getLogger("easterobot")


@egg_command_group.command(
    name="search",
    description="Rechercher un œuf",
)
@controlled_command(cooldown=True, channel_permissions={"send_messages": True})
async def search_command(ctx: Context) -> None:
    """Search command."""
    async with AsyncSession(ctx.client.engine) as session:
        hunt = await session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )
        if hunt is None:
            await ctx.response.send_message(
                "La chasse aux œufs n'est pas activée dans ce salon",
                ephemeral=True,
            )
            raise InterruptedCommandError
    try:
        await ctx.response.defer(ephemeral=False)
    except discord.errors.NotFound as err:
        raise InterruptedCommandError from err
    name = ctx.user.display_name

    async with AsyncSession(ctx.client.engine) as session:
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
            select(func.count().label("count")).where(
                and_(
                    Egg.guild_id == ctx.guild.id,
                    Egg.user_id == ctx.user.id,
                )
            )
        )
        if egg_count is None:
            egg_count = 0
    ratio = egg_count / egg_max if egg_max != 0 else 1.0

    discovered = ctx.client.config.commands.search.discovered
    prob_d = (discovered.max - discovered.min) * (1 - ratio) + discovered.min
    if ctx.client.config.in_sleep_hours():
        prob_d /= ctx.client.config.sleep.divide_discovered

    sample_d = RAND.random()
    if prob_d > sample_d or egg_count < discovered.shield:
        sample_s = RAND.random()
        spotted = ctx.client.config.commands.search.spotted
        prob_s = (spotted.max - spotted.min) * ratio + spotted.min
        if ctx.client.config.in_sleep_hours():
            prob_s /= ctx.client.config.sleep.divide_discovered
        logger.info("discovered: %.2f > %.2f", prob_d, sample_d)
        if prob_s > sample_s and egg_count > spotted.shield:
            logger.info("spotted: %.2f > %.2f", prob_s, sample_s)

            async def send_method(
                *args: Any, **kwargs: Any
            ) -> discord.Message:
                return await ctx.followup.send(*args, **kwargs)  # type: ignore[no-any-return]

            await ctx.client.hunt.start_hunt(
                ctx.channel_id,
                ctx.client.config.spotted(ctx.user),
                member_id=ctx.user.id,
                send_method=send_method,
            )
        else:
            logger.info("found: %.2f > %.2f", prob_s, sample_s)
            emoji = ctx.client.egg_emotes.rand()
            async with AsyncSession(ctx.client.engine) as session:
                session.add(
                    Egg(
                        channel_id=ctx.channel_id,
                        guild_id=ctx.guild_id,
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
                    description=ctx.client.config.hidden(ctx.user),
                    thumbnail=emoji.url,
                    egg_count=egg_count + 1,
                )
            )
    else:
        logger.info("failed: %.2f > %.2f", prob_d, sample_d)
        await ctx.followup.send(
            embed=embed(
                title=f"{name} repart bredouille",
                description=ctx.client.config.failed(ctx.user),
                egg_count=egg_count,
            )
        )
