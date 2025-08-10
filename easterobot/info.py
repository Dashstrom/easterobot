"""Metadata for easterobot."""

from importlib.metadata import Distribution

# fmt: off
__project__ = "easterobot"

_DISTRIBUTION = Distribution.from_name(__project__)
_METADATA = _DISTRIBUTION.metadata

if "Author" in _METADATA:  # pragma: no cover
    __author__ = str(_METADATA["Author"])
    __email__ = str(_METADATA["Author-email"])
else:  # pragma: no cover
    __author__, __email__ = _METADATA["Author-email"][:-1].split(" <", 1)
if "Maintainer" in _METADATA:  # pragma: no cover
    __maintainer__ = str(_METADATA["Maintainer"])
    __maintainer_email__ = str(_METADATA["Maintainer-email"])
else:  # pragma: no cover
    __maintainer__, __maintainer_email__ = _METADATA["Maintainer-email"][:-1].split(" <", 1)
if "License-Expression" in _METADATA:  # pragma: no cover
    __license__: str = _METADATA["License-Expression"]
else:  # pragma: no cover
    __license__ = _METADATA["License"]

__version__: str = _METADATA["Version"]
__summary__: str = _METADATA["Summary"]
__copyright__ = "Copyright (c) 2024, Dashstrom <dashstrom.pro@gmail.com>"
__issues__ = "https://github.com/Dashstrom/easterobot/issues"
# fmt: on
