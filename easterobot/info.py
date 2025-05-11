"""Module holding metadata."""

import logging
from importlib.metadata import Distribution

logger = logging.getLogger(__name__)
_DISTRIBUTION = Distribution.from_name(
    "easterobot",
)
_METADATA = _DISTRIBUTION.metadata
if len(_METADATA) != 0:
    if "Author" in _METADATA:
        __author__ = str(_METADATA["Author"])
        __email__ = str(_METADATA["Author-email"])
    else:
        __author__, __email__ = _METADATA["Author-email"][:-1].split(" <", 1)
    __version__ = _METADATA["Version"]
    __summary__ = _METADATA["Summary"]
else:
    logger.warning("Cannot load package metadata, please reinstall !")

    __author__ = "Unknown"
    __email__ = "Unknown"
    __version__ = "Unknown"
    __summary__ = "Unknown"

__copyright__ = f"{__author__} <{__email__}>"
__issues__ = "https://github.com/Dashstrom/easterobot/issues"
