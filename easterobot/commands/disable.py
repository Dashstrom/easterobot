from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Hunt
from .base import EasterbotContext, controled_command, egg_command_group


@egg_command_group.command(
    name="disable", description="Désactiver la chasse aux œufs dans le salon"
)
@controled_command(cooldown=True, manage_channels=True)
async def disable_command(ctx: EasterbotContext) -> None:
    await ctx.defer(ephemeral=True)
    with Session(ctx.bot.engine) as session:
        old = session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )
        if old:
            session.execute(
                delete(Hunt).where(Hunt.channel_id == ctx.channel.id)
            )
            session.commit()
    await ctx.followup.send(
        f"Chasse aux œufs{'' if old else ' déjà'} désactivée", ephemeral=True
    )
