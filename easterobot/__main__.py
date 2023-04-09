"""Main program."""
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from traceback import print_exc
from typing import Any, Dict, List, Optional, TypeVar, cast

import click
import discord
import discord.ext.commands
import discord.ext.tasks
import discord.utils
import humanize
import yaml
from dotenv import load_dotenv
from sqlalchemy import (
    Engine,
    and_,
    create_engine,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


T = TypeVar("T")

HERE = Path(__file__).parent
DEFAULT_CONFIG_PATH = HERE / "data" / "config.yml"
DEFAULT_DB_PATH = HERE / "data" / "esterobot.sqlite"
DEFAULT_DB_URI = f"sqlite:///{DEFAULT_DB_PATH.resolve()}"


class Action:
    """Represent a possible action."""

    def __init__(self, data: Any, conf: "Config") -> None:
        self._data = data
        self._config = conf

    def text(self) -> str:
        """Text used to describe action."""
        return cast(str, self._data["text"])

    def fail_text(self, member: discord.Member) -> str:
        """Text to print if action is failed."""
        return self._config.conjugate(
            self._data.get("fail", {}).get("text", ""), member
        )

    def fail_gif(self) -> str:
        """Gif to print if action is failed."""
        return cast(str, self._data.get("fail", {}).get("gif", ""))

    def success_text(self, member: discord.Member) -> str:
        """Text to print if action is success."""
        return self._config.conjugate(
            self._data.get("success", {}).get("text", ""), member
        )

    def success_gif(self) -> str:
        """Gif to print if action is success."""
        return cast(str, self._data.get("success", {}).get("gif", ""))


class Config:
    def __init__(self) -> None:
        with DEFAULT_CONFIG_PATH.open("r", encoding="utf8") as file:
            self._data = yaml.safe_load(file)
        self._emojis: List[discord.Emoji] = []

    @property
    def emojis_guild_id(self) -> int:
        return cast(int, self._data["emojis_guild_id"])

    def search_rate_discovered(self) -> float:
        return cast(
            float,
            min(max(self._data["search"]["rate"]["discovered"], 0.0), 1.0),
        )

    def search_rate_spoted(self) -> float:
        return cast(
            float, min(max(self._data["search"]["rate"]["spotted"], 0.0), 1.0)
        )

    def search_cooldown(self) -> float:
        return cast(float, self._data["search"]["cooldown"])

    def hunt_cooldown(self) -> float:
        min_ = self._data["hunt"]["cooldown"]["min"]
        max_ = self._data["hunt"]["cooldown"]["max"]
        min_, max_ = min(min_, max_), max(min_, max_)
        return cast(float, min_ + rand.random() * (max_ - min_))

    def hunt_timeout(self) -> float:
        return cast(float, self._data["hunt"]["timeout"])

    @property
    def woman_id(self) -> int:
        return cast(int, self._data["woman_id"])

    async def emoji(self) -> discord.Emoji:
        if not self._emojis:
            guild = await client.fetch_guild(config.emojis_guild_id)
            self._emojis = await guild.fetch_emojis()
        return rand.choice(self._emojis)

    def action(self) -> Action:
        return Action(rand.choice(self._data["action"]), self)

    def appear(self) -> str:
        return cast(str, rand.choice(self._data["appear"]))

    def spotted(self, member: discord.Member) -> str:
        return self.conjugate(rand.choice(self._data["spotted"]), member)

    def hidden(self, member: discord.Member) -> str:
        return self.conjugate(rand.choice(self._data["hidden"]), member)

    def failed(self, member: discord.Member) -> str:
        return self.conjugate(rand.choice(self._data["failed"]), member)

    def conjugate(self, text: str, member: discord.Member) -> str:
        if any(
            role.name.lower() in ("woman", "girl", "femme", "fille")
            for role in member.roles
        ):
            key = "woman"
        else:
            key = "man"
        for term, versions in self._data["conjugate"].items():
            word = versions.get(key, "")
            text = text.replace("{" + term.lower() + "}", word.lower())
            text = text.replace("{" + term.upper() + "}", word.upper())
            text = text.replace("{" + term.title() + "}", word.title())
        text = text.replace("{user}", f"<@{member.id}>")
        return text


class Base(DeclarativeBase):
    pass


class Egg(Base):
    __tablename__ = "egg"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(primary_key=False)
    channel_id: Mapped[int] = mapped_column(primary_key=False)
    user_id: Mapped[int] = mapped_column(nullable=False)
    emoji_id: Mapped[int] = mapped_column(nullable=False)
    message_id: Mapped[Optional[int]] = mapped_column(
        nullable=True, default=None
    )


class Hunt(Base):
    __tablename__ = "hunt"
    channel_id: Mapped[int] = mapped_column(primary_key=True)
    next_egg: Mapped[float] = mapped_column(default=0.0)


class Hunter(Base):
    __tablename__ = "hunter"
    user_id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(primary_key=True)
    last_search: Mapped[float] = mapped_column(default=0.0)


engine: Engine
client = discord.Bot(activity=discord.Game(name="rechercher des œufs"))
config = Config()
rand = random.SystemRandom()
humanize.i18n.activate("fr_FR")


@client.event
async def on_ready() -> None:
    print(f"Logged on as {client.user}!")
    await config.emoji()
    loop_hunt.start()


async def start_hunt(
    hunt_id: int,
    text: str,
    *,
    member_id: Optional[int] = None,
    send_method: Any = None,
) -> None:
    channel = cast(discord.TextChannel, client.get_channel(hunt_id))
    if channel is None:
        channel = cast(
            discord.TextChannel, await client.fetch_channel(hunt_id)
        )
    if (
        not hasattr(channel, "guild")
        or channel.guild is None
        or not isinstance(channel, discord.TextChannel)
    ):
        return
    print(f"Start hunt in {channel}")
    action = config.action()
    guild = channel.guild
    emoji = await config.emoji()
    view = discord.ui.View(timeout=config.hunt_timeout())
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
        message = interaction.message
        user = interaction.user
        if message is None or user is None or isinstance(user, discord.User):
            return
        for hunter in hunters:
            if hunter.id == user.id:
                break
        else:
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
            hunters.append()
            button.label += " (1)"

    embed = discord.Embed(
        title="Un œuf a été découvert !",
        description=text,
        colour=rand.randint(0, 1 << 24),
    )
    embed.set_thumbnail(url=emoji.url)
    timeout = humanize.naturaldelta(config.hunt_timeout())
    embed.set_footer(text=f"Vous avez {timeout} pour réagir")

    if send_method is None:
        message = await channel.send(embed=embed, view=view)
    else:
        message = await send_method(embed=embed, view=view)
    async with channel.typing():
        await view.wait()

    if hunters:
        winner = None
        hunters_id = [hunter.id for hunter in hunters]
        with Session(engine) as session:
            eggs: Dict[int, int] = dict(
                session.execute(  # type: ignore
                    select(Egg.user_id, func.count(Egg.user_id).label("count"))
                    .where(
                        and_(
                            Egg.guild_id == guild.id,
                            Egg.user_id.in_(hunters_id),
                        )
                    )
                    .group_by(Egg.user_id)
                ).all()
            )
            egg_total = max(sum(eggs.values()), 1)
            while not winner:
                for hunter in hunters:
                    percent = max(1 - eggs.get(hunter.id, 0) / egg_total, 0.1)
                    if rand.random() < percent:
                        winner = hunter
                        break
            hunters.remove(winner)
            rand.shuffle(hunters)
            session.add(
                Egg(
                    channel_id=channel.id,
                    message_id=message.id,
                    guild_id=channel.guild.id,
                    user_id=winner.id,
                    emoji_id=emoji.id,
                )
            )
            session.commit()
        winner_name = winner.nick or winner.name
        pending = []
        for hunter in hunters:
            egg_count = eggs.get(hunter.id, 0)
            embed = discord.Embed(
                title=f"{hunter.nick or hunter.name} rate un œuf",
                description=action.fail_text(hunter),
                colour=rand.randint(0, 1 << 24),
                type="gifv",
            )
            embed.set_image(url=action.fail_gif())
            embed.set_footer(
                text=(
                    f"Cela lui fait un total de {egg_count} "
                    f"œuf{'' if egg_count == 1 else 's'}"
                )
            )
            pending.append(channel.send(embed=embed, reference=message))
        egg_count = eggs.get(winner.id, 0) + 1
        embed = discord.Embed(
            title=f"{winner_name} récupère un œuf",
            description=action.success_text(winner),
            colour=rand.randint(0, 1 << 24),
            type="gifv",
        )
        embed.set_image(url=action.success_gif())
        embed.set_thumbnail(url=emoji.url)
        embed.set_footer(
            text=(
                f"Cela lui fait un total de {egg_count} "
                f"œuf{'' if egg_count == 1 else 's'}"
            )
        )
        pending.append(channel.send(embed=embed, reference=message))
        await asyncio.gather(*pending)
        button.label = f"L'œuf a été ramassé par {winner_name}"
        button.style = discord.ButtonStyle.success
        button.emoji = None
    else:
        button.label = "L'œuf n'a pas été ramassé"
        button.style = discord.ButtonStyle.danger
        button.emoji = None
    view.disable_all_items()
    view.stop()
    await message.edit(view=view)


@discord.ext.tasks.loop(seconds=5.0)
async def loop_hunt() -> None:
    with Session(engine) as session:
        now = datetime.utcnow().timestamp()
        hunts = session.scalars(select(Hunt).where(Hunt.next_egg <= now)).all()
        if hunts:
            cooldown = config.hunt_cooldown()
            print(f"Next in {cooldown} seconds")
            session.execute(
                update(Hunt)
                .where(
                    Hunt.channel_id.in_([hunt.channel_id for hunt in hunts])
                )
                .values(next_egg=now + cooldown)
            )
            session.commit()
            try:
                await asyncio.gather(
                    *[
                        start_hunt(hunt.channel_id, config.appear())
                        for hunt in hunts
                    ]
                )
            except Exception:
                print_exc()


egg_group = discord.SlashCommandGroup("egg", "Commandes en lien avec Pâque.")


@egg_group.command(description="Active la chasse l'œuf dans le salon.")
@discord.default_permissions(manage_channels=True)
@discord.guild_only()
async def enable(ctx: discord.ApplicationContext) -> None:
    with Session(engine) as session:
        old = session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )
        if old:
            await ctx.respond("Chasse à l'œuf déjà activée", ephemeral=True)
        else:
            session.add(Hunt(channel_id=ctx.channel.id, next_egg=0))
            session.commit()
            await ctx.respond("Chasse à l'œuf activée", ephemeral=True)


