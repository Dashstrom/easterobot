"""Roulette game module for Easterobot.

This module implements a roulette mini-game where players bet virtual eggs
on various outcomes. It manages bet tracking, payout calculation, and the
full game flow including user interaction via Discord UI elements.

Classes:
    Play: Represents a specific roulette bet type and payout configuration.
    RouletteResult: Stores the outcome of a roulette spin.
    Roulette: Handles bet registration and winner determination.
    BetView: Discord UI view for selecting bets.
    RouletteManager: Orchestrates the entire roulette game session.
"""

import asyncio
from asyncio import sleep
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.bot import Easterobot
from easterobot.config import RAND, agree
from easterobot.locker import EggLocker, EggLockerError
from easterobot.utils import in_seconds

if TYPE_CHECKING:
    from easterobot.models import Egg


@dataclass(frozen=True, order=True)
class Play:
    """Represents a bet option in roulette."""

    name: str
    emoji: str
    bet: int
    payout: int
    slots: frozenset[int]

    @property
    def label(self) -> str:
        """Return a human-readable bet label.

        Returns:
            str: Bet description including amount and name, with plural
            agreement.
        """
        return agree(
            f"{self.bet} œuf sur {self.name}",
            f"{self.bet} œufs sur {self.name}",
            self.bet,
        )

    @property
    def probability(self) -> float:
        """Return the probability of winning this bet.

        Returns:
            float: Probability between 0 and 1.
        """
        return len(self.slots) / 37

    @property
    def eggs(self) -> float:
        """Return the total eggs won if this bet succeeds.

        Returns:
            float: Number of eggs awarded.
        """
        return self.payout * self.bet


