"""Base class for game."""

import asyncio
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
from easterobot.commands.base import Context, Interaction

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
        self._reset_countdown_event = asyncio.Event()
        self._timeout_task: Optional[asyncio.Task[None]] = None

    async def set_completion(self, callback: AsyncCallback) -> None:
        """Get the current state for a player."""
        self._completion = callback

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
        self.terminate = True
        self.winner = winner
        if self._cleanup is not None:
            await self._cleanup()
        if self._completion is not None:
            await self._completion()

    def start_timer(self, seconds: float) -> str:
        """Start the timer for turn."""
        now = datetime.datetime.now() + datetime.timedelta(seconds=seconds)  # noqa: DTZ005
        dt = format_dt(now, style="R")
        self._timeout_task = asyncio.create_task(self._timeout_worker(seconds))
        return dt

    async def stop_timer(self) -> None:
        """Stop the timer and wait it end."""
        if self._timeout_task:
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

    async def run(self, game: Game) -> None:
        """Attach the game to the manager."""
        message_id = game.message.id

        async def _cleanup() -> None:
            if message_id in self._games:
                del self._games[message_id]
            else:
                logger.warning("Missing game: %s", game)
            await game.message.clear_reactions()

        self._games[message_id] = game
        game._cleanup = _cleanup  # noqa: SLF001
        game.bot = self.bot
        await game.on_start()

    async def ask_dual(
        self,
        ctx: Context,
        member: discord.Member,
    ) -> Optional[discord.Message]:
        """Send basic message for initialization."""
        future: asyncio.Future[bool] = asyncio.Future()
        accept = False

        view = discord.ui.View()
        yes_btn: Button = discord.ui.Button(
            label="Accepter",
            style=discord.ButtonStyle.green,
            emoji="✅"
        )
        no_btn: Button = discord.ui.Button(
            label="Refuser",
            style=discord.ButtonStyle.gray,
            emoji="❌"
        )
        async def yes(interaction: Interaction) -> Any:
            if interaction.user.id == member.id:
                future.set_result(True)
        async def no(interaction: Interaction) -> Any:
            if interaction.user.id == member.id:
                future.set_result(False)

        yes_btn.callback = yes  # type: ignore[method-assign,assignment]
        no_btn.callback = no  # type: ignore[method-assign,assignment]
        view.add_item(yes_btn)
        view.add_item(no_btn)
        now = datetime.datetime.now() + datetime.timedelta(seconds=60)  # noqa: DTZ005
        dt = format_dt(now, style="R")
        result = await ctx.response.send_message(
            f"{member.mention}, {ctx.user.mention} vous demande en duel ⚔️"
            f"Vous avez {dt} pour répondre !",
            view=view
        )
        accept = await asyncio.wait_for(future, timeout=60)
        if not accept:
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
            emoji = convert_emoji_reaction(payload.emoji)
            game = self._games[payload.message_id]
            await asyncio.gather(
                self.bot._connection.http.remove_reaction(  # noqa: SLF001
                    payload.channel_id,
                    payload.message_id,
                    emoji,
                    payload.user_id,
                ),
                game.on_reaction(payload.user_id, payload.emoji),
            )
