"""Discord TicTacToe game implementation with emoji-based user interface.

This module implements a TicTacToe game for Discord bots using reactions
for player input and embeds for visual representation. The game supports
two players and includes timeout handling and winner detection.
"""

import asyncio

import discord

from easterobot.bot import Easterobot
from easterobot.games.game import Game, Player
from easterobot.utils import in_seconds

# Mapping of emoji reactions to grid positions (0-8)
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
    """Discord TicTacToe game with emoji reactions and visual grid display."""

    def __init__(
        self,
        bot: Easterobot,
        message: discord.Message,
        *members: discord.Member,
    ) -> None:
        """Initialize the TicTacToe game with empty grid and default settings.

        Args:
            bot: The bot instance.
            message: The message where the game will be displayed.
            *members: Variable number of members participating in the game.
        """
        # 3x3 grid represented as flat list
        self.grid: list[Player | None] = [None] * 9
        self.has_timed_out = False  # Track if current turn timed out
        # Current turn counter (even=player1, odd=player2)
        self.current_turn = 0
        super().__init__(bot, message, *members)

    async def on_start(self) -> None:
        """Start the game by updating display, timer, and adding reactions.

        Updates the game message, starts a 31-second turn timer,
        and adds numbered emoji reactions for player input with a small
        delay between each.
        """
        await self.update_display()
        await self.start_timer(31)
        # Add reaction emojis with small delay to avoid rate limiting
        for emoji in EMOJIS:
            await asyncio.sleep(0.1)
            await self.message.add_reaction(emoji)

    async def update_display(self) -> None:
        """Update the Discord message with current game state and visual grid.

        Creates an embed showing the game grid, current player indicator,
        turn timer, and game status (ongoing, winner, or tie).
        """
        label = ""
        footer_text = ""

        if not self.is_terminated:
            # Show current player's symbol and mention
            mention = self.current_player.member.mention
            label = "⭕" if self.current_turn % 2 else "❌"
            label += f" Joueur actuel : {mention}\n\n"
            embed_user: Player | None = self.current_player
        elif self.winner:
            # Game ended with a winner
            forfeit_text = "par forfait " if self.has_timed_out else ""
            footer_text = (
                f"\n## Gagnant {forfeit_text}{self.winner.member.mention} 🎉"
            )
            embed_user = self.current_player
        else:
            # Game ended in a tie
            footer_text = (
                "\n## Égalité entre "
                f"{self.players[0].member.mention} "
                f"et {self.players[1].member.mention} 🤝"
            )
            embed_user = None

        content = label

        # Build the 3x3 visual grid
        grid_lines = []
        for row in range(3):
            row_pieces = []
            for col in range(3):
                grid_index = row * 3 + col
                cell_player = self.grid[grid_index]

                if cell_player == self.players[0]:
                    cell_display = "❌"
                elif cell_player == self.players[1]:
                    cell_display = "⭕"
                else:
                    # Empty cell shows the numbered emoji
                    cell_display = EMOJIS[grid_index]

                row_pieces.append(cell_display)
            grid_lines.append("│".join(row_pieces))

        content += "\n".join(grid_lines)
        content += footer_text

        # Add timer display for ongoing games
        if not self.is_terminated:
            content += f"\n\nFin du tour {in_seconds(31)}"

        embed = discord.Embed(
            description=content, color=self.get_player_color(embed_user)
        )
        embed.set_author(
            name="Partie terminée"
            if self.is_terminated
            else "Partie en cours",
            icon_url=(
                embed_user.member.display_avatar.url
                if embed_user
                else self.bot.app_emojis["end"].url
            ),
        )

        # Update the message with new embed and mention both players
        self.message = await self.message.edit(
            embed=embed,
            content=(
                f"-# {self.players[0].member.mention} "
                f"{self.players[1].member.mention}"
            ),
            view=None,
        )

    async def on_reaction(
        self, member_id: int, reaction: discord.PartialEmoji
    ) -> None:
        """Handle player reactions to make moves on the game grid.

        Args:
            member_id: Discord ID of the member who reacted.
            reaction: The emoji reaction that was added.

        Only processes valid numbered emoji reactions from the current player.
        """
        if (
            reaction.name not in EMOJIS
            or member_id != self.current_player.member.id
        ):
            return

        grid_position = EMOJIS_MAPPER[reaction.name]
        await self.make_move(grid_position, self.current_player)

    @property
    def current_player(self) -> Player:
        """Get the player whose turn it currently is.

        Returns:
            The Player for the current turn (alternates between players).
        """
        return [self.players[0], self.players[1]][self.current_turn % 2]

    def get_player_color(self, player: Player | None) -> discord.Colour | None:
        """Get the Discord embed color associated with a specific player.

        Args:
            player: The player to get the color for, or None for neutral color.

        Returns:
            Discord color object for the player (orange for player 1, blue for
            player 2, gray for None/tie).

        Raises:
            ValueError: If an invalid player object is provided.
        """
        if player is None:
            return discord.Colour.from_str("#d4d5d6")  # Gray for tie/neutral
        if player == self.players[0]:
            return discord.Colour.from_str("#F17720")  # Orange for player 1
        if player == self.players[1]:
            return discord.Colour.from_str("#0474BA")  # Blue for player 2

        error_message = f"Invalid player: {player!r}"
        raise ValueError(error_message)

    async def make_move(self, grid_index: int, player: Player) -> None:
        """Place a player's piece on the grid and update game state.

        Args:
            grid_index: Position on the grid where the piece should be placed.
            player: The player making the move.

        Handles move validation, winner detection, tie, and turn progression.
        Uses async lock to prevent race conditions.
        """
        # Ignore moves if game is over or cell is already occupied
        if self.is_terminated or self.grid[grid_index] is not None:
            return

        async with self.lock:
            await self.stop_timer()
            self.grid[grid_index] = player

            if self._check_winner(player):
                await self.set_winner(player)
            elif all(cell is not None for cell in self.grid):
                # All cells filled, it's a tie
                await self.set_winner(None)
            else:
                # Continue to next turn
                self.current_turn += 1
                await self.start_timer(31)

            await self.update_display()

    async def on_timeout(self) -> None:
        """Handle turn timeout by awarding victory to the other player.

        Called when a player doesn't make a move within the time limit.
        The current player loses and the other player wins by forfeit.
        """
        self.current_turn += 1  # Switch to other player
        self.has_timed_out = True
        await self.set_winner(self.current_player)  # Other player wins
        await self.update_display()

    def _check_winner(self, player: Player) -> bool:
        """Check if the specified player has achieved a winning combination.

        Args:
            player: The player to check for a win condition.

        Returns:
            True if the player has three pieces in a row (horizontally,
            vertically, or diagonally), False otherwise.
        """
        # All possible winning combinations on a 3x3 grid
        winning_combinations = [
            [0, 1, 2],  # Top row
            [3, 4, 5],  # Middle row
            [6, 7, 8],  # Bottom row
            [0, 3, 6],  # Left column
            [1, 4, 7],  # Middle column
            [2, 5, 8],  # Right column
            [0, 4, 8],  # Main diagonal
            [2, 4, 6],  # Anti diagonal
        ]

        return any(
            all(self.grid[position] == player for position in combination)
            for combination in winning_combinations
        )
