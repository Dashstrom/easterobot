"""Base class for game."""

import asyncio
import contextlib
import datetime
import logging
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any, Callable, Optional
from uuid import uuid4

import discord
from discord.ext import commands
from discord.message import convert_emoji_reaction
from discord.utils import format_dt

from easterobot.bot import Easterobot
from easterobot.commands.base import Context, Interaction, InteractionChannel
from easterobot.config import RAND

logger = logging.getLogger(__name__)
AsyncCallback = Callable[[], Coroutine[Any, Any, None]]
Button = discord.ui.Button[discord.ui.View]


class GameError(Exception):
    pass


class InvalidActionError(GameError):
    pass


class InvalidPlayerError(GameError):
    @staticmethod
    def from_player(member: discord.Member) -> "InvalidPlayerError":
        """Create error from a member."""
        return InvalidPlayerError(
            f"Player {member!r} is not included in the game"
        )


@dataclass
class Player:
    member: discord.Member
    number: int


class Game:
    bot: Easterobot

    def __init__(self, message: discord.Message) -> None:
        """Instantiate Game."""
        self.id = uuid4()
        self.message = message
        self.terminate = False
        self.winner: Optional[discord.Member] = None
        self.lock = asyncio.Lock()
        self._cleanup: Optional[AsyncCallback] = None
        self._completion: Optional[AsyncCallback] = None
        self._end_event = asyncio.Event()

        # timeout
        self._reset_countdown_event = asyncio.Event()
        self._timeout_task: Optional[asyncio.Task[None]] = None
        self._timeout_lock: asyncio.Lock = asyncio.Lock()

    async def set_completion(self, callback: AsyncCallback) -> None:
        """Get the current state for a player."""
        self._completion = callback

    async def wait_winner(self) -> Optional[discord.Member]:
        """Wait the end of the game."""
        await self._end_event.wait()
        return self.winner

    async def on_start(self) -> None:
        """Get the current state for a player."""

    async def on_reaction(
        self,
        member_id: int,
        reaction: discord.PartialEmoji,
    ) -> None:
        """Add a reaction to the message."""

    async def on_timeout(self) -> None:
        """Can when game timeout."""

    async def set_winner(self, winner: Optional[discord.Member]) -> None:
        """Remove the game from the manager."""
        await self.stop_timer()
        self.terminate = True
        self.winner = winner
        if self._cleanup is not None:
            await self._cleanup()
        if self._completion is not None:
            await self._completion()
        self._end_event.set()

    async def start_timer(self, seconds: float) -> str:
        """Start the timer for turn."""
        async with self._timeout_lock:
            now = datetime.datetime.now() + datetime.timedelta(seconds=seconds)  # noqa: DTZ005
            dt = format_dt(now, style="R")
            self._timeout_task = asyncio.create_task(
                self._timeout_worker(seconds)
            )
            return dt

    async def stop_timer(self) -> None:
        """Stop the timer and wait it end."""
        async with self._timeout_lock:
            if (
                self._timeout_task
                and not self._timeout_task.done()
                and not self._timeout_task.cancelled()
            ):
                self._reset_countdown_event.set()
                await self._timeout_task
                self._timeout_task = None
                self._reset_countdown_event = asyncio.Event()

    async def _timeout_worker(self, seconds: float) -> None:
        """Timeout action."""
        event = self._reset_countdown_event
        try:
            await asyncio.wait_for(event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            if not event.is_set():
                async with self.lock:
                    await self.on_timeout()

    def __repr__(self) -> str:
        """Get game representation."""
        return (
            f"<{self.__class__.__qualname__} "
            f"id={self.id!r} message={self.message!r} "
            f"terminate={self.terminate!r} winner={self.winner!r}"
            ">"
        )

    def __str__(self) -> str:
        """Get game representation."""
        return Game.__repr__(self)  # Enforce usage of Game class for __str__


class GameCog(commands.Cog):
    def __init__(self, bot: Easterobot) -> None:
        """Manage all games."""
        self.bot = bot
        self._games: dict[int, Game] = {}

    async def dual(
        self,
        channel: InteractionChannel,
        reference: discord.Message,
        user1: discord.Member,
        user2: discord.Member,
    ) -> Optional[discord.Member]:
        """Start a dual between two players."""
        from easterobot.games.connect import Connect4
        from easterobot.games.rock_paper_scissor import RockPaperScissor
        from easterobot.games.tic_tac_toe import TicTacToe

        cls = RAND.choice([Connect4, TicTacToe, RockPaperScissor])
        now = datetime.datetime.now() + datetime.timedelta(seconds=63)  # noqa: DTZ005
        dt = format_dt(now, style="R")
        msg = await channel.send(
            f"{user1.mention} et {user2.mention} vont s'affronter {dt} ...",
            reference=reference,
        )
        await asyncio.sleep(63)
        game: Game = cls(user1, user2, msg)  # type: ignore[operator]
        await self.run(game)
        return await game.wait_winner()

    async def run(self, game: Game) -> None:
        """Attach the game to the manager."""
        message_id = game.message.id

        async def _cleanup() -> None:
            if message_id in self._games:
                del self._games[message_id]
            else:
                logger.warning("Missing game: %s", game)
            try:
                await game.message.clear_reactions()
            except discord.Forbidden:
                logger.warning(
                    "Missing permission for remove all reactions from %s",
                    message_id,
                )

        self._games[message_id] = game
        game._cleanup = _cleanup  # noqa: SLF001
        game.bot = self.bot
        await game.on_start()

    async def ask_dual(
        self,
        ctx: Context,
        member: discord.Member,
        bet: int,
    ) -> Optional[discord.Message]:
        """Send basic message for initialization."""
        future: asyncio.Future[bool] = asyncio.Future()
        accept = False

        view = discord.ui.View()
        yes_btn: Button = discord.ui.Button(
            label="Accepter", style=discord.ButtonStyle.green, emoji="⚔️"
        )
        no_btn: Button = discord.ui.Button(
            label="Refuser", style=discord.ButtonStyle.red, emoji="🛡️"
        )

        async def yes(interaction: Interaction) -> Any:
            if interaction.user.id == member.id:
                future.set_result(True)
            await interaction.response.defer()

        async def no(interaction: Interaction) -> Any:
            if interaction.user.id == member.id:
                future.set_result(False)
            await interaction.response.defer()

        yes_btn.callback = yes  # type: ignore[method-assign,assignment]
        no_btn.callback = no  # type: ignore[method-assign,assignment]
        view.add_item(yes_btn)
        view.add_item(no_btn)
        now = datetime.datetime.now() + datetime.timedelta(seconds=600)  # noqa: DTZ005
        dt = format_dt(now, style="R")
        result = await ctx.response.send_message(
            f"{member.mention}, {ctx.user.mention} "
            f"vous demande en duel pour `{bet}` œufs ⚔️"
            f"\nVous devez repondre {dt} !",
            view=view,
        )
        message = result.resource
        if not isinstance(message, discord.Message):
            error_message = f"Invalid kind of message: {message!r}"
            raise TypeError(error_message)
        with contextlib.suppress(asyncio.TimeoutError):
            accept = await asyncio.wait_for(future, timeout=600)
        if not accept:
            await message.edit(
                content=(
                    f"{ctx.user.mention}, {member.mention} a refusé le duel 🛡️"
                ),
                view=None,
            )
            return None
        if not isinstance(result.resource, discord.Message):
            error_message = f"Invalid kind of message: {result.resource!r}"
            raise TypeError(error_message)
        return result.resource

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        """Handle reaction."""
        if payload.message_author_id is None:
            return
        if self.bot.user and payload.user_id == self.bot.user.id:
            return
        if payload.message_id in self._games:
            # Use connection for faster remove
            game = self._games[payload.message_id]
            await asyncio.gather(
                self.silent_reaction_remove(
                    payload.channel_id,
                    payload.message_id,
                    payload.emoji,
                    payload.user_id
                ),
                game.on_reaction(payload.user_id, payload.emoji),
            )

    async def silent_reaction_remove(
        self,
        channel_id: int,
        message_id: int,
        emoji: discord.PartialEmoji,
        user_id: int,
    ) -> None:
        """Handle reaction."""
        reaction = convert_emoji_reaction(emoji)
        try:
            await self.bot._connection.http.remove_reaction(  # noqa: SLF001
                channel_id,
                message_id,
                reaction,
                user_id,
            )
        except discord.Forbidden:
            logger.warning(
                "Missing permission for remove %s from %s",
                reaction,
                message_id,
            )
