"""TicTacToe."""

from functools import partial
from typing import Optional

import discord
from typing_extensions import override

from easterobot.commands.base import Interaction
from easterobot.games.game import Button, Game

ROCK = b"\xf0\x9f\xaa\xa8".decode("utf-8")
PAPER = b"\xf0\x9f\x93\x84".decode("utf-8")
SCISSORS = b"\xe2\x9c\x82\xef\xb8\x8f".decode("utf-8")
EMOJIS = [PAPER, ROCK, SCISSORS]


class RockPaperScissor(Game):
    def __init__(
        self,
        player1: discord.Member,
        player2: discord.Member,
        message: discord.Message,
        win_count: int = 3,
        max_turn: int = 10,
    ) -> None:
        """Initialize grid."""
        self.timeout = False
        self.max_turn = max_turn
        self.win_count = win_count
        self.player1 = player1
        self.player2 = player2
        self.play1: Optional[str] = None
        self.play2: Optional[str] = None
        self.history: list[tuple[str, str]] = []
        super().__init__(message)

    @override
    async def on_start(self) -> None:  # noqa: C901, PLR0915
        """Run."""
        embed = discord.Embed(color=0xF2BC32)
        embed.set_author(
            name="Partie en cours", icon_url=self.bot.app_emojis["wait"].url
        )
        view = discord.ui.View()
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

        async def action_callback(  # noqa: PLR0912, PLR0915
            interaction: Interaction,
            label: str,
        ) -> None:
            update = False

            # Player 1 click on button
            if interaction.user == self.player1 and self.play1 is None:
                self.play1 = label
                update = True

            # Player 2 click on button
            elif interaction.user == self.player2 and self.play2 is None:
                self.play2 = label
                update = True

            # One button has been pressed
            if update:
                # Both player have played
                header = "Partie en cours"
                if self.play1 is None:
                    icon_url = self.player1.display_avatar.url
                    info = f"En attente de {self.player1.mention} ..."
                elif self.play2 is None:
                    icon_url = self.player2.display_avatar.url
                    info = f"En attente de {self.player2.mention} ..."
                else:
                    # Play and fight
                    self.history.append((self.play1, self.play2))
                    self.play1 = None
                    self.play2 = None
                    icon_url = interaction.client.app_emojis["wait"].url
                    info = (
                        f"En attente de {self.player1.mention} "
                        f"et {self.player2.mention} ..."
                    )
                pt1 = 0
                pt2 = 0
                morsels = []
                for play1, play2 in self.history:
                    i1 = EMOJIS.index(play1)
                    i2 = EMOJIS.index(play2)
                    if i1 == (i2 + 1) % 3:
                        pt1 += 1
                        text = self.player1.mention
                    elif i1 == (i2 - 1) % 3:
                        pt2 += 1
                        text = self.player2.mention
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
                ):
                    header = "Partie terminée"
                    embed.description += "\n\n"
                    if pt1 < pt2:
                        final_winner = self.player2
                        embed.description += (
                            f"## Gagnant {final_winner.mention} 🎉"
                        )
                        icon_url = final_winner.display_avatar.url
                    elif pt2 < pt1:
                        final_winner = self.player1
                        embed.description += (
                            f"## Gagnant {final_winner.mention} 🎉"
                        )
                        icon_url = final_winner.display_avatar.url
                    else:
                        final_winner = None
                        embed.description += (
                            f"## Égalité entre {self.player1.mention} "
                            f"et {self.player2.mention} 🤝"
                        )
                        icon_url = self.bot.app_emojis["end"].url
                    view.stop()
                    view.clear_items()
                    await self.set_winner(final_winner)
                else:
                    dt = self.start_timer(63)
                    embed.description += f"\n\n{info}\n\nFin du tour {dt}"
                embed.set_author(name=header, icon_url=icon_url)
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                await interaction.response.send_message(
                    "Vous ne pouvez pas intéragir dans cette partie !",
                    ephemeral=True,
                    delete_after=5,
                )

        rock_btn.callback = partial(action_callback, label=ROCK)  # type: ignore[method-assign]
        paper_btn.callback = partial(action_callback, label=PAPER)  # type: ignore[method-assign]
        scissor_btn.callback = partial(action_callback, label=SCISSORS)  # type: ignore[method-assign]
        view.add_item(rock_btn)
        view.add_item(paper_btn)
        view.add_item(scissor_btn)
        dt = self.start_timer(60)
        embed.description = (
            f"En attente de {self.player1.mention} "
            f"et {self.player2.mention} ..."
            f"\n\nFin du tour {dt}"
        )
        self.message = await self.message.edit(
            embed=embed, content="", view=view
        )

    def compute_winner(
        self, play1: str, play2: str
    ) -> Optional[discord.Member]:
        """Get the winner."""
        i1 = EMOJIS.index(play1)
        i2 = EMOJIS.index(play2)
        if i1 == (i2 + 1) % 3:
            return self.player1
        if i1 == (i2 - 1) % 3:
            return self.player2
        return None  # Draw

    def color(
        self, member: Optional[discord.Member]
    ) -> Optional[discord.Colour]:
        """Color of the embed."""
        if member is None:
            return discord.Colour.from_str("#d4d5d6")
        if member == self.player1:
            return discord.Colour.from_str("#ca2a3e")
        if member == self.player2:
            return discord.Colour.from_str("#5865F2")
        error_message = f"Invalid member: {member!r}"
        raise ValueError(error_message)

    @override
    async def on_timeout(self) -> None:
        pass
