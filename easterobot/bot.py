"""Main program."""

import logging
import logging.config
import pathlib
import shutil
from getpass import getpass
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Optional,
    TypeVar,
    Union,
)

import discord
import discord.app_commands
import discord.ext.commands
from sqlalchemy.ext.asyncio import create_async_engine

if TYPE_CHECKING:
    from easterobot.games.game import GameCog
    from easterobot.hunts.hunt import HuntCog

from .config import (
    RESOURCES,
    MConfig,
    RandomItem,
    dump_yaml,
    load_config,
)
from .models import Base

T = TypeVar("T")

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent

DEFAULT_CONFIG_PATH = pathlib.Path("config.yml")
EXAMPLE_CONFIG_PATH = RESOURCES / "config.example.yml"
INTENTS = discord.Intents.all()


class Easterobot(discord.ext.commands.Bot):
    owner: discord.User
    game: "GameCog"
    hunt: "HuntCog"

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

    async def resolve_channel(
        self,
        channel_id: int,
    ) -> Optional[discord.TextChannel]:
        """Resolve channel."""
        channel = self.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden):
                return None
        if not isinstance(channel, discord.TextChannel):
            return None
        return channel

    # Method that loads cogs
    async def setup_hook(self) -> None:
        """Setup hooks."""
        await self.load_extension(
            "easterobot.commands", package="easterobot.commands.__init__"
        )
        await self.load_extension(
            "easterobot.games", package="easterobot.games.__init__"
        )
        await self.load_extension(
            "easterobot.hunts", package="easterobot.hunts.__init__"
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
