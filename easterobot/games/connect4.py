"""Connect4 (and Connect3) game implementation with customizable grid size.

This module implements a Connect4-style game for Discord bots using emoji
reactions for column selection. Players take turns dropping pieces
into columns, attempting to connect a specified number of pieces in
a row (horizontally, vertically, or diagonally) to win the game.
"""

import asyncio

import discord

from easterobot.bot import Easterobot
from easterobot.games.game import Game, Player
from easterobot.utils import in_seconds

# Mapping of numbered emoji reactions to column indices (0-9)
COLUMN_EMOJIS_MAPPER = {
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
COLUMN_EMOJIS = tuple(COLUMN_EMOJIS_MAPPER)

# Default game dimensions and win condition
DEFAULT_ROWS = 6
DEFAULT_COLS = 7
DEFAULT_WIN_COUNT = 4


class Connect4(Game):
    """Discord Connect4 game with customizable grid size and win conditions."""

    def __init__(
        self,
        bot: Easterobot,
        message: discord.Message,
        *members: discord.Member,
        rows: int = DEFAULT_ROWS,
        cols: int = DEFAULT_COLS,
        win_count: int = DEFAULT_WIN_COUNT,
    ) -> None:
        """Initialize Connect4 game with customizable dimensions and win.

        Args:
            bot: The Discord bot instance.
            message: The Discord message where the game will be displayed.
            *members: Variable number of members participating in the game.
            rows: Number of rows in the game grid (height).
            cols: Number of columns in the game grid (width).
            win_count: Number of consecutive pieces needed to win.
        """
        # Initialize grid as list of columns, each column is a list of rows
        # Grid[col][row] represents the piece at that position
        self.grid: list[list[Player | None]] = [
            [None] * rows for _ in range(cols)
        ]
        self.has_timed_out = False  # Track if current turn timed out
        self.row_count = rows  # Number of rows in the grid
        self.column_count = cols  # Number of columns in the grid
        self.required_connections = win_count  # Pieces needed in a row to win
        self.current_turn = (
            0  # Current turn counter (even=player1, odd=player2)
        )
        super().__init__(bot, message, *members)

    async def on_start(self) -> None:
        """Start the game by updating display, timer, and adding reactions.

        Updates the game message, starts a 61-second turn timer, and adds
        numbered emoji reactions corresponding to available columns with
        a small delay.
        """
        await self.update_display()
        await self.start_timer(61)
        # Add column selection emojis with delay to avoid rate limiting
        for emoji in COLUMN_EMOJIS[: self.column_count]:
            await asyncio.sleep(0.1)
            await self.message.add_reaction(emoji)

    async def update_display(self) -> None:
        """Update the Discord message with current game state and visual grid.

        Creates an embed showing the Connect4 grid with colored pieces, current
        player indicator, turn timer, and game status (ongoing,
        winner, or tie).
        """
        footer_text = ""
        header_label = ""

        if not self.is_terminated:
            # Show current player's piece and mention
            current_piece_emoji = self.get_piece_emoji(self.current_player)
            header_label = (
                current_piece_emoji
                + f" Joueur actuel : {self.current_player.member.mention}\n\n"
            )
            embed_player: Player | None = self.current_player
        elif self.winner:
            # Game ended with a winner
            forfeit_text = "par forfait " if self.has_timed_out else ""
            footer_text = (
                f"\n## Gagnant {forfeit_text}{self.winner.member.mention} 🎉"
            )
            embed_player = self.current_player
        else:
            # Game ended in a tie
            footer_text = (
                f"\n## Égalité entre {self.players[0].member.mention} "
                f"et {self.players[1].member.mention} 🤝"
            )
            embed_player = None

        content = header_label

        # Add column number indicators at the top
        content += "│".join(COLUMN_EMOJIS[: self.column_count])
        content += "\n"

        # Build the visual grid from top to bottom
        grid_rows = []
        for display_row in reversed(range(self.row_count)):
            row_pieces = []
            for col in range(self.column_count):
                piece_at_position = self.grid[col][display_row]
                piece_emoji = self.get_piece_emoji(piece_at_position)
                row_pieces.append(piece_emoji)
            grid_rows.append("│".join(row_pieces))

        content += "\n".join(grid_rows)
        content += footer_text

        # Add timer display for ongoing games
        if not self.is_terminated:
            content += f"\n\nFin du tour {in_seconds(61)}"

        embed = discord.Embed(
            description=content, color=self.get_player_color(embed_player)
        )
        embed.set_author(
            name="Partie terminée"
            if self.is_terminated
            else "Partie en cours",
            icon_url=(
                embed_player.member.display_avatar.url
                if embed_player
                else self.bot.app_emojis["end"].url
            ),
        )

        # Update the message with new embed and mention all players
        self.message = await self.message.edit(
            embed=embed,
            content="-# "
            + " ".join(player.member.mention for player in self.players),
            view=None,
        )

    async def on_reaction(
        self,
        member_id: int,
        reaction: discord.PartialEmoji,
    ) -> None:
        """Handle player reactions to drop pieces into columns.

        Args:
            member_id: Discord ID of the member who reacted.
            reaction: The emoji reaction that was added.

        Only processes valid column emoji reactions from the current player.
        """
        if (
            reaction.name not in COLUMN_EMOJIS[: self.column_count]
            or member_id != self.current_player.member.id
        ):
            return

        selected_column = COLUMN_EMOJIS_MAPPER[reaction.name]
        await self.drop_piece(selected_column, self.current_player)

    @property
    def current_player(self) -> Player:
        """Get the player whose turn it currently is.

        Returns:
            The Player object for the current turn.
        """
        return self.players[self.current_turn % 2]

    def get_piece_emoji(self, player: Player | None) -> str:
        """Get the emoji representation for a player's piece or empty space.

        Args:
            player: The player whose piece emoji to get, or None for empty.

        Returns:
            Emoji string representing the piece (red circle for player 1,
            yellow circle for player 2, white circle for empty).

        Raises:
            ValueError: If an invalid player object is provided.
        """
        if player is None:
            return "⚪"  # White circle for empty space
        if player == self.players[0]:
            return "🔴"  # Red circle for player 1
        if player == self.players[1]:
            return "🟡"  # Yellow circle for player 2

        error_message = f"Invalid member: {player!r}"
        raise ValueError(error_message)

    def get_player_color(self, player: Player | None) -> discord.Colour | None:
        """Get the Discord embed color associated with a specific player.

        Args:
            player: The player to get the color for, or None for neutral color.

        Returns:
            Discord color object for the player (red for player 1, yellow for
            player 2, gray for None/tie).

        Raises:
            ValueError: If an invalid player object is provided.
        """
        if player is None:
            return discord.Colour.from_str("#d4d5d6")  # Gray for tie/neutral
        if player == self.players[0]:
            return discord.Colour.from_str("#ca2a3e")  # Red for player 1
        if player == self.players[1]:
            return discord.Colour.from_str("#e9bb51")  # Yellow for player 2

        error_message = f"Invalid player: {player!r}"
        raise ValueError(error_message)

    async def drop_piece(
        self,
        column_index: int,
        player: Player,
    ) -> None:
        """Drop a piece into the specified column and update game state.

        Args:
            column_index: The column where the piece should be dropped.
            player: The player dropping the piece.

        Handles piece placement using gravity simulation, win detection, tie
        detection, and turn progression.
        Uses async lock to prevent race conditions.
        """
        async with self.lock:
            if self.is_terminated:
                return

            winning_player = None

            # Find the lowest empty row in the selected column (gravity effect)
            for row_index in range(self.row_count):
                if self.grid[column_index][row_index] is None:
                    await self.stop_timer()
                    self.grid[column_index][row_index] = player

                    # Check if this move creates a winning condition
                    if self._check_winner_at_position(
                        column_index, row_index, player
                    ):
                        winning_player = player
                    break
            else:
                # Column is full - ignore the move
                return

            if winning_player:
                await self.set_winner(winning_player)
            elif self._is_board_full():
                # All columns are full - it's a tie
                await self.set_winner(None)
            else:
                # Continue to next turn
                self.current_turn += 1
                await self.start_timer(61)

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

    def _check_winner_at_position(
        self, column: int, row: int, player: Player
    ) -> bool:
        """Check if placing a piece at the given position creates a win.

        Args:
            column: Column index where the piece was placed.
            row: Row index where the piece was placed.
            player: The player who placed the piece.

        Returns:
            True if this placement creates a winning line of the required
            length in any direction (horizontal, vertical, or diagonal).
        """
        # Check all four possible directions for consecutive pieces
        winning_directions = [
            (1, 0),  # Horizontal
            (0, 1),  # Vertical
            (1, 1),  # Diagonal (top-right)
            (1, -1),  # Diagonal (top-left)
        ]

        for direction_x, direction_y in winning_directions:
            # Count consecutive pieces in both directions from the placed piece
            consecutive_count = (
                self._count_consecutive_pieces(
                    column, row, direction_x, direction_y, player
                )
                + self._count_consecutive_pieces(
                    column, row, -direction_x, -direction_y, player
                )
                - 1  # Subtract 1 because we counted the placed piece twice
            )

            if consecutive_count >= self.required_connections:
                return True

        return False

    def _count_consecutive_pieces(
        self,
        start_col: int,
        start_row: int,
        delta_col: int,
        delta_row: int,
        player: Player,
    ) -> int:
        """Count consecutive pieces of the same player in a specific direction.

        Args:
            start_col: Starting column position.
            start_row: Starting row position.
            delta_col: Column direction to move (+1, 0, or -1).
            delta_row: Row direction to move (+1, 0, or -1).
            player: The player whose pieces to count.

        Returns:
            Number of consecutive pieces found in the specified direction,
            including the starting position.
        """
        consecutive_count = 0
        current_col, current_row = start_col, start_row

        # Keep counting while we're within bounds and finding matching pieces
        while (
            0 <= current_col < self.column_count
            and 0 <= current_row < self.row_count
            and self.grid[current_col][current_row] == player
        ):
            consecutive_count += 1
            current_col += delta_col
            current_row += delta_row

        return consecutive_count

    def _is_board_full(self) -> bool:
        """Check if the game board is completely full (tie condition).

        Returns:
            True if all columns are full (no more moves possible),
            False otherwise.
        """
        # Check if the top row of every column is occupied
        return all(
            self.grid[col][self.row_count - 1] is not None
            for col in range(self.column_count)
        )
