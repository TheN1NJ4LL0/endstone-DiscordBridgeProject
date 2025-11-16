import discord
from discord import app_commands
from discord.ext import commands

from ..util import safe_defer, safe_send, is_admin


class SettingsCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.plugin = bot.plugin

    @app_commands.command(name="set_presence", description="Admin: update the presence template.")
    @app_commands.describe(template="Example: 'Players {players} | TPS {tps:.2f}'")
    async def set_presence(self, inter: discord.Interaction, template: str):
        await safe_defer(inter, ephemeral=True)
        if not is_admin(self.bot, inter):
            await safe_send(inter, "❌ No permission.", ephemeral=True)
            return
        self.plugin.plugin_config.presence_template = template
        await safe_send(inter, f"✅ Presence template updated to:\n`{template}`", ephemeral=True)
