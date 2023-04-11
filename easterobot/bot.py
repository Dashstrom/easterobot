"""Main program."""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from traceback import print_exc
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    TypeVar,
    cast,
)

import discord
import discord.ext.tasks
import humanize
from sqlalchemy import and_, create_engine, delete, func, select, update
from sqlalchemy.orm import Session

from .config import Config, agree, rand
from .models import Base, Egg, Hunt, Hunter

T = TypeVar("T")


HERE = Path(__file__).parent
DEFAULT_CONFIG_PATH = HERE / "data" / "config.yml"

egg_command_group = discord.SlashCommandGroup(
    "egg", "Commandes en lien avec Pâque.", guild_only=True
)


class Easterbot(discord.Bot):
    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        super().__init__(  # type: ignore
            description="Bot discord pour faire la chasse aux œufs.",
            activity=discord.Game(name="rechercher des œufs"),
        )
        self.config = Config(config_path)
        if self.config.token is None:
            raise TypeError("Missing TOKEN in configuration")
        self.engine = create_engine(self.config.database, echo=True)
        Base.metadata.create_all(self.engine, checkfirst=True)
        egg_command_group.name = self.config.group
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
        description: Optional[str] = None,
        image: Optional[str] = None,
        thumbnail: Optional[str] = None,
        egg_count: Optional[int] = None,
        footer: Optional[str] = None,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            colour=rand.randint(0, 1 << 24),
            type="gifv" if image else "rich",
        )
        if image is not None:
            embed.set_image(url=image)
        if thumbnail is not None:
            embed.set_thumbnail(url=thumbnail)
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
        print(f"Start hunt in {channel}")
        action = self.config.action()
        guild = channel.guild
        emoji = self.config.emoji()
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
                button.label += " (1)"  # type: ignore

        timeout = humanize.naturaldelta(self.config.hunt_timeout())
        embed = self.embed(
            title="Un œuf a été découvert !",
            description=description,
            thumbnail=emoji.url,
            footer=f"Vous avez {timeout} pour réagir",
        )

        if send_method is None:
            message = await channel.send(embed=embed, view=view)
        else:
            message = await send_method(embed=embed, view=view)
        async with channel.typing():
            await view.wait()

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
        if hunters and has_hunt:
            winner = None
            hunters_id = [hunter.id for hunter in hunters]
            with Session(self.engine) as session:
                eggs: Dict[int, int] = dict(
                    session.execute(  # type: ignore
                        select(Egg.user_id, func.count().label("count"))
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
                print("Tirage du gagnant")
                while not winner:
                    for hunter in hunters:
                        percent = max(
                            1 - eggs.get(hunter.id, 0) / egg_total, 0.1
                        )
                        n = rand.random()
                        print(f"{hunter}: {n} < {percent} = {n < percent}")
                        if n < percent:
                            winner = hunter
                            break
                hunters.remove(winner)
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
            if hunters:
                loser = rand.choice(hunters)
                loser_name = loser.nick or loser.name
                if len(hunters) > 0:
                    text = f"{loser_name} rate un œuf"
                else:
                    text = agree(
                        "{1} et {0} autre chasseur ratent un œuf",
                        "{1} et {1} autres chasseurs ratent un œuf",
                        len(hunters) - 1,
                        loser_name,
                    )
                embed = self.embed(
                    title=text,
                    description=action.fail_text(loser),
                    image=action.fail_gif(),
                )
                pending.append(channel.send(embed=embed, reference=message))

            winner_name = winner.nick or winner.name
            embed = self.embed(
                title=f"{winner_name} récupère un œuf",
                description=action.success_text(winner),
                image=action.success_gif(),
                thumbnail=emoji.url,
                egg_count=eggs.get(winner.id, 0) + 1,
            )
            pending.append(channel.send(embed=embed, reference=message))
            button.label = f"L'œuf a été ramassé par {winner_name}"
            button.style = discord.ButtonStyle.success
        else:
            button.label = "L'œuf n'a pas été ramassé"
            button.style = discord.ButtonStyle.danger
        button.emoji = None
        view.disable_all_items()
        view.stop()
        pending.append(message.edit(view=view))
        await asyncio.gather(*pending)

    @discord.ext.tasks.loop(seconds=5.0)  # type: ignore
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
    author: discord.Member


@egg_command_group.command(description="Réinitialiser la chasse aux œufs.")
@discord.guild_only()
async def reset(ctx: ApplicationContext) -> None:
    if ctx.author is None or not ctx.author.guild_permissions.administrator:
        await ctx.respond(
            "Vous n'avez pas la permission d'administrateur", ephemeral=True
        )
        return
    view = discord.ui.View(timeout=30)
    cancel = discord.ui.Button(  # type: ignore
        label="Annuler", style=discord.ButtonStyle.danger
    )
    view.add_item(cancel)
    confirm = discord.ui.Button(  # type: ignore
        label="Confirmer", style=discord.ButtonStyle.success
    )
    view.add_item(confirm)

    async def cancel_callback(
        interaction: discord.Interaction,
    ) -> None:
        view.disable_all_items()
        view.stop()
        await interaction.response.send_message(
            embed=ctx.bot.embed(
                title="Réinitialisation annulée",
                description="Vous avez annulé la demande de réinitialisation.",
            ),
            ephemeral=True,
        )

    async def confirm_callback(
        interaction: discord.Interaction,
    ) -> None:
        view.disable_all_items()
        view.stop()
        with Session(ctx.bot.engine) as session:
            session.execute(delete(Hunt).where(Hunt.guild_id == ctx.guild_id))
            session.execute(delete(Egg).where(Egg.guild_id == ctx.guild_id))
            session.execute(
                delete(Hunter).where(Hunter.guild_id == ctx.guild_id)
            )
            session.commit()
        await interaction.response.send_message(
            embed=ctx.bot.embed(
                title="Réinitialisation",
                description=(
                    "L'ensemble des salons, œufs "
                    "et temps d'attentes ont été réinitialisatié."
                ),
            ),
            ephemeral=True,
        )

    cancel.callback = cancel_callback  # type: ignore
    confirm.callback = confirm_callback  # type: ignore
    message = await ctx.respond(
        embed=ctx.bot.embed(
            title="Demande de réinitialisation",
            description=(
                "L'ensemble des salons, œufs "
                "et temps d'attentes vont être réinitialisatiés."
            ),
            footer="Vous avez 30 secondes pour confirmer",
        ),
        ephemeral=True,
        view=view,
    )
    if await view.wait():
        await cancel_callback(cast(discord.Interaction, message))


@egg_command_group.command(description="Editer le nombre d'œufs d'un membre.")
@discord.guild_only()
@discord.option(  # type: ignore
    "user",
    input_type=discord.Member,
    required=True,
    description="Membre voulant editer",
)
@discord.option(  # type: ignore
    "montant",
    input_type=int,
    required=True,
    description="Nouveau nombre d'œufs",
)
async def edit(
    ctx: ApplicationContext,
    user: discord.Member,
    montant: int,
) -> None:
    if ctx.author is None or not ctx.author.guild_permissions.administrator:
        await ctx.respond(
            "Vous n'avez pas la permission d'administrateur", ephemeral=True
        )
        return
    with Session(ctx.bot.engine) as session:
        eggs = session.scalars(
            select(Egg).where(
                and_(
                    Egg.guild_id == ctx.guild.id,
                    Egg.user_id == ctx.author.id,
                )
            )
        ).all()
        diff = len(eggs) - montant
        if diff > 0:
            to_delete = []
            for _ in range(diff):
                egg = rand.choice(eggs)
                eggs.remove(egg)
                to_delete.append(egg.id)
            session.execute(delete(Egg).where(Egg.id.in_(to_delete)))
            session.commit()
        elif diff < 0:
            for _ in range(-diff):
                session.add(
                    Egg(
                        guild_id=ctx.guild_id,
                        channel_id=ctx.channel_id,
                        user_id=user.id,
                        emoji_id=ctx.bot.config.emoji().id,
                        message_id=None,
                    )
                )
            session.commit()
    await ctx.respond(
        embed=ctx.bot.embed(
            title="Edition terminée",
            description=(
                f"{user.mention} à maintenant "
                f"{agree('{0} œuf', '{0} œufs', montant)}"
            ),
        ),
        ephemeral=True,
    )


@egg_command_group.command(
    description="Activer la chasse aux œufs dans le salon."
)
@discord.guild_only()
async def enable(ctx: ApplicationContext) -> None:
    if ctx.author is None or not ctx.author.guild_permissions.manage_channels:
        await ctx.respond(
            "Vous n'avez pas la permission de gérer les salons", ephemeral=True
        )
        return
    with Session(ctx.bot.engine) as session:
        old = session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )
        if not old:
            session.add(
                Hunt(
                    channel_id=ctx.channel.id,
                    guild_id=ctx.guild_id,
                    next_egg=0,
                )
            )
            session.commit()
    await ctx.respond(
        f"Chasse aux œufs{' déjà' if old else ''} activée", ephemeral=True
    )


@egg_command_group.command(
    description="Désactiver la chasse aux œufs dans le salon."
)
@discord.guild_only()
async def disable(ctx: ApplicationContext) -> None:
    if ctx.author is None or not ctx.author.guild_permissions.manage_channels:
        await ctx.respond(
            "Vous n'avez pas la permission de gérer les salons", ephemeral=True
        )
        return
    with Session(ctx.bot.engine) as session:
        old = session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )
        if old:
            session.execute(
                delete(Hunt).where(Hunt.channel_id == ctx.channel.id)
            )
            session.commit()
    await ctx.respond(
        f"Chasse aux œufs{'' if old else ' déjà'} désactivée", ephemeral=True
    )


