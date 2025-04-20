"""Main program."""

import logging
import logging.config
import os
import pathlib
import random
import re
from abc import ABC, abstractmethod
from argparse import Namespace
from collections.abc import Iterable
from typing import (
    Any,
    Generic,
    List,
    Literal,
    Optional,
    TypeVar,
    Union,
    cast,
)

import discord
import msgspec
from alembic.config import Config
from typing_extensions import TypeGuard, get_args, get_origin, override

RAND = random.SystemRandom()

T = TypeVar("T")
V = TypeVar("V")
Members = Union[discord.Member, list[discord.Member]]

HERE = pathlib.Path(__file__).parent.resolve()
RESOURCES = HERE / "resources"
DEFAULT_CONFIG_PATH = pathlib.Path("config.yml")
EXAMPLE_CONFIG_PATH = RESOURCES / "config.example.yml"


class Serializable(ABC, Generic[V]):
    _decodable_flag = True

    @abstractmethod
    def encode(self) -> V:
        """Encode current object of msgspec."""

    @classmethod
    @abstractmethod
    def decode(cls: type[T], args: tuple[Any, ...], obj: V) -> T:
        """Encode current object of msgspec."""

    @staticmethod
    def decodable(typ: type[Any]) -> TypeGuard["type[Serializable[T]]"]:
        """Check if a class is decodable."""
        return hasattr(typ, "_decodable_flag")


class ConjugableText(Serializable[str]):
    __slots__ = ("_conjugation", "_text")

    def __init__(self, text: str):
        """Create a conjugable text."""
        self._text = text
        self._conjugation: Conjugation = {}

    def __str__(self) -> str:
        """Get the string representation."""
        return f"<{self.__class__.__name__} {self._text!r}>"

    __repr__ = __str__

    @override
    def encode(self) -> str:
        return self._text

    @override
    @classmethod
    def decode(cls, typ: tuple[Any, ...], obj: str) -> "ConjugableText":
        return cls(obj)

    @staticmethod
    def gender(member: discord.Member) -> Literal["man", "woman"]:
        """Get the gender of a people."""
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
        """Attach conjugation to the text."""
        self._conjugation = conjugation

    def __call__(self, members: Members) -> str:
        """Conjugate the text."""
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


class RandomItem(
    Serializable[list[T]],  # Stored form
):
    __slots__ = ("choices",)

    def __str__(self) -> str:
        """Get the string representation."""
        return f"<{self.__class__.__name__} {self.choices!r}>"

    __repr__ = __str__

    def __init__(self, choices: Optional[Iterable[T]] = None):
        """Create RandomItem."""
        self.choices = list(choices) if choices is not None else []

    @override
    def encode(self) -> list[T]:
        return self.choices

    @override
    @classmethod
    def decode(cls, args: tuple[Any, ...], obj: list[T]) -> "RandomItem[T]":
        return cls(convert(obj, typ=list[args[0]]))  # type: ignore[valid-type]

    def rand(self) -> T:
        """Get a random choice."""
        return RAND.choice(self.choices)


class RandomConjugableText(RandomItem[ConjugableText]):
    def __call__(self, members: Members) -> str:
        """Conjugate a random item."""
        return self.rand()(members)

    @override
    @classmethod
    def decode(
        cls, args: tuple[Any, ...], obj: list[ConjugableText]
    ) -> "RandomConjugableText":
        return cls(convert(obj, typ=list[ConjugableText]))


class MCooldown(msgspec.Struct):
    min: float
    max: float

    def rand(self) -> float:
        """Randomize a min to max."""
        return self.min + RAND.random() * (self.max - self.min)


class MWeights(msgspec.Struct):
    egg: float
    speed: float
    base: float


class MHunt(msgspec.Struct):
    timeout: float
    cooldown: MCooldown
    weights: MWeights
    game: float


class MCommand(msgspec.Struct):
    cooldown: float


class MDiscovered(msgspec.Struct):
    shield: int
    min: float
    max: float


class MSpotted(msgspec.Struct):
    shield: int
    min: float
    max: float


class SearchCommand(MCommand):
    discovered: MDiscovered
    spotted: MSpotted


class MGender(msgspec.Struct):
    woman: str = ""
    man: str = ""

    def __getitem__(self, key: str) -> str:
        """Get text."""
        return getattr(self, key, "")


class MEmbed(msgspec.Struct):
    text: ConjugableText
    gif: str


class MText(msgspec.Struct):
    text: str
    success: MEmbed
    fail: MEmbed


Conjugation = dict[str, MGender]


