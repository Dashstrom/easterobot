"""Start a run."""

import asyncio
import logging
import time
from collections.abc import Awaitable
from datetime import datetime, timezone
from typing import (
    Any,
    Callable,
    Optional,
)

import discord
from discord.ext import commands
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.bot import Easterobot
from easterobot.config import (
    RAND,
    agree,
)
from easterobot.models import Egg, Hunt

logger = logging.getLogger(__name__)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class HuntCog(commands.Cog):
    def __init__(self, bot: Easterobot) -> None:
        """Instantiate HuntCog."""
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Handle ready event, can be trigger many time if disconnected."""
        # Unlock all eggs
        logger.info("Unlock all previous eggs")
        async with AsyncSession(self.bot.engine) as session:
            await session.execute(
                update(Egg).where(Egg.lock).values(lock=False)
            )
            await session.commit()

        # Start hunt
        logger.info("Start hunt handler")
        pending_hunts: set[asyncio.Task[Any]] = set()
        while True:
            if pending_hunts:
                try:
                    _, pending_hunts = await asyncio.wait(
                        pending_hunts, timeout=1
                    )
                except Exception as err:  # noqa: BLE001
                    logger.critical("Unattended exception", exc_info=err)
            await asyncio.sleep(5)
            pending_hunts.add(asyncio.create_task(self.loop_hunt()))

    async def start_hunt(  # noqa: C901, PLR0912, PLR0915
        self,
        hunt_id: int,
        description: str,
        *,
        member_id: Optional[int] = None,
        send_method: Optional[
            Callable[..., Awaitable[discord.Message]]
        ] = None,
    ) -> None:
        """Start an hunt in a channel."""
        # Get the hunt channel of resolve it
        channel = await self.bot.resolve_channel(hunt_id)
        if not channel:
            return
        guild = channel.guild

        # Get from config
        action = self.bot.config.action.rand()
        emoji = self.bot.egg_emotes.rand()

        # Label and hunters
        hunters: list[discord.Member] = []
        label = action.text
        if member_id is not None:
            member = channel.guild.get_member(member_id)
            if member:
                hunters.append(member)
                label += " (1)"

        # Start hunt
        logger.info("Start hunt in %s", channel.jump_url)
        timeout = self.bot.config.hunt.timeout + 1
        view = discord.ui.View(timeout=timeout)
        button: discord.ui.Button[Any] = discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.primary,
            emoji=emoji,
        )
        view.add_item(button)
        lock_update = asyncio.Lock()

        async def button_callback(
            interaction: discord.Interaction[Any],
        ) -> None:
            # Respond later
            await interaction.response.defer()
            message = interaction.message
            user = interaction.user
            if (
                message is None  # Message must be loaded
                or not isinstance(user, discord.Member)  # Must be a member
            ):
                logger.warning("Invalid callback for %s", guild)
                return
            # Check if user doesn't already claim the egg
            for hunter in hunters:
                if hunter.id == user.id:
                    logger.info(
                        "Already hunt by %s (%s) on %s",
                        user,
                        user.id,
                        message.jump_url,
                    )
                    return

            # Add the user to the current users
            hunters.append(user)

            # Show information about the hunter
            logger.info(
                "Hunt (%d) by %s (%s) on %s",
                len(hunters),
                user,
                user.id,
                message.jump_url,
            )

            # Update button counter
            async with lock_update:
                button.label = action.text + f" ({len(hunters)})"
                await message.edit(view=view)

        # Set the button callback
        button.callback = button_callback  # type: ignore[method-assign]

        # Set next hunt
        next_hunt = time.time() + timeout

        # Create and embed
        emb = embed(
            title="Un œuf a été découvert !",
            description=description
            + f"\n\nTirage du vainqueur : <t:{next_hunt:.0f}:R>",
            thumbnail=emoji.url,
        )

        # Send the embed in the hunt channel
        if send_method is None:
            message = await channel.send(embed=emb, view=view)
        else:
            message = await send_method(embed=emb, view=view)

        # TODO(dashstrom): channel is wrong due to the send message !
        # TODO(dashstrom): Why wait if timeout ???
        # Wait the end of the hunt
        message_url = f"{channel.jump_url}/{message.id}"
        async with channel.typing():
            try:
                await asyncio.wait_for(
                    view.wait(), timeout=self.bot.config.hunt.timeout
                )
            except asyncio.TimeoutError:
                logger.info("End hunt for %s", message_url)

        # Disable button and view after hunt
        button.disabled = True
        view.stop()
        await message.edit(view=view)  # Send the stop info

        # Get if hunt is valid
        async with AsyncSession(self.bot.engine) as session:
            has_hunt = await session.scalar(
                select(Hunt).where(
                    and_(
                        Hunt.guild_id == guild.id,
                        Hunt.channel_id == channel.id,
                    )
                )
            )

        # The egg was not collected
        if not hunters or not has_hunt:
            button.label = "L'œuf n'a pas été ramassé"
            button.style = discord.ButtonStyle.danger
            logger.info("No Hunter for %s", message_url)
        else:
            # Process the winner
            async with AsyncSession(self.bot.engine) as session:
                # Get the count of egg by user
                res = await session.execute(
                    select(Egg.user_id, func.count().label("count"))
                    .where(
                        and_(
                            Egg.guild_id == guild.id,
                            Egg.user_id.in_(hunter.id for hunter in hunters),
                        )
                    )
                    .group_by(Egg.user_id)
                )
                eggs: dict[int, int] = dict(res.all())  # type: ignore[arg-type]
                logger.info("Winner draw for %s", message_url)

                ranked_hunters = self.rank_players(hunters, eggs)
                if len(ranked_hunters) == 1:
                    winner = ranked_hunters[0]
                    loser = None
                else:
                    winner = ranked_hunters[0]
                    loser = ranked_hunters[1]

                    if RAND.random() < self.bot.config.hunt.game:
                        # TODO(dashstrom): edit timer during dual
                        # Update button
                        button.label = "Duel en cours ..."
                        button.style = discord.ButtonStyle.gray

                        # Remove emoji and edit view
                        await message.edit(view=view)
                        duel_winner = await self.bot.game.dual(
                            channel=channel,
                            reference=message,
                            user1=winner,
                            user2=loser,
                        )
                        if duel_winner is None:
                            winner = None
                            loser = None
                        elif duel_winner == loser:
                            winner, loser = loser, winner

                if winner:
                    # Add the egg to the member
                    session.add(
                        Egg(
                            channel_id=channel.id,
                            guild_id=channel.guild.id,
                            user_id=winner.id,
                            emoji_id=emoji.id,
                        )
                    )
                    await session.commit()

            # Show the embed to loser
            if loser:
                loser_name = loser.display_name
                if len(hunters) == 2:  # noqa: PLR2004
                    text = f"{loser_name} rate un œuf"
                else:
                    text = agree(
                        "{1} et {0} autre chasseur ratent un œuf",
                        "{1} et {0} autres chasseurs ratent un œuf",
                        len(hunters) - 2,
                        loser_name,
                    )
                emb = embed(
                    title=text,
                    description=action.fail.text(loser),
                    image=action.fail.gif,
                )
                await channel.send(
                    embed=emb,
                    reference=message,
                    delete_after=60,
                )

            if winner:
                # Send embed for the winner
                winner_eggs = eggs.get(winner.id, 0) + 1
                emb = embed(
                    title=f"{winner.display_name} récupère un œuf",
                    description=action.success.text(winner),
                    image=action.success.gif,
                    thumbnail=emoji.url,
                    egg_count=winner_eggs,
                )
                await channel.send(embed=emb, reference=message)

                # Update button
                button.label = f"L'œuf a été ramassé par {winner.display_name}"
                button.style = discord.ButtonStyle.success
                logger.info(
                    "Winner is %s (%s) with %s",
                    winner,
                    winner.id,
                    agree("{0} egg", "{0} eggs", winner_eggs),
                )
            else:
                button.label = "L'œuf a été cassé"
                button.style = discord.ButtonStyle.danger
                logger.info("No winner %s", message_url)

        # Remove emoji and edit view
        button.emoji = None
        await message.edit(view=view)

    def rank_players(
        self, hunters: list[discord.Member], eggs: dict[int, int]
    ) -> list[discord.Member]:
        """Get a random working of player.

        Use their egg and the order of hunt join.
        """
        # If only one hunter, give the egg to him
        if len(hunters) <= 1:
            return hunters
        lh = len(hunters)

        # Get egg difference
        min_eggs = min(eggs.values(), default=0)
        max_eggs = max(eggs.values(), default=0)
        diff_eggs = max_eggs - min_eggs

        # Normalize weights
        w_egg = self.bot.config.hunt.weights.egg
        w_speed = self.bot.config.hunt.weights.speed
        w_base = self.bot.config.hunt.weights.base
        w = w_egg + w_speed + w_base
        w_egg /= w
        w_speed /= w
        w_base /= w

        # Weights by hunters
        weights = []

        # Compute chances of each hunters
        for i, h in enumerate(hunters):
            p_base = 1
            if diff_eggs != 0:
                egg = eggs.get(h.id, 0) - min_eggs
                p_egg = 1 - egg / diff_eggs
            else:
                p_egg = 1.0

            p_speed = 1 - i / lh
            w = p_base * w_base + p_speed * w_speed + p_egg * w_egg
            weights.append(w)

        # Normalize final probabilities
        r = sum(weights)
        weights = [p / r for p in weights]
        for h, w in zip(hunters, weights):
            logger.info("%.2f%% - %s (%s)", w * 100, h, h.id)

        rankings = []
        choices_hunters = list(hunters)
        while choices_hunters:
            # Get the winner
            (hunter,) = RAND.choices(choices_hunters, weights)
            index = choices_hunters.index(hunter)
            del choices_hunters[index]
            del weights[index]
            rankings.append(hunter)
        return rankings

    async def loop_hunt(self) -> None:
        """Manage the schedule of run."""
        # Create a async session
        async with AsyncSession(
            self.bot.engine, expire_on_commit=False
        ) as session:
            # Find hunt with next egg available
            now = time.time()
            hunts = (
                await session.scalars(select(Hunt).where(Hunt.next_egg <= now))
            ).all()

            # For each hunt, set the next run and store the channel ids
            if hunts:
                for hunt in hunts:
                    delta = self.bot.config.hunt.cooldown.rand()
                    if self.bot.config.in_sleep_hours():
                        delta *= self.bot.config.sleep.divide_hunt
                    next_egg = now + delta
                    dt_next = datetime.fromtimestamp(next_egg, tz=timezone.utc)
                    logger.info(
                        "Next hunt at %s on %s",
                        hunt.jump_url,
                        dt_next.strftime(DATE_FORMAT),
                    )
                    hunt.next_egg = next_egg
                await session.commit()
            hunt_ids = [hunt.channel_id for hunt in hunts]

        # Call start_hunt for each hunt
        if hunt_ids:
            try:
                await asyncio.gather(
                    *[
                        self.start_hunt(hunt_id, self.bot.config.appear.rand())
                        for hunt_id in hunt_ids
                    ]
                )
            except Exception as err:
                logger.exception(
                    "An error occurred during start hunt", exc_info=err
                )


def embed(  # noqa: PLR0913
    *,
    title: str,
    description: Optional[str] = None,
    image: Optional[str] = None,
    thumbnail: Optional[str] = None,
    egg_count: Optional[int] = None,
    footer: Optional[str] = None,
) -> discord.Embed:
    """Create an embed with default format."""
    new_embed = discord.Embed(
        title=title,
        description=description,
        colour=RAND.randint(0, 1 << 24),
        type="gifv" if image else "rich",
    )
    if image is not None:
        new_embed.set_image(url=image)
    if thumbnail is not None:
        new_embed.set_thumbnail(url=thumbnail)
    if egg_count is not None:
        footer = (footer + " - ") if footer else ""
        footer += "Cela lui fait un total de "
        footer += agree("{0} œuf", "{0} œufs", egg_count)
    if footer:
        new_embed.set_footer(text=footer)
    return new_embed
