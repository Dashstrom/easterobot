"""Initializes and registers the HuntCog extension for Easterobot.

This module is responsible for creating an instance of HuntCog,
attaching it to the bot instance, and registering it so that the bot
can handle hunt-related features.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from easterobot.bot import Easterobot

__all__ = [
    "HuntCog",
]


async def setup(bot: "Easterobot") -> None:
    """Load and register the HuntCog with the bot.

    This function creates a new HuntCog instance, attaches it as an
    attribute to the bot for easy access, and registers it so the bot
    can process hunt-related commands and events.

    Args:
        bot: The Easterobot instance to which the HuntCog will be added.
    """
    from easterobot.hunts.hunt import HuntCog  # noqa: PLC0415

    hunt_cog = HuntCog(bot)
    bot.hunt = hunt_cog
    await bot.add_cog(hunt_cog)
