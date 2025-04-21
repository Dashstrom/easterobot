"""Module for disable hunt."""

import asyncio
from typing import Callable, Optional

import discord
from discord import app_commands
from sqlalchemy import and_, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.config import RAND
from easterobot.games.connect import Connect4
from easterobot.games.game import Game
from easterobot.games.rock_paper_scissor import RockPaperScissor
from easterobot.games.tic_tac_toe import TicTacToe
from easterobot.hunts.rank import Ranking
from easterobot.models import Egg

from .base import Context, controlled_command, egg_command_group

lock = asyncio.Lock()


async def get_unlocked_eggs(
    session: AsyncSession, member: discord.Member, counter: int
) -> list[Egg]:
    """Get the count of unlocked eggs."""
    return list(
        (
            await session.scalars(
                select(Egg)
                .where(
                    and_(
                        Egg.guild_id == member.guild.id,
                        Egg.user_id == member.id,
                        not_(Egg.lock),
                    )
                )
                .order_by(func.random())  # Randomize
                .limit(counter)
            )
        ).all()
    )


async def game_dual(  # noqa: C901, D103, PLR0912
    ctx: Context,
    member: Optional[discord.Member],
    bet: int,
    cls: Callable[[discord.Member, discord.Member, discord.Message], Game],
) -> None:
    # If no member choose a random play in the guild with enough egg
    if member is None:
        if bet == 0:
            members = [m for m in ctx.guild.members if m.id != ctx.user.id]
        else:
            # TODO(dashstrom): can chose member with locked eggs
            async with AsyncSession(ctx.client.engine) as session:
                ranking = await Ranking.from_guild(session, ctx.guild_id)
            hunters = ranking.over(bet)
            mapper_member = {m.id: m for m in ctx.guild.members}
            members = [
                mapper_member[h.member_id]
                for h in hunters
                if h.member_id != ctx.user.id and h.member_id in mapper_member
            ]
        if members:
            member = RAND.choice(members)
        else:
            await ctx.response.send_message(
                "Aucun utilisateur trouvé !",
                ephemeral=True,
            )
            return

    # Validate user
    if (member.bot or member == ctx.user) and not ctx.client.is_super_admin(
        member
    ):
        await ctx.response.send_message(
            "L'utilisateur n'est pas valide !",
            ephemeral=True,
        )
        return

    # Check if user has enough eggs for ask
    async with AsyncSession(ctx.client.engine) as session:
        e1, e2 = await asyncio.gather(
            get_unlocked_eggs(session, ctx.user, bet),
            get_unlocked_eggs(session, member, bet),
        )
        if len(e1) < bet:
            await ctx.response.send_message(
                "Vous n'avez pas assez d'œufs",
                ephemeral=True,
            )
            return
        if len(e2) < bet:
            await ctx.response.send_message(
                f"{member.mention} n'a pas assez d'œufs",
                ephemeral=True,
            )
            return

    msg = await ctx.client.game.ask_dual(ctx, member, bet=bet)
    if msg:
        # Check if user still have enough eggs and lock them
        async with AsyncSession(ctx.client.engine) as session:
            async with lock:
                e1, e2 = await asyncio.gather(
                    get_unlocked_eggs(session, ctx.user, bet),
                    get_unlocked_eggs(session, member, bet),
                )
                if len(e1) < bet:
                    await ctx.response.send_message(
                        "Vous n'avez plus assez d'œufs",
                        ephemeral=True,
                    )
                    return
                for e in e1:
                    e.lock = True
                if len(e2) < bet:
                    await ctx.response.send_message(
                        f"{member.mention} n'a plus assez d'œufs",
                        ephemeral=True,
                    )
                    return
                for e in e2:
                    e.lock = True
                await session.commit()

            # Play the game
            winner = None
            try:
                game = cls(ctx.user, member, msg)
                await ctx.client.game.run(game)
                winner = await game.wait_winner()
            finally:
                # Give eggs to the winner or remove previous one
                async with lock:
                    for e in e1:
                        e.lock = False
                        if winner:
                            e.user_id = winner.id
                    for e in e2:
                        e.lock = False
                        if winner:
                            e.user_id = winner.id
                    await session.commit()


@egg_command_group.command(
    name="connect4",
    description="Lancer une partie de puissance 4",
)
@controlled_command(cooldown=True, channel_permissions={"send_messages": True})
async def connect4_command(
    ctx: Context,
    member: Optional[discord.Member] = None,
    bet: app_commands.Range[int, 0] = 0,
) -> None:
    """Run a Connect4."""
    await game_dual(ctx, member, bet, Connect4)


@egg_command_group.command(
    name="tictactoe",
    description="Lancer une partie de morpion",
)
@controlled_command(cooldown=True, channel_permissions={"send_messages": True})
async def tictactoe_command(
    ctx: Context,
    member: Optional[discord.Member] = None,
    bet: app_commands.Range[int, 0] = 0,
) -> None:
    """Run a tictactoe."""
    await game_dual(ctx, member, bet, TicTacToe)


@egg_command_group.command(
    name="rockpaperscissor",
    description="Lancer une partie de pierre papier ciseaux",
)
@controlled_command(cooldown=True, channel_permissions={"send_messages": True})
async def rockpaperscissor_command(
    ctx: Context,
    member: Optional[discord.Member] = None,
    bet: app_commands.Range[int, 0] = 0,
) -> None:
    """Run a rockpaperscissor."""
    await game_dual(ctx, member, bet, RockPaperScissor)
