"""Base classes and management system for Discord bot games.

This module provides the foundational Game class and GameCog manager for
implementing turn-based multiplayer games in Discord. It handles player
management, game lifecycle, timeout mechanics, reaction handling, and duel
initialization with betting systems.
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import discord
from discord.ext import commands
from discord.message import convert_emoji_reaction

from easterobot.bot import Easterobot
from easterobot.commands.base import Context, Interaction, InteractionChannel
from easterobot.config import RAND, agree
from easterobot.utils import in_seconds

logger = logging.getLogger(__name__)
AsyncCallback = Callable[[], Coroutine[Any, Any, None]]
Button = discord.ui.Button[discord.ui.View]


class GameError(Exception):
    """Base exception for all game-related errors."""


class InvalidActionError(GameError):
    """Exception raised when an invalid game action is attempted."""


class InvalidPlayerError(GameError):
    """Exception raised when an invalid player is referenced."""

    @staticmethod
    def from_player(member: discord.Member) -> "InvalidPlayerError":
        """Create an InvalidPlayerError from a Discord member.

        Args:
            member: The Discord member that caused the error.

        Returns:
            A new InvalidPlayerError with a descriptive message.
        """
        return InvalidPlayerError(
            f"Player {member!r} is not included in the game"
        )


@dataclass(frozen=True)
class Player:
    """Represents a player in a game with their member and assigned number.

    Attributes:
        member: The Discord member associated with this player.
        number: The player's assigned number/index in the game.
    """

    member: discord.Member
    number: int


class Game:
    """Base class for all bot games with player management and lifecycle.

    Provides core functionality for multiplayer games including
    player validation, game state management, timeout handling,
    reaction processing, and cleanup.
    Subclasses should implement game-specific logic in the provided methods.
    """

    def __init__(
        self,
        bot: Easterobot,
        message: discord.Message,
        *members: discord.Member,
    ) -> None:
        """Initialize a new game instance with players and validation.

        Args:
            bot: The Discord bot instance managing this game.
            message: The Discord message where the game will be displayed.
            *members: Variable number of Discord members participating.

        Raises:
            InvalidActionError: If player count is outside allowed range.
        """
        self.id = uuid4()  # Unique identifier for this game instance

        # Validate player count against game requirements
        if self.minimum_player_count() > len(members):
            error_message = "Not enough players."
            raise InvalidActionError(error_message)
        if self.maximum_player_count() < len(members):
            error_message = "Too many players."
            raise InvalidActionError(error_message)

        self.bot = bot
        self.players = [Player(member, i) for i, member in enumerate(members)]
        self.message = message
        self.is_terminated = False  # True when game has ended
        self.winner: Player | None = None  # Winner of the game (None for tie)
        self.lock = asyncio.Lock()  # Prevents race conditions in game logic

        # Game lifecycle management callbacks
        self._cleanup_callback: AsyncCallback | None = None
        self._completion_callback: AsyncCallback | None = None
        self._game_end_event = asyncio.Event()  # Signals when game ends

        # Turn timeout management system
        self._reset_timer_event = asyncio.Event()  # Signals timer reset
        # Current timeout task
        self._timeout_task: asyncio.Task[None] | None = None
        # Protects timeout operations
        self._timeout_lock: asyncio.Lock = asyncio.Lock()
        self.timer_display: str | None = None  # Human-readable timer text

    async def set_completion_callback(self, callback: AsyncCallback) -> None:
        """Set a callback to be executed when the game completes.

        Args:
            callback: Async function to call when game ends.
        """
        self._completion_callback = callback

    @classmethod
    def minimum_player_count(cls) -> int:
        """Get the minimum number of players required for this game type.

        Returns:
            Minimum player count (default: 2).
        """
        return 2

    @classmethod
    def maximum_player_count(cls) -> int:
        """Get the maximum number of players allowed for this game type.

        Returns:
            Maximum player count (default: 2).
        """
        return 2

    async def wait_for_completion(self) -> Player | None:
        """Wait for the game to complete and return the winner.

        Returns:
            The winning Player object, or None if the game ended in a tie.
        """
        await self._game_end_event.wait()
        return self.winner

    async def on_start(self) -> None:
        """Hook method called when the game starts.

        Subclasses should override this to implement game initialization logic
        such as setting up the initial display, adding reactions,
        or starting timers.
        """

    async def on_reaction(
        self,
        member_id: int,
        reaction: discord.PartialEmoji,
    ) -> None:
        """Hook method called when a player adds a reaction.

        Args:
            member_id: Discord ID of the member who added the reaction.
            reaction: The emoji reaction that was added.

        Subclasses should override this to handle player input via reactions.
        """

    async def on_timeout(self) -> None:
        """Hook method called when a turn timer expires.

        Subclasses should override this to handle timeout scenarios,
        typically by advancing the turn or ending the game.
        """

    async def set_winner(self, winner: Player | None) -> None:
        """End the game and set the winner, triggering cleanup processes.

        Args:
            winner: The winning player, or None if the game ended in a tie.

        Marks the game as terminated, executes cleanup callbacks, and signals
        any waiting processes that the game has ended.
        """
        self.is_terminated = True
        self.winner = winner

        # Execute registered cleanup and completion callbacks
        if self._cleanup_callback is not None:
            await self._cleanup_callback()
        if self._completion_callback is not None:
            await self._completion_callback()

        # Signal that the game has ended
        self._game_end_event.set()

    async def start_timer(self, duration_seconds: float) -> str:
        """Start a turn timer that will trigger timeout if not stopped.

        Args:
            duration_seconds: How long the timer should run before timing out.

        Returns:
            Human-readable string showing when the timer will expire.

        Raises:
            RuntimeError: If a timer is already running.
        """
        async with self._timeout_lock:
            if self._timeout_task and (
                self._timeout_task.done() or self._timeout_task.cancelled()
            ):
                error_message = "Timer was already started"
                raise RuntimeError(error_message)

            logger.info(
                "Start timer of %s seconds for %s",
                duration_seconds,
                self,
            )

            # Create the timeout task
            self._timeout_task = asyncio.create_task(
                self._timeout_worker(duration_seconds)
            )
            self.timer_display = in_seconds(duration_seconds)
            return self.timer_display

    async def stop_timer(self) -> None:
        """Stop the current timer and wait for it to complete cleanup.

        Cancels the active timeout task and resets the timer system for
        the next turn. Safe to call even if no timer is running.
        """
        async with self._timeout_lock:
            logger.info("Stop timer for %s", self)

            if (
                self._timeout_task
                and not self._timeout_task.done()
                and not self._timeout_task.cancelled()
            ):
                # Signal the timeout worker to stop
                self._reset_timer_event.set()
                await self._timeout_task

            # Reset timeout system for next use
            self._timeout_task = None
            self._reset_timer_event = asyncio.Event()
            logger.info("Timer stopped for %s", self)

    async def _timeout_worker(self, duration_seconds: float) -> None:
        """Background task that handles timer expiration and timeout logic.

        Args:
            duration_seconds: How long to wait before triggering timeout.

        Waits for the specified duration or until signaled to stop. If the
        timer expires naturally, acquires the game lock and calls on_timeout().
        """
        reset_event = self._reset_timer_event
        try:
            # Wait for either timeout duration or manual cancellation
            await asyncio.wait_for(
                reset_event.wait(), timeout=duration_seconds
            )
        except asyncio.TimeoutError:
            # Timer expired, trigger timeout handling if not manually cancelled
            if not reset_event.is_set():
                logger.info("Acquire lock for %s", self)
                async with self.lock:
                    logger.info("Timeout for %s", self)
                    # Create timeout task without waiting to avoid blocking
                    asyncio.create_task(self.on_timeout())  # noqa: RUF006
        logger.info("Terminate worker for %s ", self)

    def __repr__(self) -> str:
        """Get detailed string representation of the game for debugging.

        Returns:
            String containing class name, ID, message ID, termination status,
            and winner.
        """
        return (
            f"<{self.__class__.__qualname__} "
            f"id={str(self.id)!r} message={self.message.id!r} "
            f"terminate={self.is_terminated!r} winner={self.winner!r}"
            ">"
        )

    def __str__(self) -> str:
        """Get string representation of the game.

        Returns:
            Same as __repr__ to maintain consistency across string conversions.
        """
        return Game.__repr__(self)  # Enforce usage of Game class for __str__


class GameCog(commands.Cog):
    """Cog that manages all active games and handles game-related events.

    Provides functionality for starting duels between players, managing active
    game instances, handling reaction events, and cleaning up completed games.
    """

    def __init__(self, bot: Easterobot) -> None:
        """Initialize the game manager with an empty games registry.

        Args:
            bot: The Discord bot instance this cog belongs to.
        """
        self.bot = bot
        self._active_games: dict[
            int, Game
        ] = {}  # Maps message IDs to Game instances

    async def start_duel(
        self,
        channel: InteractionChannel,
        reference_message: discord.Message,
        player1: discord.Member,
        player2: discord.Member,
    ) -> Player | None:
        """Start a random game duel between two players.

        Args:
            channel: The Discord channel where the duel will take place.
            reference_message: Message to reference when starting the duel.
            player1: First player in the duel.
            player2: Second player in the duel.

        Returns:
            The winning Player object, or None if the game ended in a tie.

        Creates a countdown sequence, randomly selects a game type, and manages
        the complete game lifecycle from start to completion.
        """
        # Import game classes locally to avoid circular imports
        from easterobot.games.connect4 import Connect4  # noqa: PLC0415, I001, RUF100
        from easterobot.games.rock_paper_scissors import RockPaperScissors  # noqa: PLC0415, I001, RUF100
        from easterobot.games.skyjo import Skyjo  # noqa: PLC0415, I001, RUF100
        from easterobot.games.tic_tac_toe import TicTacToe  # noqa: PLC0415, I001, RUF100

        # Randomly select a game type for the duel
        game_class = RAND.choice(
            [Connect4, TicTacToe, RockPaperScissors, Skyjo]
        )

        # Send initial duel announcement with 5-minute countdown
        duel_message = await channel.send(
            f"{player1.mention} et {player2.mention} "
            f"vont s'affronter {in_seconds(300)} ...",
            reference=reference_message,
        )

        # Wait 4.5 minutes, then send 30-second warning
        await asyncio.sleep(270)
        await duel_message.reply(
            content=(
                f"{player1.mention} et {player2.mention} "
                "vont commencer le duel "
                f"{in_seconds(30)}"
            ),
            delete_after=30,
        )

        # Wait final 30 seconds, then start the actual game
        await asyncio.sleep(30)
        game: Game = game_class(self.bot, duel_message, player1, player2)
        await self.register_and_run_game(game)
        return await game.wait_for_completion()

    async def register_and_run_game(self, game: Game) -> None:
        """Register a game with the manager and start it running.

        Args:
            game: The Game instance to register and start.

        Adds the game to the active games registry, sets up cleanup callbacks,
        and initiates the game by calling its on_start() method.
        """
        message_id = game.message.id

        async def cleanup_game() -> None:
            """Clean up game resources when it ends."""
            # Remove from active games registry
            if message_id in self._active_games:
                del self._active_games[message_id]
            else:
                logger.warning("Missing game: %s", game)

            # Clear all reactions from the game message
            try:
                await game.message.clear_reactions()
            except discord.Forbidden:
                logger.warning(
                    "Missing permission for remove all reactions from %s",
                    message_id,
                )

        # Register the game and set up cleanup
        self._active_games[message_id] = game
        game._cleanup_callback = cleanup_game  # noqa: SLF001

        # Start the game
        await game.on_start()

    async def request_duel(  # noqa: C901, PLR0915
        self,
        ctx: Context,
        target_members: Iterable[discord.Member],
        bet_amount: int,
    ) -> discord.Message | None:
        """Send a duel request with accept/decline buttons.

        Args:
            ctx: The command context containing the requesting user.
            target_members: Discord members being challenged to the duel.
            bet_amount: Amount being wagered on the duel outcome.

        Returns:
            The original duel request message if accepted, None if declined.

        Creates an interactive message with accept/decline buttons, waits for
        responses from all challenged players, and handles various outcomes
        including timeouts, cancellations, and acceptances.
        """
        pending_players = list(target_members)
        response_received = asyncio.Event()
        accepted_players: list[discord.Member] = [ctx.user]
        cancelled_by: discord.Member | None = None

        # Create interactive view with accept/decline buttons
        button_view = discord.ui.View()
        accept_button: Button = discord.ui.Button(
            label="Accepter", style=discord.ButtonStyle.green, emoji="⚔️"
        )
        decline_button: Button = discord.ui.Button(
            label="Refuser", style=discord.ButtonStyle.red, emoji="🛡️"
        )

        async def handle_accept(interaction: Interaction) -> Any:
            """Handle accept button clicks from challenged players."""
            nonlocal cancelled_by
            if TYPE_CHECKING:
                assert isinstance(interaction.user, discord.Member)

            # Only process if game hasn't been decided
            # and user is a valid target
            if not response_received.is_set() and any(
                interaction.user.id == member.id for member in pending_players
            ):
                await interaction.response.send_message(
                    "Vous avez accepté le duel !",
                    ephemeral=True,
                )

                # Move player from pending to accepted
                accepted_players.append(interaction.user)
                pending_players.remove(interaction.user)

                # If all players accepted, proceed with duel
                if not pending_players:
                    response_received.set()
            else:
                await interaction.response.defer()

        async def handle_decline(interaction: Interaction) -> Any:
            """Handle decline button clicks from any involved player."""
            nonlocal cancelled_by
            if TYPE_CHECKING:
                assert isinstance(interaction.user, discord.Member)

            await interaction.response.defer()

            # Cancel duel if any participant declines
            if not response_received.is_set():
                if interaction.user in pending_players:
                    pending_players.remove(interaction.user)
                    cancelled_by = interaction.user
                    response_received.set()
                elif interaction.user in accepted_players:
                    accepted_players.remove(interaction.user)
                    cancelled_by = interaction.user
                    response_received.set()

        # Assign button callbacks and add to view
        accept_button.callback = handle_accept  # type: ignore[method-assign,assignment]
        decline_button.callback = handle_decline  # type: ignore[method-assign,assignment]
        button_view.add_item(accept_button)
        button_view.add_item(decline_button)

        # Send initial duel request message
        request_timeout = 300
        target_mentions = " ".join(
            member.mention for member in pending_players
        )
        response_result = await ctx.response.send_message(
            f"{target_mentions}, "
            f"{ctx.user.mention} vous demande en duel pour "
            f"`{bet_amount}` œufs ⚔️"
            f"\nVous devez repondre {in_seconds(request_timeout)} !",
            view=button_view,
        )

        request_message = response_result.resource
        if not isinstance(request_message, discord.Message):
            error_message = f"Invalid kind of message: {request_message!r}"
            raise TypeError(error_message)

        # Wait for responses or timeout
        try:
            await asyncio.wait_for(
                response_received.wait(), timeout=request_timeout
            )
        except asyncio.TimeoutError:
            # Handle timeout - no response from challenged players
            all_mentions = " ".join(
                member.mention for member in accepted_players
            )
            await request_message.edit(
                content=(
                    f"{all_mentions}, "
                    f"{' '.join(member.mention for member in pending_players)}"
                    + agree(" n'a pas", " n'ont pas", len(pending_players) - 1)
                    + " accepté le duel 🛡️"
                    + "\n-# Ce message disparaîtra {in_seconds(30)}"
                ),
                delete_after=30,
                view=None,
            )
            return None

        # Handle cancellation by any player
        if cancelled_by:
            all_mentions = " ".join(
                member.mention
                for group in (accepted_players, pending_players)
                for member in group
            )
            action_word = "refusé" if cancelled_by == ctx.user else "annulé"
            await request_message.edit(
                content=(
                    f"{all_mentions}, {cancelled_by.mention} "
                    f"a {action_word} le duel 🛡️"
                    f"\n-# Ce message disparaîtra {in_seconds(30)}"
                ),
                delete_after=30,
                view=None,
            )
            return None

        # Handle successful acceptance by all players
        if not isinstance(response_result.resource, discord.Message):
            error_message = (
                f"Invalid kind of message: {response_result.resource!r}"
            )
            raise TypeError(error_message)

        other_players_mentions = " ".join(
            member.mention for member in accepted_players if member != ctx.user
        )
        await response_result.resource.reply(
            f"{ctx.user.mention}, {other_players_mentions} "
            + agree("a", "ont", len(accepted_players) - 1)
            + " accepté le duel ⚔️"
            + f"\n-# Début du duel {in_seconds(30)}",
            delete_after=30,
        )

        # Wait 30 seconds before returning the message for game start
        await asyncio.sleep(30)
        return await ctx.channel.fetch_message(response_result.resource.id)

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        """Handle reaction additions to active game messages.

        Args:
            payload: Raw reaction event data from Discord.

        Filters out bot reactions and forwards valid reactions to the
        game instance. Also removes the reaction to keep the message clean.
        """
        # Ignore reactions without message author info
        if payload.message_author_id is None:
            return

        # Ignore bot's own reactions
        if self.bot.user and payload.user_id == self.bot.user.id:
            return

        # Process reactions on active game messages
        if payload.message_id in self._active_games:
            game = self._active_games[payload.message_id]

            # Concurrently remove the reaction and notify the game
            await asyncio.gather(
                self._remove_reaction_silently(
                    payload.channel_id,
                    payload.message_id,
                    payload.emoji,
                    payload.user_id,
                ),
                game.on_reaction(payload.user_id, payload.emoji),
            )

    async def _remove_reaction_silently(
        self,
        channel_id: int,
        message_id: int,
        emoji: discord.PartialEmoji,
        user_id: int,
    ) -> None:
        """Remove a reaction from a message without raising exceptions.

        Args:
            channel_id: ID of the channel containing the message.
            message_id: ID of the message to remove reaction from.
            emoji: The emoji reaction to remove.
            user_id: ID of the user whose reaction should be removed.

        Uses the Discord HTTP API directly for better performance and handles
        permission errors gracefully by logging warnings instead of crashing.
        """
        try:
            reaction_string = convert_emoji_reaction(emoji)
            await self.bot._connection.http.remove_reaction(  # noqa: SLF001
                channel_id,
                message_id,
                reaction_string,
                user_id,
            )
        except discord.Forbidden:
            logger.warning(
                "Missing permission for remove reaction from %s",
                message_id,
            )
