from ..bot import Easterbot
from .base import egg_command_group
from .basket import basket_command
from .disable import disable_command
from .edit import edit_command
from .enable import enable_command
from .help import help_command
from .reset import reset_command
from .search import search_command
from .top import top_command

__all__ = [
    "egg_command_group",
    "basket_command",
    "disable_command",
    "edit_command",
    "enable_command",
    "help_command",
    "reset_command",
    "search_command",
    "top_command",
]


def setup(bot: Easterbot) -> None:
    egg_command_group.name = bot.config.group
    bot.add_application_command(egg_command_group)
