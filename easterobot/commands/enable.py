from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Hunt
from .base import EasterbotContext, controled_command, egg_command_group


@egg_command_group.command(
    name="enable", description="Activer la chasse aux œufs dans le salon"
)
@controled_command(cooldown=True, manage_channels=True)
async def enable_command(ctx: EasterbotContext) -> None:
    await ctx.defer(ephemeral=True)
    with Session(ctx.bot.engine) as session:
        old = session.scalar(
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
            session.commit()
    await ctx.followup.send(
        f"Chasse aux œufs{' déjà' if old else ''} activée", ephemeral=True
    )
