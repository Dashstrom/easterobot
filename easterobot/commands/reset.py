import asyncio
from typing import cast

import discord
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..bot import embed
from ..models import Cooldown, Egg, Hunt
from .base import EasterbotContext, controled_command, egg_command_group


@egg_command_group.command(
    name="reset", description="Réinitialiser la chasse aux œufs"
)
@controled_command(cooldown=True, administrator=True)
async def reset_command(ctx: EasterbotContext) -> None:
    view = discord.ui.View(timeout=None)
    cancel = discord.ui.Button(  # type: ignore
        label="Annuler", style=discord.ButtonStyle.danger
    )
    view.add_item(cancel)
    confirm = discord.ui.Button(  # type: ignore
        label="Confirmer", style=discord.ButtonStyle.success
    )
    view.add_item(confirm)
    done = False
    cancel_embed = embed(
        title="Réinitialisation annulée",
        description="Vous avez annulé la demande de réinitialisation.",
    )
    confirm_embed = embed(
        title="Réinitialisation",
        description=(
            "L'ensemble des salons, œufs "
            "et temps d'attentes ont été réinitialisatié."
        ),
    )

    async def cancel_callback(
        interaction: discord.Interaction,
    ) -> None:
        nonlocal done
        done = True
        view.disable_all_items()
        view.stop()
        await asyncio.gather(
            message.edit_original_response(view=view),
            interaction.response.send_message(
                embed=cancel_embed,
                ephemeral=True,
            ),
        )

    async def confirm_callback(
        interaction: discord.Interaction,
    ) -> None:
        nonlocal done
        done = True
        view.disable_all_items()
        view.stop()
        await asyncio.gather(
            message.edit_original_response(view=view),
            interaction.response.defer(ephemeral=True),
        )

        with Session(ctx.bot.engine) as session:
            session.execute(delete(Hunt).where(Hunt.guild_id == ctx.guild_id))
            session.execute(delete(Egg).where(Egg.guild_id == ctx.guild_id))
            session.execute(
                delete(Cooldown).where(Cooldown.guild_id == ctx.guild_id)
            )
            session.commit()
        await interaction.followup.send(
            embed=confirm_embed,
            ephemeral=True,
        )

    cancel.callback = cancel_callback  # type: ignore
    confirm.callback = confirm_callback  # type: ignore
    message = cast(
        discord.Interaction,
        await ctx.respond(
            embed=embed(
                title="Demande de réinitialisation",
                description=(
                    "L'ensemble des salons, œufs "
                    "et temps d'attentes vont être réinitialisatiés."
                ),
                footer="Vous avez 30 secondes pour confirmer",
            ),
            ephemeral=True,
            view=view,
        ),
    )
    await asyncio.sleep(30.0)
    if not done:
        view.disable_all_items()
        view.stop()
        await message.edit_original_response(view=view)
        await ctx.followup.send(embed=cancel_embed, ephemeral=True)
