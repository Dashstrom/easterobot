"""Main program."""

import asyncio
import logging
import logging.config
import pathlib
import shutil
import time
from collections.abc import Awaitable
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Optional,
    TypeVar,
    Union,
)

import discord
import discord.app_commands
import discord.ext.commands
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.sql.expression import Select

if TYPE_CHECKING:
    from easterobot.games.game import GameCog

from .config import (
    RAND,
    RESOURCES,
    MConfig,
    RandomItem,
    agree,
    dump_yaml,
    load_config,
)
from .models import Base, Egg, Hunt

T = TypeVar("T")

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

DEFAULT_CONFIG_PATH = pathlib.Path("config.yml")
EXAMPLE_CONFIG_PATH = RESOURCES / "config.example.yml"
RANK_MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}
INTENTS = discord.Intents.all()


class Easterobot(discord.ext.commands.Bot):
    owner: discord.User
    game: "GameCog"

    def __init__(self, config: MConfig) -> None:
        """Initialise Easterbot."""
        super().__init__(
            command_prefix=".",
            description="Bot discord pour faire la chasse aux œufs",
            activity=discord.Game(name="rechercher des œufs"),
            intents=INTENTS,
        )
        self.config = config
        defaults = {"data": self.config.working_directory.as_posix()}
        if self.config.use_logging_file:
            logging_file = self.config.resources / "logging.conf"
            if not logging_file.is_file():
                error_message = f"Cannot find message: {str(logging_file)!r}"
                raise FileNotFoundError(error_message)
            logging.config.fileConfig(
                logging_file,
                disable_existing_loggers=False,
                defaults=defaults,
            )
        self.app_commands: list[discord.app_commands.AppCommand] = []
        self.app_emojis: dict[str, discord.Emoji] = {}
        database_uri = self.config.database.replace(
            "%(data)s", "/" + self.config.working_directory.as_posix()
        )
        logger.info("Open database %s", database_uri)
        self.engine = create_async_engine(database_uri, echo=False)

    @classmethod
    def from_config(
        cls,
        config_path: Union[str, Path] = DEFAULT_CONFIG_PATH,
        *,
        token: Optional[str] = None,
        env: bool = False,
    ) -> "Easterobot":
        """Instantiate Easterobot from config."""
        path = pathlib.Path(config_path)
        data = pathlib.Path(path).read_bytes()
        config = load_config(data, token=token, env=env)
        config.attach_default_working_directory(path.parent)
        return Easterobot(config)

    @classmethod
    def generate(
        cls,
        destination: Union[Path, str],
        *,
        token: Optional[str],
        env: bool,
        interactive: bool,
    ) -> "Easterobot":
        """Generate all data."""
        destination = Path(destination).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        config_data = EXAMPLE_CONFIG_PATH.read_bytes()
        config = load_config(config_data, token=token, env=env)
        config.attach_default_working_directory(destination)
        if interactive:
            while True:
                try:
                    config.verified_token()
                    break
                except (ValueError, TypeError):
                    config.token = getpass("Token: ")
        config._resources = pathlib.Path("resources")  # noqa: SLF001
        shutil.copytree(
            RESOURCES, destination / "resources", dirs_exist_ok=True
        )
        config_path = destination / "config.yml"
        config_path.write_bytes(dump_yaml(config))
        (destination / ".gitignore").write_bytes(b"*\n")
        return Easterobot(config)

    def is_super_admin(
        self,
        user: Union[discord.User, discord.Member],
    ) -> bool:
        """Get if user is admin."""
        return (
            user.id in self.config.admins
            or user.id in (self.owner.id, self.owner_id)
            or (self.owner_ids is not None and user.id in self.owner_ids)
        )

    # Method that loads cogs
    async def setup_hook(self) -> None:
        """Setup hooks."""
        await self.load_extension(
            "easterobot.commands", package="easterobot.commands.__init__"
        )
        await self.load_extension(
            "easterobot.games", package="easterobot.games.__init__"
        )

    def auto_run(self) -> None:
        """Run the bot with the given token."""
        self.run(token=self.config.verified_token())

    async def on_ready(self) -> None:
        """Handle ready event, can be trigger many time if disconnected."""
        # Sync bot commands
        logger.info("Syncing command")
        await self.tree.sync()
        self.app_commands = await self.tree.fetch_commands()

        # Sync bot owner
        app_info = await self.application_info()
        self.owner = app_info.owner
        logger.info("Owner is %s (%s)", self.owner.display_name, self.owner.id)

        # Load emojis
        await self._load_emojis()

        # Load eggs
        eggs_path = (self.config.resources / "emotes" / "eggs").resolve()
        self.egg_emotes = RandomItem(
            [self.app_emojis[path.stem] for path in eggs_path.glob("**/*")]
        )

        # Create the tables
        async with self.engine.begin() as session:
            await session.run_sync(Base.metadata.create_all, checkfirst=True)

        # Log all available guilds
        async for guild in self.fetch_guilds():
            logger.info("Guild %s (%s)", guild, guild.id)
        logger.info(
            "Logged on as %s (%s) !",
            self.user,
            getattr(self.user, "id", "unknown"),
        )
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

    async def _load_emojis(self) -> None:
        emojis = {
            emoji.name: emoji
            for emoji in await self.fetch_application_emojis()
        }
        emotes_path = (self.config.resources / "emotes").resolve()
        self.app_emojis = {}
        for emote in emotes_path.glob("**/*"):
            if not emote.is_file():
                continue
            name = emote.stem
            if emote.stem not in emojis:
                logger.info(
                    "Missing emoji %s, create emoji on application",
                    name,
                )
                image_data = emote.read_bytes()
                emoji = await self.create_application_emoji(
                    name=name,
                    image=image_data,
                )
                self.app_emojis[name] = emoji
            else:
                logger.info("Load emoji %s", name)
                self.app_emojis[name] = emojis[name]

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
        channel = self.get_channel(hunt_id)
        if channel is None:
            channel = await self.fetch_channel(hunt_id)
        if not isinstance(channel, discord.TextChannel):
            logger.warning("Invalid channel type %s", channel)
            return

        # Get from config
        action = self.config.action.rand()
        guild = channel.guild
        emoji = self.egg_emotes.rand()

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
        timeout = self.config.hunt.timeout + 1
        view = discord.ui.View(timeout=timeout)
        button: discord.ui.Button[Any] = discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.primary,
            emoji=emoji,
        )
        view.add_item(button)
        waiting = False
        active = False

        async def button_callback(
            interaction: discord.Interaction[Any],
        ) -> None:
            nonlocal waiting, active
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

            # TODO(dashstrom): must refactor this lock ?
            if active and not waiting:
                waiting = True
                while active:  # noqa: ASYNC110
                    await asyncio.sleep(0.01)
                waiting = False

            active = True
            button.label = action.text + f" ({len(hunters)})"
            await message.edit(view=view)
            active = False

        # Set the button callback
        button.callback = button_callback  # type: ignore[method-assign]

        # Set next hunt
        next_hunt = time.time() + timeout

        # Create and embed
        emb = embed(
            title="Un œuf a été découvert !",
            description=description
            + f"\n\nTirage du vinqueur : <t:{next_hunt:.0f}:R>",
            thumbnail=emoji.url,
        )

        # Send the embed in the hunt channel
        if send_method is None:
            message = await channel.send(embed=emb, view=view)
        else:
            message = await send_method(embed=emb, view=view)

        # TODO(dashstrom): channel is wrong due to the send message !
        # Wait the end of the hunt
        message_url = f"{channel.jump_url}/{message.id}"
        async with channel.typing():
            try:
                await asyncio.wait_for(
                    view.wait(), timeout=self.config.hunt.timeout
                )
            except asyncio.TimeoutError:
                logger.info("End hunt for %s", message_url)

        # Disable button and view after hunt
        button.disabled = True
        view.stop()
        await message.edit(view=view)  # Send the stop info

        # Get if hunt is valid
        async with AsyncSession(self.engine) as session:
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

        # Process the winner
        else:
            async with AsyncSession(self.engine) as session:
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

                # If only one hunter, give the egg to him
                if len(hunters) == 1:
                    winner = hunters[0]
                    loser = None
                    logger.info("100%% - %s (%s)", winner, winner.id)
                else:
                    lh = len(hunters)
                    min_eggs = min(eggs.values(), default=0)
                    max_eggs = max(eggs.values(), default=0)
                    diff_eggs = max_eggs - min_eggs
                    w_egg = self.config.hunt.weights.egg
                    w_speed = self.config.hunt.weights.speed
                    weights = []

                    # Compute chances of each hunters
                    for i, h in enumerate(hunters, start=1):
                        if diff_eggs != 0:
                            egg = eggs.get(h.id, 0) - min_eggs
                            p_egg = (1 - egg / diff_eggs) * w_egg + 1 - w_egg
                        else:
                            p_egg = 1.0
                        if lh != 0:
                            p_speed = (1 - i / lh) * w_speed + 1 - w_speed
                        else:
                            p_speed = 1.0
                        weights.append(p_egg * p_speed)
                    r = sum(weights)
                    chances = [(h, p / r) for h, p in zip(hunters, weights)]
                    for h, c in chances:
                        logger.info("%.2f%% - %s (%s)", c * 100, h, h.id)

                    # Get the winner
                    n = RAND.random()
                    for h, p in chances:
                        if n < p:
                            winner = h
                            break
                        n -= p
                    else:
                        winner = hunters[-1]

                    # Get a random loser
                    hunters.remove(winner)
                    loser = RAND.choice(hunters)

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
                    description=action.fail.text(loser),
                    image=action.fail.gif,
                )
                await channel.send(embed=emb, reference=message)

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

        # Remove emoji and edit view
        button.emoji = None
        await message.edit(view=view)

    async def loop_hunt(self) -> None:
        """Manage the schedule of run."""
        # Create a async session
        async with AsyncSession(
            self.engine, expire_on_commit=False
        ) as session:
            # Find hunt with next egg available
            now = time.time()
            hunts = (
                await session.scalars(select(Hunt).where(Hunt.next_egg <= now))
            ).all()

            # For each hunt, set the next run and store the channel ids
            if hunts:
                for hunt in hunts:
                    next_egg = now + self.config.hunt.cooldown.rand()
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
                        self.start_hunt(hunt_id, self.config.appear.rand())
                        for hunt_id in hunt_ids
                    ]
                )
            except Exception as err:
                logger.exception(
                    "An error occurred during start hunt", exc_info=err
                )

    async def get_rank(
        self,
        session: AsyncSession,
        guild_id: int,
        user_id: int,
    ) -> Optional[tuple[int, str, int]]:
        """Get the rank of single user."""
        query = _prepare_rank(guild_id)
        subq = query.subquery()
        select(subq).where(subq.c.user_id == user_id)
        ranks = await _compute_rank(session, query)
        return ranks[0] if ranks else None

    async def get_ranks(
        self,
        session: AsyncSession,
        guild_id: int,
        limit: Optional[int] = None,
        page: Optional[int] = None,
    ) -> list[tuple[int, str, int]]:
        """Get ranks by page."""
        query = _prepare_rank(guild_id)
        if limit is not None:
            query = query.limit(limit)
            if page is not None:
                query = query.offset(page * limit)
        return await _compute_rank(session, query)


def _prepare_rank(guild_id: int) -> Select[Any]:
    """Create a select query with order user by egg count."""
    return (
        select(
            Egg.user_id,
            func.rank().over(order_by=func.count().desc()).label("row"),
            func.count().label("count"),
        )
        .where(Egg.guild_id == guild_id)
        .group_by(Egg.user_id)
        .order_by(func.count().desc())
    )


async def _compute_rank(
    session: AsyncSession, query: Select[Any]
) -> list[tuple[int, str, int]]:
    res = await session.execute(query)
    return [
        (member_id, RANK_MEDAL.get(rank, f"`#{rank}`"), egg_count)
        for member_id, rank, egg_count in res.all()
    ]


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
