"""Command enable."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.models import Hunt

from .base import Context, controlled_command, egg_command_group


@egg_command_group.command(
    name="enable", description="Activer la chasse dans le salon"
)
@controlled_command(
    cooldown=True,
    channel_permissions={"send_messages": True},
    manage_channels=True,
)
async def enable_command(
    ctx: Context,
) -> None:
    """Enable hunt in a channel."""
    await ctx.response.defer(ephemeral=True)
    async with AsyncSession(ctx.client.engine) as session:
        old = await session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )
        if not old:
            session.add(
                Hunt(
                    channel_id=ctx.channel.id,
                    guild_id=ctx.guild_id,
                    next_egg=0,
                )
            )
            await session.commit()
    await ctx.followup.send(
        f"Chasse aux œufs{' déjà' if old else ''} activée", ephemeral=True
    )
