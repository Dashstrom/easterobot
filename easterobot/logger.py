"""Module for logging stuff."""

import pathlib
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Union


class AutoDirRotatingFileHandler(RotatingFileHandler):
    def __init__(
        self, filename: Union[str, pathlib.Path], *args: Any, **kwargs: Any
    ) -> None:
        """Show logger."""
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(filename, *args, **kwargs)
