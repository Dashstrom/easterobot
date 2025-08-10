"""Easter hunt basket command.

This module provides the command to display a user's easter egg collection.
It shows detailed egg counts by type, missing eggs, and the user's ranking.
"""

import discord
from discord import app_commands
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.commands.base import (
    Context,
    controlled_command,
    egg_command_group,
)
from easterobot.config import agree
from easterobot.hunts.hunt import embed
from easterobot.hunts.rank import Ranking
from easterobot.models import Egg


@egg_command_group.command(
    name="basket",
    description="Regarder le contenu d'un panier",
)
@app_commands.describe(
    user="Membre possèdant le panier à inspecter",
)
@controlled_command(cooldown=True)
async def basket_command(
    ctx: Context, user: discord.Member | None = None
) -> None:
    """Display the easter egg basket contents for a user.

    Shows a detailed breakdown of the user's egg collection including counts
    by emoji type, missing egg types, current ranking, and total count.
    If no user is specified, shows the command user's own basket.

    Args:
        ctx: Discord command context containing guild information.
        user: Member whose basket to inspect. Defaults to command user.
    """
    # Defer response to allow time for database operations
    await ctx.response.defer(ephemeral=True)

    # Determine whose basket to display
    target_user = user or ctx.user

    # Check if viewing own basket for proper grammar conjugation
    is_viewing_own_basket = ctx.user == target_user

    async with AsyncSession(ctx.client.engine) as database_session:
        basket_display_lines = []
        missing_egg_types = []

        # Get user's ranking in the guild
        guild_ranking = await Ranking.from_guild(
            database_session, ctx.guild_id
        )
        user_rank = guild_ranking.get(target_user.id)

        # Query egg counts grouped by emoji type
        egg_count_query_result = await database_session.execute(
            select(
                Egg.emoji_id,
                func.count().label("count"),
            )
            .where(
                and_(
                    Egg.guild_id == ctx.guild.id,
                    Egg.user_id == target_user.id,
                )
            )
            .group_by(Egg.emoji_id)
        )
        user_egg_counts: dict[int, int] = dict(egg_count_query_result.all())  # type: ignore[arg-type]

        total_egg_count = 0

        # Process each available egg emoji type
        for egg_emoji in ctx.client.egg_emotes.choices:
            try:
                emoji_count = user_egg_counts.pop(egg_emoji.id)
                total_egg_count += emoji_count
                basket_display_lines.append(f"{egg_emoji} \xd7 {emoji_count}")
            # User doesn't have this egg type
            except KeyError:  # noqa: PERF203
                missing_egg_types.append(egg_emoji)

        # Handle eggs with unknown/removed emoji types
        unknown_emoji_count = sum(user_egg_counts.values())
        if unknown_emoji_count:
            total_egg_count += unknown_emoji_count
            basket_display_lines.insert(0, f"🥚 \xd7 {unknown_emoji_count}")

        # Add ranking information at the top
        conjugated_verb = ctx.client.config.conjugate("{Iel} est", target_user)
        ranking_text = (
            f"**{'Tu es' if is_viewing_own_basket else conjugated_verb} "
            f"au rang** {user_rank.badge}\n"
        )
        basket_display_lines.insert(0, ranking_text)

        # Add missing egg types information if any
        pronoun = "te" if is_viewing_own_basket else "lui"
        if missing_egg_types:
            missing_emojis_text = "".join(map(str, missing_egg_types))
            basket_display_lines.append(
                f"\nIl {pronoun} manque : {missing_emojis_text}"
            )

        # Combine all display lines
        basket_description = "\n".join(basket_display_lines).strip()

        # Send the basket display embed
        await ctx.followup.send(
            embed=embed(
                title=f"Contenu du panier de {target_user.display_name}",
                description=basket_description,
                footer=(
                    f"Cela {pronoun} fait un total de "
                    + agree("{0} œuf", "{0} œufs", total_egg_count)
                ),
            ),
            ephemeral=True,
        )
