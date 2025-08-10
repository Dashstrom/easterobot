"""Logging utility with automatic directory creation.

This module provides a rotating file handler that ensures the target
log directory exists before writing logs, preventing runtime errors
due to missing directories.
"""

import pathlib
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class AutoDirRotatingFileHandler(RotatingFileHandler):
    """Rotating file handler that creates directories automatically."""

    def __init__(
        self,
        filename: str | pathlib.Path,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize handler and create parent directories if needed.

        Args:
            filename: Path to the log file.
            *args: Additional positional arguments passed to the base class.
            **kwargs: Additional keyword arguments passed to the base class.
        """
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(filename, *args, **kwargs)
