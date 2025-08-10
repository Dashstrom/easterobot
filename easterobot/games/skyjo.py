"""Skyjo card game implementation for Discord bot interactions.

This module implements the Skyjo card game featuring grid-based card placement,
strategic card revealing, combo removal mechanics, and AI opponents. Players
compete to achieve the lowest total score by managing hidden and visible cards
in a 3x4 grid layout with special scoring rules and endgame triggers.
"""

import logging
from dataclasses import dataclass
from enum import Enum, auto
from functools import partial
from string import ascii_uppercase
from typing import TYPE_CHECKING, Any

import discord

from easterobot.bot import Easterobot
from easterobot.commands.base import Interaction
from easterobot.config import RAND
from easterobot.games.game import Button, Game, Player

if TYPE_CHECKING:
    from collections.abc import Callable

# Card distribution: value -> quantity in deck
CARDS = {-2: 5, -1: 10, 0: 15, **dict.fromkeys(range(1, 13), 10)}
logger = logging.getLogger(__name__)

# Color palette for different players and game states
COLORS = [
    0xFF595E,  # Red
    0x52A675,  # Green
    0xFF924C,  # Orange
    0x1982C4,  # Blue
    0xFFCA3A,  # Yellow
    0x4267AC,  # Dark Blue
    0x8AC926,  # Lime
    0x6A4C93,  # Purple
]


class ActionView(discord.ui.View):
    """UI view for handling Skyjo game interactions and button clicks."""

    def __init__(
        self,
        skyjo_game: "Skyjo",
    ) -> None:
        """Initialize the action view with game reference.

        Args:
            skyjo_game: The main Skyjo game instance.
        """
        super().__init__(timeout=None)
        self.skyjo = skyjo_game

        # Configure view based on game phase
        if self.skyjo.starting:
            self.clear_items()
            card_placement_options = self.skyjo.current_grid.place_options
            for option in card_placement_options:
                option.emoji = self.skyjo.back
            self.return_select.options = card_placement_options  # type: ignore[attr-defined]
            self.add_item(self.return_select)
        else:
            self.draw_button.emoji = self.skyjo.back
            self.place_select.options = self.skyjo.current_grid.place_options  # type: ignore[attr-defined]
            if not self.place_select.options:  # type: ignore[attr-defined]
                self.remove_item(self.place_select)
            self.remove_item(self.return_select)
            if self.skyjo.turn_state != TurnState.START:
                self._update_buttons()

    async def check_player(self, interaction: Interaction) -> bool:
        """Validate if the interaction user is the current player.

        Args:
            interaction: Discord interaction to validate.

        Returns:
            True if the user is the current player, False otherwise.
        """
        await interaction.response.defer()
        return interaction.user == self.skyjo.current_player.member

    @discord.ui.button(
        label="Piocher une nouvelle carte",
        style=discord.ButtonStyle.gray,
    )
    async def draw_button(
        self,
        interaction: Interaction,
        button: Button,  # noqa: ARG002
    ) -> None:
        """Handle drawing a new card from the deck.

        Args:
            interaction: Discord interaction from button click.
            button: The button that was clicked.
        """
        if await self.check_player(interaction):
            self.skyjo.draw_card()
            await self.update_buttons()

    async def update_buttons(self) -> None:
        """Update the view buttons and refresh the game display."""
        self._update_buttons()
        await self.skyjo.update()

    def _update_buttons(self) -> None:
        """Internal method to update button visibility and options."""
        self.clear_items()
        if self.skyjo.current_grid.return_options:
            self.return_select.options = self.skyjo.current_grid.return_options  # type: ignore[attr-defined]
            self.add_item(self.return_select)
        if self.skyjo.current_grid.place_options:
            self.place_select.options = self.skyjo.current_grid.place_options  # type: ignore[attr-defined]
            self.add_item(self.place_select)

    @discord.ui.select(placeholder="Retourner une de mes cartes", options=[])
    async def return_select(
        self, interaction: Interaction, select: discord.ui.Select["ActionView"]
    ) -> None:
        """Handle revealing a hidden card from the player's grid.

        Args:
            interaction: Discord interaction from selection.
            select: The select menu that was used.
        """
        card_position: str = select.values[0]

        # Handle starting phase where any player can reveal cards
        if self.skyjo.starting:
            for player in self.skyjo.players:
                if interaction.user == player.member:
                    player_grid = self.skyjo.grids[player]
                    if player_grid.ready:
                        logger.info(
                            "%s (%s) has already returned their cards",
                            player.member.display_name,
                            player.member.id,
                        )
                        await interaction.response.defer()
                    else:
                        selected_card = player_grid.get(card_position)
                        await interaction.response.defer()
                        if selected_card.hidden:
                            player_grid.return_card(card_position)
                            logger.info(
                                "%s (%s) revealed %s with value %s",
                                player.member.display_name,
                                player.member.id,
                                card_position,
                                selected_card.value,
                            )
                            await self.skyjo.update()
                        else:
                            logger.info(
                                "%s (%s) tried to reveal an already "
                                "visible card",
                                player.member.display_name,
                                player.member.id,
                            )
                    return
            logger.info(
                "%s (%s) is not part of the game",
                interaction.user.display_name,
                interaction.user.id,
            )
            await interaction.response.defer()
            return

        # Handle normal gameplay phase
        if await self.check_player(interaction):
            self.skyjo.remove_timeout_penalty()
            self.skyjo.return_card(card_position)
            await self.update_selects()

    @discord.ui.select(placeholder="Prendre et remplacer", options=[])
    async def place_select(
        self, interaction: Interaction, select: discord.ui.Select["ActionView"]
    ) -> None:
        """Handle placing the current card in the player's grid.

        Args:
            interaction: Discord interaction from selection.
            select: The select menu that was used.
        """
        if await self.check_player(interaction):
            card_position: str = select.values[0]
            self.skyjo.remove_timeout_penalty()
            self.skyjo.place_card(card_position)
            await self.update_selects()

    async def update_selects(self) -> None:
        """Update select menus and refresh the game display."""
        self.clear_items()
        self.add_item(self.draw_button)
        await self.skyjo.update()


