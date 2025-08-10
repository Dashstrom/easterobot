"""Discord bot games module.

This module provides various game commands for the Easter bot including
Connect4, Tic-Tac-Toe, Rock Paper Scissors, and Skyjo. All games support
betting with eggs and can be played against specific members or random players.
"""

import asyncio
from contextlib import suppress

import discord
from discord import app_commands
from sqlalchemy.ext.asyncio import AsyncSession

from easterobot.commands.base import (
    Context,
    controlled_command,
    egg_command_group,
)
from easterobot.config import RAND
from easterobot.games.connect4 import Connect4
from easterobot.games.game import Game
from easterobot.games.rock_paper_scissors import RockPaperScissors
from easterobot.games.skyjo import Skyjo
from easterobot.games.tic_tac_toe import TicTacToe
from easterobot.hunts.rank import Ranking
from easterobot.locker import EggLocker, EggLockerError


async def get_random_members(
    ctx: Context,
    bet_amount: int,
) -> list[discord.Member]:
    """Get random eligible members for game participation.

    If no bet is required, returns all non-bot members except the command user.
    If a bet is required, returns members with sufficient eggs.

    Args:
        ctx: The command context containing guild and user information.
        bet_amount: The number of eggs required to participate.

    Returns:
        A shuffled list of eligible members.
    """
    if bet_amount == 0:
        # No bet required - include all non-bot members except command user
        eligible_members = [
            member
            for member in ctx.guild.members
            if member.id != ctx.user.id and not member.bot
        ]
    else:
        # Bet required - check which members have sufficient eggs
        # TODO(dashstrom): can choose member with locked eggs
        async with AsyncSession(ctx.client.engine) as session:
            ranking = await Ranking.from_guild(
                session,
                ctx.guild_id,
                unlock_only=True,
            )

        # Get hunters with enough eggs for the bet
        qualified_hunters = ranking.over(bet_amount)
        member_id_to_member = {
            member.id: member for member in ctx.guild.members
        }

        # Filter out command user and ensure member is still in guild
        eligible_members = [
            member_id_to_member[hunter.member_id]
            for hunter in qualified_hunters
            if (
                hunter.member_id != ctx.user.id
                and hunter.member_id in member_id_to_member
            )
        ]

    RAND.shuffle(eligible_members)
    return eligible_members


async def start_game_duel(
    ctx: Context,
    bet_amount: int,
    game_class: type[Game],
    *opponents: discord.Member,
) -> None:
    """Start a game duel with specified opponents and bet amount.

    Validates player count, checks egg balances, locks eggs for betting,
    and runs the game. Winner takes all bet eggs.

    Args:
        ctx: The command context.
        bet_amount: Number of eggs each player must bet.
        game_class: The game class to instantiate.
        *opponents: Variable number of opponent members.
    """
    # Remove command user from opponents set if present
    opponent_set = set(opponents)
    with suppress(KeyError):
        opponent_set.remove(ctx.user)

    # Validate player count against game requirements
    min_players = game_class.minimum_player_count()
    max_players = game_class.maximum_player_count()
    total_players = len(opponent_set) + 1  # +1 for command user

    if min_players > total_players:
        await ctx.response.send_message(
            f"Vous devez être au minimum {min_players} joueurs",
            ephemeral=True,
        )
        return

    if max_players < total_players:
        await ctx.response.send_message(
            f"Vous devez être au maximum {max_players} joueurs",
            ephemeral=True,
        )
        return

    # Check if all players have enough eggs for the bet
    async with AsyncSession(
        ctx.client.engine,
        expire_on_commit=False,
    ) as session:
        egg_locker = EggLocker(session, ctx.guild.id)

        try:
            # Pre-check all players have sufficient eggs
            player_bets = {
                ctx.user: bet_amount,
                **dict.fromkeys(opponent_set, bet_amount),
            }
            await egg_locker.pre_check(player_bets)
        except EggLockerError as error:
            await ctx.response.send_message(str(error), ephemeral=True)
            return

        # Ask for game confirmation and get message
        game_message = await ctx.client.game.request_duel(
            ctx,
            opponent_set,
            bet_amount=bet_amount,
        )
        if game_message:
            # Lock eggs and run the game
            async with egg_locker:
                try:
                    # Lock eggs for all players within a transaction
                    async with egg_locker.transaction():
                        all_player_eggs = await asyncio.gather(
                            egg_locker.get(ctx.user, bet_amount),
                            *[
                                egg_locker.get(opponent, bet_amount)
                                for opponent in opponent_set
                            ],
                        )
                except EggLockerError as error:
                    await game_message.reply(str(error), delete_after=30)
                    return

                # Shuffle players and start the game
                all_players = [ctx.user, *opponent_set]
                RAND.shuffle(all_players)
                game_instance = game_class(
                    ctx.client, game_message, *all_players
                )

                await ctx.client.game.register_and_run_game(game_instance)
                winner = await game_instance.wait_for_completion()

                # Transfer all eggs to winner if there is one
                if winner:
                    for player_eggs in all_player_eggs:
                        for egg in player_eggs:
                            egg.user_id = winner.member.id

                # Commit all changes to database
                await session.commit()


