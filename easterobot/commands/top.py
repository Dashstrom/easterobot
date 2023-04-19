from math import ceil
from typing import Optional, Tuple, Union

import discord
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..bot import embed
from ..config import agree
from ..models import Egg
from .base import EasterbotContext, controled_command, egg_command_group

PAGE_SIZE = 10


def record_top(rank: str, user_id: int, count: int) -> str:
    return (
        f"{rank} <@{user_id}>\n"
        f"\u2004\u2004\u2004\u2004\u2004"
        f"➥ {agree('{0} œuf', '{0} œufs', count)}"
    )


async def embed_rank(
    ctx: EasterbotContext,
    page: int,
    colour: Optional[Union[discord.Colour, discord.embeds._EmptyEmbed]] = None,
) -> Tuple[discord.Embed, bool]:
    async with AsyncSession(ctx.bot.engine) as session:
        egg_counts = await ctx.bot.get_ranks(
            session, ctx.guild_id, PAGE_SIZE, page
        )
        morsels = []
        if egg_counts:
            for user_id, rank, egg_count in egg_counts[:10]:
                morsels.append(record_top(rank, user_id, egg_count))
        else:
            morsels.append("\n:spider_web: Personne n'a d'œuf")

        total = ceil(
            await session.scalar(
                select(func.count().label("count"))
                .where(Egg.guild_id == ctx.guild_id)
                .group_by(Egg.user_id)
            )
            / PAGE_SIZE
        )
        total = total + 1
    text = "\n".join(morsels)
    emb = embed(
        title=f"Chasse aux œufs : {ctx.guild.name}",
        description=text,
        thumbnail=ctx.guild.icon.url if ctx.guild.icon else None,
        footer=f"Page {page + 1}/{total + 1}",
    )
    if colour is not None:
        emb.colour = colour
    return emb, page >= total


@egg_command_group.command(
    name="top", description="Classement des chasseurs d'œufs"
)
@controled_command(cooldown=True)
async def top_command(ctx: EasterbotContext) -> None:
    await ctx.defer(ephemeral=True)

    view = discord.ui.View(timeout=None)
    previous_page = discord.ui.Button(  # type: ignore
        label="⮜", style=discord.ButtonStyle.gray, disabled=True
    )
    view.add_item(previous_page)
    next_page = discord.ui.Button(  # type: ignore
        label="⮞", style=discord.ButtonStyle.gray
    )
    view.add_item(next_page)
    page = 0

    async def edit(interaction: discord.Interaction) -> None:
        previous_page.disabled = page <= 0
        emb, next_page.disabled = await embed_rank(
            ctx, page, base_embed.colour
        )
        await interaction.response.edit_message(view=view, embed=emb)

    async def previous_callback(interaction: discord.Interaction) -> None:
        nonlocal page
        page = max(page - 1, 0)
        await edit(interaction)

    async def next_callback(interaction: discord.Interaction) -> None:
        nonlocal page
        page += 1
        await edit(interaction)

    previous_page.callback = previous_callback  # type: ignore
    next_page.callback = next_callback  # type: ignore
    base_embed, next_page.disabled = await embed_rank(ctx, page)
    await ctx.followup.send(embed=base_embed, ephemeral=True, view=view)