@dataclass
class Card:
    """Represents a single card with value, display emoji, and state."""

    value: int
    value_emoji: discord.PartialEmoji
    hidden: bool
    hidden_emoji: discord.PartialEmoji

    def copy(self) -> "Card":
        """Create a deep copy of this card.

        Returns:
            A new Card instance with identical properties.
        """
        return Card(
            self.value,
            self.value_emoji,
            self.hidden,
            self.hidden_emoji,
        )

    @property
    def emoji(self) -> discord.PartialEmoji:
        """Get the appropriate emoji based on card visibility.

        Returns:
            Hidden emoji if card is face-down, value emoji if face-up.
        """
        if self.hidden:
            return self.hidden_emoji
        return self.value_emoji

    def __str__(self) -> str:
        """Return string representation showing the card's current emoji.

        Returns:
            String representation of the card's emoji.
        """
        return str(self.emoji)


class AI:
    """Artificial intelligence player for automated Skyjo."""

    def __init__(self, skyjo_game: "Skyjo") -> None:
        """Initialize AI with reference to the game instance.

        Args:
            skyjo_game: The Skyjo game instance to make decisions for.
        """
        self.skyjo = skyjo_game

    def hypothetic_value(self, player_grid: "Grid") -> float:
        """Calculate hypothetical value of a grid state for AI decision making.

        Considers card values, hidden card estimates, combo bonuses,
        and penalties to evaluate the desirability
        of a particular grid configuration.

        Args:
            player_grid: The grid to evaluate.

        Returns:
            Hypothetical score value (lower is better).
        """
        # Base value calculation (hidden cards estimated at 5.0666)
        total_value = sum(
            5.0666 if card.hidden else card.value
            for card in player_grid.cards.values()
        )

        # Add combo bonus consideration based on remaining turns
        turns_remaining = self.minimal_turn_left()
        turn_ratio = 1 - max(turns_remaining / 10, 1.0)
        combo_multiplier = 2 + turn_ratio * 6
        grid_columns = len(player_grid.content[0])

        # Check for potential column combos (same values in column)
        for column_index in range(grid_columns):
            for row_index in range(3):
                current_card = player_grid.content[row_index][column_index]
                if current_card.hidden or current_card.value <= 0:
                    continue

                # Look for matching cards in the same column
                for compare_row in range(3):
                    compare_card = player_grid.content[compare_row][
                        column_index
                    ]
                    if row_index == compare_row or compare_card.hidden:
                        continue
                    if compare_card.value == current_card.value:
                        total_value -= current_card.value / combo_multiplier

        # Add penalty for broken combo potential
        for column_index in range(grid_columns):
            top_card = player_grid.content[0][column_index]
            middle_card = player_grid.content[1][column_index]
            bottom_card = player_grid.content[2][column_index]

            if top_card.hidden or middle_card.hidden or bottom_card.hidden:
                continue

            # Penalty if partial matches exist (broken combo opportunity)
            if (
                top_card.value in (middle_card.value, bottom_card.value)
                or middle_card.value == bottom_card.value
            ):
                total_value += 1.5

        return total_value

    async def random_starting(self) -> None:
        """Handle random card revealing for all AI players during game start.

        Randomly selects two cards per player to reveal.
        """
        for player_grid in self.skyjo.grids.values():
            while not player_grid.ready:
                available_positions = [
                    position
                    for position, card in player_grid.cards.items()
                    if card.hidden
                ]
                random_position = RAND.choice(available_positions)
                player_grid.return_card(random_position)

        # Update game display after all reveals
        await self.skyjo.update()

    def near_full(self, player_grid: "Grid") -> bool:
        """Check if a grid is nearly complete (1 or fewer hidden cards).

        Args:
            player_grid: The grid to check for completion.

        Returns:
            True if grid has 1 or fewer hidden cards.
        """
        return sum(card.hidden for card in player_grid.cards.values()) <= 1

    async def play(self) -> None:
        """Execute a turn by evaluating possible actions and choosing the best.

        Analyzes drawing vs placing current card,
        considers combo opportunities, and makes strategic decisions based
        on hypothetical value calculations.
        """
        # Initialize action evaluation list
        possible_actions: list[tuple[Callable[[], Any], float, bool]] = []
        current_grid = self.skyjo.current_grid

        # Evaluate actions for start of turn (before drawing)
        if self.skyjo.turn_state == TurnState.START:
            current_card = self.skyjo.current_card
            initial_grid_value = self.hypothetic_value(current_grid)

            # Evaluate placing current card in each position
            for row_index, grid_row in enumerate(current_grid.content):
                for column_index, existing_card in enumerate(grid_row):
                    position = current_grid.place(row_index, column_index)
                    grid_copy = current_grid.copy()
                    grid_copy.replace_card(position, current_card)

                    # Add penalty for replacing visible cards
                    replacement_penalty = 0 if existing_card.hidden else 2.5
                    possible_actions.append(
                        (
                            partial(self.skyjo.place_card, position),
                            self.hypothetic_value(grid_copy)
                            + replacement_penalty,
                            grid_copy.full,
                        )
                    )

            # Calculate expected value of drawing a new card
            total_cards_in_deck = sum(CARDS.values())
            expected_draw_value = 0.0

            for card_value, card_quantity in CARDS.items():
                card_probability = card_quantity / total_cards_in_deck
                position_values = []
                hypothetical_card = self.skyjo.card(card_value, hidden=True)

                # Evaluate placing this hypothetical card in each position
                for row_index, grid_row in enumerate(current_grid.content):
                    for column_index, existing_card in enumerate(grid_row):
                        position = current_grid.place(row_index, column_index)
                        grid_copy = current_grid.copy()
                        grid_copy.replace_card(position, hypothetical_card)
                        position_value = self.hypothetic_value(grid_copy)

                        # Don't penalize if card stays hidden
                        if (
                            existing_card.hidden
                            and position_value < initial_grid_value
                        ):
                            position_value = initial_grid_value
                        position_values.append(position_value)

                # Weight by probability of drawing this card
                expected_draw_value += min(position_values) * card_probability

            # Choose between placing current card or drawing new one
            RAND.shuffle(possible_actions)
            best_action, best_value, ends_game = min(
                possible_actions,
                key=lambda action: (
                    not (action[2] and self.is_best_player(action[1])),
                    (action[2] and not self.is_best_player(action[1])),
                    action[1],
                ),
            )

            # Execute the action if it's better than drawing
            if best_value < expected_draw_value:
                best_action()
                await self.skyjo.update()
                return

            # Otherwise, draw a new card
            self.skyjo.draw_card()

        # Recalculate actions after drawing (or if we drew)
        current_card = self.skyjo.current_card
        initial_grid_value = self.hypothetic_value(current_grid)
        possible_actions.clear()

        # Evaluate all possible actions with the current card
        for row_index, grid_row in enumerate(current_grid.content):
            for column_index, existing_card in enumerate(grid_row):
                position = current_grid.place(row_index, column_index)

                # Option to reveal hidden card
                if existing_card.hidden:
                    possible_actions.append(
                        (
                            partial(self.skyjo.return_card, position),
                            initial_grid_value,
                            self.near_full(current_grid),
                        )
                    )

                # Option to place current card
                grid_copy = current_grid.copy()
                grid_copy.replace_card(position, current_card)
                replacement_penalty = 0 if existing_card.hidden else 2.5
                possible_actions.append(
                    (
                        partial(self.skyjo.place_card, position),
                        self.hypothetic_value(grid_copy) + replacement_penalty,
                        grid_copy.full,
                    )
                )

        # Select and execute the best action
        RAND.shuffle(possible_actions)
        best_action, best_value, ends_game = min(
            possible_actions,
            key=lambda action: (
                not (action[2] and self.is_best_player(action[1])),
                (action[2] and not self.is_best_player(action[1])),
                action[1],
            ),
        )
        best_action()

        # Update game display
        await self.skyjo.update()

    def is_best_player(self, player_score: float) -> bool:
        """Check if the given score would make this player the current leader.

        Args:
            player_score: The score to evaluate for leadership.

        Returns:
            True if this score beats all other players.
        """
        max_opponent_score = max(
            self.hypothetic_value(grid)
            for player, grid in self.skyjo.grids.items()
            if player != self.skyjo.current_player
        )
        return max_opponent_score < player_score

    def minimal_turn_left(self) -> int:
        """Calculate minimum turns remaining based on hidden cards across.

        Returns:
            Minimum number of hidden cards across all player grids.
        """
        return min(
            [
                sum(card.hidden for row in grid.content for card in row)
                for grid in self.skyjo.grids.values()
            ],
            default=0,
        )


