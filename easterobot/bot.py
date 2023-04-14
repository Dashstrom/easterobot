"""Main program."""
import asyncio
from datetime import datetime
from pathlib import Path
from traceback import print_exc
from typing import Awaitable, Callable, Dict, List, Optional, TypeVar, cast

import discord
import discord.ext.tasks
import humanize
from sqlalchemy import and_, create_engine, func, select
from sqlalchemy.orm import Session

from .config import RAND, Config, agree
from .logger import DATE_FORMAT, logger
from .models import Base, Egg, Hunt

T = TypeVar("T")


HERE = Path(__file__).parent
DEFAULT_CONFIG_PATH = HERE / "data" / "config.yml"


class Easterbot(discord.Bot):
    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        super().__init__(  # type: ignore
            description="Bot discord pour faire la chasse aux œufs",
            activity=discord.Game(name="rechercher des œufs"),
        )
        self.config = Config(config_path)

        if self.config.token is None:
            raise TypeError("Missing TOKEN in configuration")
        self.engine = create_engine(self.config.database, echo=False)
        Base.metadata.create_all(self.engine, checkfirst=True)
        self.load_extension(
            "easterobot.commands", package="easterobot.commands.__init__"
        )
        self.run(self.config.token)

    async def on_ready(self) -> None:
        await self.config.load(client=self)
        self.loop_hunt.start()
        logger.info(
            "Logged on as %s (%s) !",
            self.user,
            getattr(self.user, "id", "unknow"),
        )

    async def start_hunt(
        self,
        hunt_id: int,
        description: str,
        *,
        member_id: Optional[int] = None,
        send_method: Optional[
            Callable[..., Awaitable[discord.Message]]
        ] = None,
    ) -> None:
        channel = cast(discord.TextChannel, self.get_channel(hunt_id))
        if channel is None:
            channel = cast(
                discord.TextChannel, await self.fetch_channel(hunt_id)
            )
        if (
            not hasattr(channel, "guild")
            or channel.guild is None
            or not isinstance(channel, discord.TextChannel)
        ):
            return
        action = self.config.action()
        guild = channel.guild
        emoji = self.config.emoji()
        logger.info("Start hunt in %s", channel.jump_url)
        view = discord.ui.View(timeout=self.config.hunt_timeout())
        button = discord.ui.Button(  # type: ignore
            label=action.text(),
            style=discord.ButtonStyle.primary,
            emoji=emoji,
        )
        view.add_item(button)
        hunters: List[discord.Member] = []
        waiting = False
        active = False

        async def button_callback(
            interaction: discord.Interaction,
        ) -> None:
            nonlocal waiting, active
            await interaction.response.defer()
            logger.info(
                "Hunt (%d) by %s (%s) on %s",
                len(hunters),
                interaction.user,
                getattr(interaction.user, "id", "unkown"),
                getattr(interaction.message, "jump_url", interaction.guild_id),
            )
            message = interaction.message
            user = interaction.user
            if (
                message is None
                or user is None
                or isinstance(user, discord.User)
            ):
                return
            # Don't update if hunters already click
            for hunter in hunters:
                if hunter.id == user.id:
                    return
            hunters.append(user)
            if active and not waiting:
                waiting = True
                while active:
                    await asyncio.sleep(0.01)
                waiting = False

            active = True
            button.label = action.text() + f" ({len(hunters)})"
            await message.edit(view=view)
            active = False

        button.callback = button_callback  # type: ignore
        if member_id is not None:
            member = channel.guild.get_member(member_id)
            if member:
                hunters.append(member)
                button.label += " (1)"  # type: ignore

        timeout = humanize.naturaldelta(self.config.hunt_timeout())
        emb = embed(
            title="Un œuf a été découvert !",
            description=description,
            thumbnail=emoji.url,
            footer=f"Vous avez {timeout} pour réagir",
        )

        if send_method is None:
            message = await channel.send(embed=emb, view=view)
        else:
            message = await send_method(embed=emb, view=view)
        message_url = f"{channel.jump_url}/{message.id}"
        async with channel.typing():
            try:
                await asyncio.wait_for(
                    view.wait(), timeout=self.config.hunt_timeout() + 3
                )
            except asyncio.TimeoutError:
                logger.warning("Timeout for %s", message_url)

        with Session(self.engine) as session:
            has_hunt = session.scalar(
                select(Hunt).where(
                    and_(
                        Hunt.guild_id == guild.id,
                        Hunt.channel_id == channel.id,
                    )
                )
            )
        pending = []
        if not hunters or not has_hunt:
            button.label = "L'œuf n'a pas été ramassé"
            button.style = discord.ButtonStyle.danger
            logger.info("No Hunter for %s", message_url)
        else:
            with Session(self.engine) as session:
                eggs: Dict[int, int] = dict(
                    session.execute(  # type: ignore
                        select(Egg.user_id, func.count().label("count"))
                        .where(
                            and_(
                                Egg.guild_id == guild.id,
                                Egg.user_id.in_(
                                    hunter.id for hunter in hunters
                                ),
                            )
                        )
                        .group_by(Egg.user_id)
                    ).all()
                )
                logger.info("Winner draw for %s", message_url)
                if len(hunters) == 1:
                    winner = hunters[0]
                    loser = None
                    logger.info("100%% - %s (%s)", winner, winner.id)
                else:
                    lh = len(eggs)
                    minh = min(eggs.values())
                    maxh = max(eggs.values()) - minh
                    w_egg = self.config.hunt_weight_egg()
                    w_speed = self.config.hunt_weight_speed()
                    weigths = []
                    for i, h in enumerate(hunters, start=1):
                        if maxh != 0:
                            egg = eggs.get(h.id, 0) - minh
                            p_egg = (1 - egg / maxh) * w_egg + 1 - w_egg
                        else:
                            p_egg = 1.0
                        p_speed = (1 - i / lh) * w_speed + 1 - w_speed
                        weigths.append(p_egg * p_speed)
                    r = sum(weigths)
                    chances = [(h, p / r) for h, p in zip(hunters, weigths)]
                    for h, c in chances:
                        logger.info("%.2f%% - %s (%s)", c * 100, h, h.id)
                    n = RAND.random()
                    for h, p in chances:
                        if n < p:
                            winner = h
                            break
                        else:
                            n -= p
                    else:
                        winner = hunters[-1]
                    hunters.remove(winner)
                    loser = RAND.choice(hunters)

                session.add(
                    Egg(
                        channel_id=channel.id,
                        guild_id=channel.guild.id,
                        user_id=winner.id,
                        emoji_id=emoji.id,
                    )
                )
                session.commit()
            if loser:
                loser_name = loser.nick or loser.name
                if len(hunters) == 1:
                    text = f"{loser_name} rate un œuf"
                else:
                    text = agree(
                        "{1} et {0} autre chasseur ratent un œuf",
                        "{1} et {0} autres chasseurs ratent un œuf",
                        len(hunters) - 1,
                        loser_name,
                    )
                emb = embed(
                    title=text,
                    description=action.fail_text(loser),
                    image=action.fail_gif(),
                )
                pending.append(channel.send(embed=emb, reference=message))

            winner_name = winner.nick or winner.name
            winner_eggs = eggs.get(winner.id, 0) + 1
            emb = embed(
                title=f"{winner_name} récupère un œuf",
                description=action.success_text(winner),
                image=action.success_gif(),
                thumbnail=emoji.url,
                egg_count=winner_eggs,
            )
            pending.append(channel.send(embed=emb, reference=message))
            button.label = f"L'œuf a été ramassé par {winner_name}"
            button.style = discord.ButtonStyle.success
            logger.info(
                "Winner is %s (%s) with %s",
                winner,
                winner.id,
                agree("{0} egg", "{0} eggs", winner_eggs),
            )
        button.emoji = None
        view.disable_all_items()
        view.stop()
        pending.append(message.edit(view=view))
        await asyncio.gather(*pending)

    @discord.ext.tasks.loop(seconds=5.0)
    async def loop_hunt(self) -> None:
        with Session(self.engine) as session:
            now = datetime.now().timestamp()
            hunts = session.scalars(
                select(Hunt).where(Hunt.next_egg <= now)
            ).all()
            if hunts:
                for hunt in hunts:
                    next_egg = now + self.config.hunt_cooldown()
                    dt_next = datetime.fromtimestamp(next_egg)
                    logger.info(
                        "Next hunt at %s on %s",
                        hunt.jump_url,
                        dt_next.strftime(DATE_FORMAT),
                    )
                    hunt.next_egg = next_egg
                session.commit()
                try:
                    await asyncio.gather(
                        *[
                            self.start_hunt(
                                hunt.channel_id, self.config.appear()
                            )
                            for hunt in hunts
                        ]
                    )
                except Exception:
                    print_exc()


def embed(
    *,
    title: str,
    description: Optional[str] = None,
    image: Optional[str] = None,
    thumbnail: Optional[str] = None,
    egg_count: Optional[int] = None,
    footer: Optional[str] = None,
) -> discord.Embed:
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
