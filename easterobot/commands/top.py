"""Command top."""

import logging
from math import floor
from typing import Optional

import discord
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.hunts.hunt import embed
from easterobot.hunts.rank import Ranking
from easterobot.models import Egg

from .base import Context, Interaction, controlled_command, egg_command_group

PAGE_SIZE = 10
logger = logging.getLogger(__name__)


async def embed_rank(
    ctx: Context,
    page: int,
    colour: Optional[discord.Colour] = None,
) -> tuple[discord.Embed, bool]:
    """Embed for rank."""
    async with AsyncSession(ctx.client.engine) as session:
        ranking = await Ranking.from_guild(session, ctx.guild_id)
        hunters = ranking.page(page, limit=PAGE_SIZE)
        morsels: list[str] = []
        if hunters:
            morsels.extend(hunter.record for hunter in hunters)
        else:
            morsels.append("\n:spider_web: Personne n'a d'œuf")
        total = await session.scalar(
            select(func.count(distinct(Egg.user_id)).label("count")).where(
                Egg.guild_id == ctx.guild_id
            )
        )
        if total is None:
            total = 0
            logger.warning("No total egg !")
        total = floor(total / PAGE_SIZE)
    text = "\n".join(morsels)
    emb = embed(
        title="Chasse aux œufs",
        description=text,
        footer=f"Page {page + 1}/{total + 1}",
    )
    if colour is not None:
        emb.colour = colour
    return emb, page >= total


@egg_command_group.command(
    name="top", description="Classement des chasseurs d'œufs"
)
@controlled_command(cooldown=True)
async def top_command(ctx: Context) -> None:
    """Top command."""
    await ctx.response.defer(ephemeral=True)

    view = discord.ui.View(timeout=None)
    previous_page: discord.ui.Button[discord.ui.View] = discord.ui.Button(
        label="<", style=discord.ButtonStyle.gray, disabled=True
    )
    view.add_item(previous_page)
    next_page: discord.ui.Button[discord.ui.View] = discord.ui.Button(
        label=">", style=discord.ButtonStyle.gray
    )
    view.add_item(next_page)
    page = 0

    async def edit(interaction: Interaction) -> None:
        previous_page.disabled = page <= 0
        emb, next_page.disabled = await embed_rank(
            ctx, page, base_embed.colour
        )
        await interaction.response.edit_message(view=view, embed=emb)

    async def previous_callback(interaction: Interaction) -> None:
        nonlocal page
        page = max(page - 1, 0)
        await edit(interaction)

    async def next_callback(interaction: Interaction) -> None:
        nonlocal page
        page += 1
        await edit(interaction)

    previous_page.callback = previous_callback  # type: ignore[assignment]
    next_page.callback = next_callback  # type: ignore[assignment]
    base_embed, next_page.disabled = await embed_rank(ctx, page)
    await ctx.followup.send(embed=base_embed, ephemeral=True, view=view)
