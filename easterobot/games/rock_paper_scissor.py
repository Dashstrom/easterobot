"""TicTacToe."""

import asyncio
from functools import partial
from typing import Optional

import discord
from typing_extensions import override

from easterobot.bot import Easterobot
from easterobot.commands.base import Interaction
from easterobot.games.game import Button, Game

ROCK = b"\xf0\x9f\xaa\xa8".decode("utf-8")
PAPER = b"\xf0\x9f\x93\x84".decode("utf-8")
SCISSORS = b"\xe2\x9c\x82\xef\xb8\x8f".decode("utf-8")
EMOJIS = [PAPER, ROCK, SCISSORS]


class RockPaperScissor(Game):
    view: discord.ui.View

    def __init__(
        self,
        bot: Easterobot,
        message: discord.Message,
        *members: discord.Member,
        win_count: int = 3,
        max_turn: int = 10,
    ) -> None:
        """Initialize grid."""
        self.timeout = False
        self.max_turn = max_turn
        self.win_count = win_count
        self.play1: Optional[str] = None
        self.play2: Optional[str] = None
        self.history: list[tuple[str, str]] = []
        super().__init__(bot, message, *members)

    @override
    async def on_start(self) -> None:
        """Run."""
        embed = discord.Embed(color=0xF2BC32)
        embed.set_author(
            name="Partie en cours", icon_url=self.bot.app_emojis["wait"].url
        )
        self.view = discord.ui.View(timeout=1800)
        rock_btn: Button = discord.ui.Button(
            style=discord.ButtonStyle.gray,
            emoji=ROCK,
        )
        paper_btn: Button = discord.ui.Button(
            style=discord.ButtonStyle.gray,
            emoji=PAPER,
        )
        scissor_btn: Button = discord.ui.Button(
            style=discord.ButtonStyle.gray,
            emoji=SCISSORS,
        )

        async def action_callback(
            interaction: Interaction,
            label: str,
        ) -> None:
            update = False
            user = interaction.user

            # Player 1 click on button
            if user == self.players[0].member and self.play1 is None:
                self.play1 = label
                update = True

            # Player 2 click on button
            elif user == self.players[1].member and self.play2 is None:
                self.play2 = label
                update = True

            # One button has been pressed
            if update:
                await asyncio.gather(
                    self.stop_timer(),
                    interaction.response.defer(),
                )
                await self.update()
            else:
                await interaction.response.send_message(
                    "Vous ne pouvez pas intéragir dans cette partie !",
                    ephemeral=True,
                    delete_after=5,
                )

        rock_btn.callback = partial(action_callback, label=ROCK)  # type: ignore[method-assign]
        paper_btn.callback = partial(action_callback, label=PAPER)  # type: ignore[method-assign]
        scissor_btn.callback = partial(action_callback, label=SCISSORS)  # type: ignore[method-assign]
        self.view.add_item(rock_btn)
        self.view.add_item(paper_btn)
        self.view.add_item(scissor_btn)
        await self.update()

    async def update(self) -> None:  # noqa: C901, PLR0912, PLR0915
        """Update the current display."""
        embed = discord.Embed(color=0xF2BC32)
        # Both player have played
        header = "Partie en cours"
        if self.play1 is None and self.play2 is None:
            icon_url = self.bot.app_emojis["wait"].url
            info = (
                f"En attente de {self.players[0].member.mention} "
                f"et {self.players[1].member.mention} ..."
            )
        elif self.play1 is None:
            icon_url = self.players[0].member.display_avatar.url
            info = f"En attente de {self.players[0].member.mention} ..."
        elif self.play2 is None:
            icon_url = self.players[1].member.display_avatar.url
            info = f"En attente de {self.players[1].member.mention} ..."
        else:
            # Play and fight
            self.history.append((self.play1, self.play2))
            self.play1 = None
            self.play2 = None
            icon_url = self.bot.app_emojis["wait"].url
            info = (
                f"En attente de {self.players[0].member.mention} "
                f"et {self.players[1].member.mention} ..."
            )
        pt1 = 0
        pt2 = 0
        morsels = []
        for play1, play2 in self.history:
            i1 = EMOJIS.index(play1)
            i2 = EMOJIS.index(play2)
            if i1 == (i2 - 1) % 3:
                pt1 += 1
                text = self.players[0].member.mention
            elif i1 == (i2 + 1) % 3:
                pt2 += 1
                text = self.players[1].member.mention
            else:
                text = "**égalité**"
            morsels.append(
                f"### {play1} {self.bot.app_emojis['versus']} {play2} "
                f"{self.bot.app_emojis['arrow']} {text}"
            )
        embed.description = "\n".join(morsels)
        if (
            len(self.history) >= self.max_turn
            or pt1 >= self.win_count
            or pt2 >= self.win_count
            or self.timeout
        ):
            header = "Partie terminée"
            embed.description += "\n\n"
            if self.timeout:
                final_winner = self.winner
            elif pt1 < pt2:
                final_winner = self.players[1]
            elif pt2 < pt1:
                final_winner = self.players[0]
            else:
                final_winner = None
            if final_winner:
                forfait = "par forfait " if self.timeout else ""
                embed.description += (
                    f"## Gagnant {forfait}{final_winner.member.mention} 🎉"
                )
                icon_url = final_winner.member.display_avatar.url
            else:
                embed.description += (
                    f"## Égalité entre {self.players[0].member.mention} "
                    f"et {self.players[1].member.mention} 🤝"
                )
                icon_url = self.bot.app_emojis["end"].url
            self.view.stop()
            self.view.clear_items()
            if not self.timeout:
                await self.set_winner(final_winner)
        else:
            dt = await self.start_timer(31)
            embed.description += f"\n\n{info}\n\nFin du tour {dt}"
        embed.set_author(name=header, icon_url=icon_url)
        await self.message.edit(
            embed=embed,
            view=self.view,
            content=(
                f"-# {self.players[0].member.mention} "
                f"{self.players[1].member.mention}"
            ),
        )

    def compute_winner(
        self, play1: str, play2: str
    ) -> Optional[discord.Member]:
        """Get the winner."""
        i1 = EMOJIS.index(play1)
        i2 = EMOJIS.index(play2)
        if i1 == (i2 + 1) % 3:
            return self.players[0].member
        if i1 == (i2 - 1) % 3:
            return self.players[1].member
        return None  # Draw

    def color(
        self, member: Optional[discord.Member]
    ) -> Optional[discord.Colour]:
        """Color of the embed."""
        if member is None:
            return discord.Colour.from_str("#d4d5d6")
        if member == self.players[0]:
            return discord.Colour.from_str("#ca2a3e")
        if member == self.players[1]:
            return discord.Colour.from_str("#5865F2")
        error_message = f"Invalid member: {member!r}"
        raise ValueError(error_message)

    @override
    async def on_timeout(self) -> None:
        self.timeout = True
        if self.play1 is None:
            await self.set_winner(self.players[1])
        if self.play2 is None:
            await self.set_winner(self.players[0])
        await self.update()
