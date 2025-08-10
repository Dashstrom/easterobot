"""Base module for Discord slash commands.

This module provides decorators and utilities for implementing controlled
slash commands with cooldowns, permission checks, and error handling.
It includes the main command group for easter egg hunt commands
and base types for interactions.
"""

import asyncio
import functools
import logging
from collections.abc import Callable, Coroutine
from time import time
from typing import Any, Concatenate, ParamSpec, TypeVar, cast

import discord
from discord import Permissions, app_commands
from sqlalchemy import and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.bot import Easterobot
from easterobot.models import Cooldown

# Main command group for all easter egg related commands
egg_command_group = app_commands.Group(
    name="egg",
    description="Commandes en lien avec Pâque",
    guild_only=True,
)

logger = logging.getLogger(__name__)

# Lock to prevent race conditions in cooldown checks
cooldown_lock = asyncio.Lock()


class InterruptedCommandError(Exception):
    """Raised when a command is interrupted and should reset cooldown."""


# Type alias for all possible Discord interaction channels
InteractionChannel = (
    discord.VoiceChannel
    | discord.StageChannel
    | discord.TextChannel
    | discord.Thread
    | discord.DMChannel
    | discord.GroupChannel
)


class Context(discord.Interaction[Easterobot]):
    """Enhanced Discord interaction context with guaranteed attributes.

    This context ensures that user, command, channel, and guild information
    is always available, making command handlers more reliable.
    """

    user: discord.Member
    command: "app_commands.Command[Any, ..., Any]"  # type: ignore[assignment,unused-ignore]
    channel: InteractionChannel
    channel_id: int
    guild: discord.Guild
    guild_id: int


# Type variables and aliases for generic function signatures
P = ParamSpec("P")
T = TypeVar("T")
Interaction = discord.Interaction[Easterobot]
Coro = Coroutine[Any, Any, T]


def controlled_command(  # noqa: C901, PLR0915
    *,
    cooldown: bool = True,
    channel_permissions: dict[str, bool] | None = None,
    **user_permissions: bool,
) -> Callable[
    [Callable[Concatenate[Context, P], Coro[None]]],
    Callable[Concatenate[Interaction, P], Coro[None]],
]:
    """Decorator that adds cooldown and permission checks to slash commands.

    Provides comprehensive validation including guild-only enforcement,
    user and bot permission checks, cooldown management, and error handling.
    Super admins can bypass cooldowns and most permission checks.

    Args:
        cooldown: Whether to enforce command cooldowns.
        channel_permissions: Bot permissions required in the channel.
        **user_permissions: User permissions required to run the command.

    Returns:
        Decorated command function with all validations applied.
    """

    def decorator(  # noqa: C901
        command_function: Callable[Concatenate[Context, P], Coro[None]],
    ) -> Callable[Concatenate[Interaction, P], Coro[None]]:
        @functools.wraps(command_function)
        async def decorated_command(  # noqa: C901, PLR0911, PLR0912
            interaction: Interaction, *args: P.args, **kwargs: P.kwargs
        ) -> None:
            # Validate interaction has required command information
            if not isinstance(interaction.command, app_commands.Command):
                logger.warning("No command provided %s", interaction)
                return
            if interaction.channel is None or interaction.channel_id is None:
                logger.warning("No channel provided %s", interaction)
                return

            # Create readable event identifier for logging
            event_identifier = (
                f"/{interaction.command.qualified_name} by {interaction.user} "
                f"({interaction.user.id}) in {interaction.channel.jump_url}"
            )

            # Enforce guild-only usage
            if interaction.guild is None or interaction.guild_id is None:
                logger.warning("Command must be used in a guild!")
                return
            if not isinstance(interaction.user, discord.Member):
                logger.warning("User must be guild member %s", interaction)
                return

            # Check if bot has required channel permissions
            if channel_permissions:
                bot_channel_permissions = discord.Permissions()
                if interaction.client.user:
                    bot_member = interaction.guild.get_member(
                        interaction.client.user.id
                    )
                    if bot_member is not None:
                        bot_channel_permissions = (
                            interaction.channel.permissions_for(bot_member)
                        )

                required_channel_permissions = Permissions(
                    **channel_permissions
                )
                if not bot_channel_permissions.is_superset(
                    required_channel_permissions
                ):
                    logger.warning(
                        "%s failed due to insufficient "
                        "bot channel permissions",
                        event_identifier,
                    )
                    await interaction.response.send_message(
                        "Le bot n'a pas la permission",
                        ephemeral=True,
                    )
                    return

            # Check user permissions (can be bypassed by super admins)
            required_user_permissions = discord.Permissions(**user_permissions)
            user_has_permissions = (
                interaction.user.guild_permissions.is_superset(
                    required_user_permissions
                )
            )
            is_super_administrator = interaction.client.is_super_admin(
                interaction.user
            )

            if not user_has_permissions and not is_super_administrator:
                logger.warning(
                    "%s failed due to insufficient user permissions",
                    event_identifier,
                )
                await interaction.response.send_message(
                    "Vous n'avez pas la permission",
                    ephemeral=True,
                )
                return

            # Handle command cooldown (super admins bypass cooldowns)
            command_name = interaction.command.name
            if cooldown and not is_super_administrator:
                cooldown_expires_at = None
                async with (
                    AsyncSession(
                        interaction.client.engine
                    ) as database_session,
                    # Prevent race conditions in cooldown checks
                    cooldown_lock,
                ):
                    # Check existing cooldown for this user/guild/command
                    existing_cooldown = await database_session.get(
                        Cooldown,
                        (
                            interaction.user.id,
                            interaction.guild_id,
                            command_name,
                        ),
                    )
                    command_cooldown_duration = (
                        interaction.client.config.commands[
                            command_name
                        ].cooldown
                    )
                    current_timestamp = time()

                    # Update or create cooldown record if expired
                    if (
                        existing_cooldown is None
                        or current_timestamp
                        > command_cooldown_duration
                        + existing_cooldown.timestamp
                    ):
                        await database_session.merge(
                            Cooldown(
                                user_id=interaction.user.id,
                                guild_id=interaction.guild_id,
                                command=command_name,
                                timestamp=current_timestamp,
                            )
                        )
                        await database_session.commit()
                    else:
                        # Calculate when cooldown expires
                        cooldown_expires_at = command_cooldown_duration
                        cooldown_expires_at += existing_cooldown.timestamp

                # Reject command if still on cooldown
                if cooldown_expires_at:
                    logger.warning(
                        "%s failed due to active cooldown", event_identifier
                    )
                    await interaction.response.send_message(
                        "Vous devez encore attendre "
                        f"<t:{cooldown_expires_at + 1:.0f}:R>",
                        ephemeral=True,
                    )
                    return

            # Execute the command with proper error handling
            logger.info("%s", event_identifier)
            try:
                await command_function(
                    cast("Context", interaction), *args, **kwargs
                )
            except InterruptedCommandError:
                # Reset cooldown if command was interrupted
                logger.warning(
                    "InterruptedCommandError occurred for %s",
                    event_identifier,
                )
                async with (
                    AsyncSession(
                        interaction.client.engine
                    ) as database_session,
                    cooldown_lock,
                ):
                    # Remove cooldown record to allow immediate retry
                    await database_session.execute(
                        delete(Cooldown).where(
                            and_(
                                Cooldown.guild_id == interaction.guild_id,
                                Cooldown.user_id == interaction.user.id,
                                Cooldown.command == command_name,
                            )
                        )
                    )
                    await database_session.commit()

        return decorated_command

    return decorator
