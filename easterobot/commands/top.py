"""Top command for displaying paginated egg hunt leaderboards.

This module implements a Discord slash command that displays a paginated
leaderboard of egg hunters in a guild. It includes interactive pagination
buttons allowing users to navigate through multiple pages of rankings
with real-time database queries.
"""

import logging
from typing import TYPE_CHECKING

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.hunts.hunt import embed
from easterobot.hunts.rank import Ranking

from .base import Context, controlled_command, egg_command_group

if TYPE_CHECKING:
    from easterobot.bot import Easterobot

# Number of hunters displayed per page in the leaderboard
HUNTERS_PER_PAGE = 10
logger = logging.getLogger(__name__)


class PaginatedLeaderboard(discord.ui.View):
    """Interactive paginated view for displaying egg hunt leaderboards.

    Provides navigation buttons to browse through multiple pages of hunter
    rankings, with automatic button state management and dynamic embed updates.
    """

    embed: discord.Embed

    def __init__(
        self,
        *,
        ranking: Ranking,
        initial_page: int = 0,
        items_per_page: int = HUNTERS_PER_PAGE,
        timeout: int = 180,
    ) -> None:
        """Initialize the paginated leaderboard view.

        Args:
            ranking: The Ranking object containing hunter data for the guild.
            initial_page: Starting page number (0-indexed).
            items_per_page: Number of hunters to display per page.
            timeout: Time in seconds before the view expires.
        """
        super().__init__(timeout=timeout)
        self._current_page = 0
        self._items_per_page = items_per_page
        self._ranking_data = ranking
        self.current_page = (
            initial_page  # Use setter to trigger initial update
        )

    @property
    def current_page(self) -> int:
        """Get the currently displayed page number (0-indexed).

        Returns:
            Current page number.
        """
        return self._current_page

    @current_page.setter
    def current_page(self, page_number: int) -> None:
        """Set the current page and update the view accordingly.

        Args:
            page_number: The page to navigate to (0-indexed).

        Automatically clamps the page number to valid bounds and updates
        button states and embed content to reflect the new page.
        """
        max_page = self._ranking_data.count_page(HUNTERS_PER_PAGE) - 1
        self._current_page = min(max(page_number, 0), max(max_page, 0))
        self._update_view()

    def _update_view(self) -> None:
        """Update button states and embed content based on current page.

        Disables navigation buttons when at first/last page, retrieves hunter
        data for the current page, and creates a new embed with the leaderboard
        information and pagination details.
        """
        total_pages = self._ranking_data.count_page(HUNTERS_PER_PAGE)

        # Update button states based on current position
        self.previous_page_button.disabled = self._current_page <= 0
        self.next_page_button.disabled = self._current_page >= total_pages - 1

        # Get hunters for the current page
        page_hunters = self._ranking_data.page(
            self._current_page, limit=HUNTERS_PER_PAGE
        )

        if page_hunters:
            # Format hunter records into leaderboard text
            leaderboard_text = "\n".join(
                hunter.record for hunter in page_hunters
            )
        else:
            # Display message when no hunters have any eggs
            leaderboard_text = "\n:spider_web: Personne n'a d'œuf"

        # Create new embed with updated content
        new_embed = embed(
            title="Chasse aux œufs",
            description=leaderboard_text,
            footer=f"Page {self._current_page + 1}/{total_pages or 1}",
        )

        # Preserve embed color if one was previously set
        if hasattr(self, "embed"):
            new_embed.colour = self.embed.colour

        self.embed = new_embed

    @discord.ui.button(
        label="<",
        style=discord.ButtonStyle.gray,
    )
    async def previous_page_button(
        self,
        interaction: discord.Interaction["Easterobot"],
        button: discord.ui.Button["PaginatedLeaderboard"],  # noqa: ARG002
    ) -> None:
        """Navigate to the previous page of the leaderboard.

        Args:
            interaction: The Discord interaction from the button press.
            button: The button that was pressed (unused).

        Decrements the current page by 1 and updates the message with the new
        leaderboard content. Button is automatically disabled on first page.
        """
        self.current_page -= 1
        await interaction.response.edit_message(view=self, embed=self.embed)

    @discord.ui.button(label=">", style=discord.ButtonStyle.gray)
    async def next_page_button(
        self,
        interaction: discord.Interaction["Easterobot"],
        button: discord.ui.Button["PaginatedLeaderboard"],  # noqa: ARG002
    ) -> None:
        """Navigate to the next page of the leaderboard.

        Args:
            interaction: The Discord interaction from the button press.
            button: The button that was pressed (unused).

        Increments the current page by 1 and updates the message with the new
        leaderboard content. Button is automatically disabled on last page.
        """
        self.current_page += 1
        await interaction.response.edit_message(view=self, embed=self.embed)


@egg_command_group.command(
    name="top", description="Classement des chasseurs d'œufs"
)
@controlled_command(cooldown=True)
async def top_command(ctx: Context) -> None:
    """Display the egg hunt leaderboard for the current guild with pagination.

    Args:
        ctx: The Discord application command context.

    Retrieves hunter rankings from the database, creates an interactive
    paginated view, and sends it as an ephemeral response. The leaderboard
    shows hunters ranked by their egg collection statistics with navigation
    buttons.
    """
    # Defer response to allow time for database query
    await ctx.response.defer(ephemeral=True)

    # Fetch ranking data from database for the current guild
    async with AsyncSession(ctx.client.engine) as database_session:
        guild_ranking = await Ranking.from_guild(
            database_session, ctx.guild_id
        )

    # Create paginated view with the ranking data
    leaderboard_view = PaginatedLeaderboard(ranking=guild_ranking, timeout=180)

    # Send the initial leaderboard page as an ephemeral follow-up
    await ctx.followup.send(
        embed=leaderboard_view.embed, ephemeral=True, view=leaderboard_view
    )
