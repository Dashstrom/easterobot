"""Discord bot help command module.

This module provides a help command that displays available bot commands
and their descriptions in an embedded message format.
"""

from discord.app_commands import AppCommandGroup

from easterobot.hunts.hunt import embed

from .base import Context, controlled_command, egg_command_group


@egg_command_group.command(
    name="help",
    description="Obtenir l'aide des commandes",
)
@controlled_command(cooldown=True, channel_permissions={"send_messages": True})
async def help_command(ctx: Context) -> None:
    """Display help information for available bot commands.

    Creates and sends an embed containing a list of all available commands
    with their descriptions. Only shows AppCommandGroup options from the
    bot's registered app commands.

    Args:
        ctx: The command context containing client and response information.
    """
    # Create the main help embed with bot information
    help_embed = embed(
        title="Liste des commandes",
        description=ctx.client.description,
        thumbnail=(
            ctx.client.user.display_avatar.url if ctx.client.user else None
        ),
        footer="Crée par dashstrom",
    )

    # Iterate through all registered app commands
    for app_command in ctx.client.app_commands:
        # Check each option within the command
        for command_option in app_command.options:
            # Only process AppCommandGroup options
            if not isinstance(command_option, AppCommandGroup):
                continue

            # Add command information as an embed field
            help_embed.add_field(
                name=(
                    f"</{egg_command_group.name} {command_option.name}:"
                    f"{app_command.id}>"
                ),
                value=f"{command_option.description}",
                inline=False,
            )

    # Send the help embed as a response
    await ctx.response.send_message(embed=help_embed)
