from ..bot import embed
from .base import EasterbotContext, controled_command, egg_command_group


@egg_command_group.command(name="help", description="Obtenir de l'aide")
@controled_command(cooldown=True)
async def help_command(ctx: EasterbotContext) -> None:
    emb = embed(
        title="Liste des commandes",
        description=ctx.bot.description,
        thumbnail=ctx.bot.user.display_avatar.url,  # type: ignore
        footer="Crée par Dashstrom#6593",
    )
    for cmd in egg_command_group.subcommands:
        emb.add_field(
            name=f"/{egg_command_group.name} {cmd.name}",
            value=f"{cmd.description}",
            inline=False,
        )
    await ctx.respond(embed=emb, ephemeral=True)
