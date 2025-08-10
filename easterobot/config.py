"""Core configuration and serialization utilities for Easterobot.

This module contains configuration structures, serialization logic,
utility functions, and text conjugation helpers used by the Easterobot
Discord bot. It includes message formats, randomization helpers, and
YAML-based configuration loading/saving.
"""

import logging
import logging.config
import os
import pathlib
import random
import re
from abc import ABC, abstractmethod
from argparse import Namespace
from collections.abc import Iterable
from datetime import datetime, time, timezone
from typing import (
    Any,
    Generic,
    Literal,
    TypeGuard,
    TypeVar,
    cast,
    get_args,
    get_origin,
)

import discord
import msgspec
from alembic.config import Config

RAND = random.SystemRandom()

T = TypeVar("T")
V = TypeVar("V")
Members = discord.Member | list[discord.Member]

HERE = pathlib.Path(__file__).parent.resolve()
RESOURCES = HERE / "resources"
DEFAULT_CONFIG_PATH = pathlib.Path("config.yml")
EXAMPLE_CONFIG_PATH = RESOURCES / "config.example.yml"


class Serializable(ABC, Generic[V]):
    """Abstract base class for serializable objects."""

    _decodable_flag = True

    @abstractmethod
    def encode(self) -> V:
        """Convert the object to its serializable form."""

    @classmethod
    @abstractmethod
    def decode(cls: type[T], args: tuple[Any, ...], obj: V) -> T:
        """Reconstruct an object from its serialized form."""

    @staticmethod
    def decodable(typ: type[Any]) -> TypeGuard["type[Serializable[T]]"]:
        """Check whether a class is a Serializable subclass."""
        return hasattr(typ, "_decodable_flag")


class ConjugableText(Serializable[str]):
    """Text that supports gender-based conjugation."""

    __slots__ = ("_conjugation", "_text")

    def __init__(self, text: str) -> None:
        """Initialize a ConjugableText instance.

        Args:
            text: Base text containing placeholders for conjugation.
        """
        self._text = text
        self._conjugation: Conjugation = {}

    def __str__(self) -> str:
        """Return a readable string representation."""
        return f"<{self.__class__.__name__} {self._text!r}>"

    __repr__ = __str__

    def encode(self) -> str:
        """Serialize as a plain string."""
        return self._text

    @classmethod
    def decode(cls, typ: tuple[Any, ...], obj: str) -> "ConjugableText":  # noqa: ARG003
        """Deserialize from a plain string."""
        return cls(obj)

    @staticmethod
    def gender(member: discord.Member) -> Literal["man", "woman"]:
        """Infer gender based on member's role names.

        Args:
            member: Discord member to check.

        Returns:
            Either "man" or "woman".
        """
        if any(
            marker in tokenize(role.name)
            for role in member.roles
            for marker in (
                "woman",
                "girl",
                "femme",
                "fille",
                "elle",
                "elles",
                "her",
                "she",
            )
        ):
            return "woman"
        return "man"

    def attach(self, conjugation: "Conjugation") -> None:
        """Attach a conjugation mapping to the text."""
        self._conjugation = conjugation

    def __call__(self, members: Members) -> str:
        """Apply gender-based conjugation for given members.

        Args:
            members: A member or list of members to conjugate for.

        Returns:
            The conjugated text.
        """
        if isinstance(members, discord.Member):
            members = [members]
        if not members:
            gender = "man"
        else:
            for member in members:
                if self.gender(member) == "man":
                    gender = "man"
                    break
            else:
                gender = "woman"

        text = self._text
        for term, versions in self._conjugation.items():
            word = versions[gender]
            text = text.replace("{" + term.lower() + "}", word.lower())
            text = text.replace("{" + term.upper() + "}", word.upper())
            text = text.replace("{" + term.title() + "}", word.title())
        return text.replace("{user}", f"<@{member.id}>")


class CasinoEvent(msgspec.Struct):
    """Represents an event in the casino."""

    duration: float


class MCasino(msgspec.Struct):
    """Casino configuration."""

    probability: float
    roulette: CasinoEvent

    def sample_event(self) -> CasinoEvent | None:
        """Randomly return a casino event based on probability."""
        if self.probability < RAND.random():
            return None
        return self.roulette


