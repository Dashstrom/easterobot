"""Init package."""

from easterobot.bot import Easterobot
from easterobot.games.game import GameCog

__all__ = [
    "basket_command",
    "connect4_command",
    "disable_command",
    "edit_command",
    "egg_command_group",
    "enable_command",
    "help_command",
    "reset_command",
    "search_command",
    "top_command",
]


async def setup(bot: Easterobot) -> None:
    game_cog = GameCog(bot)
    bot.game = game_cog
    await bot.add_cog(game_cog)
