"""Utility functions related to time formatting."""

from datetime import datetime, timedelta

from discord.utils import format_dt


def in_seconds(seconds: float) -> str:
    """Return a human-readable relative time string from seconds offset.

    Calculates a future time by adding the given seconds to the current time
    and formats it as a relative timestamp suitable for Discord.

    Args:
        seconds: Number of seconds to add to the current time.

    Returns:
        A string representing the relative time (e.g., "in 5 minutes").
    """
    future_time = datetime.now() + timedelta(seconds=seconds)  # noqa: DTZ005
    return format_dt(future_time, style="R")
