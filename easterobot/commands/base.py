import asyncio
import functools
import logging
from time import time
from typing import Awaitable, Callable, cast

import discord
from sqlalchemy import and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Concatenate, ParamSpec

from ..bot import Easterbot
from ..models import Cooldown


class EasterbotContext(discord.ApplicationContext):
    bot: Easterbot
    user: discord.Member  # type: ignore
    author: discord.Member  # type: ignore


egg_command_group = discord.SlashCommandGroup(
    "egg", "Commandes en lien avec Pâque", guild_only=True
)
logger = logging.getLogger("easterobot")


Param = ParamSpec("Param")


class InteruptedCommandError(Exception):
    def __init__(self) -> None:
        pass


lock = asyncio.Lock()


def controled_command(
    cooldown: bool = True, **perms: bool
) -> Callable[
    [Callable[Concatenate[EasterbotContext, Param], Awaitable[None]]],
    Callable[Concatenate[discord.ApplicationContext, Param], Awaitable[None]],
]:
    def decorator(
        f: Callable[Concatenate[EasterbotContext, Param], Awaitable[None]]
    ) -> Callable[
        Concatenate[discord.ApplicationContext, Param], Awaitable[None]
    ]:
        @functools.wraps(f)
        async def decorated(
            ctx: EasterbotContext, *args: Param.args, **kwargs: Param.kwargs
        ) -> None:
            cmd = ctx.command.name
            eventname = (
                f"/{ctx.command.qualified_name} by {ctx.user} "
                f"({ctx.user.id}) in {ctx.channel.jump_url}"
            )
            needed_perms = discord.Permissions(**perms)
            if isinstance(ctx.user, discord.Member):
                have_perms = ctx.user.guild_permissions.is_superset(
                    needed_perms
                )
            else:
                have_perms = False
            is_superadmin = ctx.user.id in ctx.bot.config.admin_ids
            if not have_perms and not is_superadmin:
                logger.warning("%s failed for wrong permissions", eventname)
                await ctx.respond(
                    "Vous n'avez pas la permission",
                    ephemeral=True,
                )
                return

            if cooldown:
                wait = None
                async with AsyncSession(ctx.bot.engine) as session, lock:
                    cd = await session.get(
                        Cooldown,
                        (ctx.user.id, ctx.guild_id, cmd),
                    )
                    cd_cmd: float = ctx.bot.config.command_attr(
                        cmd, "cooldown"
                    )
                    now = time()
                    if cd is None or now > cd_cmd + cd.timestamp:
                        await session.merge(
                            Cooldown(
                                user_id=ctx.user.id,
                                guild_id=ctx.guild_id,
                                command=cmd,
                                timestamp=now,
                            )
                        )
                        await session.commit()
                    else:
                        wait = cd_cmd + cd.timestamp
                if wait:
                    logger.warning("%s failed for cooldown", eventname)
                    await ctx.respond(
                        f"Vous devez encore attendre <t:{wait + 1:.0f}:R>",
                        ephemeral=True,
                    )
                    return
            logger.info("%s", eventname)
            try:
                await f(ctx, *args, **kwargs)
            except InteruptedCommandError:
                logger.exception("InteruptedCommandError occur")
                async with AsyncSession(ctx.bot.engine) as session:
                    # This is unsafe
                    await session.execute(
                        delete(Cooldown).where(
                            and_(
                                Cooldown.guild_id == ctx.guild_id,
                                Cooldown.user_id == ctx.user.id,
                                Cooldown.command == cmd,
                            )
                        )
                    )
                    await session.commit()

        return cast(
            Callable[
                Concatenate[discord.ApplicationContext, Param], Awaitable[None]
            ],
            decorated,
        )

    return decorator
