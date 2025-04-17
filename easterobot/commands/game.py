"""Module for disable hunt."""

import discord

from easterobot.games.connect import Connect4
from easterobot.games.rock_paper_scissor import RockPaperScissor
from easterobot.games.tic_tac_toe import TicTacToe

from .base import Context, controlled_command, egg_command_group


@egg_command_group.command(
    name="connect4", description="Lancer une partie de puissance 4."
)
@controlled_command(cooldown=True)
async def connect4_command(ctx: Context, member: discord.Member) -> None:
    """Run a Connect4."""
    if (member.bot or member == ctx.user) and not ctx.client.is_super_admin(
        member
    ):
        await ctx.response.send_message("Invalid user !", ephemeral=True)
        return
    msg = await ctx.client.game.ask_dual(ctx, member)
    if msg:
        game = Connect4(ctx.user, member, msg)
        await ctx.client.game.run(game)


@egg_command_group.command(
    name="tictactoe", description="Lancer une partie de morpion."
)
@controlled_command(cooldown=True)
async def tictactoe_command(ctx: Context, member: discord.Member) -> None:
    """Run a tictactoe."""
    if (member.bot or member == ctx.user) and not ctx.client.is_super_admin(
        member
    ):
        await ctx.response.send_message("Invalid user !", ephemeral=True)
        return

    msg = await ctx.client.game.ask_dual(ctx, member)
    if msg:
        game = TicTacToe(ctx.user, member, msg)
        await ctx.client.game.run(game)


@egg_command_group.command(
    name="rockpaperscissor",
    description="Lancer une partie de pierre papier ciseaux.",
)
@controlled_command(cooldown=True)
async def rockpaperscissor_command(
    ctx: Context, member: discord.Member
) -> None:
    """Run a rockpaperscissor."""
    if (member.bot or member == ctx.user) and not ctx.client.is_super_admin(
        member
    ):
        await ctx.response.send_message("Invalid user !", ephemeral=True)
        return

    msg = await ctx.client.game.ask_dual(ctx, member)
    if msg:
        game = RockPaperScissor(ctx.user, member, msg)
        await ctx.client.game.run(game)