class RandomItem(Serializable[list[T]]):
    """Container for randomly selecting from a list of items."""

    __slots__ = ("choices",)

    def __init__(self, choices: Iterable[T] | None = None):
        """Initialize RandomItem.

        Args:
            choices: Optional iterable of initial choices.
        """
        self.choices = list(choices) if choices is not None else []

    def __str__(self) -> str:
        """Return a readable string representation."""
        return f"<{self.__class__.__name__} {self.choices!r}>"

    __repr__ = __str__

    def encode(self) -> list[T]:
        """Serialize as a list of items."""
        return self.choices

    @classmethod
    def decode(cls, args: tuple[Any, ...], obj: list[T]) -> "RandomItem[T]":
        """Deserialize from a list of items."""
        return cls(convert(obj, target_type=list[args[0]]))  # type: ignore[valid-type]

    def rand(self) -> T:
        """Select and return a random item."""
        return RAND.choice(self.choices)


class RandomConjugableText(RandomItem[ConjugableText]):
    """Randomly select and conjugate text."""

    def __call__(self, members: Members) -> str:
        """Select and conjugate a random ConjugableText."""
        return self.rand()(members)

    @classmethod
    def decode(
        cls,
        args: tuple[Any, ...],  # noqa: ARG003
        obj: list[ConjugableText],
    ) -> "RandomConjugableText":
        """Deserialize into RandomConjugableText."""
        return cls(convert(obj, target_type=list[ConjugableText]))


class MSleep(msgspec.Struct):
    """Configuration for bot's sleep schedule."""

    start: time
    end: time
    divide_hunt: float
    divide_discovered: float
    divide_spotted: float


class MCooldown(msgspec.Struct):
    """Cooldown range configuration."""

    min: float
    max: float

    def rand(self) -> float:
        """Return a random value between min and max."""
        return self.min + RAND.random() * (self.max - self.min)


class MWeights(msgspec.Struct):
    """Weight configuration for egg, speed, and base."""

    egg: float
    speed: float
    base: float


class MHunt(msgspec.Struct):
    """Hunt configuration."""

    timeout: float
    cooldown: MCooldown
    weights: MWeights
    game: float


class MCommand(msgspec.Struct):
    """Command cooldown configuration."""

    cooldown: float


class MDiscovered(msgspec.Struct):
    """Discovered state configuration."""

    shield: int
    min: float
    max: float

    def probability(self, luck: float) -> float:
        """Return discovery probability based on luck."""
        return (self.max - self.min) * luck + self.min


class MSpotted(msgspec.Struct):
    """Spotted state configuration."""

    shield: int
    min: float
    max: float

    def probability(self, luck: float) -> float:
        """Return spotted probability based on lack of luck."""
        return (self.max - self.min) * (1 - luck) + self.min


class SearchCommand(MCommand):
    """Search command configuration."""

    discovered: MDiscovered
    spotted: MSpotted


class MGender(msgspec.Struct):
    """Mapping of gender to text forms."""

    woman: str = ""
    man: str = ""

    def __getitem__(self, key: str) -> str:
        """Return the text form for the given gender."""
        return getattr(self, key, "")


class MEmbed(msgspec.Struct):
    """Embed content with text and GIF."""

    text: ConjugableText
    gif: str


class MText(msgspec.Struct):
    """Command text with success and failure embeds."""

    text: str
    success: MEmbed
    fail: MEmbed


Conjugation = dict[str, MGender]


class MCommands(msgspec.Struct, forbid_unknown_fields=True):
    """Container for all configured bot commands."""

    search: SearchCommand
    top: MCommand
    basket: MCommand
    reset: MCommand
    enable: MCommand
    disable: MCommand
    help: MCommand
    edit: MCommand
    connect4: MCommand
    skyjo: MCommand
    info: MCommand
    tictactoe: MCommand
    rockpaperscissors: MCommand

    def __getitem__(self, key: str, /) -> MCommand:
        """Return the MCommand object for the given command name.

        Args:
            key: Name of the command to retrieve.

        Returns:
            The corresponding MCommand instance.

        Raises:
            KeyError: If the key is a invalid command.
        """
        if key not in self.__struct_fields__:
            raise KeyError(key)
        try:
            result = getattr(self, key)
            if not isinstance(result, MCommand):
                raise KeyError(key)
        except AttributeError:
            raise KeyError(key) from None
        return result


