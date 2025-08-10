"""Main program for Easterobot.

This module defines the `Easterobot` Discord bot class, which manages the
bot lifecycle, configuration, database connections, and integration with
game and hunt cogs. It also handles emoji loading, command syncing, and
guild logging.
"""

import asyncio
import logging
import pathlib
import shutil
from getpass import getpass
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

import discord
import discord.app_commands
import discord.ext.commands
from alembic.command import upgrade
from sqlalchemy.ext.asyncio import create_async_engine

if TYPE_CHECKING:
    from easterobot.games.game import GameCog
    from easterobot.hunts.hunt import HuntCog

from .config import (
    DEFAULT_CONFIG_PATH,
    EXAMPLE_CONFIG_PATH,
    RESOURCES,
    MConfig,
    RandomItem,
    dump_yaml,
    load_config_from_buffer,
    load_config_from_path,
)

T = TypeVar("T")

logger = logging.getLogger(__name__)
INTENTS = discord.Intents.default()
INTENTS.message_content = True


class Easterobot(discord.ext.commands.Bot):
    """Main Easterobot Discord bot class."""

    owner: discord.User
    game: "GameCog"
    hunt: "HuntCog"
    init_finished: asyncio.Event

    def __init__(self, config: MConfig) -> None:
        """Initialize the Easterobot instance.

        Args:
            config: Loaded bot configuration.
        """
        intents = discord.Intents.default()
        if config.message_content:
            intents.message_content = True

        # Suppress NaCl warnings for voice
        discord.VoiceClient.warn_nacl = False

        super().__init__(
            command_prefix=".",
            description="Bot Discord pour faire la chasse aux œufs",
            activity=discord.Game(name="rechercher des œufs"),
            intents=INTENTS,
        )

        self.app_commands: list[discord.app_commands.AppCommand] = []
        self.app_emojis: dict[str, discord.Emoji] = {}
        self.config = config
        self.config.configure_logging()

        # Ensure database schema is up-to-date
        upgrade(self.config.alembic_config(), "head")

        logger.info("Opening database %s", self.config.database_uri)
        self.engine = create_async_engine(
            self.config.database_uri,
            echo=False,
        )

    @classmethod
    def from_config(
        cls,
        path: str | Path = DEFAULT_CONFIG_PATH,
        *,
        token: str | None = None,
        env: bool = False,
    ) -> "Easterobot":
        """Create an instance from a configuration file.

        Args:
            path: Path to the configuration file.
            token: Bot token override.
            env: If True, load configuration from environment variables.

        Returns:
            An initialized `Easterobot` instance.
        """
        config = load_config_from_path(path, token=token, env=env)
        return Easterobot(config)

    @classmethod
    def generate(
        cls,
        destination: Path | str,
        *,
        token: str | None = None,
        env: bool = False,
        interactive: bool = False,
    ) -> "Easterobot":
        """Generate a new bot configuration and resources.

        Args:
            destination: Directory where the bot's data will be created.
            token: Bot token override.
            env: If True, load configuration from environment variables.
            interactive: If True, prompt user for the bot token.

        Returns:
            An initialized `Easterobot` instance.
        """
        destination = Path(destination).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        config_data = EXAMPLE_CONFIG_PATH.read_bytes()
        config = load_config_from_buffer(config_data, token=token, env=env)
        config.attach_default_working_directory(destination)

        if interactive:
            while True:
                try:
                    config.verified_token()
                    break
                except (ValueError, TypeError):
                    config.token = getpass("Token: ")

        # Create resources directory
        config._resources = pathlib.Path("resources")  # noqa: SLF001
        shutil.copytree(
            RESOURCES, destination / "resources", dirs_exist_ok=True
        )

        # Save configuration
        config_path = destination / "config.yml"
        config_path.write_bytes(dump_yaml(config))
        (destination / ".gitignore").write_bytes(b"*\n")
        return Easterobot(config)

    def is_super_admin(
        self,
        user: discord.User | discord.Member,
    ) -> bool:
        """Check whether a user is a super admin.

        Args:
            user: The Discord user or member to check.

        Returns:
            True if the user is a super admin, False otherwise.
        """
        return (
            user.id in self.config.admins
            or user.id in (self.owner.id, self.owner_id)
            or (self.owner_ids is not None and user.id in self.owner_ids)
        )

    async def resolve_channel(
        self,
        channel_id: int,
    ) -> discord.TextChannel | None:
        """Get a text channel by its ID.

        Args:
            channel_id: ID of the channel to fetch.

        Returns:
            The corresponding text channel, or None if unavailable.
        """
        channel = self.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden):
                return None
        if not isinstance(channel, discord.TextChannel):
            return None
        return channel

    async def setup_hook(self) -> None:
        """Load bot extensions (commands, games, hunts)."""
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
        """Start the bot using the verified token."""
        self.run(token=self.config.verified_token())

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        """Start the bot and initialize the ready event.

        Args:
            token: Bot authentication token.
            reconnect: Whether to automatically reconnect on disconnect.
        """
        self.init_finished = asyncio.Event()
        await super().start(token=token, reconnect=reconnect)

    async def on_ready(self) -> None:
        """Handle the bot ready event.

        This may trigger multiple times if the bot reconnects.
        """
        logger.info("Syncing commands...")
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

        # Log all available guilds
        async for guild in self.fetch_guilds():
            logger.info("Guild %s (%s)", guild, guild.id)

        # Log user
        logger.info(
            "Logged in as %s (%s)",
            self.user,
            getattr(self.user, "id", "unknown"),
        )

        # Set init event as finished
        self.init_finished.set()

    async def _load_emojis(self) -> None:
        """Load or create application emojis from resource files."""
        emojis = {
            emoji.name: emoji
            for emoji in await self.fetch_application_emojis()
        }
        emotes_path = (self.config.resources / "emotes").resolve()

        # TODO(dashstrom): Remove outdated emojis.
        # TODO(dashstrom): Implement emoji caching.
        self.app_emojis = {}
        for emote in emotes_path.glob("**/*"):
            if not emote.is_file():
                continue
            name = emote.stem
            if name not in emojis:
                logger.info(
                    "Missing emoji %s, creating on application...",
                    name,
                )
                image_data = emote.read_bytes()
                emoji = await self.create_application_emoji(
                    name=name,
                    image=image_data,
                )
                self.app_emojis[name] = emoji
            else:
                logger.info("Loaded emoji %s", name)
                self.app_emojis[name] = emojis[name]
