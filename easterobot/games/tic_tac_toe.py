"""TicTacToe."""

import asyncio
from typing import Optional

import discord
from typing_extensions import override

from easterobot.bot import Easterobot
from easterobot.games.game import Game, Player
from easterobot.utils import in_seconds

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
}
EMOJIS = tuple(EMOJIS_MAPPER)


class TicTacToe(Game):
    def __init__(
        self,
        bot: Easterobot,
        message: discord.Message,
        *members: discord.Member,
    ) -> None:
        """Initialize grid."""
        self.grid: list[Optional[Player]] = [None] * 9
        self.timeout = False
        self.turn = 0
        super().__init__(bot, message, *members)

    @override
    async def on_start(self) -> None:
        """Run."""
        await self.update()
        await self.start_timer(31)
        for emoji in EMOJIS:
            await asyncio.sleep(0.1)
            await self.message.add_reaction(emoji)

    async def update(self) -> None:
        """Update the message."""
        label = ""
        footer = ""
        if not self.terminate:
            label = "⭕" if self.turn % 2 else "❌"
            label += f" Joueur actuel : {self.current.member.mention}\n\n"
            user: Optional[Player] = self.current
        elif self.winner:
            forfait = "par forfait " if self.timeout else ""
            footer = f"\n## Gagnant {forfait}{self.winner.member.mention} 🎉"
            user = self.current
        else:
            footer = (
                "\n## Égalité entre "
                f"{self.players[0].member.mention} "
                f"et {self.players[1].member.mention} 🤝"
            )
            user = None

        content = label
        lines = []
        for row in range(3):
            pieces = []
            for col in range(3):
                index = row * 3 + col
                player = self.grid[index]
                if player == self.players[0]:
                    piece = "❌"
                elif player == self.players[1]:
                    piece = "⭕"
                else:
                    piece = EMOJIS[index]
                pieces.append(piece)
            lines.append("│".join(pieces))
        content += "\n".join(lines)
        content += footer

        if not self.terminate:
            content += f"\n\nFin du tour {in_seconds(31)}"

        embed = discord.Embed(description=content, color=self.color(user))
        embed.set_author(
            name="Partie terminée" if self.terminate else "Partie en cours",
            icon_url=(
                user.member.display_avatar.url
                if user
                else self.bot.app_emojis["end"].url
            ),
        )
        self.message = await self.message.edit(
            embed=embed,
            content=(
                f"-# {self.players[0].member.mention} "
                f"{self.players[1].member.mention}"
            ),
            view=None,
        )

    @override
    async def on_reaction(
        self, member_id: int, reaction: discord.PartialEmoji
    ) -> None:
        if reaction.name not in EMOJIS or member_id != self.current.member.id:
            return
        index = EMOJIS_MAPPER[reaction.name]
        await self.place(index, self.current)

    @property
    def current(self) -> Player:
        """Get current member."""
        return [self.players[0], self.players[1]][self.turn % 2]

    def color(self, player: Optional[Player]) -> Optional[discord.Colour]:
        """Color of the embed."""
        if player is None:
            return discord.Colour.from_str("#d4d5d6")
        if player == self.players[0]:
            return discord.Colour.from_str("#F17720")
        if player == self.players[1]:
            return discord.Colour.from_str("#0474BA")
        error_message = f"Invalid player: {player!r}"
        raise ValueError(error_message)

    async def place(self, index: int, player: Player) -> None:
        """Place a piece."""
        if self.terminate or self.grid[index] is not None:
            return
        async with self.lock:
            await self.stop_timer()
            self.grid[index] = player

            if self._is_winner(player):
                await self.set_winner(player)
            elif all(cell is not None for cell in self.grid):
                await self.set_winner(None)
            else:
                self.turn += 1
                await self.start_timer(31)
            await self.update()

    @override
    async def on_timeout(self) -> None:
        self.turn += 1
        self.timeout = True
        await self.set_winner(self.current)
        await self.update()

    def _is_winner(self, player: Player) -> bool:
        wins = [
            [0, 1, 2],
            [3, 4, 5],
            [6, 7, 8],  # rows
            [0, 3, 6],
            [1, 4, 7],
            [2, 5, 8],  # cols
            [0, 4, 8],
            [2, 4, 6],  # diagonals
        ]
        return any(
            all(self.grid[i] == player for i in combo) for combo in wins
        )