# Predefined roulette bets with corresponding slots and payouts.
plays = [
    Play(
        "noir",
        "⚫",
        1,
        2,
        frozenset(
            {
                2,
                4,
                6,
                8,
                10,
                11,
                13,
                15,
                17,
                20,
                22,
                24,
                26,
                28,
                29,
                31,
                33,
                35,
            }
        ),
    ),
    Play(
        "rouge",
        "🔴",
        1,
        2,
        frozenset(
            {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
        ),
    ),
    Play("impaire", "1️⃣", 3, 2, frozenset(range(1, 37, 2))),
    Play("pair", "2️⃣", 3, 2, frozenset(range(2, 37, 2))),
    Play("manque", "⬅️", 5, 2, frozenset(range(1, 19))),
    Play("passe", "➡️", 5, 2, frozenset(range(19, 37))),
    Play("zero", "0️⃣", 1, 36, frozenset({0})),
]
play_mapper = {p.label: p for p in plays}


@dataclass
class RouletteResult:
    """Stores the outcome of a roulette spin."""

    draw: int
    winners: dict[discord.Member, Play]
    losers: dict[discord.Member, Play]

    @property
    def label(self) -> str:
        """Return a human-readable description of winning bets.

        Returns:
            str: Names of winning plays, or a 'no win' message.
        """
        winning_plays = sorted(set(self.winners.values()))
        if len(winning_plays) == 1:
            return winning_plays[0].name
        if winning_plays:
            last = winning_plays[-1]
            return (
                ", ".join(p.name for p in winning_plays[:-1])
                + " et "
                + last.name
            )
        return "rien au numéro"


class Roulette:
    """Tracks bets and resolves roulette spins."""

    def __init__(self, locker: EggLocker) -> None:
        """Initialize the roulette game state.

        Args:
            locker: EggLocker instance for managing eggs.
        """
        self.bets: dict[discord.Member, Play] = {}
        self.eggs: dict[discord.Member, list[Egg]] = {}
        self.locker = locker

    async def bet(self, member: discord.Member, play: Play) -> None:
        """Register a player's bet.

        Args:
            member: The player placing the bet.
            play: The bet details.

        Raises:
            ValueError: If the player has already placed a bet.
        """
        if member in self.eggs:
            raise ValueError
        async with self.locker.transaction():
            eggs = await self.locker.get(member, play.bet)
        self.eggs[member] = eggs
        self.bets[member] = play

    async def sample(self) -> "RouletteResult":
        """Spin the roulette wheel and determine winners/losers.

        Returns:
            RouletteResult: Outcome containing draw result and player statuses.
        """
        ball = RAND.randint(0, 36)
        losers = {}
        winners = {}
        futures = []
        async with self.locker.transaction():
            for member, play in self.bets.items():
                eggs = self.eggs[member]
                if ball in play.slots:
                    added_eggs = [
                        egg.duplicate()
                        for egg in eggs
                        for _ in range(play.payout - 1)
                    ]
                    self.locker.update(added_eggs)
                    winners[member] = play
                else:
                    futures.append(self.locker.delete(eggs))
                    losers[member] = play
            await asyncio.gather(*futures)
        return RouletteResult(draw=ball, losers=losers, winners=winners)


class BetView(discord.ui.View):
    """Interactive Discord view for placing bets."""

    def __init__(self, embed: discord.Embed, roulette: Roulette) -> None:
        """Initialize the bet selection UI.

        Args:
            embed: Embed showing bet announcements.
            roulette: Roulette game instance handling bets.
        """
        super().__init__()
        self.embed = embed
        self.roulette = roulette
        self.already_interact: set[discord.Member] = set()

    def disable(self) -> None:
        """Disable bet selection and stop interaction."""
        self.select_bet.disabled = True  # type: ignore[attr-defined]
        self.stop()

    @discord.ui.select(
        placeholder="Parier",
        options=[
            discord.SelectOption(
                label=f"Parier {play.label}",
                emoji=play.emoji,
                value=play.label,
                description=(
                    f"{play.probability:.2%} de repartir avec {play.eggs} œufs"
                ),
            )
            for play in plays
        ],
    )
    async def select_bet(
        self,
        interaction: discord.Interaction["Easterobot"],
        select: discord.ui.Select["BetView"],
    ) -> None:
        """Handle bet selection by a player.

        Args:
            interaction: Discord interaction triggered by the selection.
            select: The dropdown menu object representing bet choices.
        """
        user = interaction.user
        if not isinstance(user, discord.Member) or interaction.message is None:
            await interaction.response.defer()
            return
        if user in self.already_interact:
            await interaction.response.send_message(
                "Vous avez déjà choisi votre pari !",
                ephemeral=True,
            )
            return
        self.already_interact.add(user)
        bet = play_mapper[select.values[0]]
        try:
            await self.roulette.bet(user, bet)
        except EggLockerError:
            self.already_interact.remove(user)
            await interaction.response.send_message(
                "Vous n'avez pas assez d'œufs disponibles !",
                ephemeral=True,
            )
            return
        embeds = interaction.message.embeds
        assert self.embed.description is not None  # noqa: S101
        self.embed.description += (
            f"\n> {interaction.user.mention} a parié {bet.label} {bet.emoji}"
        )
        await interaction.response.edit_message(embeds=[embeds[0], self.embed])


class RouletteManager:
    """Manages the flow of a roulette game session."""

    def __init__(self, bot: Easterobot) -> None:
        """Initialize the roulette manager.

        Args:
            bot: Instance of Easterobot.
        """
        self.bot = bot

    async def run(
        self,
        source: discord.Message | discord.TextChannel,
    ) -> None:
        """Execute a complete roulette session.

        Args:
            source: Message or channel where the game will take place.

        Raises:
            ValueError: If the game is started outside of a guild.
        """
        guild = source.guild
        if guild is None:
            raise ValueError
        async with (
            AsyncSession(
                self.bot.engine,
                expire_on_commit=False,
            ) as session,
            EggLocker(session, guild.id) as locker,
        ):
            timeout = self.bot.config.casino.roulette.duration + 40
            roulette = Roulette(locker)
            embed = discord.Embed(
                description=(
                    "# Roulette lapinique"
                    "\nLe Casino vous ouvre exceptionnellement ses portes. "
                    "Devant vous se trouve un élégant croupier lapin. "
                    "Il vous fixe droit dans les yeux "
                    "et prononce de simples mots en langue lapinique. "
                    "Magiquement, vous semblez comprendre : 'Faites vos jeux'."
                    "\n\n-# Faites attention, "
                    f"il annoncera sans doute la fin {in_seconds(timeout)}."
                ),
                color=0x00FF00,
            )
            text = discord.Embed(
                description="# Annonces du croupier\n> Faites vos jeux",
                color=0x00FF00,
            )
            assert text.description is not None  # noqa: S101
            embed.set_image(
                url="https://i.pinimg.com/originals/32/37/bf/3237bf1e172a6089e0c437ffd3b28010.gif"
            )
            view = BetView(text, roulette)
            if isinstance(source, discord.Message):
                message = source
                await message.edit(
                    embeds=[embed, text],
                    content="",
                    view=view,
                )
            else:
                message = await source.send(
                    embeds=[embed, text],
                    view=view,
                )
            await sleep(timeout)
            text.description += "\n> Les jeux sont faits"
            await message.edit(embeds=[embed, text])
            await sleep(20)
            view.disable()
            text.description += "\n> Rien ne va plus"
            await message.edit(view=view, embeds=[embed, text])
            await sleep(20)
            result = await roulette.sample()
            text.description += "\n> La bille s'arrête "
            number = f"{result.draw:2d}".replace(" ", "\xa0")
            text.description += f"sur le ||{number}||"
            text.description += f"\n> Le lapin annonce ||{result.label}||"
            await message.edit(view=None, embeds=[embed, text])

        messages = []
        for member, bet in result.winners.items():
            egg_text = agree("œuf", "œufs", bet.bet)
            messages.append(
                f"{member.mention} repart avec {bet.eggs} {egg_text}"
            )
        for member, bet in result.losers.items():
            egg_text = agree("œuf", "œufs", bet.bet)
            messages.append(f"{member.mention} perd {bet.bet} {egg_text}")
        if messages:
            await sleep(5)
            await message.reply(  # type: ignore[call-overload]
                content="\n".join(messages),
                view=None,
            )
