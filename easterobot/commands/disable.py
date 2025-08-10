"""Easter hunt disable command.

This module provides the command to disable easter egg hunts in channels.
It handles removing hunt sessions from the database and provides user feedback.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.models import Hunt

from .base import Context, controlled_command, egg_command_group


@egg_command_group.command(
    name="disable",
    description="Désactiver la chasse aux œufs dans le salon",
)
@controlled_command(cooldown=True, manage_channels=True)
async def disable_command(ctx: Context) -> None:
    """Disable easter egg hunt in the current Discord channel.

    Removes the hunt session from the database if one exists for the channel.
    Sends confirmation message to the user indicating whether the hunt was
    disabled or was already inactive.

    Args:
        ctx: Discord command context containing channel information.
    """
    # Defer response to allow time for database operations
    await ctx.response.defer(ephemeral=True)

    async with AsyncSession(ctx.client.engine) as database_session:
        # Check if hunt exists for this channel
        existing_hunt = await database_session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )

        if existing_hunt:
            # Remove hunt session from database
            await database_session.execute(
                delete(Hunt).where(Hunt.channel_id == ctx.channel.id)
            )
            await database_session.commit()

    # Send confirmation message (visible only to command user)
    status_message = (
        f"Chasse aux œufs{'' if existing_hunt else ' déjà'} désactivée"
    )
    await ctx.followup.send(status_message, ephemeral=True)