@egg_command_group.command(
    name="connect4",
    description="Lancer une partie de puissance 4",
)
@controlled_command(cooldown=True, channel_permissions={"send_messages": True})
async def connect4_command(
    ctx: Context,
    member: discord.Member | None = None,
    bet: app_commands.Range[int, 0] = 0,
) -> None:
    """Start a Connect4 game against a specified or random opponent.

    Args:
        ctx: The command context.
        member: Specific member to challenge. If None, selects random opponent.
        bet: Number of eggs to bet on the game.
    """
    opponents = (
        (await get_random_members(ctx, bet))[:1]
        if member is None
        else [member]
    )
    await start_game_duel(ctx, bet, Connect4, *opponents)


@egg_command_group.command(
    name="tictactoe",
    description="Lancer une partie de morpion",
)
@controlled_command(cooldown=True, channel_permissions={"send_messages": True})
async def tictactoe_command(
    ctx: Context,
    member: discord.Member | None = None,
    bet: app_commands.Range[int, 0] = 0,
) -> None:
    """Start a Tic-Tac-Toe game against a specified or random opponent.

    Args:
        ctx: The command context.
        member: Specific member to challenge. If None, selects random opponent.
        bet: Number of eggs to bet on the game.
    """
    opponents = (
        (await get_random_members(ctx, bet))[:1]
        if member is None
        else [member]
    )
    await start_game_duel(ctx, bet, TicTacToe, *opponents)


@egg_command_group.command(
    name="rockpaperscissors",
    description="Lancer une partie de pierre papier ciseaux",
)
@controlled_command(cooldown=True, channel_permissions={"send_messages": True})
async def rockpaperscissors_command(
    ctx: Context,
    member: discord.Member | None = None,
    bet: app_commands.Range[int, 0] = 0,
) -> None:
    """Start a Rock Paper Scissors game against a specified or random opponent.

    Args:
        ctx: The command context.
        member: Specific member to challenge. If None, selects random opponent.
        bet: Number of eggs to bet on the game.
    """
    opponents = (
        (await get_random_members(ctx, bet))[:1]
        if member is None
        else [member]
    )
    await start_game_duel(ctx, bet, RockPaperScissors, *opponents)


@egg_command_group.command(
    name="skyjo",
    description="Lancer une partie de Skyjo",
)
@controlled_command(cooldown=True, channel_permissions={"send_messages": True})
async def skyjo_command(
    ctx: Context,
    member1: discord.Member | None = None,
    member2: discord.Member | None = None,
    member3: discord.Member | None = None,
    member4: discord.Member | None = None,
    member5: discord.Member | None = None,
    member6: discord.Member | None = None,
    member7: discord.Member | None = None,
    bet: app_commands.Range[int, 0] = 0,
) -> None:
    """Start a Skyjo game with specified members or random players.

    If no members are specified, randomly selects 1-8 players for the game.
    Skyjo supports multiple players unlike other games.

    Args:
        ctx: The command context.
        member1: First optional member to include.
        member2: Second optional member to include.
        member3: Third optional member to include.
        member4: Fourth optional member to include.
        member5: Fifth optional member to include.
        member6: Sixth optional member to include.
        member7: Seventh optional member to include.
        bet: Number of eggs to bet on the game.
    """
    # Collect all specified members
    specified_members = [
        member
        for member in (
            member1,
            member2,
            member3,
            member4,
            member5,
            member6,
            member7,
        )
        if member is not None
    ]

    # If no members specified, select random players
    if not specified_members:
        random_player_count = RAND.randint(1, 8)
        available_members = await get_random_members(ctx, bet)
        specified_members = available_members[:random_player_count]

    await start_game_duel(ctx, bet, Skyjo, *specified_members)
