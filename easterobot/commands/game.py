"""Module for disable hunt."""

import asyncio
from contextlib import suppress
from typing import Optional

import discord
from discord import app_commands
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.config import RAND
from easterobot.games.connect4 import Connect4
from easterobot.games.game import Game
from easterobot.games.rock_paper_scissor import RockPaperScissor
from easterobot.games.skyjo import Skyjo
from easterobot.games.tic_tac_toe import TicTacToe
from easterobot.hunts.rank import Ranking
from easterobot.locker import EggLocker, EggLockerError

from .base import Context, controlled_command, egg_command_group


async def random_members(
    ctx: Context,
    bet: int,
) -> list[discord.Member]:
    """Random members."""
    # If no member choose a random play in the guild with enough egg
    if bet == 0:
        members = [
            m for m in ctx.guild.members if m.id != ctx.user.id and not m.bot
        ]
    else:
        # TODO(dashstrom): can chose member with locked eggs
        async with AsyncSession(ctx.client.engine) as session:
            ranking = await Ranking.from_guild(
                session,
                ctx.guild_id,
                unlock_only=True,
            )
        hunters = ranking.over(bet)
        mapper_member = {m.id: m for m in ctx.guild.members}
        members = [
            mapper_member[h.member_id]
            for h in hunters
            if h.member_id != ctx.user.id and h.member_id in mapper_member
        ]
    RAND.shuffle(members)
    return members


async def game_dual(  # noqa: D103
    ctx: Context,
    bet: int,
    cls: type[Game],
    *members: discord.Member,
) -> None:
    set_members = set(members)
    with suppress(KeyError):
        set_members.remove(ctx.user)
    min_player = cls.minimum_player()
    max_player = cls.maximum_player()
    if min_player > len(set_members) + 1:
        await ctx.response.send_message(
            f"Vous devez être au minimum {min_player} joueurs",
            ephemeral=True,
        )
        return
    if max_player < len(set_members) + 1:
        await ctx.response.send_message(
            f"Vous devez être au maximum {min_player} joueurs",
            ephemeral=True,
        )
        return

    # Check if user has enough eggs for ask
    async with AsyncSession(
        ctx.client.engine,
        expire_on_commit=False,
    ) as session:
        locker = EggLocker(session, ctx.guild.id)
        try:
            await locker.pre_check(
                {ctx.user: bet, **{m: bet for m in set_members}}
            )
        except EggLockerError as err:
            await ctx.response.send_message(str(err), ephemeral=True)
            return

        msg = await ctx.client.game.ask_dual(ctx, set_members, bet=bet)
        if msg:
            # Unlock all egg at end
            async with locker:
                # Lock the egg of player
                try:
                    async with locker.transaction():
                        all_eggs = await asyncio.gather(
                            locker.get(ctx.user, bet),
                            *[locker.get(m, bet) for m in set_members],
                        )
                except EggLockerError as err:
                    await msg.reply(str(err), delete_after=30)
                    return

                players = [ctx.user, *set_members]
                RAND.shuffle(players)
                game = cls(ctx.client, msg, *players)
                await ctx.client.game.run(game)
                winner = await game.wait_winner()
                if winner:
                    for eggs in all_eggs:
                        for egg in eggs:
                            egg.user_id = winner.member.id

                # Send change
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
    members = (
        (await random_members(ctx, bet))[:1] if member is None else [member]
    )
    await game_dual(ctx, bet, Connect4, *members)


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
    members = (
        (await random_members(ctx, bet))[:1] if member is None else [member]
    )
    await game_dual(ctx, bet, TicTacToe, *members)


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
    members = (
        (await random_members(ctx, bet))[:1] if member is None else [member]
    )
    await game_dual(ctx, bet, RockPaperScissor, *members)


@egg_command_group.command(
    name="skyjo",
    description="Lancer une partie de Skyjo",
)
@controlled_command(cooldown=True, channel_permissions={"send_messages": True})
async def skyjo_command(  # noqa: PLR0913
    ctx: Context,
    member1: Optional[discord.Member] = None,
    member2: Optional[discord.Member] = None,
    member3: Optional[discord.Member] = None,
    member4: Optional[discord.Member] = None,
    member5: Optional[discord.Member] = None,
    member6: Optional[discord.Member] = None,
    member7: Optional[discord.Member] = None,
    bet: app_commands.Range[int, 0] = 0,
) -> None:
    """Run a skyjo."""
    members = [
        m
        for m in (
            member1,
            member2,
            member3,
            member4,
            member5,
            member6,
            member7,
        )
        if m
    ]
    if not members:
        player_count = RAND.randint(1, 8)
        rand_members = await random_members(ctx, bet)
        members = rand_members[:player_count]
    await game_dual(ctx, bet, Skyjo, *members)
