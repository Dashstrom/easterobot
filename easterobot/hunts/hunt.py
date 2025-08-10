"""Hunt system for managing egg discovery events in Discord channels.

This module handles the core egg hunting mechanics including hunt scheduling,
player participation, winner selection, and game interactions. It manages
database operations for eggs and hunts, implements weighted random selection
for fair winner determination, and integrates with Discord UI components.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterable, Sequence
from datetime import datetime, timezone
from typing import (
    TYPE_CHECKING,
    Any,
    Optional,
)

import discord
from discord.ext import commands
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.casino.roulette import RouletteManager
from easterobot.config import (
    RAND,
    agree,
)
from easterobot.hunts.luck import HuntLuck
from easterobot.models import Egg, Hunt
from easterobot.query import QueryManager
from easterobot.utils import in_seconds

logger = logging.getLogger(__name__)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

if TYPE_CHECKING:
    from easterobot.bot import Easterobot


class HuntQuery(QueryManager):
    """Database query manager for hunt-related operations."""

    async def unlock_all_eggs(self, session: AsyncSession) -> None:
        """Unlock all currently locked eggs in the database.

        Args:
            session: Database session for executing the query.
        """
        await session.execute(update(Egg).where(Egg.lock).values(lock=False))

    async def get_egg_count_for_members(
        self,
        session: AsyncSession,
        guild_id: int,
        user_ids: Iterable[int],
    ) -> dict[int, int]:
        """Retrieve egg counts for specified guild members.

        Args:
            session: Database session for executing queries.
            guild_id: Discord guild identifier.
            user_ids: Collection of user identifiers to query.

        Returns:
            Dictionary mapping user IDs to their egg counts.
        """
        result = await session.execute(
            select(Egg.user_id, func.count().label("count"))
            .where(
                and_(
                    Egg.guild_id == guild_id,
                    Egg.user_id.in_(user_ids),
                )
            )
            .group_by(Egg.user_id)
        )
        return dict(result.all())  # type: ignore[arg-type]

    async def get_hunt(
        self,
        session: AsyncSession,
        guild_id: int,
        channel_id: int,
    ) -> Optional[Hunt]:
        """Retrieve hunt configuration for a specific channel.

        Args:
            session: Database session for executing queries.
            guild_id: Discord guild identifier.
            channel_id: Discord channel identifier.

        Returns:
            Hunt object if found, None otherwise.
        """
        hunt = await session.scalar(
            select(Hunt).where(
                and_(
                    Hunt.guild_id == guild_id,
                    Hunt.channel_id == channel_id,
                )
            )
        )
        return hunt  # noqa: RET504

    async def get_hunts_after(
        self,
        session: AsyncSession,
        after_timestamp: float,
    ) -> Sequence[Hunt]:
        """Retrieve all hunts scheduled after the specified timestamp.

        Args:
            session: Database session for executing queries.
            after_timestamp: Unix timestamp threshold.

        Returns:
            Sequence of Hunt objects scheduled after the given time.
        """
        result = await session.scalars(
            select(Hunt).where(Hunt.next_egg <= after_timestamp),
        )
        return result.all()

    async def get_max_eggs(
        self,
        session: AsyncSession,
        guild_id: int,
    ) -> int:
        """Find the maximum egg count among all users in the guild.

        Args:
            session: Database session for executing queries.
            guild_id: Discord guild identifier.

        Returns:
            Maximum egg count, or 0 if no eggs exist.
        """
        max_egg_count = await session.scalar(
            select(
                func.count().label("max"),
            )
            .where(Egg.guild_id == guild_id)
            .group_by(Egg.user_id)
            .order_by(func.count().label("max").desc())
            .limit(1)
        )
        return max_egg_count or 0

    async def get_egg_count(
        self,
        session: AsyncSession,
        guild_id: int,
        user_id: int,
    ) -> int:
        """Get the total egg count for a specific user in a guild.

        Args:
            session: Database session for executing queries.
            guild_id: Discord guild identifier.
            user_id: Discord user identifier.

        Returns:
            Total number of eggs owned by the user.
        """
        egg_count = await session.scalar(
            select(func.count().label("count")).where(
                and_(
                    Egg.guild_id == guild_id,
                    Egg.user_id == user_id,
                )
            )
        )
        return egg_count or 0

    async def get_luck(
        self,
        session: AsyncSession,
        guild_id: int,
        user_id: int,
        *,
        sleep_hours: bool = False,
    ) -> HuntLuck:
        """Calculate luck factor for a user based on their egg count.

        Args:
            session: Database session for executing queries.
            guild_id: Discord guild identifier.
            user_id: Discord user identifier.
            sleep_hours: Whether to apply sleep hours modifier.

        Returns:
            HuntLuck object containing luck calculations.
        """
        luck_multiplier = 1.0
        user_egg_count = await self.get_egg_count(session, guild_id, user_id)
        if user_egg_count != 0:
            max_egg_count = await self.get_max_eggs(session, guild_id)
            if max_egg_count != 0:
                luck_multiplier = 1 - user_egg_count / max_egg_count
        return HuntLuck(
            egg_count=user_egg_count,
            luck=luck_multiplier,
            sleep_hours=sleep_hours,
            config=self.config,
        )


class HuntCog(commands.Cog, HuntQuery):
    """Discord cog managing egg hunt events and interactions."""

    def __init__(self, bot: "Easterobot") -> None:
        """Initialize the hunt cog with bot reference.

        Args:
            bot: The main bot instance.
        """
        self.bot = bot
        super().__init__(self.bot.config)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Handle bot ready event and start hunt management loop.

        This method unlocks all previously locked eggs and starts the main
        hunt scheduling loop. Can be triggered multiple times on reconnection.
        """
        # Wait for main initialization to complete
        await self.bot.init_finished.wait()

        # Unlock all eggs from previous sessions
        logger.info("Unlock all previous eggs")
        async with AsyncSession(self.bot.engine) as session:
            await self.unlock_all_eggs(session)
            await session.commit()

        # Start the hunt management loop
        logger.info("Start hunt handler")
        # TODO(dashstrom): refactor this loop structure
        pending_hunt_tasks: set[asyncio.Task[Any]] = set()
        while True:
            if pending_hunt_tasks:
                try:
                    _, pending_hunt_tasks = await asyncio.wait(
                        pending_hunt_tasks, timeout=1
                    )
                except Exception as err:  # noqa: BLE001
                    logger.critical("Unattended exception", exc_info=err)
            await asyncio.sleep(5)
            pending_hunt_tasks.add(asyncio.create_task(self.loop_hunt()))

    async def start_hunt(  # noqa: C901, PLR0912, PLR0915
        self,
        hunt_channel_id: int,
        hunt_description: str,
        *,
        member_id: Optional[int] = None,
        casino: bool = False,
        send_method: Optional[
            Callable[..., Awaitable[discord.Message]]
        ] = None,
    ) -> None:
        """Start an egg hunt event in the specified channel.

        Args:
            hunt_channel_id: Discord channel ID where the hunt occurs.
            hunt_description: Descriptive text for the hunt event.
            member_id: Optional specific member to highlight in the hunt.
            casino: Whether this hunt can trigger casino events.
            send_method: Optional custom method for sending the hunt message.
        """
        # Resolve the hunt channel from the ID
        channel = await self.bot.resolve_channel(hunt_channel_id)
        if not channel:
            return
        guild = channel.guild

        # Handle random casino event triggers
        if casino:
            casino_event = self.bot.config.casino.sample_event()
            if casino_event:
                roulette_manager = RouletteManager(self.bot)
                await roulette_manager.run(channel)
                return

        # Get random action and emoji from configuration
        hunt_action = self.bot.config.action.rand()
        hunt_emoji = self.bot.egg_emotes.rand()

        # Initialize hunters list and button label
        participating_hunters: list[discord.Member] = []
        button_label = hunt_action.text
        if member_id is not None:
            target_member = channel.guild.get_member(member_id)
            if target_member:
                participating_hunters.append(target_member)
                button_label += " (1)"

        # Start the hunt event
        logger.info("Start hunt in %s", channel.jump_url)
        hunt_timeout = self.bot.config.hunt.timeout + 1
        has_duel_game = False
        hunt_view = discord.ui.View(timeout=hunt_timeout)
        hunt_button: discord.ui.Button[Any] = discord.ui.Button(
            label=button_label,
            style=discord.ButtonStyle.primary,
            emoji=hunt_emoji,
        )
        hunt_view.add_item(hunt_button)
        button_update_lock = asyncio.Lock()

        async def button_callback(
            interaction: discord.Interaction[Any],
        ) -> None:
            """Handle button clicks for egg hunt participation.

            Args:
                interaction: Discord interaction from button click.
            """
            # Defer response to prevent timeout
            await interaction.response.defer()
            hunt_message = interaction.message
            clicking_user = interaction.user
            if (
                hunt_message is None  # Message must be loaded
                or not isinstance(
                    clicking_user, discord.Member
                )  # Must be a member
            ):
                logger.warning("Invalid callback for %s", guild)
                return
            # Check if user hasn't already claimed the egg
            for existing_hunter in participating_hunters:
                if existing_hunter.id == clicking_user.id:
                    logger.info(
                        "Already hunt by %s (%s) on %s",
                        clicking_user,
                        clicking_user.id,
                        hunt_message.jump_url,
                    )
                    return

            # Add the user to the participants
            participating_hunters.append(clicking_user)

            # Log hunter information
            logger.info(
                "Hunt (%d) by %s (%s) on %s",
                len(participating_hunters),
                clicking_user,
                clicking_user.id,
                hunt_message.jump_url,
            )

            # Update button counter with thread safety
            async with button_update_lock:
                hunt_button.label = (
                    hunt_action.text + f" ({len(participating_hunters)})"
                )
                await hunt_message.edit(view=hunt_view)

        # Assign the callback to the button
        hunt_button.callback = button_callback  # type: ignore[method-assign]

        # Create hunt embed
        hunt_embed = embed(
            title="Un œuf a été découvert !",
            description=hunt_description
            + f"\n\n-# Tirage du vainqueur {in_seconds(hunt_timeout)}",
            thumbnail=hunt_emoji.url,
        )

        # Send the hunt message
        if send_method is None:
            hunt_message = await channel.send(embed=hunt_embed, view=hunt_view)
        else:
            hunt_message = await send_method(embed=hunt_embed, view=hunt_view)
            hunt_message = await hunt_message.channel.fetch_message(
                hunt_message.id
            )

        # TODO(dashstrom): channel is incorrect due to send message method
        # TODO(dashstrom): investigate why wait if timeout exists
        # Wait for hunt completion or timeout
        message_url = f"{channel.jump_url}/{hunt_message.id}"
        try:
            await asyncio.wait_for(
                hunt_view.wait(), timeout=self.bot.config.hunt.timeout
            )
        except asyncio.TimeoutError:
            logger.info("End hunt for %s", message_url)

        # Disable button and stop view after hunt ends
        hunt_button.disabled = True
        hunt_view.stop()
        await hunt_message.edit(view=hunt_view)

        # Process hunt results
        async with AsyncSession(self.bot.engine) as session:
            hunt_config = await self.get_hunt(session, guild.id, channel.id)

            # Handle case where no one participated or hunt doesn't exist
            if not participating_hunters or not hunt_config:
                hunt_button.label = "L'œuf n'a pas été ramassé"
                hunt_button.style = discord.ButtonStyle.danger
                logger.info("No Hunter for %s", message_url)
            else:
                # Get current egg counts for all participants
                participant_egg_counts = await self.get_egg_count_for_members(
                    session,
                    guild_id=guild.id,
                    user_ids=[hunter.id for hunter in participating_hunters],
                )
                logger.info("Winner draw for %s", message_url)

                # Rank participants for winner selection
                ranked_participants = self.rank_players(
                    participating_hunters, participant_egg_counts
                )
                if len(ranked_participants) == 1:
                    hunt_winner = ranked_participants[0]
                    hunt_loser = None
                else:
                    hunt_winner = ranked_participants[0]
                    hunt_loser = ranked_participants[1]

                    # Check for duel game trigger
                    if RAND.random() < self.bot.config.hunt.game:
                        # Update button for duel state
                        has_duel_game = True
                        hunt_button.label = "Duel en cours ..."
                        hunt_button.style = discord.ButtonStyle.gray

                        # Edit message and start duel
                        await hunt_message.edit(view=hunt_view)
                        duel_result = await self.bot.game.start_duel(
                            channel=channel,
                            reference_message=hunt_message,
                            player1=hunt_winner,
                            player2=hunt_loser,
                        )
                        if duel_result is None:
                            hunt_winner = None
                            hunt_loser = None
                        elif duel_result.member == hunt_loser:
                            hunt_winner, hunt_loser = hunt_loser, hunt_winner

                # Award egg to winner
                if hunt_winner:
                    session.add(
                        Egg(
                            channel_id=channel.id,
                            guild_id=channel.guild.id,
                            user_id=hunt_winner.id,
                            emoji_id=hunt_emoji.id,
                        )
                    )
                    await session.commit()

                # Display loser message if applicable
                if hunt_loser:
                    loser_display_name = hunt_loser.display_name
                    if len(participating_hunters) == 2:  # noqa: PLR2004
                        loser_text = f"{loser_display_name} rate un œuf"
                    else:
                        loser_text = agree(
                            "{1} et {0} autre chasseur ratent un œuf",
                            "{1} et {0} autres chasseurs ratent un œuf",
                            len(participating_hunters) - 2,
                            loser_display_name,
                        )
                    loser_embed = embed(
                        title=loser_text,
                        description=(
                            hunt_action.fail.text(hunt_loser)
                            + "\n\n-# Ce message disparaîtra "
                            + in_seconds(300)
                        ),
                        image=hunt_action.fail.gif,
                    )
                    await channel.send(
                        embed=loser_embed,
                        reference=hunt_message,
                        delete_after=300,
                    )

                # Display winner message and update button
                if hunt_winner:
                    # Get updated egg count for winner
                    if has_duel_game:
                        winner_total_eggs = await self.get_egg_count(
                            session,
                            hunt_winner.guild.id,
                            hunt_winner.id,
                        )
                    else:
                        winner_total_eggs = (
                            participant_egg_counts.get(hunt_winner.id, 0) + 1
                        )

                    # Create and send winner embed
                    winner_embed = embed(
                        title=f"{hunt_winner.display_name} récupère un œuf",
                        description=hunt_action.success.text(hunt_winner),
                        image=hunt_action.success.gif,
                        thumbnail=hunt_emoji.url,
                        egg_count=winner_total_eggs,
                    )
                    await channel.send(
                        embed=winner_embed, reference=hunt_message
                    )

                    # Update button for winner
                    hunt_button.label = (
                        f"L'œuf a été ramassé par {hunt_winner.display_name}"
                    )
                    hunt_button.style = discord.ButtonStyle.success
                    logger.info(
                        "Winner is %s (%s) with %s",
                        hunt_winner,
                        hunt_winner.id,
                        agree("{0} egg", "{0} eggs", winner_total_eggs),
                    )
                else:
                    hunt_button.label = "L'œuf a été cassé"
                    hunt_button.style = discord.ButtonStyle.danger
                    logger.info("No winner %s", message_url)

        # Remove emoji and finalize message
        hunt_button.emoji = None
        await hunt_message.edit(view=hunt_view)

    def rank_players(
        self, hunters: list[discord.Member], egg_counts: dict[int, int]
    ) -> list[discord.Member]:
        """Rank players using weighted random selection.

        Uses egg count disadvantage and join order to determine fair ranking.
        Players with fewer eggs have better chances of winning.

        Args:
            hunters: List of participating members.
            egg_counts: Dictionary mapping user IDs to their egg counts.

        Returns:
            List of members ranked by weighted probability selection.
        """
        # Handle single or no hunters
        if len(hunters) <= 1:
            return hunters
        total_hunters = len(hunters)

        # Calculate egg count statistics
        min_egg_count = min(egg_counts.values(), default=0)
        max_egg_count = max(egg_counts.values(), default=0)
        egg_count_difference = max_egg_count - min_egg_count

        # Normalize weight components
        weight_egg = self.bot.config.hunt.weights.egg
        weight_speed = self.bot.config.hunt.weights.speed
        weight_base = self.bot.config.hunt.weights.base
        total_weight = weight_egg + weight_speed + weight_base
        weight_egg /= total_weight
        weight_speed /= total_weight
        weight_base /= total_weight

        # Calculate individual hunter weights
        hunter_weights = []
        for hunter_index, hunter in enumerate(hunters):
            # Base probability component
            base_probability = 1

            # Egg disadvantage component (fewer eggs = higher probability)
            if egg_count_difference != 0:
                hunter_egg_count = egg_counts.get(hunter.id, 0) - min_egg_count
                egg_probability = 1 - hunter_egg_count / egg_count_difference
            else:
                egg_probability = 1.0

            # Speed component (earlier joiners get advantage)
            speed_probability = 1 - hunter_index / total_hunters

            # Combine weighted probabilities
            final_weight = (
                base_probability * weight_base
                + speed_probability * weight_speed
                + egg_probability * weight_egg
            )
            hunter_weights.append(final_weight)

        # Normalize final probabilities
        weight_sum = sum(hunter_weights)
        normalized_weights = [weight / weight_sum for weight in hunter_weights]
        for hunter, weight in zip(hunters, normalized_weights):
            logger.info("%.2f%% - %s (%s)", weight * 100, hunter, hunter.id)

        # Generate rankings using weighted random selection
        final_rankings = []
        remaining_hunters = list(hunters)
        remaining_weights = list(normalized_weights)
        while remaining_hunters:
            # Select winner using weights
            (selected_hunter,) = RAND.choices(
                remaining_hunters, remaining_weights
            )
            hunter_index = remaining_hunters.index(selected_hunter)

            # Remove selected hunter from remaining lists
            del remaining_hunters[hunter_index]
            del remaining_weights[hunter_index]
            final_rankings.append(selected_hunter)
        return final_rankings

    async def loop_hunt(self) -> None:
        """Manage hunt scheduling and execute pending hunts.

        Checks for hunts ready to execute, schedules their next occurrence,
        and starts hunt events with appropriate timing and casino integration.
        """
        # Create database session for hunt management
        async with AsyncSession(self.bot.engine) as session:
            # Find hunts ready to execute
            current_time = time.time()
            ready_hunts = await self.get_hunts_after(session, current_time)
            ready_hunt_ids = [hunt.channel_id for hunt in ready_hunts]

            # Schedule next occurrence for each ready hunt
            if ready_hunts:
                for hunt in ready_hunts:
                    # Calculate next hunt time with cooldown
                    cooldown_delta = self.bot.config.hunt.cooldown.rand()
                    if self.bot.config.in_sleep_hours():
                        cooldown_delta *= self.bot.config.sleep.divide_hunt
                    next_hunt_time = current_time + cooldown_delta
                    next_hunt_datetime = datetime.fromtimestamp(
                        next_hunt_time, tz=timezone.utc
                    )

                    logger.info(
                        "Next hunt at %s on %s",
                        hunt.jump_url,
                        next_hunt_datetime.strftime(DATE_FORMAT),
                    )
                    hunt.next_egg = next_hunt_time
                await session.commit()

        # Execute all ready hunts concurrently
        if ready_hunt_ids:
            try:
                await asyncio.gather(
                    *[
                        self.start_hunt(
                            hunt_id,
                            self.bot.config.appear.rand(),
                            casino=True,
                        )
                        for hunt_id in ready_hunt_ids
                    ]
                )
            except Exception as err:
                logger.exception(
                    "An error occurred during start hunt", exc_info=err
                )


def embed(
    *,
    title: str,
    description: Optional[str] = None,
    image: Optional[str] = None,
    thumbnail: Optional[str] = None,
    egg_count: Optional[int] = None,
    footer: Optional[str] = None,
) -> discord.Embed:
    """Create a formatted Discord embed for hunt-related messages.

    Args:
        title: Main title text for the embed.
        description: Optional description content.
        image: Optional image URL to display.
        thumbnail: Optional thumbnail image URL.
        egg_count: Optional egg count to include in footer.
        footer: Optional custom footer text.

    Returns:
        Configured Discord embed object.
    """
    new_embed = discord.Embed(
        title=title,
        description=description,
        colour=RAND.randint(0, 1 << 24),
        type="gifv" if image else "rich",
    )
    if image is not None:
        new_embed.set_image(url=image)
    if thumbnail is not None:
        new_embed.set_thumbnail(url=thumbnail)
    if egg_count is not None:
        footer_text = (footer + " - ") if footer else ""
        footer_text += "Cela lui fait un total de "
        footer_text += agree("{0} œuf", "{0} œufs", egg_count)
        footer = footer_text
    if footer:
        new_embed.set_footer(text=footer)
    return new_embed
