"""Reset command module for Easter egg hunt bot.

This module implements the reset command that allows administrators
to completely reset all Easter egg hunt data for their guild. The command
provides a confirmation interface with a 30-second timeout
to prevent accidental data loss.
"""

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
    """Reset all Easter egg hunt data for the current guild.

    Completely removes all hunts, eggs, and cooldowns (except reset cooldown)
    for the guild. Requires administrator permission and provides
    a confirmation interface with cancel/confirm buttons
    and a 30-second timeout.

    Args:
        ctx: Discord interaction context containing guild and client info.

    Returns:
        None. Sends response messages through Discord interaction system.
    """
    await ctx.response.defer(ephemeral=True)

    # Create confirmation UI with cancel and confirm buttons
    confirmation_view = discord.ui.View(timeout=None)
    cancel_button: discord.ui.Button[discord.ui.View] = discord.ui.Button(
        label="Annuler", style=discord.ButtonStyle.danger
    )
    confirmation_view.add_item(cancel_button)
    confirm_button: discord.ui.Button[discord.ui.View] = discord.ui.Button(
        label="Confirmer", style=discord.ButtonStyle.success
    )
    confirmation_view.add_item(confirm_button)

    # Track if user has already responded to prevent timeout conflicts
    user_has_responded = False

    # Pre-define embed messages for different outcomes
    cancellation_embed = embed(
        title="Réinitialisation annulée",
        description="Vous avez annulé la demande de réinitialisation.",
    )
    confirmation_success_embed = embed(
        title="Réinitialisation",
        description=(
            "L'ensemble des salons, œufs "
            "et temps d'attentes ont été réinitialisatiés."
        ),
    )

    async def handle_cancel_action(
        interaction: Interaction,
    ) -> None:
        """Handle cancel button click.

        Disables both buttons, stops the view, and sends cancellation message.

        Args:
            interaction: Discord button interaction from cancel button click.

        Returns:
            None. Updates UI and sends cancellation response.
        """
        nonlocal user_has_responded
        user_has_responded = True
        cancel_button.disabled = True
        confirm_button.disabled = True
        confirmation_view.stop()
        await asyncio.gather(
            confirmation_message.edit(view=confirmation_view),
            interaction.response.send_message(
                embed=cancellation_embed,
                ephemeral=True,
            ),
        )

    async def handle_confirm_action(
        interaction: Interaction,
    ) -> None:
        """Handle confirm button click and execute database reset.

        Disables buttons, performs database cleanup removing all hunts, eggs,
        and non-reset cooldowns for the guild, then sends success message.

        Args:
            interaction: Discord button interaction from confirm button click.

        Returns:
            None. Executes reset and sends confirmation response.
        """
        nonlocal user_has_responded
        user_has_responded = True
        cancel_button.disabled = True
        confirm_button.disabled = True
        confirmation_view.stop()
        await asyncio.gather(
            confirmation_message.edit(view=confirmation_view),
            interaction.response.defer(ephemeral=True),
        )

        # Execute database cleanup operations
        async with AsyncSession(ctx.client.engine) as database_session:
            # Remove all hunts for this guild
            await database_session.execute(
                delete(Hunt).where(Hunt.guild_id == ctx.guild_id)
            )
            # Remove all eggs for this guild
            await database_session.execute(
                delete(Egg).where(Egg.guild_id == ctx.guild_id)
            )
            # Remove all cooldowns except reset command cooldown
            await database_session.execute(
                delete(Cooldown).where(
                    and_(
                        Cooldown.guild_id == ctx.guild_id,
                        Cooldown.command != "reset",
                    )
                )
            )
            await database_session.commit()

        # Send success confirmation
        await interaction.followup.send(
            embed=confirmation_success_embed,
            ephemeral=True,
        )

    # Assign callback functions to button interactions
    cancel_button.callback = handle_cancel_action  # type: ignore[assignment]
    confirm_button.callback = handle_confirm_action  # type: ignore[assignment]

    # Send initial confirmation message with buttons
    confirmation_message = await ctx.followup.send(
        embed=embed(
            title="Demande de réinitialisation",
            description=(
                "L'ensemble des salons, œufs "
                "et temps d'attentes vont être réinitialisatiés."
                f"\n\n-# Vous devez confirmer {in_seconds(30)}"
            ),
        ),
        ephemeral=True,
        view=confirmation_view,
        wait=True,
    )

    # Wait 30 seconds for user response, then handle timeout if no response
    await asyncio.sleep(30.0)
    if not user_has_responded:
        cancel_button.disabled = True
        confirm_button.disabled = True
        confirmation_view.stop()
        await asyncio.gather(
            confirmation_message.edit(view=confirmation_view),
            ctx.followup.send(embed=cancellation_embed, ephemeral=True),
        )
