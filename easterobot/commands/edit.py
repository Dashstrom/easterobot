"""Easter hunt edit command.

This module provides the command to edit a member's egg count in guilds.
It handles adding or removing eggs from the database to match the target count.
"""

import discord
from discord import app_commands
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.config import RAND, agree
from easterobot.hunts.hunt import embed
from easterobot.models import Egg

from .base import Context, controlled_command, egg_command_group


@egg_command_group.command(
    name="edit",
    description="Editer le nombre d'œufs d'un membre",
)
@controlled_command(cooldown=True, administrator=True)
async def edit_command(
    ctx: Context,
    user: discord.Member,
    oeufs: app_commands.Range[int, 0, 10_000],
) -> None:
    """Edit a member's egg count to the specified target amount.

    Adjusts a user's egg collection by adding or removing eggs
    from the database to match the target count. If reducing eggs,
    randomly selects which eggs to remove.
    If increasing, creates new eggs with random emoji IDs.

    Args:
        ctx: Discord command context containing guild and channel information.
        user: Discord member whose egg count should be modified.
        oeufs: Target number of eggs the user should have (0-10,000).
    """
    await ctx.response.defer(ephemeral=True)

    async with AsyncSession(ctx.client.engine) as database_session:
        # Fetch all current eggs for the user in this guild
        current_eggs: list[Egg] = list(
            (
                await database_session.scalars(
                    select(Egg).where(
                        and_(
                            Egg.guild_id == ctx.guild_id,
                            Egg.user_id == user.id,
                        )
                    )
                )
            ).all()
        )

        # Calculate difference between current and target egg count
        egg_difference = len(current_eggs) - oeufs

        if egg_difference > 0:
            # Need to remove eggs - randomly select which ones to delete
            eggs_to_delete_ids = []
            for _ in range(egg_difference):
                egg_to_remove = RAND.choice(current_eggs)
                current_eggs.remove(egg_to_remove)
                eggs_to_delete_ids.append(egg_to_remove.id)

            # Delete selected eggs from database
            await database_session.execute(
                delete(Egg).where(Egg.id.in_(eggs_to_delete_ids))
            )
            await database_session.commit()

        elif egg_difference < 0:
            # Need to add eggs - create new ones with random emojis
            eggs_to_add = -egg_difference
            for _ in range(eggs_to_add):
                database_session.add(
                    Egg(
                        guild_id=ctx.guild_id,
                        channel_id=ctx.channel_id,
                        user_id=user.id,
                        emoji_id=ctx.client.egg_emotes.rand().id,
                    )
                )
            await database_session.commit()

    # Send confirmation message with updated egg count
    await ctx.followup.send(
        embed=embed(
            title="Edition terminée",
            description=(
                f"{user.mention} a maintenant "
                f"{agree('{0} œuf', '{0} œufs', oeufs)}"
            ),
        ),
        ephemeral=True,
    )
