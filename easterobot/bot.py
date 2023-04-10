"""Main program."""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from traceback import print_exc
from typing import Any, Dict, List, Optional, TypeVar, cast

import discord
import discord.ext.tasks
import humanize
from sqlalchemy import (
    and_,
    create_engine,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.orm import Session

from .config import (
    Config,
    agree,
    rand,
)
from .models import Base, Hunt, Hunter, Egg

T = TypeVar("T")


HERE = Path(__file__).parent
DEFAULT_CONFIG_PATH = HERE / "data" / "config.yml"

egg_command_group = discord.SlashCommandGroup(
    "egg", "Commandes en lien avec Pâque."
)


class Easterbot(discord.Bot):
    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        super().__init__(
            "Amazing bot", activity=discord.Game(name="rechercher des œufs")
        )
        self.config = Config(config_path)
        if self.config.token is None:
            raise TypeError("Missing TOKEN in configuration")
        self.engine = create_engine(self.config.database, echo=True)
        Base.metadata.create_all(self.engine, checkfirst=True)
        self.add_application_command(egg_command_group)
        self.run(self.config.token)

    async def on_ready(self) -> None:
        await self.config.load(client=self)
        self.loop_hunt.start()
        print(f"Logged on as {self.user}!")

    def embed(
        self,
        *,
        title: str,
        description: str,
        url: Optional[str] = None,
        emoji: Optional[discord.Emoji] = None,
        egg_count: Optional[int] = None,
        footer: Optional[str] = None,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            colour=rand.randint(0, 1 << 24),
            type="gifv" if url else "rich",
        )
        if url is not None:
            embed.set_image(url=url)
        if emoji is not None:
            embed.set_thumbnail(url=emoji.url)
        if egg_count is not None:
            footer = (footer + " - ") if footer else ""
            footer += "Cela lui fait un total de "
            footer += agree("{0} œuf", "{0} œufs", egg_count)
        if footer:
            embed.set_footer(text=footer)
        return embed

    async def start_hunt(
        self,
        hunt_id: int,
        description: str,
        *,
        member_id: Optional[int] = None,
        send_method: Any = None,
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
        print(f"Start hunt in {channel}")
        action = self.config.action()
        guild = channel.guild
        emoji = await self.config.emoji()
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
            message = interaction.message
            user = interaction.user
            if (
                message is None
                or user is None
                or isinstance(user, discord.User)
            ):
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
                hunters.append(member)
                button.label += " (1)"

        timeout = humanize.naturaldelta(self.config.hunt_timeout())
        embed = self.embed(
            title="Un œuf a été découvert !",
            description=description,
            emoji=emoji,
            footer=f"Vous avez {timeout} pour réagir",
        )

        if send_method is None:
            message = await channel.send(embed=embed, view=view)
        else:
            message = await send_method(embed=embed, view=view)
        async with channel.typing():
            await view.wait()

        with Session(self.engine) as session:
            has_hunt = session.scalar(  # type: ignore
                select(Hunt).where(
                    and_(
                        Hunt.guild_id == guild.id,
                        Hunt.channel_id == channel.id,
                    )
                )
            )
        if hunters and has_hunt:
            winner = None
            hunters_id = [hunter.id for hunter in hunters]
            with Session(self.engine) as session:
                eggs: Dict[int, int] = dict(
                    session.execute(  # type: ignore
                        select(
                            Egg.user_id, func.count(Egg.user_id).label("count")
                        )
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
                        percent = max(
                            1 - eggs.get(hunter.id, 0) / egg_total, 0.1
                        )
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
            pending = []
            for hunter in hunters:
                embed = self.embed(
                    title=f"{hunter.nick or hunter.name} rate un œuf",
                    description=action.fail_text(hunter),
                    url=action.fail_gif(),
                    egg_count=eggs.get(hunter.id, 0),
                )
                pending.append(channel.send(embed=embed, reference=message))

            winner_name = winner.nick or winner.name
            embed = self.embed(
                title=f"{winner_name} récupère un œuf",
                description=action.success_text(hunter),
                url=action.success_gif(),
                emoji=emoji,
                egg_count=eggs.get(winner.id, 0) + 1,
            )
            pending.append(channel.send(embed=embed, reference=message))
            await asyncio.gather(*pending)
            button.label = f"L'œuf a été ramassé par {winner_name}"
            button.style = discord.ButtonStyle.success
        else:
            button.label = "L'œuf n'a pas été ramassé"
            button.style = discord.ButtonStyle.danger
        button.emoji = None
        view.disable_all_items()
        view.stop()
        await message.edit(view=view)

    @discord.ext.tasks.loop(seconds=5.0)
    async def loop_hunt(self) -> None:
        with Session(self.engine) as session:
            now = datetime.utcnow().timestamp()
            hunts = session.scalars(
                select(Hunt).where(Hunt.next_egg <= now)
            ).all()
            if hunts:
                cooldown = self.config.hunt_cooldown()
                print(f"Next in {cooldown} seconds")
                session.execute(
                    update(Hunt)
                    .where(
                        Hunt.channel_id.in_(
                            [hunt.channel_id for hunt in hunts]
                        )
                    )
                    .values(next_egg=now + cooldown)
                )
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


class ApplicationContext(discord.ApplicationContext):
    bot: Easterbot


@egg_command_group.command(description="Remise à zero.")
@discord.default_permissions(administrator=True)
@discord.guild_only()
async def reset(ctx: ApplicationContext) -> None:
    await ctx.defer()
    with Session(ctx.bot.engine) as session:
        session.execute(delete(Hunt).where(Hunt.guild_id == ctx.guild_id))
        session.commit()
        await asyncio.sleep(10)
        session.execute(delete(Egg).where(Egg.guild_id == ctx.guild_id))
        session.execute(delete(Hunter).where(Hunter.guild_id == ctx.guild_id))
        session.commit()
        await ctx.followup.send(
            embed=ctx.bot.embed(
                title="Réinitialisation",
                description=(
                    "L'ensemble des salons, œufs "
                    "et temps d'attentes ont été réinitialisatié."
                ),
            )
        )


@egg_command_group.command(description="Active la chasse l'œuf dans le salon.")
@discord.default_permissions(manage_channels=True)
@discord.guild_only()
async def enable(ctx: ApplicationContext) -> None:
    with Session(ctx.bot.engine) as session:
        old = session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )
        if old:
            await ctx.respond("Chasse à l'œuf déjà activée", ephemeral=True)
        else:
            session.add(
                Hunt(
                    channel_id=ctx.channel.id,
                    guild_id=ctx.guild_id,
                    next_egg=0,
                )
            )
            session.commit()
            await ctx.respond("Chasse à l'œuf activée", ephemeral=True)


@egg_command_group.command(
    description="Désactive la chasse l'œuf dans le salon."
)
@discord.default_permissions(manage_channels=True)
@discord.guild_only()
async def disable(ctx: ApplicationContext) -> None:
    with Session(ctx.bot.engine) as session:
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


@egg_command_group.command(description="Regarder le contenu de votre panier.")
@discord.guild_only()
async def basket(ctx: ApplicationContext) -> None:
    author = cast(discord.Member, ctx.author)
    with Session(ctx.bot.engine) as session:
        hunt = session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )

    if hunt is None:
        await ctx.respond(
            "La chasse à l'œuf n'est pas activé dans ce salon",
            ephemeral=True,
        )
        return
    with Session(ctx.bot.engine) as session:
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
        none_emoji = 0
        morsels = []
        for egg in egg_counts:
            emoji = ctx.bot.get_emoji(egg[0])
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
            text="Cela lui fait un total de "
            + agree("{0} œuf", "{0} œufs", egg_count)
        )
        await ctx.respond(embed=embed)


@egg_command_group.command(description="Rechercher un œuf.")
@discord.guild_only()
async def search(ctx: ApplicationContext) -> None:
    author = cast(discord.Member, ctx.author)
    with Session(ctx.bot.engine) as session:
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
        cd = ctx.bot.config.search_cooldown()

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
    if ctx.bot.config.search_rate_discovered() < rand.random():
        if ctx.bot.config.search_rate_spoted() < rand.random():

            async def send_method(*args, **kwargs):
                interaction = await ctx.respond(*args, **kwargs)
                return await interaction.original_response()

            await ctx.bot.start_hunt(
                ctx.channel_id,
                ctx.bot.config.spotted(author),
                member_id=author.id,
                send_method=send_method,
            )
        else:
            emoji = await ctx.bot.config.emoji()
            with Session(ctx.bot.engine) as session:
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
                description=ctx.bot.config.hidden(author),
                colour=rand.randint(0, 1 << 24),
            )
            embed.set_thumbnail(url=emoji.url)
            embed.set_footer(
                text="Cela lui fait un total de "
                + agree("{0} œuf", "{0} œufs", egg_count)
            )
            await ctx.respond(embed=embed)
    else:
        embed = discord.Embed(
            title=f"{name} repart bredouille",
            description=ctx.bot.config.failed(author),
            colour=rand.randint(0, 1 << 24),
        )
        await ctx.respond(embed=embed)
