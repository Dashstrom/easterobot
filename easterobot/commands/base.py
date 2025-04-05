"""Base module for command."""

import asyncio
import functools
import logging
from collections.abc import Coroutine
from time import time
from typing import Any, Callable, TypeVar, Union, cast

import discord
from discord import app_commands
from sqlalchemy import and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Concatenate, ParamSpec

from easterobot.bot import Easterobot
from easterobot.models import Cooldown

egg_command_group = app_commands.Group(
    name="egg",
    description="Commandes en lien avec Pâque",
    guild_only=True,
)
logger = logging.getLogger(__name__)
cooldown_lock = asyncio.Lock()


class InterruptedCommandError(Exception):
    pass


InteractionChannel = Union[
    discord.VoiceChannel,
    discord.StageChannel,
    discord.TextChannel,
    discord.ForumChannel,
    discord.CategoryChannel,
    discord.Thread,
    discord.DMChannel,
    discord.GroupChannel,
]


class Context(discord.Interaction[Easterobot]):
    user: discord.Member
    command: "app_commands.Command[Any, ..., Any]"  # type: ignore[assignment]
    channel: InteractionChannel
    channel_id: int
    guild: discord.Guild
    guild_id: int


P = ParamSpec("P")
T = TypeVar("T")
Interaction = discord.Interaction[Easterobot]
Coro = Coroutine[Any, Any, T]


def controlled_command(
    *, cooldown: bool = True, **perms: bool
) -> Callable[
    [Callable[Concatenate[Context, P], Coro[None]]],
    Callable[Concatenate[Interaction, P], Coro[None]],
]:
    """Add a cooldown and permission check."""

    def decorator(
        f: Callable[Concatenate[Context, P], Coro[None]],
    ) -> Callable[Concatenate[Interaction, P], Coro[None]]:
        @functools.wraps(f)
        async def decorated(
            interaction: Interaction, *args: P.args, **kwargs: P.kwargs
        ) -> None:
            # Check if interaction is valid
            if not isinstance(interaction.command, app_commands.Command):
                logger.warning("No command provided %s", interaction)
                return
            if interaction.channel is None or interaction.channel_id is None:
                logger.warning("No channel provided %s", interaction)
                return

            # Preformat event repr
            event_repr = (
                f"/{interaction.command.qualified_name} by {interaction.user} "
                f"({interaction.user.id}) in {interaction.channel.jump_url}"
            )

            # Check if in guild
            if interaction.guild is None or interaction.guild_id is None:
                logger.warning("Must be use in a guild !")
                return
            if not isinstance(interaction.user, discord.Member):
                logger.warning("No channel provided %s", interaction)
                return

            # Compute needed permissions
            needed_perms = discord.Permissions(**perms)
            have_perms = interaction.user.guild_permissions.is_superset(
                needed_perms
            )
            admin_ids = interaction.client.config.admins
            is_super_admin = (
                interaction.user.id in admin_ids
                or interaction.user.id == interaction.client.owner_id
            )
            if not have_perms and not is_super_admin:
                logger.warning("%s failed for wrong permissions", event_repr)
                await interaction.response.send_message(
                    "Vous n'avez pas la permission",
                    ephemeral=True,
                )
                return

            # Check command cooldown
            cmd = interaction.command.name
            if cooldown:
                available_at = None
                async with (
                    AsyncSession(interaction.client.engine) as session,
                    cooldown_lock,  # We must use lock for avoid race condition
                ):
                    cd_user = await session.get(
                        Cooldown,
                        (interaction.user.id, interaction.guild_id, cmd),
                    )
                    cd_cmd = interaction.client.config.commands[cmd].cooldown
                    now = time()
                    if cd_user is None or now > cd_cmd + cd_user.timestamp:
                        await session.merge(
                            Cooldown(
                                user_id=interaction.user.id,
                                guild_id=interaction.guild_id,
                                command=cmd,
                                timestamp=now,
                            )
                        )
                        await session.commit()
                    else:
                        available_at = cd_cmd + cd_user.timestamp
                if available_at:
                    logger.warning("%s failed for cooldown", event_repr)
                    await interaction.response.send_message(
                        "Vous devez encore attendre "
                        f"<t:{available_at + 1:.0f}:R>",
                        ephemeral=True,
                    )
                    return
            logger.info("%s", event_repr)
            try:
                await f(cast(Context, interaction), *args, **kwargs)
            except InterruptedCommandError:
                logger.exception("InterruptedCommandError occur")
                async with (
                    AsyncSession(interaction.client.engine) as session,
                    cooldown_lock,
                ):
                    # This is unsafe
                    await session.execute(
                        delete(Cooldown).where(
                            and_(
                                Cooldown.guild_id == interaction.guild_id,
                                Cooldown.user_id == interaction.user.id,
                                Cooldown.command == cmd,
                            )
                        )
                    )
                    await session.commit()

        return decorated

    return decorator
