"""Module for utils functions."""

from datetime import datetime, timedelta

from discord.utils import format_dt


def in_seconds(seconds: float) -> str:
    """Get format as seconds."""
    now = datetime.now() + timedelta(seconds=seconds)  # noqa: DTZ005
    return format_dt(now, style="R")