@dataclass
class Grid:
    """Represents a player's 3x4 card grid with placement and combo logic."""

    content: list[list[Card]]
    app_emojis: dict[str, discord.Emoji]

    def copy(self) -> "Grid":
        """Create a deep copy of the entire grid.

        Returns:
            New Grid instance with copied cards and emoji references.
        """
        return Grid(
            [[card.copy() for card in row] for row in self.content],
            app_emojis=self.app_emojis,
        )

    def index(self, position: str) -> tuple[int, int]:
        """Convert position string (e.g., 'A1') to grid coordinates.

        Args:
            position: Position string in format 'A1', 'B2', etc.

        Returns:
            Tuple of (row, column) indices.
        """
        column_letter = ascii_uppercase.index(position[0])
        row_number = int(position[1:]) - 1
        return row_number, column_letter

    def return_card(self, position: str) -> Card:
        """Reveal a hidden card at the specified position.

        Args:
            position: Grid position to reveal.

        Returns:
            The revealed card, or removed card if combo was triggered.
        """
        row, column = self.index(position)
        target_card = self.content[row][column]
        target_card.hidden = False

        # Check for and handle any combos created
        removed_combo_card = self._remove_combo()
        return removed_combo_card if removed_combo_card else target_card

    def return_all_card(self) -> None:
        """Reveal all hidden cards in the grid (used at game end)."""
        for card in self.cards.values():
            card.hidden = False

    def replace_card(self, position: str, new_card: Card) -> Card:
        """Replace a card at the specified position with a new card.

        Args:
            position: Grid position to replace.
            new_card: Card to place in the position.

        Returns:
            The previous card that was replaced, or removed combo card.
        """
        row, column = self.index(position)
        previous_card = self.content[row][column]
        self.content[row][column] = new_card
        previous_card.hidden = False

        # Check for and handle any combos created
        removed_combo_card = self._remove_combo()
        return removed_combo_card if removed_combo_card else previous_card

    def _remove_combo(self) -> Card | None:
        """Check for and remove any column combos (3 matching visible cards).

        Scans each column from right to left, removing complete columns where
        all three cards have the same value and are visible.

        Returns:
            The card from a removed combo, or None if no combo was found.
        """
        grid_columns = len(self.content[0])
        removed_combo_card = None

        # Check columns from right to left to handle removal properly
        for column_index in range(grid_columns - 1, -1, -1):
            first_card = self.content[0][column_index]
            if first_card.hidden:
                continue

            # Check if all cards in column match and are visible
            combo_found = True
            for row_index in range(1, 3):
                other_card = self.content[row_index][column_index]
                if other_card.hidden or other_card.value != first_card.value:
                    combo_found = False
                    break

            # Remove the entire column if combo is found
            if combo_found:
                removed_combo_card = first_card
                for row_index in range(3):
                    del self.content[row_index][column_index]

        return removed_combo_card

    def get(self, position: str) -> Card:
        """Retrieve the card at the specified position.

        Args:
            position: Grid position to retrieve from.

        Returns:
            The card at the specified position.
        """
        row, column = self.index(position)
        return self.content[row][column]

    def __str__(self) -> str:
        """Generate string representation of the grid with coordinate labels.

        Returns:
            Formatted string showing the grid with row/column headers.
        """
        if not self.content:
            return str(self.app_emojis["s_"])

        # Create column headers
        column_headers = str(self.app_emojis["s_"]) + "".join(
            str(self.app_emojis["s" + ascii_uppercase[col_num]])
            for col_num in range(len(self.content[0]))
        )

        # Create rows with row numbers and cards
        grid_rows = "\n".join(
            str(self.app_emojis["s" + str(row_num)])
            + "".join(str(card) for card in row)
            for row_num, row in enumerate(self.content, start=1)
        )

        return column_headers + "\n" + grid_rows + "\n\n"

    @property
    def ready(self) -> bool:
        """Check if player has revealed at least 2 cards (ready to start).

        Returns:
            True if at least 2 cards are visible.
        """
        return sum(not card.hidden for card in self.cards.values()) >= 2  # noqa: PLR2004

    @property
    def value(self) -> int:
        """Calculate total value of all cards in the grid.

        Returns:
            Sum of all card values (including hidden ones).
        """
        return sum(card.value for card in self.cards.values())

    @property
    def value_visible(self) -> int:
        """Calculate total value of only visible cards in the grid.

        Returns:
            Sum of visible card values only.
        """
        return sum(
            card.value for card in self.cards.values() if not card.hidden
        )

    @property
    def full(self) -> bool:
        """Check if all cards in the grid are visible.

        Returns:
            True if no cards are hidden.
        """
        return all(not card.hidden for card in self.cards.values())

    @property
    def cards(self) -> dict[str, Card]:
        """Get dictionary mapping position strings to cards.

        Returns:
            Dictionary with position keys (e.g., 'A1') and Card values.
        """
        position_cards = {}
        for row_index, row in enumerate(self.content, start=1):
            for column_index, card in enumerate(row):
                column_letter = ascii_uppercase[column_index]
                position = f"{column_letter}{row_index}"
                position_cards[position] = card
        return position_cards

    def place(self, row_index: int, column_index: int) -> str:
        """Convert grid coordinates to position string.

        Args:
            row_index: Zero-based row index.
            column_index: Zero-based column index.

        Returns:
            Position string in format 'A1', 'B2', etc.
        """
        return f"{ascii_uppercase[column_index]}{row_index + 1}"

    @property
    def place_options(self) -> list[discord.SelectOption]:
        """Generate Discord select options for all grid positions.

        Returns:
            Sorted list of SelectOption objects for each grid position.
        """
        return sorted(
            [
                discord.SelectOption(
                    label=position, emoji=card.emoji, value=position
                )
                for position, card in self.cards.items()
            ],
            key=lambda option: option.label,
        )

    @property
    def return_options(self) -> list[discord.SelectOption]:
        """Generate Discord select options for hidden cards only.

        Returns:
            Sorted list of SelectOption objects for hidden cards.
        """
        return sorted(
            [
                discord.SelectOption(
                    label=position, emoji=card.emoji, value=position
                )
                for position, card in self.cards.items()
                if card.hidden
            ],
            key=lambda option: option.label,
        )


