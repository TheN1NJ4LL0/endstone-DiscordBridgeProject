
from datetime import datetime, timezone

import discord
from discord import app_commands

from ..util import MinecraftCogBase


class AccountLinkCommands(MinecraftCogBase):
    """Discord-side of the in-game link system (/link in MC -> /verify here)."""

    @app_commands.command(name="verify", description="Link your Discord to your Minecraft using a /link code.")
    @app_commands.describe(code="Your 6-character code from /link in Minecraft")
    async def verify(self, interaction: discord.Interaction, code: str):
        await interaction.response.defer(ephemeral=True)

        def do_verify():
            store = self.plugin.linked
            now = datetime.now(timezone.utc).timestamp()
            for uuid, meta in list(store.pending.items()):
                if meta.get("code") == code:
                    if meta.get("expires", 0) < now:
                        return False, "This code expired. Run /link again in-game."
                    store.links[uuid] = str(interaction.user.id)
                    del store.pending[uuid]
                    self.plugin.save_linked()
                    return True, uuid
            return False, "Invalid code."

        ok, msg = await self._run_on_server_thread(do_verify)
        if ok:
            await interaction.followup.send(f"✅ Linked to Minecraft UUID `{msg}`.")
            if self.plugin.config.features.nick_sync and isinstance(interaction.user, discord.Member):
                try:
                    mc_name = self.plugin.lookup_name_by_uuid(msg) or interaction.user.display_name
                    await interaction.user.edit(nick=mc_name)
                except Exception:
                    pass
        else:
            await interaction.followup.send(f"❌ {msg}", ephemeral=True)

    @app_commands.command(name="whoami", description="Show the Minecraft account linked to your Discord.")
    async def whoami(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        def lookup():
            for uuid, did in self.plugin.linked.links.items():
                if did == str(interaction.user.id):
                    return f"🔗 You are linked to **{uuid}**"
            return "ℹ️ You are not linked. Use `/link` in-game, then `/verify <code>` here."

        msg = await self._run_on_server_thread(lookup)
        await interaction.followup.send(msg, ephemeral=True)
