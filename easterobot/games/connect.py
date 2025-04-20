"""Connect4 and Connect3."""

import datetime
from functools import partial
from typing import Optional

import discord
from discord.utils import format_dt
from typing_extensions import override

from easterobot.games.game import Game, Player

EMOJIS_MAPPER = {
    "1️⃣": 0,
    "2️⃣": 1,
    "3️⃣": 2,
    "4️⃣": 3,
    "5️⃣": 4,
    "6️⃣": 5,
    "7️⃣": 6,
    "8️⃣": 7,
    "9️⃣": 8,
    "🔟": 9,
}
EMOJIS = tuple(EMOJIS_MAPPER)


class Connect(Game):
    def __init__(  # noqa: PLR0913
        self,
        player1: discord.Member,
        player2: discord.Member,
        message: discord.Message,
        rows: int,
        cols: int,
        win_count: int,
    ) -> None:
        """Instantiate Connect4."""
        self.grid: list[list[Optional[Player]]] = [
            [None] * rows for _ in range(cols)
        ]
        self.timeout = False
        self.player1 = Player(player1, 1)
        self.player2 = Player(player2, 2)
        self.rows = rows
        self.cols = cols
        self.win_count = win_count
        self.turn = 0
        super().__init__(message)

    async def on_start(self) -> None:
        """Run."""
        await self.update()
        await self.start_timer(61)
        for emoji in EMOJIS[: self.cols]:
            await self.message.add_reaction(emoji)

    async def update(self) -> None:
        """Update the text."""
        footer = ""
        label = ""
        if not self.terminate:
            label = self.piece(self.current)
            label += f" Joueur actuel : {self.current.member.mention}\n\n"
            player: Optional[Player] = self.current
        elif self.winner:
            forfait = "par forfait " if self.timeout else ""
            footer = f"\n## Gagnant {forfait}{self.winner.mention} 🎉"
            player = self.current
        else:
            footer = (
                f"\n## Égalité entre {self.player1.member.mention} "
                f"et {self.player2.member.mention} 🤝"
            )
            player = None
        content = label
        content += "│".join(EMOJIS[: self.cols])
        content += "\n"
        content += "\n".join(
            "│".join(self.piece(self.grid[y][x]) for y in range(self.cols))
            for x in reversed(range(self.rows))
        )
        content += footer
        now = datetime.datetime.now() + datetime.timedelta(seconds=61)  # noqa: DTZ005
        if not self.terminate:
            content += f"\n\nFin du tour {format_dt(now, style='R')}"
        embed = discord.Embed(description=content, color=self.color(player))
        embed.set_author(
            name="Partie terminée" if self.terminate else "Partie en cours",
            icon_url=(
                player.member.display_avatar.url
                if player
                else self.bot.app_emojis["end"].url
            ),
        )
        self.message = await self.message.edit(
            embed=embed,
            content="",
            view=None,
        )

    async def on_reaction(
        self,
        member_id: int,
        reaction: discord.PartialEmoji,
    ) -> None:
        """Add a reaction to the message."""
        if (
            reaction.name not in EMOJIS[: self.cols]
            or member_id != self.current.member.id
        ):
            return
        await self.place(EMOJIS_MAPPER[reaction.name], self.current)

    @property
    def current(self) -> Player:
        """Get the current member playing."""
        return [self.player1, self.player2][self.turn % 2]

    def piece(self, member: Optional[Player]) -> str:
        """Get the current member playing."""
        if member is None:
            return "⚪"
        if member == self.player1:
            return "🔴"
        if member == self.player2:
            return "🟡"
        error_message = f"Invalid member: {member!r}"
        raise ValueError(error_message)

    def color(self, player: Optional[Player]) -> Optional[discord.Colour]:
        """Get the current player playing."""
        if player is None:
            return discord.Colour.from_str("#d4d5d6")  # Grey
        if player == self.player1:
            return discord.Colour.from_str("#ca2a3e")  # Red
        if player == self.player2:
            return discord.Colour.from_str("#e9bb51")  # Yellow
        error_message = f"Invalid player: {player!r}"
        raise ValueError(error_message)

    async def place(
        self,
        col: int,
        player: Player,
    ) -> None:
        """Place a jetton."""
        async with self.lock:
            if self.terminate:
                return
            winner = None
            for row in range(self.rows):
                if self.grid[col][row] is None:
                    await self.stop_timer()
                    self.grid[col][row] = player
                    if self._is_winner(col, row, player):
                        winner = player
                    break
            else:
                return  # Can't be placed
            if winner:
                await self.set_winner(player.member)
            elif all(  # Draw case
                self.grid[col][-1] is not None for col in range(self.cols)
            ):
                await self.set_winner(None)
            else:
                self.turn += 1
                await self.start_timer(61)
            await self.update()

    @override
    async def on_timeout(self) -> None:
        self.turn += 1
        self.timeout = True
        await self.set_winner(self.current.member)
        await self.update()

    def _is_winner(self, col: int, row: int, player: Player) -> bool:
        directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
        for dx, dy in directions:
            if (
                self._count_consecutive(col, row, dx, dy, player)
                + self._count_consecutive(col, row, -dx, -dy, player)
                - 1
            ) >= self.win_count:
                return True
        return False

    def _count_consecutive(
        self, col: int, row: int, dx: int, dy: int, player: Player
    ) -> int:
        count = 0
        c, r = col, row
        while (
            0 <= c < self.cols
            and 0 <= r < self.rows
            and self.grid[c][r] == player
        ):
            count += 1
            c += dx
            r += dy
        return count


Connect4 = partial(Connect, rows=6, cols=7, win_count=4)