class TurnState(Enum):
    """Enumeration of possible turn states during gameplay."""

    START = auto()  # Beginning of turn, can draw or place current card
    DRAW = auto()  # After drawing, must place or reveal


class Skyjo(Game):
    """Main Skyjo game class managing game state, players, and turn flow."""

    emojis: dict[discord.PartialEmoji, int]

    def __init__(
        self,
        bot: Easterobot,
        message: discord.Message,
        *members: discord.Member,
    ) -> None:
        """Initialize a new Skyjo game instance.

        Args:
            bot: The Discord bot instance.
            message: Discord message to update with game state.
            members: Discord members participating in the game.
        """
        self.turn = 0
        self.card_deck: list[int] = []
        self.starting = True
        self.finish_turn: int | None = None
        self.turn_state = TurnState.START
        self.timeout_penalty: dict[Player, float] = {}
        super().__init__(bot, message, *members)

    def recreate_decks(self) -> None:
        """Recreate and shuffle a fresh deck of cards."""
        self.card_deck = [
            card_value
            for card_value, quantity in CARDS.items()
            for _ in range(quantity)
        ]
        RAND.shuffle(self.card_deck)

    @classmethod
    def maximum_player_count(cls) -> int:
        """Get the maximum number of players allowed in a game.

        Returns:
            Maximum player count (8 players).
        """
        return 8

    @property
    def current_player(self) -> Player:
        """Get the player whose turn it currently is.

        Returns:
            The Player object for the current turn.
        """
        return self.players[self.turn % len(self.players)]

    @property
    def current_grid(self) -> Grid:
        """Get the current player's grid.

        Returns:
            Grid object belonging to the current player.
        """
        return self.grids[self.current_player]

    @property
    def finish_player(self) -> Player | None:
        """Get the player who triggered the final round.

        Returns:
            Player who finished first, or None if unfinished.
        """
        if self.finish_turn is not None:
            return self.players[self.finish_turn % len(self.players)]
        return None

    def card_value_to_emoji_name(self, card_value: int) -> str:
        """Convert card value to corresponding emoji name for bot assets.

        Args:
            card_value: Numeric value of the card.

        Returns:
            Emoji name string for bot emoji lookup.
        """
        return "skyjo_" + (
            f"m{-card_value}" if card_value < 0 else f"p{card_value}"
        )

    def draw_hidden_card(self) -> Card:
        """Draw a random card from the deck as a hidden card.

        Returns:
            New Card instance with hidden=True.
        """
        if not self.card_deck:
            self.recreate_decks()
        drawn_value = self.card_deck.pop()
        return self.card(drawn_value, hidden=True)

    def remove_timeout_penalty(self) -> None:
        """Remove timeout penalty for the current player."""
        if self.current_player in self.timeout_penalty:
            del self.timeout_penalty[self.current_player]

    def draw_card(self) -> Card:
        """Draw a card and make it the current card (visible to all).

        Returns:
            The newly drawn card that becomes the current card.
        """
        self.current_card = self.draw_hidden_card()
        self.current_card.hidden = False
        logger.info(
            "%s (%s) drew card with value %s",
            self.current_player.member.display_name,
            self.current_player.member.id,
            self.current_card.value,
        )
        self.turn_state = TurnState.DRAW
        return self.current_card

    def return_card(self, position: str) -> Card:
        """Reveal a card in the active player's grid.

        Args:
            position: The position identifier of the card to reveal.

        Returns:
            The revealed card.
        """
        revealed = self.current_grid.return_card(position)
        logger.info(
            "%s (%s) revealed card at %s (value %s)",
            self.current_player.member.display_name,
            self.current_player.member.id,
            position,
            revealed.value,
        )
        self.turn += 1
        self.turn_state = TurnState.START
        return revealed

    def place_card(self, position: str) -> Card:
        """Replace a card in the grid with the drawn card.

        Args:
            position: The grid position to replace.

        Returns:
            The replaced card (now in discard).
        """
        replaced = self.current_card
        self.current_card = self.current_grid.replace_card(position, replaced)
        logger.info(
            "%s (%s) replaced card at %s (value %s) with %s",
            self.current_player.member.display_name,
            self.current_player.member.id,
            position,
            self.current_card.value,
            replaced.value,
        )
        self.turn += 1
        self.turn_state = TurnState.START
        return self.current_card

    def card(self, value: int, *, hidden: bool) -> Card:
        """Create a Card object from a value.

        Args:
            value: The numeric value of the card.
            hidden: Whether the card is face-down.

        Returns:
            A new Card instance.
        """
        return Card(
            value=value,
            value_emoji=self.cards[value],
            hidden=hidden,
            hidden_emoji=self.back,
        )

    async def on_start(self) -> None:
        """Set up the game at the start."""
        self.cards = {
            i: self.bot.app_emojis[  # noqa: SLF001
                self.card_value_to_emoji_name(i)
            ]._to_partial()
            for i in range(-2, 13)
        }
        self.back = self.bot.app_emojis["skyjo_back"]._to_partial()  # noqa: SLF001
        self.grids = {
            p: Grid(
                [
                    [self.draw_hidden_card() for _ in range(4)]
                    for _ in range(3)
                ],
                app_emojis=self.bot.app_emojis,
            )
            for p in self.players
        }
        self.current_card = self.draw_hidden_card()
        self.current_card.hidden = False
        await self.start_timer(120)
        await self.update()

    async def update(self) -> None:  # noqa: C901, PLR0912, PLR0915
        """Refresh and render the game state to Discord."""
        # Implementation kept same, docstring clarified above
        embed = discord.Embed()

        # End of starting phase
        if self.starting and all(grid.ready for grid in self.grids.values()):
            logger.info("All players have 2 card face up")
            self.starting = False
            self.players.sort(
                key=lambda p: self.grids[p].value_visible,
                reverse=True,
            )

        # One player have complete one of his grid
        if (
            any(grid.full for grid in self.grids.values())
            and self.finish_turn is None
        ):
            self.finish_turn = self.turn + len(self.players) - 1
            logger.info("Last turn will be %s", self.finish_turn)
            assert self.finish_player  # noqa: S101
            logger.info(
                "Finisher is %s (%s)",
                self.finish_player.member.display_name,
                self.finish_player.member.id,
            )

        # The game is finished
        scores = None
        header = "Partie en cours"
        if self.finish_turn is not None and self.finish_turn == self.turn:
            await self.stop_timer()
            logger.info("Game is finished !")
            scores = self.scores()
            header = "Partie terminée"
            best_score = float("+inf")
            best_players = []
            for p, s in scores.items():
                if s < best_score:
                    best_score = s
                    best_players = [p]
                elif s == best_score:
                    best_players.append(p)
            if len(best_players) >= 2:  # noqa: PLR2004
                content = "## Égalité entre "
                content += ", ".join(
                    p.member.mention for p in best_players[:-1]
                )
                content += f" et {best_players[-1].member.mention} 🤝"
                icon_url = self.bot.app_emojis["end"].url
                color = RAND.choice(COLORS)
                await self.set_winner(None)
            else:
                winner = best_players[0]
                content = f"## Gagnant {winner.member.mention} 🎉"
                color = COLORS[self.players.index(winner)]
                icon_url = winner.member.display_avatar.url
                await self.set_winner(winner)

        # The game is starting
        elif self.starting:
            icon_url = self.bot.app_emojis["wait"].url
            color = RAND.choice(COLORS)
            content = "Retournez chacun 2 cartes.\n"
            content += f"-# Fin du tour {self.timer_display}"

        # Normal play
        else:
            icon_url = self.current_player.member.display_avatar.url
            color = COLORS[self.turn % len(self.players)]
            content = f"Tour n°{self.turn + 1}\n"
            content += "Joueur actuel : "
            content += f"{self.current_player.member.mention}\n"
            if self.finish_turn:
                content += "**Attention, c'est le dernier tour !**\n"
            if self.turn_state == TurnState.START:
                content += (
                    f"Piochez une carte ou prenez {self.current_card.emoji}\n"
                )
            else:
                content += f"Vous avez pioché {self.current_card.emoji}\n"
                content += "Remplacez une carte ou retournez-en une.\n"
            if self.turn_state == TurnState.START:
                await self.stop_timer()
                await self.start_timer(
                    self.timeout_penalty.get(
                        self.current_player,
                        60,
                    )
                )
            content += f"-# Fin du tour {self.timer_display}"

        # Show player grid
        for p in self.players:
            grid = self.grids[p]
            score = scores[p] if scores else grid.value_visible
            embed.add_field(
                name=p.member.display_name,
                value=f"-# {score} points\n{grid}",
                inline=False,
            )

        # Update view
        options: dict[str, Any] = {}
        if not self.starting or all(
            c.hidden for g in self.grids.values() for c in g.cards.values()
        ):
            options["view"] = ActionView(self)
        if scores:
            options["view"] = None

        # Update embed
        logger.info("Update display")
        embed.set_author(name=header, icon_url=icon_url)
        embed.description = content
        embed.colour = color  # type: ignore[assignment,unused-ignore]
        await self.message.edit(
            content=f"-# {' '.join(p.member.mention for p in self.players)}",
            embed=embed,
            **options,
        )

    def scores(self) -> dict[Player, int]:
        """Calculate final scores for all players.

        Returns:
            A mapping of Player to their total score.
        """
        scores = {}
        for p, grid in self.grids.items():
            grid.return_all_card()
            scores[p] = grid.value
        finish_player = self.finish_player
        if finish_player:
            finish_score = scores[finish_player]
            for p, value in scores.items():
                if p != finish_player and value < finish_score:
                    scores[finish_player] *= 2
                break
        return scores

    async def on_timeout(self) -> None:
        """Handle turn timeout with AI fallback."""
        if self.starting:
            await AI(self).random_starting()
        else:
            self.timeout_penalty[self.current_player] = 20
            await AI(self).play()