class MConfig(msgspec.Struct, dict=True):
    """Main configuration structure for the bot."""

    owner_is_admin: bool
    use_logging_file: bool
    admins: list[int]
    database: str
    group: str
    hunt: MHunt
    casino: MCasino
    conjugation: Conjugation
    failed: RandomConjugableText
    hidden: RandomConjugableText
    spotted: RandomConjugableText
    appear: RandomItem[str]
    action: RandomItem[MText]
    commands: MCommands
    sleep: MSleep = msgspec.field(
        default_factory=lambda: MSleep(
            start=time(hour=23),
            end=time(hour=9),
            divide_hunt=2.0,
            divide_discovered=2.0,
            divide_spotted=1.5,
        )
    )
    message_content: bool = True
    token: str | msgspec.UnsetType | None = msgspec.UNSET
    _resources: pathlib.Path | msgspec.UnsetType | None = msgspec.field(
        name="resources", default=msgspec.UNSET
    )
    _working_directory: pathlib.Path | msgspec.UnsetType | None = (
        msgspec.field(name="working_directory", default=msgspec.UNSET)
    )

    @property
    def database_uri(self) -> str:
        """Return the database URI with placeholders resolved."""
        return self.database.replace(
            "%(data)s", "/" + self.working_directory.as_posix()
        )

    def is_sleep_hours(self, hour: time) -> bool:
        """Check whether the given time falls within configured sleep hours.

        Args:
            hour: Time to check.

        Returns:
            True if the given time is within the sleep window, False otherwise.

        Examples:
            >>> config.is_sleep_hours(time(hour=0, minute=59))
            False
            >>> config.is_sleep_hours(time(hour=2))
            True
            >>> config.is_sleep_hours(time(hour=1))
            True
        """
        if self.sleep.start < self.sleep.end:
            return self.sleep.start <= hour < self.sleep.end
        if self.sleep.start > self.sleep.end:
            return self.sleep.end > hour or self.sleep.start <= hour
        return False

    def in_sleep_hours(self) -> bool:
        """Return True if the current UTC time is within sleep hours."""
        hour = datetime.now(tz=timezone.utc).time()
        return self.is_sleep_hours(hour)

    def verified_token(self) -> str:
        """Return the bot token after validating it.

        Raises:
            TypeError: If no token is set.
            ValueError: If the token format is invalid.
        """
        if self.token is None or self.token is msgspec.UNSET:
            msg = "Token was not provided"
            raise TypeError(msg)
        if "." not in self.token:
            msg = "Wrong token format"
            raise ValueError(msg)
        return self.token

    def attach_default_working_directory(
        self, path: pathlib.Path | str
    ) -> None:
        """Attach a fallback working directory path for this config."""
        self._cwd = pathlib.Path(path)

    @property
    def working_directory(self) -> pathlib.Path:
        """Return the working directory, falling back to the current path."""
        if (
            self._working_directory is None
            or self._working_directory is msgspec.UNSET
        ):
            if hasattr(self, "_cwd"):
                return self._cwd.resolve()
            return pathlib.Path.cwd().resolve()
        return self._working_directory.resolve()

    @property
    def resources(self) -> pathlib.Path:
        """Return the resources path, defaulting to embedded resources."""
        if self._resources is None or self._resources is msgspec.UNSET:
            return RESOURCES
        if self._resources.is_absolute():
            return self._resources
        return self.working_directory / self._resources

    def __post_init__(self) -> None:
        """Attach conjugation mappings to all conjugable texts."""
        for conjugable in self.failed.choices:
            conjugable.attach(self.conjugation)
        for conjugable in self.hidden.choices:
            conjugable.attach(self.conjugation)
        for conjugable in self.spotted.choices:
            conjugable.attach(self.conjugation)
        for choice in self.action.choices:
            choice.success.text.attach(self.conjugation)
            choice.fail.text.attach(self.conjugation)

    def conjugate(self, text: str, member: discord.Member) -> str:
        """Return gender-conjugated text for a given member."""
        conj_text = ConjugableText(text)
        conj_text.attach(self.conjugation)
        return conj_text(member)

    def alembic_config(self, namespace: Namespace | None = None) -> Config:
        """Return an Alembic configuration object for migrations."""
        config_alembic = str(self.resources / "alembic.ini")
        cfg = Config(
            file_=config_alembic,
            ini_section="alembic" if namespace is None else namespace.name,
            cmd_opts=namespace,
            attributes={"easterobot_config": self},
        )
        cfg.set_main_option("sqlalchemy.url", self.database_uri)
        cfg.set_main_option("script_location", str(HERE / "alembic"))
        return cfg

    def configure_logging(self) -> None:
        """Configure logging from file if enabled."""
        if self.use_logging_file and not hasattr(self, "__logging_flag"):
            logging_file = self.resources / "logging.conf"
            defaults = {"data": self.working_directory.as_posix()}
            if not logging_file.is_file():
                msg = f"Cannot find logging file: {logging_file!r}"
                raise FileNotFoundError(msg)
            logging.config.fileConfig(
                logging_file,
                disable_existing_loggers=False,
                defaults=defaults,
            )

    def __str__(self) -> str:
        """Return a human-readable representation of the config."""
        return f"<Config {str(self.working_directory)!r}>"

    def __repr__(self) -> str:
        """Return a human-readable representation of the config."""
        return f"<Config {str(self.working_directory)!r}>"


