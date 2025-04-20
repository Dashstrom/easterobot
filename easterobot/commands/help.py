"""Module for help command."""

from discord.app_commands import AppCommandGroup

from easterobot.hunts.hunt import embed

from .base import Context, controlled_command, egg_command_group


@egg_command_group.command(
    name="help",
    description="Obtenir l'aide des commandes"
)
@controlled_command(cooldown=True)
async def help_command(ctx: Context) -> None:
    """Help command."""
    emb = embed(
        title="Liste des commandes",
        description=ctx.client.description,
        thumbnail=(
            ctx.client.user.display_avatar.url if ctx.client.user else None
        ),
        footer="Crée par dashstrom",
    )
    for command in ctx.client.app_commands:
        for option in command.options:
            if not isinstance(option, AppCommandGroup):
                continue
            emb.add_field(
                name=(
                    f"</{egg_command_group.name} {option.name}:{command.id}>"
                ),
                value=f"{option.description}",
                inline=False,
            )
    await ctx.response.send_message(embed=emb, ephemeral=True)
