"""Command top."""

import logging
from typing import TYPE_CHECKING

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.hunts.hunt import embed
from easterobot.hunts.rank import Ranking

from .base import Context, controlled_command, egg_command_group

if TYPE_CHECKING:
    from easterobot.bot import Easterobot

PAGE_SIZE = 10
logger = logging.getLogger(__name__)


class PaginationRanking(discord.ui.View):
    embed: discord.Embed

    def __init__(
        self,
        *,
        ranking: Ranking,
        page: int = 0,
        limit: int = PAGE_SIZE,
        timeout: int = 180,
    ) -> None:
        """Instantiate PaginationRanking."""
        super().__init__(timeout=timeout)
        self._page = 0
        self._limit = limit
        self._ranking = ranking
        self.page = page

    @property
    def page(self) -> int:
        """Current page."""
        return self._page

    @page.setter
    def page(self, n: int) -> None:
        self._page = n
        self._update()

    def _update(self) -> None:
        count_page = self._ranking.count_page(PAGE_SIZE)
        self.previous.disabled = self._page <= 0
        self.next.disabled = self._page >= count_page - 1
        hunters = self._ranking.page(self._page, limit=PAGE_SIZE)
        if hunters:
            text = "\n".join(hunter.record for hunter in hunters)
        else:
            text = "\n:spider_web: Personne n'a d'œuf"
        emb = embed(
            title="Chasse aux œufs",
            description=text,
            footer=(f"Page {self._page + 1}/{count_page or 1}"),
        )
        if hasattr(self, "embed"):
            emb.colour = self.embed.colour
        self.embed = emb

    @discord.ui.button(
        label="<",
        style=discord.ButtonStyle.gray,
    )
    async def previous(
        self,
        interaction: discord.Interaction["Easterobot"],
        button: discord.ui.Button["PaginationRanking"],  # noqa: ARG002
    ) -> None:
        """Get previous page."""
        self._page = max(self._page - 1, 0)
        await interaction.response.edit_message(view=self, embed=self.embed)

    @discord.ui.button(label=">", style=discord.ButtonStyle.gray)
    async def next(
        self,
        interaction: discord.Interaction["Easterobot"],
        button: discord.ui.Button["PaginationRanking"],  # noqa: ARG002
    ) -> None:
        """Get next page."""
        self._page = min(self._page + 1, self._ranking.count_page(self._limit))
        await interaction.response.edit_message(view=self, embed=self.embed)


@egg_command_group.command(
    name="top", description="Classement des chasseurs d'œufs"
)
@controlled_command(cooldown=True)
async def top_command(ctx: Context) -> None:
    """Top command."""
    await ctx.response.defer(ephemeral=True)

    async with AsyncSession(ctx.client.engine) as session:
        ranking = await Ranking.from_guild(session, ctx.guild_id)
    view = PaginationRanking(ranking=ranking, timeout=180)
    await ctx.followup.send(embed=view.embed, ephemeral=True, view=view)
