"""Command basket."""

from typing import Optional

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
    ctx: Context, user: Optional[discord.Member] = None
) -> None:
    """Show current user basket."""
    # Delay the response
    await ctx.response.defer(ephemeral=True)

    # Set the user of the basket
    hunter = user or ctx.user

    # Util for accord in some language
    you = ctx.user == hunter

    async with AsyncSession(ctx.client.engine) as session:
        morsels = []
        missing = []
        ranking = await Ranking.from_guild(session, ctx.guild_id)
        hunter_rank = ranking.get(hunter.id)
        res = await session.execute(
            select(
                Egg.emoji_id,
                func.count().label("count"),
            )
            .where(
                and_(
                    Egg.guild_id == ctx.guild.id,
                    Egg.user_id == hunter.id,
                )
            )
            .group_by(Egg.emoji_id)
        )
        egg_counts: dict[int, int] = dict(res.all())  # type: ignore[arg-type]
        egg_count = 0
        for emoji in ctx.client.egg_emotes.choices:
            try:
                type_count = egg_counts.pop(emoji.id)
                egg_count += type_count
                morsels.append(f"{emoji} \xd7 {type_count}")
            except KeyError:  # noqa: PERF203
                missing.append(emoji)

        absent_count = sum(egg_counts.values())
        if absent_count:
            egg_count += absent_count
            morsels.insert(0, f"🥚 \xd7 {absent_count}")

        il = ctx.client.config.conjugate("{Iel} est", hunter)
        morsels.insert(
            0,
            f"**{'Tu es' if you else il} au rang** {hunter_rank.badge}\n",
        )

        their = "te" if you else "lui"
        if missing:
            morsels.append(
                f"\nIl {their} manque : {''.join(map(str, missing))}"
            )
        text = "\n".join(morsels).strip()
        await ctx.followup.send(
            embed=embed(
                title=f"Contenu du panier de {hunter.display_name}",
                description=text,
                footer=(
                    f"Cela {their} fait un total de "
                    + agree("{0} œuf", "{0} œufs", egg_count)
                ),
            ),
            ephemeral=True,
        )
