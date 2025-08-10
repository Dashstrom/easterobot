"""Init module of easterobot."""

from .bot import Easterobot
from .cli import entrypoint
from .info import (
    __author__,
    __copyright__,
    __email__,
    __issues__,
    __license__,
    __maintainer__,
    __maintainer_email__,
    __project__,
    __summary__,
    __version__,
)

__all__ = [
    "Easterobot",
    "__author__",
    "__copyright__",
    "__email__",
    "__issues__",
    "__license__",
    "__maintainer__",
    "__maintainer_email__",
    "__project__",
    "__summary__",
    "__version__",
    "entrypoint",
]
