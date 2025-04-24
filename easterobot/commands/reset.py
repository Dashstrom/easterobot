"""Module for reset command."""

import asyncio

import discord
from sqlalchemy import and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.hunts.hunt import embed
from easterobot.models import Cooldown, Egg, Hunt
from easterobot.utils import in_seconds

from .base import Context, Interaction, controlled_command, egg_command_group


@egg_command_group.command(
    name="reset",
    description="Réinitialiser la chasse aux œufs",
)
@controlled_command(cooldown=True, administrator=True)
async def reset_command(ctx: Context) -> None:
    """Reset command."""
    await ctx.response.defer(ephemeral=True)
    view = discord.ui.View(timeout=None)
    cancel: discord.ui.Button[discord.ui.View] = discord.ui.Button(
        label="Annuler", style=discord.ButtonStyle.danger
    )
    view.add_item(cancel)
    confirm: discord.ui.Button[discord.ui.View] = discord.ui.Button(
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
            "et temps d'attentes ont été réinitialisatiés."
        ),
    )

    async def cancel_callback(
        interaction: Interaction,
    ) -> None:
        nonlocal done
        done = True
        cancel.disabled = True
        confirm.disabled = True
        view.stop()
        await asyncio.gather(
            message.edit(view=view),
            interaction.response.send_message(
                embed=cancel_embed,
                ephemeral=True,
            ),
        )

    async def confirm_callback(
        interaction: Interaction,
    ) -> None:
        nonlocal done
        done = True
        cancel.disabled = True
        confirm.disabled = True
        view.stop()
        await asyncio.gather(
            message.edit(view=view),
            interaction.response.defer(ephemeral=True),
        )

        async with AsyncSession(ctx.client.engine) as session:
            await session.execute(
                delete(Hunt).where(Hunt.guild_id == ctx.guild_id)
            )
            await session.execute(
                delete(Egg).where(Egg.guild_id == ctx.guild_id)
            )
            await session.execute(
                delete(Cooldown).where(
                    and_(
                        Cooldown.guild_id == ctx.guild_id,
                        Cooldown.command != "reset",
                    )
                )
            )
            await session.commit()
        await interaction.followup.send(
            embed=confirm_embed,
            ephemeral=True,
        )

    cancel.callback = cancel_callback  # type: ignore[assignment]
    confirm.callback = confirm_callback  # type: ignore[assignment]
    message = await ctx.followup.send(
        embed=embed(
            title="Demande de réinitialisation",
            description=(
                "L'ensemble des salons, œufs "
                "et temps d'attentes vont être réinitialisatiés."
                f"\n\n-# Vous devez confirmer {in_seconds(30)}"
            ),
        ),
        ephemeral=True,
        view=view,
        wait=True,
    )
    await asyncio.sleep(30.0)
    if not done:
        cancel.disabled = True
        confirm.disabled = True
        view.stop()
        await asyncio.gather(
            message.edit(view=view),
            ctx.followup.send(embed=cancel_embed, ephemeral=True),
        )
