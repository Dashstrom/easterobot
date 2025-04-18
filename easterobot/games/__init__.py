"""Init package."""

from easterobot.bot import Easterobot
from easterobot.games.game import GameCog

__all__ = [
    "GameCog",
]


async def setup(bot: Easterobot) -> None:
    game_cog = GameCog(bot)
    bot.game = game_cog
    await bot.add_cog(game_cog)
