"""Discord Rock Paper Scissors game implementation with button-based interface.

This module implements a Rock Paper Scissors game for Discord bots using
interactive buttons for player input and embeds for visual representation.
The game supports customizable win conditions and maximum turn limits with
comprehensive match history.
"""

import asyncio
from functools import partial
from typing import Optional

import discord

from easterobot.bot import Easterobot
from easterobot.commands.base import Interaction
from easterobot.games.game import Button, Game

# Emoji constants for game choices (decoded from UTF-8 bytes for reliability)
ROCK = b"\xf0\x9f\xaa\xa8".decode("utf-8")
PAPER = b"\xf0\x9f\x93\x84".decode("utf-8")
SCISSORS = b"\xe2\x9c\x82\xef\xb8\x8f".decode("utf-8")
CHOICE_EMOJIS = [
    PAPER,
    ROCK,
    SCISSORS,
]  # Order matters for win calculation logic


class RockPaperScissors(Game):
    """Rock Paper Scissors game with interactive buttons and match history."""

    view: discord.ui.View

    def __init__(
        self,
        bot: Easterobot,
        message: discord.Message,
        *members: discord.Member,
        win_count: int = 3,
        max_turn: int = 10,
    ) -> None:
        """Initialize the Rock Paper Scissors game.

        Args:
            bot: The bot instance.
            message: The message where the game will be displayed.
            *members: Variable number of members participating in the game.
            win_count: Number of rounds a player must win to claim victory.
            max_turn: Maximum number of rounds before the game ends in a tie.
        """
        self.has_timed_out = False  # Track if current round timed out
        self.max_turn = max_turn  # Maximum allowed rounds
        self.win_count = win_count  # Rounds needed to win the match
        # Current round choice for player 1
        self.player1_choice: Optional[str] = None
        # Current round choice for player 2
        self.player2_choice: Optional[str] = None
        self.match_history: list[
            tuple[str, str]
        ] = []  # History of all played rounds
        super().__init__(bot, message, *members)

    async def on_start(self) -> None:
        """Start the game by creating interactive buttons and initial display.

        Sets up Rock, Paper, and Scissors buttons with click handlers,
        creates the game view, and displays the initial waiting state.
        """
        embed = discord.Embed(color=0xF2BC32)
        embed.set_author(
            name="Partie en cours", icon_url=self.bot.app_emojis["wait"].url
        )

        # Create view with 30-minute timeout for the entire match
        self.view = discord.ui.View(timeout=1800)

        # Create interactive buttons for each game choice
        rock_button: Button = discord.ui.Button(
            style=discord.ButtonStyle.gray,
            emoji=ROCK,
        )
        paper_button: Button = discord.ui.Button(
            style=discord.ButtonStyle.gray,
            emoji=PAPER,
        )
        scissors_button: Button = discord.ui.Button(
            style=discord.ButtonStyle.gray,
            emoji=SCISSORS,
        )

        async def handle_choice_click(
            interaction: Interaction,
            selected_choice: str,
        ) -> None:
            """Handle player button clicks and update game state accordingly.

            Args:
                interaction: The Discord interaction from the button click.
                selected_choice: The emoji representing the player's choice.

            Validates the clicking user, records their choice, and updates the
            display when appropriate.
            Shows error messages for invalid interactions.
            """
            should_update = False
            clicking_user = interaction.user
            # TODO(dashstrom): user is in the party ?

            # Handle player 1 making their choice
            if (
                clicking_user == self.players[0].member
                and self.player1_choice is None
            ):
                self.player1_choice = selected_choice
                should_update = True

            # Handle player 2 making their choice
            elif (
                clicking_user == self.players[1].member
                and self.player2_choice is None
            ):
                self.player2_choice = selected_choice
                should_update = True

            # Update display if a valid choice was made
            if should_update:
                await asyncio.gather(
                    self.stop_timer(),
                    interaction.response.defer(),
                )
                await self.update_display()
            elif clicking_user in (
                self.players[0].member,
                self.players[1].member,
            ):
                # Invalid interaction (already chosen)
                await interaction.response.send_message(
                    "Vous avez déjà joué à cette manche !",
                    ephemeral=True,
                    delete_after=5,
                )
            else:
                # Invalid interaction (wrong user)
                await interaction.response.send_message(
                    "Vous ne pouvez pas intéragir dans cette partie !",
                    ephemeral=True,
                    delete_after=5,
                )

        # Assign callbacks to buttons using partial to pass the choice
        rock_button.callback = partial(  # type: ignore[method-assign]
            handle_choice_click, selected_choice=ROCK
        )
        paper_button.callback = partial(  # type: ignore[method-assign]
            handle_choice_click, selected_choice=PAPER
        )
        scissors_button.callback = partial(  # type: ignore[method-assign]
            handle_choice_click, selected_choice=SCISSORS
        )

        # Add all buttons to the view
        self.view.add_item(rock_button)
        self.view.add_item(paper_button)
        self.view.add_item(scissors_button)

        await self.update_display()

    async def update_display(self) -> None:  # noqa: C901, PLR0912, PLR0915
        """Update the message with current game state and match history.

        Displays waiting status, round results, running score, and determines
        when the match should end based on win conditions or turn limits.
        Complex method handling multiple game states and display formatting.
        """
        embed = discord.Embed(color=0xF2BC32)

        # Determine current game status and waiting message
        match_status = "Partie en cours"
        if self.player1_choice is None and self.player2_choice is None:
            # Waiting for both players
            status_icon_url = self.bot.app_emojis["wait"].url
            waiting_message = (
                f"En attente de {self.players[0].member.mention} "
                f"et {self.players[1].member.mention} ..."
            )
        elif self.player1_choice is None:
            # Waiting for player 1
            status_icon_url = self.players[0].member.display_avatar.url
            waiting_message = (
                f"En attente de {self.players[0].member.mention} ..."
            )
        elif self.player2_choice is None:
            # Waiting for player 2
            status_icon_url = self.players[1].member.display_avatar.url
            waiting_message = (
                f"En attente de {self.players[1].member.mention} ..."
            )
        else:
            # Both players have chosen - process the round
            self.match_history.append(
                (self.player1_choice, self.player2_choice)
            )
            self.player1_choice = None
            self.player2_choice = None
            status_icon_url = self.bot.app_emojis["wait"].url
            waiting_message = (
                f"En attente de {self.players[0].member.mention} "
                f"et {self.players[1].member.mention} ..."
            )

        # Calculate running score from match history
        player1_wins = 0
        player2_wins = 0
        round_results = []

        for p1_choice, p2_choice in self.match_history:
            choice1_index = CHOICE_EMOJIS.index(p1_choice)
            choice2_index = CHOICE_EMOJIS.index(p2_choice)

            # Determine round winner using circular win logic
            if choice1_index == (choice2_index - 1) % 3:
                # Player 1 wins this round
                player1_wins += 1
                round_winner_text = self.players[0].member.mention
            elif choice1_index == (choice2_index + 1) % 3:
                # Player 2 wins this round
                player2_wins += 1
                round_winner_text = self.players[1].member.mention
            else:
                # Round is a tie
                round_winner_text = "**égalité**"

            # Format the round result for display
            round_results.append(
                f"### {p1_choice} {self.bot.app_emojis['versus']} {p2_choice} "
                f"{self.bot.app_emojis['arrow']} {round_winner_text}"
            )

        embed.description = "\n".join(round_results)

        # Check if match should end (win condition, turn limit, or timeout)
        match_should_end = (
            len(self.match_history) >= self.max_turn
            or player1_wins >= self.win_count
            or player2_wins >= self.win_count
            or self.has_timed_out
        )

        if match_should_end:
            # Match is over - determine final winner and update display
            match_status = "Partie terminée"
            embed.description += "\n\n"

            if self.has_timed_out:
                # Winner was set during timeout handling
                final_winner = self.winner
            elif player1_wins < player2_wins:
                final_winner = self.players[1]
            elif player2_wins < player1_wins:
                final_winner = self.players[0]
            else:
                # Match ended in overall tie
                final_winner = None

            if final_winner:
                # Display winner announcement
                forfeit_text = "par forfait " if self.has_timed_out else ""
                embed.description += f"## Gagnant {forfeit_text}"
                embed.description += f"{final_winner.member.mention} 🎉"
                status_icon_url = final_winner.member.display_avatar.url
            else:
                # Display tie announcement
                embed.description += (
                    f"## Égalité entre {self.players[0].member.mention} "
                    f"et {self.players[1].member.mention} 🤝"
                )
                status_icon_url = self.bot.app_emojis["end"].url

            # Disable all buttons since match is over
            self.view.stop()
            self.view.clear_items()

            if not self.has_timed_out:
                await self.set_winner(final_winner)
        else:
            # Match continues - start timer for next round
            round_timer = await self.start_timer(31)
            embed.description += (
                f"\n\n{waiting_message}\n\nFin du tour {round_timer}"
            )

        embed.set_author(name=match_status, icon_url=status_icon_url)

        # Update the Discord message with new embed and view
        await self.message.edit(
            embed=embed,
            view=self.view,
            content=(
                f"-# {self.players[0].member.mention} "
                f"{self.players[1].member.mention}"
            ),
        )

    def determine_round_winner(
        self, player1_choice: str, player2_choice: str
    ) -> Optional[discord.Member]:
        """Determine the winner of a single round.

        Args:
            player1_choice: The emoji choice made by player 1.
            player2_choice: The emoji choice made by player 2.

        Returns:
            The Discord member who won the round, or None if it's a tie.
            Uses circular logic: Rock beats Scissors, Scissors beats Paper,
            Paper beats Rock.
        """
        choice1_index = CHOICE_EMOJIS.index(player1_choice)
        choice2_index = CHOICE_EMOJIS.index(player2_choice)

        if choice1_index == (choice2_index + 1) % 3:
            return self.players[0].member
        if choice1_index == (choice2_index - 1) % 3:
            return self.players[1].member
        return None  # Round is a tie

    def get_player_color(
        self, member: Optional[discord.Member]
    ) -> Optional[discord.Colour]:
        """Get the Discord embed color associated with a specific player.

        Args:
            member: The member to get the color for, or None for neutral color.

        Returns:
            Discord color object for the player (red for player 1, blurple
            for player 2, gray for None/tie).

        Raises:
            ValueError: If an invalid member object is provided.
        """
        if member is None:
            return discord.Colour.from_str("#d4d5d6")  # Gray for tie/neutral
        if member == self.players[0]:
            return discord.Colour.from_str("#ca2a3e")  # Red for player 1
        if member == self.players[1]:
            return discord.Colour.from_str(
                "#5865F2"
            )  # Discord blurple for player 2

        error_message = f"Invalid member: {member!r}"
        raise ValueError(error_message)

    async def on_timeout(self) -> None:
        """Handle timeout by awarding victory to the player who made a choice.

        If only one player made their choice, they win the match.
        If neither player made a choice, the game ends with a draw.
        Updates the display after setting the winner.
        """
        self.has_timed_out = True

        # Award victory to the player who made their choice
        if self.player1_choice is None:
            await self.set_winner(self.players[1])
        if self.player2_choice is None:
            await self.set_winner(self.players[0])

        await self.update_display()
