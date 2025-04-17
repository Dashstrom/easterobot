"""Init package."""

from easterobot.bot import Easterobot
from easterobot.commands.base import egg_command_group
from easterobot.commands.basket import basket_command
from easterobot.commands.disable import disable_command
from easterobot.commands.edit import edit_command
from easterobot.commands.enable import enable_command
from easterobot.commands.game import (
    connect4_command,
    rockpaperscissor_command,
    tictactoe_command,
)
from easterobot.commands.help import help_command
from easterobot.commands.reset import reset_command
from easterobot.commands.search import search_command
from easterobot.commands.top import top_command

__all__ = [
    "basket_command",
    "connect4_command",
    "disable_command",
    "edit_command",
    "egg_command_group",
    "enable_command",
    "help_command",
    "reset_command",
    "rockpaperscissor_command",
    "search_command",
    "tictactoe_command",
    "top_command",
]


async def setup(bot: Easterobot) -> None:
    bot.tree.add_command(egg_command_group)