@egg_group.command(description="Désactive la chasse l'œuf dans le salon.")
@discord.default_permissions(manage_channels=True)
@discord.guild_only()
async def disable(ctx: discord.ApplicationContext) -> None:
    with Session(engine) as session:
        old = session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )
        if old:
            session.execute(
                delete(Hunt).where(Hunt.channel_id == ctx.channel.id)
            )
            session.commit()
            await ctx.respond("Chasse à l'œuf désactivée", ephemeral=True)
        else:
            await ctx.respond("Chasse à l'œuf déjà désactivée", ephemeral=True)


@egg_group.command(description="Regarder le contenu de votre panier.")
@discord.guild_only()
async def basket(ctx: discord.ApplicationContext) -> None:
    author = cast(discord.Member, ctx.author)
    with Session(engine) as session:
        hunt = session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )

    if hunt is None:
        await ctx.respond(
            "La chasse à l'œuf n'est pas activé dans ce salon", ephemeral=True
        )
        return
    with Session(engine) as session:
        egg_counts = list(
            session.execute(  # type: ignore
                select(
                    Egg.emoji_id,
                    func.count().label("count"),
                )
                .where(
                    and_(
                        Egg.guild_id == ctx.guild.id,
                        Egg.user_id == author.id,
                    )
                )
                .group_by(Egg.emoji_id)
            ).all()
        )
        print(egg_counts)
        none_emoji = 0
        morsels = []
        for egg in egg_counts:
            emoji = client.get_emoji(egg[0])
            if emoji is None:
                none_emoji += egg[1]
            else:
                morsels.append(f"{emoji} × {egg[1]}")
        if none_emoji:
            morsels.append(f"🥚 × {none_emoji}")
        if morsels:
            text = "\n".join(morsels)
        else:
            text = "Vous n'avez aucun œuf"
        egg_count = sum(egg[1] for egg in egg_counts)
        embed = discord.Embed(
            title=f"Contenu du panier de {author.nick or author.name}",
            description=text,
            colour=rand.randint(0, 1 << 24),
            type="gifv",
        )
        embed.set_footer(
            text=(
                f"Cela lui fait un total de {egg_count} "
                f"œuf{'' if egg_count == 1 else 's'}"
            )
        )
        await ctx.respond(embed=embed)


