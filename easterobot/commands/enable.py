"""Easter hunt enable command.

This module provides the command to enable easter egg hunts in channels.
It handles database operations to track hunt sessions.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.models import Hunt

from .base import Context, controlled_command, egg_command_group


@egg_command_group.command(
    name="enable",
    description="Activer la chasse dans le salon",
)
@controlled_command(
    cooldown=True,
    channel_permissions={"send_messages": True},
    manage_channels=True,
)
async def enable_command(
    ctx: Context,
) -> None:
    """Enable easter egg hunt in the current Discord channel.

    Creates a new hunt session in the database if one doesn't already exist
    for the channel. Sends confirmation message to the user indicating whether
    the hunt was newly enabled or was already active.

    Args:
        ctx: Discord command context containing channel and guild information.
    """
    # Defer response to allow time for database operations
    await ctx.response.defer(ephemeral=True)

    async with AsyncSession(ctx.client.engine) as database_session:
        # Check if hunt is already enabled for this channel
        existing_hunt = await database_session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )

        if not existing_hunt:
            # Create new hunt session for the channel
            database_session.add(
                Hunt(
                    channel_id=ctx.channel.id,
                    guild_id=ctx.guild_id,
                    next_egg=0,  # Initialize with no pending eggs
                )
            )
            await database_session.commit()

    # Send confirmation message (visible only to command user)
    status_message = (
        f"Chasse aux œufs{' déjà' if existing_hunt else ''} activée"
    )
    await ctx.followup.send(status_message, ephemeral=True)
