"""Enable hunt."""

from easterobot.bot import Easterobot
from easterobot.hunts.hunt import HuntCog

__all__ = [
    "HuntCog",
]


async def setup(bot: Easterobot) -> None:
    hunt_cog = HuntCog(bot)
    bot.hunt = hunt_cog
    await bot.add_cog(hunt_cog)
