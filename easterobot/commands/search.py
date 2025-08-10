"""Search command module for Easter egg hunt bot.

This module implements the search command that allows users to search
for Easter eggs in channels where egg hunts are active. The command handles
luck calculation, egg discovery, and hunt mechanics including cooldowns
and permissions.
"""

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
    """Execute the Easter egg search command.

    Allows users to search for Easter eggs in the current channel. The command
    checks if a hunt is active, calculates user's luck based on various
    factors, and either rewards an egg, starts a hunt sequence,
    or returns empty-handed.

    Args:
        ctx: Interaction context containing user, channel, and guild info.

    Raises:
        InterruptedCommandError: If no hunt is active in the channel or if the
            Discord response fails.
    """
    # Check if hunt is active in the current channel
    async with AsyncSession(ctx.client.engine) as database_session:
        active_hunt = await database_session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )
        if active_hunt is None:
            await ctx.response.send_message(
                "La chasse aux œufs n'est pas activée dans ce salon",
                ephemeral=True,
            )
            raise InterruptedCommandError

    # Defer response to allow for longer processing time
    try:
        await ctx.response.defer(ephemeral=False)
    except discord.errors.NotFound as error:
        raise InterruptedCommandError from error

    user_display_name = ctx.user.display_name

    # Calculate user's luck for finding eggs
    async with AsyncSession(ctx.client.engine) as database_session:
        user_luck = await ctx.client.hunt.get_luck(
            guild_id=ctx.guild_id,
            user_id=ctx.user.id,
            session=database_session,
            sleep_hours=ctx.client.config.in_sleep_hours(),
        )

    # Process luck results and determine outcome
    if user_luck.sample_discovered():
        if user_luck.sample_spotted():
            # User spotted something - start interactive hunt sequence

            async def followup_send_method(
                *args: Any, **kwargs: Any
            ) -> discord.Message:
                """Send follow-up message through Discord interaction.

                Args:
                    *args: Positional arguments for followup.send.
                    **kwargs: Keyword arguments for followup.send.

                Returns:
                    The sent Discord message.
                """
                return await ctx.followup.send(*args, **kwargs)  # type: ignore[no-any-return]

            await ctx.client.hunt.start_hunt(
                ctx.channel_id,
                ctx.client.config.spotted(ctx.user),
                member_id=ctx.user.id,
                send_method=followup_send_method,
            )
        else:
            # User found a hidden egg - add it to database
            random_egg_emoji = ctx.client.egg_emotes.rand()
            async with AsyncSession(ctx.client.engine) as database_session:
                database_session.add(
                    Egg(
                        channel_id=ctx.channel_id,
                        guild_id=ctx.guild_id,
                        user_id=ctx.user.id,
                        emoji_id=random_egg_emoji.id,
                    )
                )
                await database_session.commit()

            # Log successful egg discovery
            logger.info(
                "%s (%s) got an egg for a total %s in %s",
                ctx.user,
                ctx.user.id,
                agree("{0} egg", "{0} eggs", user_luck.egg_count),
                ctx.channel.jump_url,
            )

            # Send success message with egg embed
            await ctx.followup.send(
                embed=embed(
                    title=f"{user_display_name} récupère un œuf",
                    description=ctx.client.config.hidden(ctx.user),
                    thumbnail=random_egg_emoji.url,
                    egg_count=user_luck.egg_count + 1,
                )
            )
    else:
        # User found nothing - send failure message
        await ctx.followup.send(
            embed=embed(
                title=f"{user_display_name} repart bredouille",
                description=ctx.client.config.failed(ctx.user),
                egg_count=user_luck.egg_count,
            )
        )
