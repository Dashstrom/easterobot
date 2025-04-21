"""Module for search command."""

import logging
from typing import Any

import discord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.config import agree
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
        luck = await ctx.client.hunt.get_luck(
            guild_id=ctx.guild_id,
            user_id=ctx.user.id,
            session=session,
            sleep_hours=ctx.client.config.in_sleep_hours(),
        )

    if luck.sample_discovered():
        if luck.sample_spotted():

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
                agree("{0} egg", "{0} eggs", luck.egg_count),
                ctx.channel.jump_url,
            )
            await ctx.followup.send(
                embed=embed(
                    title=f"{name} récupère un œuf",
                    description=ctx.client.config.hidden(ctx.user),
                    thumbnail=emoji.url,
                    egg_count=luck.egg_count + 1,
                )
            )
    else:
        await ctx.followup.send(
            embed=embed(
                title=f"{name} repart bredouille",
                description=ctx.client.config.failed(ctx.user),
                egg_count=luck.egg_count,
            )
        )
