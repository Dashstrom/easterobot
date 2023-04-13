import functools
import logging
from datetime import timedelta
from time import time
from typing import Awaitable, Callable, cast

import discord
import humanize
from sqlalchemy.orm import Session
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
                with Session(ctx.bot.engine) as session:
                    cd = session.get(
                        Cooldown,
                        (ctx.user.id, ctx.guild_id, cmd),
                    )
                    cd_cmd: float = ctx.bot.config.command_attr(
                        cmd, "cooldown"
                    )
                    now = time()
                    if cd is None or now > cd_cmd + cd.timestamp:
                        session.merge(
                            Cooldown(
                                user_id=ctx.user.id,
                                guild_id=ctx.guild_id,
                                command=cmd,
                                timestamp=now,
                            )
                        )
                        session.commit()
                    else:
                        wait = timedelta(seconds=cd_cmd + cd.timestamp - now)
                if wait:
                    wait_msg = humanize.naturaldelta(wait)
                    logger.warning("%s failed for cooldown", eventname)
                    await ctx.respond(
                        f"Vous devez encore attendre {wait_msg}",
                        ephemeral=True,
                    )
                    return
            logger.info("%s", eventname)
            await f(ctx, *args, **kwargs)

        return cast(
            Callable[
                Concatenate[discord.ApplicationContext, Param], Awaitable[None]
            ],
            decorated,
        )

    return decorator
