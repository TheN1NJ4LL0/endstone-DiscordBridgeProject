
import discord
from discord import app_commands

from ..util import MinecraftCogBase


class ServerStatusCommands(MinecraftCogBase):
    @app_commands.command(name="list", description="List players currently online.")
    async def list_cmd(self, interaction: discord.Interaction):
        dm = self.plugin.config.features.list_dm_default

        def pull():
            players = [p.name for p in self.server.online_players]
            return players

        players = await self._run_on_server_thread(pull)
        text = (", ".join(players) or "None") + f" ({len(players)} online)"

        if dm:
            try:
                await interaction.user.send(f"Online: {text}")
                await interaction.response.send_message("📬 Sent to your DMs.", ephemeral=True)
                return
            except Exception:
                pass
        await interaction.response.send_message(f"**Online:** {text}")

    @app_commands.command(name="tps", description="Quick TPS/MSPT readout.")
    async def tps(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        def collect():
            s = self.server
            return getattr(s, "current_tps", None), getattr(s, "current_mspt", None)

        tps, mspt = await self._run_on_server_thread(collect)
        if tps is None or mspt is None:
            await interaction.followup.send("No TPS/MSPT data available.", ephemeral=True)
            return
        await interaction.followup.send(f"**TPS:** {tps:.2f} | **MSPT:** {mspt:.2f} ms", ephemeral=True)
