"""Easterobot commands package initializer.

This module imports all available command handlers for Easterobot and
registers the root command group when the bot is set up.
"""

from easterobot.bot import Easterobot
from easterobot.commands.base import egg_command_group
from easterobot.commands.basket import basket_command
from easterobot.commands.disable import disable_command
from easterobot.commands.edit import edit_command
from easterobot.commands.enable import enable_command
from easterobot.commands.game import (
    connect4_command,
    rockpaperscissors_command,
    tictactoe_command,
)
from easterobot.commands.help import help_command
from easterobot.commands.info import info_command
from easterobot.commands.reset import reset_command
from easterobot.commands.roulette import roulette_command
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
    "info_command",
    "reset_command",
    "rockpaperscissors_command",
    "roulette_command",
    "search_command",
    "tictactoe_command",
    "top_command",
]


async def setup(bot: Easterobot) -> None:
    """Register the Easterobot root command group.

    Args:
        bot: The Easterobot instance to register commands to.
    """
    egg_command_group.name = bot.config.group
    bot.tree.add_command(egg_command_group)
