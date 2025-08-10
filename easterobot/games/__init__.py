"""Games package initialization for Discord bot game management system.

This module handles the setup and registration of the game management system,
providing the GameCog that orchestrates all game-related functionality
including turn-based games, duels, reaction handling, and game lifecycle
management.
"""

from easterobot.bot import Easterobot
from easterobot.games.game import GameCog

__all__ = [
    "GameCog",
]


async def setup(bot: Easterobot) -> None:
    """Set up and register the game management system with the Discord bot.

    Args:
        bot: The Easterobot instance to register the game system with.

    Creates a GameCog instance, assigns it to the bot's game attribute for
    easy access, and registers it as a Discord.py cog to handle events and
    commands related to game functionality.
    """
    # Create the game management cog
    game_manager = GameCog(bot)

    # Assign to bot for direct access to game management functionality
    bot.game = game_manager

    # Register the cog with Discord.py's command and event system
    await bot.add_cog(game_manager)
