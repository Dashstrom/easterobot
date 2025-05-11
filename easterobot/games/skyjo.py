"""Skyjo."""

import logging
from dataclasses import dataclass
from enum import Enum, auto
from functools import partial
from string import ascii_uppercase
from typing import Any, Callable, Optional

import discord
from typing_extensions import override

from easterobot.bot import Easterobot
from easterobot.commands.base import Interaction
from easterobot.config import RAND
from easterobot.games.game import Button, Game, Player

CARDS = {-2: 5, -1: 10, 0: 15, **{i: 10 for i in range(1, 13)}}
logger = logging.getLogger(__name__)
COLORS = [
    0xFF595E,
    0x52A675,
    0xFF924C,
    0x1982C4,
    0xFFCA3A,
    0x4267AC,
    0x8AC926,
    0x6A4C93,
]


class ActionView(discord.ui.View):
    def __init__(
        self,
        skyjo: "Skyjo",
    ) -> None:
        """ActionView."""
        super().__init__(timeout=None)
        self.skyjo = skyjo
        if self.skyjo.starting:
            self.clear_items()
            options = self.skyjo.current_grid.place_options
            for opt in options:
                opt.emoji = self.skyjo.back
            self.return_select.options = options  # type: ignore[attr-defined]
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
        """Respond to interaction if invalid player."""
        await interaction.response.defer()  # Not the player !
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
        """Draw button."""
        if await self.check_player(interaction):
            self.skyjo.draw_card()
            await self.update_buttons()

    async def update_buttons(self) -> None:
        """Update the view."""
        self._update_buttons()
        await self.skyjo.update()

    def _update_buttons(self) -> None:
        """Update the view."""
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
        """Take button."""
        place: str = select.values[0]
        if self.skyjo.starting:
            for p in self.skyjo.players:
                if interaction.user == p.member:
                    grid = self.skyjo.grids[p]
                    if grid.ready:
                        logger.info(
                            "%s (%s) has already return his cards",
                            p.member.display_name,
                            p.member.id,
                        )
                        await interaction.response.defer()
                    else:
                        card = grid.get(place)
                        await interaction.response.defer()
                        if card.hidden:
                            grid.return_card(place)
                            logger.info(
                                "%s (%s) return %s with value %s",
                                p.member.display_name,
                                p.member.id,
                                place,
                                card.value,
                            )
                            await self.skyjo.update()
                        else:
                            logger.info(
                                "%s (%s) try to return a already visible card",
                                p.member.display_name,
                                p.member.id,
                            )
                    return
            logger.info(
                "%s (%s) is not part of the game",
                interaction.user.display_name,
                interaction.user.id,
            )
            await interaction.response.defer()
            return
        if await self.check_player(interaction):
            self.skyjo.remove_timeout_penalty()
            self.skyjo.return_card(place)
            await self.update_selects()
        return

    @discord.ui.select(placeholder="Prendre et remplacer", options=[])
    async def place_select(
        self, interaction: Interaction, select: discord.ui.Select["ActionView"]
    ) -> None:
        """Take button."""
        if await self.check_player(interaction):
            place: str = select.values[0]
            self.skyjo.remove_timeout_penalty()
            self.skyjo.place_card(place)
            await self.update_selects()

    async def update_selects(self) -> None:
        """Update select."""
        self.clear_items()
        self.add_item(self.draw_button)
        await self.skyjo.update()


@dataclass
class Card:
    value: int
    value_emoji: discord.PartialEmoji
    hidden: bool
    hidden_emoji: discord.PartialEmoji

    def copy(self) -> "Card":
        """Get the current emoji."""
        return Card(
            self.value,
            self.value_emoji,
            self.hidden,
            self.hidden_emoji,
        )

    @property
    def emoji(self) -> discord.PartialEmoji:
        """Get the current emoji."""
        if self.hidden:
            return self.hidden_emoji
        return self.value_emoji

    def __str__(self) -> str:
        """Return the str representation of the card."""
        return str(self.emoji)