@egg_group.command(description="Rechercher un œuf.")
@discord.guild_only()
async def search(ctx: discord.ApplicationContext) -> None:
    author = cast(discord.Member, ctx.author)
    with Session(engine) as session:
        hunt = session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )
        hunter = session.scalar(
            select(Hunter).where(
                and_(
                    Hunter.user_id == author.id,
                    Hunter.guild_id == ctx.guild_id,
                )
            )
        )

        if hunt is None:
            await ctx.respond(
                "La chasse à l'œuf n'est pas activé dans ce salon",
                ephemeral=True,
            )
            return
        if hunter is None:
            last_search = 0.0
        else:
            last_search = hunter.last_search

        dt = datetime.now() - datetime.fromtimestamp(last_search)
        cd = config.search_cooldown()

        if dt.total_seconds() < cd:
            wait = humanize.naturaldelta(timedelta(seconds=cd) - dt)
            await ctx.respond(
                f"Vous devez encore attendre {wait}", ephemeral=True
            )
            return

        session.merge(
            Hunter(
                user_id=author.id,
                guild_id=ctx.guild_id,
                last_search=datetime.now().timestamp(),
            )
        )
        session.commit()

    name = author.nick or author.name
    if config.search_rate_discovered() < rand.random():
        if config.search_rate_spoted() < rand.random():

            async def send_method(*args, **kwargs):
                interaction = await ctx.respond(*args, **kwargs)
                return await interaction.original_response()

            await start_hunt(
                ctx.channel_id,
                config.spotted(author),
                member_id=author.id,
                send_method=send_method,
            )
        else:
            emoji = await config.emoji()
            with Session(engine) as session:
                session.add(
                    Egg(
                        channel_id=ctx.channel.id,
                        message_id=None,
                        guild_id=ctx.channel.guild.id,
                        user_id=author.id,
                        emoji_id=emoji.id,
                    )
                )
                egg_count = session.scalar(  # type: ignore
                    select(
                        func.count(Egg.user_id).label("count"),
                    ).where(
                        and_(
                            Egg.guild_id == ctx.guild.id,
                            Egg.user_id == author.id,
                        )
                    )
                )
                session.commit()
            embed = discord.Embed(
                title=f"{name} récupère un œuf",
                description=config.hidden(author),
                colour=rand.randint(0, 1 << 24),
            )
            embed.set_thumbnail(url=emoji.url)
            embed.set_footer(
                text=(
                    f"Cela lui fait un total de {egg_count} "
                    f"œuf{'' if egg_count == 1 else 's'}"
                )
            )
            await ctx.respond(embed=embed)
    else:
        embed = discord.Embed(
            title=f"{name} repart bredouille",
            description=config.failed(author),
            colour=rand.randint(0, 1 << 24),
        )
        await ctx.respond(embed=embed)


client.add_application_command(egg_group)


@click.command()
def easterobot() -> None:
    global engine
    load_dotenv()
    token = os.environ.get("TOKEN")
    database = os.environ.get("DATABASE")
    if token is None:
        print("Please put TOKEN in env", file=sys.stderr)
        sys.exit(1)
    if database is None:
        DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        database = DEFAULT_DB_URI
    print(database)
    engine = create_engine(database, echo=True)
    Base.metadata.create_all(engine, checkfirst=True)
    client.run(token)


if __name__ == "__main__":
    easterobot()