@egg_command_group.command(description="Regarder le contenu d'un panier.")
@discord.guild_only()
@discord.option(  # type: ignore
    "user",
    input_type=discord.Member,
    required=False,
    default=None,
    description="Membre possèdant le panier à inspecter",
)
async def basket(ctx: ApplicationContext, user: discord.Member) -> None:
    hunter = user or ctx.author
    with Session(ctx.bot.engine) as session:
        egg_counts = list(
            session.execute(
                select(
                    Egg.emoji_id,
                    func.count().label("count"),
                )
                .where(
                    and_(
                        Egg.guild_id == ctx.guild.id,
                        Egg.user_id == hunter.id,
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
            if hunter == ctx.author:
                text = ":spider_web: Vous n'avez aucun œuf"
            else:
                text = ctx.bot.config.conjugate(
                    ":spider_web: {Iel} n'a aucun œuf", hunter
                )
        await ctx.respond(
            embed=ctx.bot.embed(
                title=f"Contenu du panier de {hunter.nick or hunter.name}",
                description=text,
                egg_count=sum(egg[1] for egg in egg_counts),
            ),
            ephemeral=True,
        )


@egg_command_group.command(description="Rechercher un œuf.")
@discord.guild_only()
async def search(ctx: ApplicationContext) -> None:
    with Session(ctx.bot.engine) as session:
        hunt = session.scalar(
            select(Hunt).where(Hunt.channel_id == ctx.channel.id)
        )
        if hunt is None:
            await ctx.respond(
                "La chasse aux œufs n'est pas activée dans ce salon",
                ephemeral=True,
            )
            return
        hunter = session.scalar(
            select(Hunter).where(
                and_(
                    Hunter.user_id == ctx.author.id,
                    Hunter.guild_id == ctx.guild_id,
                )
            )
        )
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
                user_id=ctx.author.id,
                guild_id=ctx.guild_id,
                last_search=datetime.now().timestamp(),
            )
        )
        session.commit()

    name = ctx.author.nick or ctx.author.name
    n1, n2 = rand.random(), rand.random()
    print(f"Search {ctx.author} : {n1} {n2}")
    if ctx.bot.config.search_rate_discovered() < n1:
        if ctx.bot.config.search_rate_spoted() < n2:

            async def send_method(
                *args: Any, **kwargs: Any
            ) -> discord.Message:
                interaction = cast(
                    discord.Interaction, await ctx.respond(*args, **kwargs)
                )
                return await interaction.original_response()

            await ctx.bot.start_hunt(
                ctx.channel_id,
                ctx.bot.config.spotted(ctx.author),
                member_id=ctx.author.id,
                send_method=send_method,
            )
        else:
            emoji = ctx.bot.config.emoji()
            with Session(ctx.bot.engine) as session:
                session.add(
                    Egg(
                        channel_id=ctx.channel.id,
                        message_id=None,
                        guild_id=ctx.channel.guild.id,
                        user_id=ctx.author.id,
                        emoji_id=emoji.id,
                    )
                )
                egg_count = session.scalar(
                    select(
                        func.count(Egg.user_id).label("count"),
                    ).where(
                        and_(
                            Egg.guild_id == ctx.guild.id,
                            Egg.user_id == ctx.author.id,
                        )
                    )
                )
                session.commit()
            await ctx.respond(
                embed=ctx.bot.embed(
                    title=f"{name} récupère un œuf",
                    description=ctx.bot.config.hidden(ctx.author),
                    thumbnail=emoji.url,
                    egg_count=egg_count,
                )
            )
    else:
        await ctx.respond(
            embed=ctx.bot.embed(
                title=f"{name} repart bredouille",
                description=ctx.bot.config.failed(ctx.author),
            )
        )


@egg_command_group.command(description="Classement des chasseurs d'œufs.")
@discord.guild_only()
async def top(ctx: ApplicationContext) -> None:
    with Session(ctx.bot.engine) as session:
        base = (
            select(
                Egg.user_id,
                func.rank().over(order_by=func.count().desc()).label("row"),
                func.count().label("count"),
            )
            .where(Egg.guild_id == ctx.guild_id)
            .group_by(Egg.user_id)
            .order_by(func.count().desc())
        )
        egg_counts = session.execute(base.limit(3)).all()
        morsels = []
        top_player = False
        rank_medal = {1: "🥇", 2: "🥈", 3: "🥉"}
        for user_id, rank, count in egg_counts:
            if user_id == ctx.author.id:
                top_player = True
            morsels.append(
                f"{rank_medal.get(rank, rank)} <@{user_id}>\n"
                f"\u2004\u2004\u2004\u2004\u2004"
                f"➥ {agree('{0} œuf', '{0} œufs', count)}"
            )
        if not top_player:
            subq = base.subquery()
            user_egg_count = session.execute(
                select(subq).where(subq.c.user_id == ctx.author.id)
            ).first()
            if user_egg_count:
                user_id, rank, egg_count = user_egg_count
                morsels.append(
                    f"\n{rank_medal.get(rank, f'`#{rank}`')} "
                    f"<@{user_id}>\n"
                    f"\u2004\u2004\u2004\u2004\u2004"
                    f"➥ {agree('{0} œuf', '{0} œufs', egg_count)}"
                )
            else:
                morsels.append("\nVous n'avez pas encore œuf")
    text = "\n".join(morsels)
    await ctx.respond(
        embed=ctx.bot.embed(
            title=f"Chasse aux œufs : {ctx.guild.name}",
            description=text,
            thumbnail=ctx.guild.icon.url,
        ),
        ephemeral=True,
    )


@egg_command_group.command(description="Obtenir de l'aide.")
@discord.guild_only()
async def help(ctx: ApplicationContext) -> None:
    embed: discord.Embed = ctx.bot.embed(
        title="Liste des commandes",
        description=ctx.bot.description,
        thumbnail=ctx.bot.user.display_avatar.url,  # type: ignore
        footer="Crée par Dashstrom#6593",
    )
    for cmd in egg_command_group.subcommands:
        embed.add_field(
            name=f"/{egg_command_group.name} {cmd.name}",
            value=f"{cmd.description}",
            inline=False,
        )
    await ctx.respond(embed=embed, ephemeral=True)