class AI:
    def __init__(self, skyjo: "Skyjo") -> None:
        """Instantiate IA."""
        self.skyjo = skyjo

    def hypothetic_value(self, grid: "Grid") -> float:
        """Hypothetic value."""
        value = sum(
            5.0666 if c.hidden else c.value for c in grid.cards.values()
        )
        # Add bonus for row with double
        turn_left = self.minimal_turn_left()
        ratio = 1 - max(turn_left / 10, 1.0)
        ratio = 2 + ratio * 6
        columns = len(grid.content[0])
        for x in range(columns):
            for y in range(3):
                card = grid.content[y][x]
                if card.hidden or card.value <= 0:
                    continue
                for y2 in range(3):
                    card_cmp = grid.content[y2][x]
                    if y == y2 or card_cmp.hidden:
                        continue
                    if card_cmp.value == card.value:
                        value -= card.value / ratio

        # Penalty for row with broken combo
        for x in range(columns):
            c1 = grid.content[0][x]
            c2 = grid.content[0][x]
            c3 = grid.content[0][x]
            if c1.hidden or c2.hidden or c3.hidden:
                continue
            if (
                c1.value == c2.value  # noqa: PLR1714
                or c1.value == c3.value
                or c2.value == c3.value
            ):
                value += 1.5
        return value

    async def random_starting(self) -> None:
        """Random starting."""
        for grid in self.skyjo.grids.values():
            while not grid.ready:
                rand_place = RAND.choice(
                    [
                        place
                        for place, card in grid.cards.items()
                        if card.hidden
                    ]
                )
                grid.return_card(rand_place)

        # Update view
        await self.skyjo.update()

    def near_full(self, grid: "Grid") -> bool:
        """Return True if the grid is nearly full."""
        return sum(c.hidden for c in grid.cards.values()) <= 1

    async def play(self) -> None:
        """Play for player."""
        # Compute all actions
        actions: list[tuple[Callable[[], Any], float, bool]] = []
        grid = self.skyjo.current_grid

        # Replace card
        if self.skyjo.turn_state == TurnState.START:
            # Take the card or return
            current_card = self.skyjo.current_card
            initial_value = self.hypothetic_value(grid)
            for i_line, line in enumerate(grid.content):
                for i_col, card in enumerate(line):
                    place = grid.place(i_line, i_col)
                    grid_copy = grid.copy()
                    grid_copy.replace_card(place, current_card)
                    penalty = 0 if card.hidden else 2.5
                    actions.append(
                        (
                            partial(self.skyjo.place_card, place),
                            self.hypothetic_value(grid_copy) + penalty,
                            grid_copy.full,
                        )
                    )

            # Compute esperance of take the new card
            total_card = sum(CARDS.values())
            hypothetic_value_draw = 0.0
            for c, n in CARDS.items():
                prob = n / total_card
                values = []
                card = self.skyjo.card(c, hidden=True)
                for i_line, line in enumerate(grid.content):
                    for i_col, card in enumerate(line):
                        place = grid.place(i_line, i_col)
                        grid_copy = grid.copy()
                        grid_copy.replace_card(place, card)
                        value = self.hypothetic_value(grid_copy)
                        if card.hidden and value < initial_value:
                            value = initial_value
                        values.append(value)
                hypothetic_value_draw += min(values) * prob

            # Choose between draw and place
            RAND.shuffle(actions)
            action, value, end = min(
                actions,
                key=lambda t: (
                    not (t[2] and self.is_best_player(t[1])),
                    (t[2] and not self.is_best_player(t[1])),
                    t[1],
                ),
            )
            if value < hypothetic_value_draw:
                action()  # make the action
                await self.skyjo.update()
                return

            # Redraw !
            self.skyjo.draw_card()

        # Recompute actions
        current_card = self.skyjo.current_card
        initial_value = self.hypothetic_value(grid)
        for i_line, line in enumerate(grid.content):
            for i_col, card in enumerate(line):
                place = grid.place(i_line, i_col)
                if card.hidden:
                    actions.append(
                        (
                            partial(self.skyjo.return_card, place),
                            initial_value,
                            self.near_full(grid),
                        )
                    )
                grid_copy = grid.copy()
                grid_copy.replace_card(place, current_card)
                penalty = 0 if card.hidden else 2.5
                actions.append(
                    (
                        partial(self.skyjo.place_card, place),
                        self.hypothetic_value(grid_copy) + penalty,
                        grid_copy.full,
                    )
                )

        # Pick the best action
        RAND.shuffle(actions)
        action, value, end = min(
            actions,
            key=lambda t: (
                not (t[2] and self.is_best_player(t[1])),
                (t[2] and not self.is_best_player(t[1])),
                t[1],
            ),
        )
        action()

        # Update view
        await self.skyjo.update()

    def is_best_player(self, score: float) -> bool:
        """Check if the score is the best player."""
        max_enemy_value = max(
            self.hypothetic_value(grid)
            for p, grid in self.skyjo.grids.items()
            if p != self.skyjo.current_player
        )
        return max_enemy_value < score

    def minimal_turn_left(self) -> int:
        """Get minimal turn left."""
        return min(
            [
                sum(card.hidden for line in grid.content for card in line)
                for grid in self.skyjo.grids.values()
            ],
            default=0,
        )