def _dec_hook(target_type: type[T], value: Any) -> T:
    """Decode YAML or msgspec values into appropriate Python types.

    Args:
        target_type: The type into which the value should be decoded.
        value: The raw value to decode.

    Returns:
        The decoded Python object.

    Raises:
        TypeError: If the type is unsupported for decoding.
    """
    origin = get_origin(target_type) or target_type
    args = get_args(target_type)
    if issubclass(origin, discord.PartialEmoji):
        return discord.PartialEmoji(name="_", animated=False, id=value)  # type: ignore[return-value]
    if issubclass(origin, pathlib.Path):
        return cast("T", pathlib.Path(value))
    if Serializable.decodable(origin):
        return cast("T", origin.decode(args, value))
    msg = f"Invalid type {target_type!r} for {value!r}"
    raise TypeError(msg)


def _enc_hook(value: Any) -> Any:
    """Encode Python objects into YAML/msgspec-friendly representations.

    Args:
        value: The object to encode.

    Returns:
        The encoded value.

    Raises:
        TypeError: If the object cannot be encoded.
    """
    if isinstance(value, discord.PartialEmoji):
        return value.id
    if isinstance(value, pathlib.Path):
        return str(value)
    if isinstance(value, Serializable):
        return value.encode()
    msg = f"Invalid object {value!r}"
    raise TypeError(msg)


def load_yaml(data: bytes | str, target_type: type[T]) -> T:
    """Load an object from YAML data.

    Args:
        data: YAML-formatted bytes or string.
        target_type: The type into which the data should be decoded.

    Returns:
        An instance of target_type loaded from YAML.
    """
    return msgspec.yaml.decode(  # type: ignore[no-any-return,unused-ignore]
        data,
        type=target_type,
        dec_hook=_dec_hook,
    )


def dump_yaml(value: Any) -> bytes:
    """Serialize an object into YAML bytes.

    Args:
        value: Object to serialize.

    Returns:
        YAML-encoded bytes.
    """
    return msgspec.yaml.encode(value, enc_hook=_enc_hook)


def convert(value: Any, target_type: type[T]) -> T:
    """Convert a value into a specific type using msgspec.

    Args:
        value: The object to convert.
        target_type: Desired output type.

    Returns:
        The converted object.
    """
    return msgspec.convert(  # type: ignore[no-any-return,unused-ignore]
        value,
        type=target_type,
        dec_hook=_dec_hook,
    )


def load_config_from_buffer(
    data: bytes | str,
    token: str | None = None,
    *,
    env: bool = False,
) -> MConfig:
    """Load configuration from YAML data in memory.

    Args:
        data: YAML bytes or string containing the configuration.
        token: Optional bot token override.
        env: If True, load token from DISCORD_TOKEN environment variable.

    Returns:
        Loaded MConfig instance.
    """
    config = load_yaml(data, MConfig)
    if env:
        potential_token = os.environ.get("DISCORD_TOKEN")
        if potential_token is not None:
            config.token = potential_token
    if token is not None:
        config.token = token
    return config


def load_config_from_path(
    path: str | pathlib.Path,
    token: str | None = None,
    *,
    env: bool = False,
) -> MConfig:
    """Load configuration from a YAML file path.

    Args:
        path: Path to the YAML configuration file.
        token: Optional bot token override.
        env: If True, load token from DISCORD_TOKEN environment variable.

    Returns:
        Loaded MConfig instance.
    """
    path = pathlib.Path(path)
    data = path.read_bytes()
    config = load_config_from_buffer(data, token=token, env=env)
    config.attach_default_working_directory(path.parent)
    return config


def agree(
    singular: str, plural: str, /, amount: int | None, *args: Any
) -> str:
    """Return singular or plural form based on the amount.

    Args:
        singular: Singular text format string.
        plural: Plural text format string.
        amount: Number to determine singular/plural form.
        *args: Additional formatting arguments.

    Returns:
        Formatted string in correct grammatical number.
    """
    if amount is None or amount in (-1, 0, 1):
        return singular.format(amount, *args)
    return plural.format(amount, *args)


RE_VALID = re.compile(r"[^a-zA-Z0-9éàèê]")


def tokenize(text: str) -> list[str]:
    """Split text into lowercase tokens, removing special characters.

    Args:
        text: The string to tokenize.

    Returns:
        List of tokens in lowercase.

    Examples:
        >>> tokenize("Activités manuelles")
        ['activités', 'manuelles']
        >>> tokenize("Elle")
        ['elle']
        >>> tokenize("Iel/Iels")
        ['iel', 'iels']
        >>> tokenize("🦉 Elle")
        ['elle']
    """
    text = text.casefold()
    text = RE_VALID.sub(" ", text)
    return text.strip().split()