class MCommands(msgspec.Struct, forbid_unknown_fields=True):
    search: SearchCommand
    top: MCommand
    basket: MCommand
    reset: MCommand
    enable: MCommand
    disable: MCommand
    help: MCommand
    edit: MCommand
    connect4: MCommand
    tictactoe: MCommand
    rockpaperscissor: MCommand

    def __getitem__(self, key: str, /) -> MCommand:
        """Get a command."""
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
    owner_is_admin: bool
    use_logging_file: bool
    admins: list[int]
    database: str
    group: str
    hunt: MHunt
    conjugation: Conjugation
    failed: RandomConjugableText
    hidden: RandomConjugableText
    spotted: RandomConjugableText
    appear: RandomItem[str]
    action: RandomItem[MText]
    commands: MCommands
    token: Optional[Union[str, msgspec.UnsetType]] = msgspec.UNSET
    _resources: Optional[Union[pathlib.Path, msgspec.UnsetType]] = (
        msgspec.field(name="resources", default=msgspec.UNSET)
    )
    _working_directory: Optional[Union[pathlib.Path, msgspec.UnsetType]] = (
        msgspec.field(name="working_directory", default=msgspec.UNSET)
    )

    @property
    def database_uri(self) -> str:
        """Get async string for database."""
        return self.database.replace(
            "%(data)s", "/" + self.working_directory.as_posix()
        )

    def verified_token(self) -> str:
        """Get the safe token."""
        if self.token is None or self.token is msgspec.UNSET:
            error_message = "Token was not provided"
            raise TypeError(error_message)
        if "." not in self.token:
            error_message = "Wrong token format"
            raise ValueError(error_message)
        return self.token

    def attach_default_working_directory(
        self,
        path: Union[pathlib.Path, str],
    ) -> None:
        """Attach working directory."""
        self._cwd = pathlib.Path(path)

    @property
    def working_directory(self) -> pathlib.Path:
        """Get the safe token."""
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
        """Get path to resources or the embed resources if not configured."""
        if self._resources is None or self._resources is msgspec.UNSET:
            return RESOURCES
        if self._resources.is_absolute():
            return self._resources
        return self.working_directory / self._resources

    def __post_init__(self) -> None:
        """Add conjugation to item and check some value."""
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
        """Conjugate the text."""
        conj = ConjugableText(text)
        conj.attach(self.conjugation)
        return conj(member)

    def alembic_config(self, namespace: Optional[Namespace] = None) -> Config:
        """Get alembic config."""
        config_alembic = str(self.resources / "alembic.ini")
        cfg = Config(
            file_=config_alembic,
            ini_section="alembic" if namespace is None else namespace.name,
            cmd_opts=namespace,
            attributes={
                "easterobot_config": self,
            },
        )
        cfg.set_main_option("sqlalchemy.url", self.database_uri)
        cfg.set_main_option("script_location", str(HERE / "alembic"))
        return cfg

    def configure_logging(self) -> None:
        """Configure logging."""
        if self.use_logging_file and not hasattr(self, "__logging_flag"):
            logging_file = self.resources / "logging.conf"
            defaults = {"data": self.working_directory.as_posix()}
            if not logging_file.is_file():
                error_message = f"Cannot find message: {str(logging_file)!r}"
                raise FileNotFoundError(error_message)
            logging.config.fileConfig(
                logging_file,
                disable_existing_loggers=False,
                defaults=defaults,
            )
            self.__logging_flag = True


def _dec_hook(typ: type[T], obj: Any) -> T:
    # Get the base type
    origin: Optional[type[T]] = get_origin(typ)
    if origin is None:
        origin = typ
    args = get_args(typ)
    if issubclass(origin, discord.PartialEmoji):
        return discord.PartialEmoji(  # type: ignore[return-value]
            name="_", animated=False, id=obj
        )
    if issubclass(origin, pathlib.Path):
        return cast(T, pathlib.Path(obj))
    if Serializable.decodable(origin):
        return cast(T, origin.decode(args, obj))
    error_message = f"Invalid type {typ!r} for {obj!r}"
    raise TypeError(error_message)


def _enc_hook(obj: Any) -> Any:
    if isinstance(obj, discord.PartialEmoji):
        return obj.id
    if isinstance(obj, pathlib.Path):
        return str(obj)
    if isinstance(obj, Serializable):
        return obj.encode()
    error_message = f"Invalid object {obj!r}"
    raise TypeError(error_message)


def load_yaml(data: Union[bytes, str], typ: type[T]) -> T:
    """Load YAML."""
    return msgspec.yaml.decode(  # type: ignore[no-any-return,unused-ignore]
        data, type=typ, dec_hook=_dec_hook
    )


def dump_yaml(obj: Any) -> bytes:
    """Load YAML."""
    return msgspec.yaml.encode(  # type: ignore[no-any-return,unused-ignore]
        obj, enc_hook=_enc_hook
    )


def convert(obj: Any, typ: type[T]) -> T:
    """Convert object."""
    return msgspec.convert(  # type: ignore[no-any-return,unused-ignore]
        obj, type=typ, dec_hook=_dec_hook
    )


def load_config_from_buffer(
    data: Union[bytes, str],
    token: Optional[str] = None,
    *,
    env: bool = False,
) -> MConfig:
    """Load config."""
    config = load_yaml(data, MConfig)
    if env:
        potential_token = os.environ.get("DISCORD_TOKEN")
        if potential_token is not None:
            config.token = potential_token
    if token is not None:
        config.token = token
    return config


def load_config_from_path(
    path: Union[str, pathlib.Path],
    token: Optional[str] = None,
    *,
    env: bool = False,
) -> MConfig:
    """Load config."""
    path = pathlib.Path(path)
    data = path.read_bytes()
    config = load_config_from_buffer(data, token=token, env=env)
    config.attach_default_working_directory(path.parent)
    return config


def agree(
    singular: str,
    plural: str,
    /,
    amount: Optional[int],
    *args: Any,
) -> str:
    """Agree the text to the text."""
    if amount is None or amount in (-1, 0, 1):
        return singular.format(amount, *args)
    return plural.format(amount, *args)


RE_VALID = re.compile(r"[^a-zA-Z0-9éàèê]")


def tokenize(text: str) -> List[str]:
    """Get token from text.

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