@dataclass
class Grid:
    content: list[list[Card]]
    app_emojis: dict[str, discord.Emoji]

    def copy(self) -> "Grid":
        """Copy the grid."""
        return Grid(
            [[c.copy() for c in line] for line in self.content],
            app_emojis=self.app_emojis,
        )

    def index(self, place: str) -> tuple[int, int]:
        """Get index from place."""
        letter = ascii_uppercase.index(place[0])
        digit = int(place[1:]) - 1
        return digit, letter

    def return_card(self, place: str) -> Card:
        """Return a card."""
        x, y = self.index(place)
        card = self.content[x][y]
        card.hidden = False
        removed_card = self._remove_combo()
        return removed_card if removed_card else card

    def return_all_card(self) -> None:
        """Cards."""
        for card in self.cards.values():
            card.hidden = False

    def replace_card(self, place: str, card: Card) -> Card:
        """Replace a card."""
        x, y = self.index(place)
        prev = self.content[x][y]
        self.content[x][y] = card
        prev.hidden = False
        removed_card = self._remove_combo()
        return removed_card if removed_card else prev

    def _remove_combo(self) -> Optional[Card]:
        columns = len(self.content[0])
        removed_card = None
        for x in range(columns - 1, -1, -1):
            card = self.content[0][x]
            if card.hidden:
                continue
            for y in range(1, 3):
                other = self.content[y][x]
                if other.hidden or other.value != card.value:
                    break
            else:
                # Combo !
                removed_card = card
                for y in range(3):
                    del self.content[y][x]
        return removed_card

    def get(self, place: str) -> Card:
        """Return a card."""
        x, y = self.index(place)
        return self.content[x][y]

    def __str__(self) -> str:
        """Get the string representation."""
        if not self.content:
            return str(self.app_emojis["s_"])
        return (
            str(self.app_emojis["s_"])
            + "".join(
                str(self.app_emojis["s" + ascii_uppercase[n]])
                for n in range(len(self.content[0]))
            )
            + "\n"
            + "\n".join(
                str(self.app_emojis["s" + str(i)])
                + "".join(str(card) for card in line)
                for i, line in enumerate(self.content, start=1)
            )
            + "\n\n"
        )

    @property
    def ready(self) -> bool:
        """Cards."""
        return sum(not card.hidden for card in self.cards.values()) >= 2  # noqa: PLR2004

    @property
    def value(self) -> int:
        """Compute value."""
        return sum(c.value for c in self.cards.values())

    @property
    def value_visible(self) -> int:
        """Compute value."""
        return sum(c.value for c in self.cards.values() if not c.hidden)

    @property
    def full(self) -> bool:
        """Cards."""
        return all(not card.hidden for card in self.cards.values())

    @property
    def cards(self) -> dict[str, Card]:
        """Cards."""
        cards = {}
        for digit, line in enumerate(self.content, start=1):
            for x, card in enumerate(line):
                letter = ascii_uppercase[x]
                place = f"{letter}{digit}"
                cards[place] = card
        return cards

    def place(self, i_line: int, i_col: int) -> str:
        """Get the place."""
        return f"{ascii_uppercase[i_col]}{i_line + 1}"

    @property
    def place_options(self) -> list[discord.SelectOption]:
        """Place options."""
        return sorted(
            [
                discord.SelectOption(
                    label=place, emoji=card.emoji, value=place
                )
                for place, card in self.cards.items()
            ],
            key=lambda o: o.label,
        )

    @property
    def return_options(self) -> list[discord.SelectOption]:
        """Return options."""
        return sorted(
            [
                discord.SelectOption(
                    label=place, emoji=card.emoji, value=place
                )
                for place, card in self.cards.items()
                if card.hidden
            ],
            key=lambda o: o.label,
        )


