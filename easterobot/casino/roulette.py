"""Module to play roulette."""

import asyncio
from asyncio import sleep
from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.bot import Easterobot
from easterobot.config import RAND, agree
from easterobot.locker import EggLocker

if TYPE_CHECKING:
    from easterobot.models import Egg


@dataclass(frozen=True, order=True)
class Play:
    name: str
    emoji: str
    bet: int
    payout: int
    slots: frozenset[int]

    @property
    def label(self) -> str:
        """Returns the label of the bet."""
        return agree(
            f"{self.bet} œuf sur {self.name}",
            f"{self.bet} œufs sur {self.name}",
            self.bet,
        )

    @property
    def probability(self) -> float:
        """Returns the winning probability."""
        return len(self.slots) / 37

    @property
    def eggs(self) -> float:
        """Returns the number of eggs won."""
        return self.payout * self.bet


# fmt: off
plays = [
    Play("noir", "⚫", 1, 2, frozenset({2, 4, 6, 8, 10, 11, 13, 15, 17, 20,
                                       22, 24, 26, 28, 29, 31, 33, 35})),
    Play("rouge", "🔴", 1, 2, frozenset({1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21,
                                        23, 25, 27, 30, 32, 34, 36})),
    Play("impaire", "1️⃣", 3, 2, frozenset(range(1, 37, 2))),
    Play("pair", "2️⃣", 3, 2, frozenset(range(2, 37, 2))),
    Play("manque", "⬅️", 5, 2, frozenset(range(1, 19))),
    Play("passe", "➡️", 5, 2, frozenset(range(19, 37))),
    Play("zero", "0️⃣", 1, 36, frozenset({0})),
]
play_mapper = {p.label: p for p in plays}
# fmt: on


@dataclass
class RouletteResult:
    draw: int
    winners: dict[discord.Member, Play]
    losers: dict[discord.Member, Play]

    @property
    def label(self) -> str:
        """Returns the name(s) of the winning bet(s)."""
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
    def __init__(self, locker: EggLocker) -> None:
        """Initialize an empty bet tracker."""
        self.bets: dict[discord.Member, Play] = {}
        self.eggs: dict[discord.Member, list[Egg]] = {}
        self.locker = locker

    async def bet(self, member: discord.Member, play: Play) -> None:
        """Register a bet from a member."""
        if member in self.eggs:
            raise ValueError
        async with self.locker.transaction():
            eggs = await self.locker.get(member, play.bet)
        self.eggs[member] = eggs
        self.bets[member] = play

    async def sample(self) -> "RouletteResult":
        """Draw a number and determine winners/losers."""
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
        return RouletteResult(
            draw=ball,
            losers=losers,
            winners=winners,
        )


class BetView(discord.ui.View):
    def __init__(self, embed: discord.Embed, roulette: Roulette) -> None:
        """Create an interactive view for placing bets."""
        super().__init__()
        self.embed = embed
        self.roulette = roulette
        self.already_interact: set[discord.Member] = set()

    def disable(self) -> None:
        """Disable the selection UI."""
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
        """Handle the player's bet selection."""
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
        await self.roulette.bet(user, bet)
        embeds = interaction.message.embeds
        assert self.embed.description is not None  # noqa: S101
        self.embed.description += (
            f"\n> {interaction.user.mention} a parié {bet.label} {bet.emoji}"
        )
        await interaction.response.edit_message(embeds=[embeds[0], self.embed])


class RouletteManager:
    def __init__(self, bot: Easterobot) -> None:
        """Main manager for roulette game logic."""
        self.bot = bot

    async def run(
        self,
        source: Union[discord.Message, discord.TextChannel],
    ) -> None:
        """Run a full roulette session."""
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
            roulette = Roulette(locker)
            embed = discord.Embed(
                description=(
                    "# Événement Casino : Roulette"
                    "\nLe Casino vous ouvre exceptionnellement ses portes. "
                    "Devant vous se trouve un élégant croupier lapin. "
                    "Il vous fixe droit dans les yeux "
                    "et prononce de simples mots en langue lapinique. "
                    "Magiquement, vous semblez comprendre : 'Faites vos jeux'."
                    "\n\n-# Faites attention, "
                    "il annoncera sans doute la fin d'ici peu."
                ),
                color=0x00FF00,
            )
            text = discord.Embed(
                description="### Annonces du croupier\n> Faites vos jeux",
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
            await sleep(self.bot.config.casino.roulette.duration)
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
            egg_text = agree("œeuf", "œufs", bet.bet)
            messages.append(f"{member.mention} gagne {bet.bet} {egg_text}")
        for member, bet in result.losers.items():
            egg_text = agree("œeuf", "œufs", bet.bet)
            messages.append(f"{member.mention} perd {bet.bet} {egg_text}")
        if messages:
            await sleep(5)
            await message.reply(  # type: ignore[call-overload]
                content="\n".join(messages),
                view=None,
            )
