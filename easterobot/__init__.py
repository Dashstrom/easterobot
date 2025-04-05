"""Main module."""

from .bot import Easterobot
from .cli import entrypoint
from .info import (
    __author__,
    __email__,
    __summary__,
    __version__,
)

__all__ = [
    "Easterobot",
    "__author__",
    "__email__",
    "__summary__",
    "__version__",
    "entrypoint",
]
