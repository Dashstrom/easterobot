"""Module for disable hunt."""

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
    """Disable the hunt."""
    await ctx.response.defer(ephemeral=True)
    async with AsyncSession(ctx.client.engine) as session:
        old = await session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )
        if old:
            await session.execute(
                delete(Hunt).where(Hunt.channel_id == ctx.channel.id)
            )
            await session.commit()
    await ctx.followup.send(
        f"Chasse aux œufs{'' if old else ' déjà'} désactivée", ephemeral=True
    )