class TurnState(Enum):
    START = auto()
    DRAW = auto()


class Skyjo(Game):
    emojis: dict[discord.PartialEmoji, int]

    def __init__(
        self,
        bot: Easterobot,
        message: discord.Message,
        *members: discord.Member,
    ) -> None:
        """Instantiate Connect4."""
        self.turn = 0
        self.decks: list[int] = []
        self.starting = True
        self.finish_turn: Optional[int] = None
        self.turn_state = TurnState.START
        self.timeout_penalty: dict[Player, float] = {}
        super().__init__(bot, message, *members)

    def recreate_decks(self) -> None:
        """Recrate decks."""
        self.decks = [
            value for value, cards in CARDS.items() for _ in range(cards)
        ]
        RAND.shuffle(self.decks)

    @classmethod
    def maximum_player(cls) -> int:
        """Get the maximum player number."""
        return 8

    @property
    def current_player(self) -> Player:
        """Get current player."""
        return self.players[self.turn % len(self.players)]

    @property
    def current_grid(self) -> Grid:
        """Get current player."""
        return self.grids[self.current_player]

    @property
    def finish_player(self) -> Optional[Player]:
        """Get the final player."""
        if self.finish_turn is not None:
            return self.players[self.finish_turn % len(self.players)]
        return None

    def card_value_to_emoji_name(self, value: int) -> str:
        """Get name of card from point."""
        return "skyjo_" + (f"m{-value}" if value < 0 else f"p{value}")

    def draw_hidden_card(self) -> Card:
        """Draw card."""
        if not self.decks:
            self.recreate_decks()
        card = self.decks.pop()
        return self.card(card, hidden=True)

    def remove_timeout_penalty(self) -> None:
        """Remove the timeout penalty."""
        if self.current_player in self.timeout_penalty:
            del self.timeout_penalty[self.current_player]

    def draw_card(self) -> Card:
        """Draw card."""
        self.current_card = self.draw_hidden_card()
        self.current_card.hidden = False
        logger.info(
            "%s (%s) draw card of value %s",
            self.current_player.member.display_name,
            self.current_player.member.id,
            self.current_card.value,
        )
        self.turn_state = TurnState.DRAW
        return self.current_card

    def return_card(self, place: str) -> Card:
        """Return a card."""
        card = self.current_grid.return_card(place)
        logger.info(
            "%s (%s) return card at %s and got %s",
            self.current_player.member.display_name,
            self.current_player.member.id,
            place,
            card.value,
        )
        self.turn += 1
        self.turn_state = TurnState.START
        return card

    def place_card(self, place: str) -> Card:
        """Place a card."""
        card = self.current_card
        self.current_card = self.current_grid.replace_card(
            place,
            self.current_card,
        )
        logger.info(
            "%s (%s) replace his card at %s of value %s by %s",
            self.current_player.member.display_name,
            self.current_player.member.id,
            place,
            self.current_card.value,
            card.value,
        )
        self.turn += 1
        self.turn_state = TurnState.START
        return self.current_card

    def card(self, value: int, *, hidden: bool) -> Card:
        """Get the card."""
        return Card(
            value=value,
            value_emoji=self.cards[value],
            hidden=hidden,
            hidden_emoji=self.back,
        )

    async def on_start(self) -> None:
        """Run."""
        self.cards = {
            i: self.bot.app_emojis[  # noqa: SLF001
                self.card_value_to_emoji_name(i)
            ]._to_partial()
            for i in range(-2, 13, 1)
        }
        self.back = self.bot.app_emojis["skyjo_back"]._to_partial()  # noqa: SLF001
        self.grids = {
            p: Grid(
                [
                    [self.draw_hidden_card() for x in range(4)]
                    for line in range(3)
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
        """Update the text."""
        # Instantiate view and embed
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
            content += f"-# Fin du tour {self.in_seconds}"

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
            content += f"-# Fin du tour {self.in_seconds}"

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
        embed.colour = color  # type: ignore[assignment]
        await self.message.edit(
            content=f"-# {' '.join(p.member.mention for p in self.players)}",
            embed=embed,
            **options,
        )

    def scores(self) -> dict[Player, int]:
        """Get all score."""
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

    @override
    async def on_timeout(self) -> None:
        if self.starting:
            await AI(self).random_starting()
        else:
            self.timeout_penalty[self.current_player] = 20
            await AI(self).play()
