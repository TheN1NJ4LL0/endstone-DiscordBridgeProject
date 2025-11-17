
from typing import Optional

import discord
from discord import app_commands

from ..util import MinecraftCogBase, admin_only


class AdminCommands(MinecraftCogBase):
    def _parse_time_range(self, time_range: str) -> tuple[Optional[int], Optional[int]]:
        """Parse time range string into hours and days

        Args:
            time_range: String like "1h", "2h", "1d", "7d", etc.

        Returns:
            Tuple of (hours, days) where one will be None
        """
        time_range = time_range.lower().strip()

        if time_range.endswith('h'):
            # Hours
            try:
                hours = int(time_range[:-1])
                return (hours, None)
            except ValueError:
                return (None, 7)  # Default to 7 days on error
        elif time_range.endswith('d'):
            # Days
            try:
                days = int(time_range[:-1])
                return (None, days)
            except ValueError:
                return (None, 7)  # Default to 7 days on error
        else:
            # Try to parse as number (assume days)
            try:
                days = int(time_range)
                return (None, days)
            except ValueError:
                return (None, 7)  # Default to 7 days on error

    # -------- console execute & audit --------
    @app_commands.command(name="execute", description="Execute a Minecraft command on the server console.")
    @admin_only()
    @app_commands.describe(command_string="The command to run (e.g., 'summon pig 0 10 0')")
    async def execute(self, interaction: discord.Interaction, command_string: str):
        await self.safe_defer(interaction, ephemeral=True)
        def dispatch_command():
            cs = self.server.command_sender
            return self.server.dispatch_command(cs, command_string)
        ok = await self._run_on_server_thread(dispatch_command)
        await self.bot.audit(f"**{interaction.user}** executed: `{command_string}`")
        await interaction.followup.send("✅ Dispatched." if ok else "⚠️ Command not found.", ephemeral=True)

    @app_commands.command(name="execute_when_online", description="Execute a command when a specific player comes online.")
    @admin_only()
    @app_commands.describe(
        player="The player name to target",
        command_string="The command to run when they join (e.g., 'give {player} diamond 1')",
        notify_message="Optional message to send to the player when command executes"
    )
    async def execute_when_online(self, interaction: discord.Interaction, player: str, command_string: str, notify_message: str = ""):
        await self.safe_defer(interaction, ephemeral=True)

        # Replace {player} placeholder with actual player name
        formatted_command = command_string.replace("{player}", player)

        def queue_command():
            return self.plugin.apply_or_queue_command(player, formatted_command, notify_message)

        ok = await self._run_on_server_thread(queue_command)
        await self.bot.audit(f"**{interaction.user}** queued command for **{player}**: `{formatted_command}`")

        # Check if player is currently online
        def check_online():
            return self.plugin._online_player_obj(player) is not None

        is_online = await self._run_on_server_thread(check_online)

        if is_online:
            await interaction.followup.send(f"✅ Command executed immediately (player is online).", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Command queued for **{player}** when they come online.", ephemeral=True)

    # -------- moderation: kick / ban / unban --------
    @app_commands.command(name="kick", description="Kick a player (optional reason).")
    @admin_only()
    async def kick(self, interaction: discord.Interaction, player: str, reason: Optional[str] = None):
        await self.safe_defer(interaction, ephemeral=True)
        cmd = f'kick {player} {reason or ""}'.strip()
        ok = await self._run_on_server_thread(lambda: self.server.dispatch_command(self.server.command_sender, cmd))
        await self.bot.audit(f"**{interaction.user}** kicked **{player}** ({reason or 'no reason'})")
        await interaction.followup.send("✅ Kicked." if ok else "⚠️ Failed.", ephemeral=True)

    @app_commands.command(name="ban", description="Ban a player (optional reason).")
    @admin_only()
    async def ban(self, interaction: discord.Interaction, player: str, reason: Optional[str] = None):
        await self.safe_defer(interaction, ephemeral=True)
        def do():
            cs = self.server.command_sender
            return self.server.dispatch_command(cs, f'ban {player} {reason or ""}'.strip()) or \
                   self.server.dispatch_command(cs, f"kick {player} {('[Banned] ' + reason) if reason else '[Banned]'}")
        ok = await self._run_on_server_thread(do)
        await self.bot.audit(f"**{interaction.user}** ban **{player}** ({reason or 'no reason'})")
        await interaction.followup.send("✅ Banned (or kicked as fallback)." if ok else "⚠️ Failed.", ephemeral=True)

    @app_commands.command(name="unban", description="Unban a player.")
    @admin_only()
    async def unban(self, interaction: discord.Interaction, player: str):
        await self.safe_defer(interaction, ephemeral=True)
        def do():
            cs = self.server.command_sender
            return self.server.dispatch_command(cs, f"pardon {player}") or \
                   self.server.dispatch_command(cs, f"unban {player}")
        ok = await self._run_on_server_thread(do)
        await self.bot.audit(f"**{interaction.user}** unban **{player}**")
        await interaction.followup.send("✅ Unbanned." if ok else "⚠️ Failed.", ephemeral=True)

    # -------- allowlist/whitelist --------
    def _allow_or_white(self, subcmd: str) -> bool:
        cs = self.server.command_sender
        return self.server.dispatch_command(cs, f"allowlist {subcmd}") or \
               self.server.dispatch_command(cs, f"whitelist {subcmd}")

    @app_commands.command(name="allowlist_add", description="Add a player to the allowlist/whitelist.")
    @admin_only()
    async def allowlist_add(self, interaction: discord.Interaction, player: str):
        await self.safe_defer(interaction, ephemeral=True)
        ok = await self._run_on_server_thread(lambda: self._allow_or_white(f"add {player}"))
        await self.bot.audit(f"**{interaction.user}** allowlist add **{player}**")
        await interaction.followup.send("✅ Added." if ok else "⚠️ Failed.", ephemeral=True)

    @app_commands.command(name="allowlist_remove", description="Remove a player from the allowlist/whitelist.")
    @admin_only()
    async def allowlist_remove(self, interaction: discord.Interaction, player: str):
        await self.safe_defer(interaction, ephemeral=True)
        ok = await self._run_on_server_thread(lambda: self._allow_or_white(f"remove {player}"))
        await self.bot.audit(f"**{interaction.user}** allowlist remove **{player}**")
        await interaction.followup.send("✅ Removed." if ok else "⚠️ Failed.", ephemeral=True)

    @app_commands.command(name="allowlist_on", description="Enable the allowlist/whitelist.")
    @admin_only()
    async def allowlist_on(self, interaction: discord.Interaction):
        await self.safe_defer(interaction, ephemeral=True)
        ok = await self._run_on_server_thread(lambda: self._allow_or_white("on"))
        await self.bot.audit(f"**{interaction.user}** allowlist ON")
        await interaction.followup.send("✅ Enabled." if ok else "⚠️ Failed.", ephemeral=True)

    @app_commands.command(name="allowlist_off", description="Disable the allowlist/whitelist.")
    @admin_only()
    async def allowlist_off(self, interaction: discord.Interaction):
        await self.safe_defer(interaction, ephemeral=True)
        ok = await self._run_on_server_thread(lambda: self._allow_or_white("off"))
        await self.bot.audit(f"**{interaction.user}** allowlist OFF")
        await interaction.followup.send("✅ Disabled." if ok else "⚠️ Failed.", ephemeral=True)

    @app_commands.command(name="allowlist_list", description="Show allowlist/whitelist (printed in console).")
    @admin_only()
    async def allowlist_list(self, interaction: discord.Interaction):
        await self.safe_defer(interaction, ephemeral=True)
        ok = await self._run_on_server_thread(lambda: self._allow_or_white("list"))
        await self.bot.audit(f"**{interaction.user}** allowlist LIST")
        await interaction.followup.send("🖨️ Printed to server console." if ok else "⚠️ Failed.", ephemeral=True)

    # -------- soft mute --------
    @app_commands.command(name="mute", description="Soft-mute a player (plugin-side).")
    @admin_only()
    async def mute(self, interaction: discord.Interaction, player: str):
        await self.safe_defer(interaction, ephemeral=True)
        def do():
            muted = getattr(self.plugin, "_muted", set())
            self.plugin._muted = muted
            muted.add(player.lower())
            return True
        await self._run_on_server_thread(do)
        await self.bot.audit(f"**{interaction.user}** muted **{player}**")
        await interaction.followup.send(f"🔇 **{player}** muted.", ephemeral=True)

    @app_commands.command(name="unmute", description="Remove soft-mute.")
    @admin_only()
    async def unmute(self, interaction: discord.Interaction, player: str):
        await self.safe_defer(interaction, ephemeral=True)
        def do():
            muted = getattr(self.plugin, "_muted", set())
            if player.lower() in muted:
                muted.remove(player.lower())
                return True
            return False
        ok = await self._run_on_server_thread(do)
        await self.bot.audit(f"**{interaction.user}** unmuted **{player}**")
        await interaction.followup.send(f"🔊 **{player}** unmuted." if ok else "ℹ️ Was not muted.", ephemeral=True)

    # -------- economy: add/remove only (offline-safe) --------
    @app_commands.command(name="pay", description="Modify Money: add/remove only (offline-safe). Use quotes for names with spaces.")
    @admin_only()
    @app_commands.choices(action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="remove", value="remove"),
    ])
    @app_commands.describe(
        action="Whether to add or remove money",
        player="Player name (use quotes for names with spaces)",
        amount="Amount to add or remove"
    )
    async def pay(self, interaction: discord.Interaction, action: app_commands.Choice[str], player: str, amount: int):
        await self.safe_defer(interaction, ephemeral=True)
        econ_obj = self.plugin.config.economy.scoreboard_objective
        delta = amount if action.value == "add" else -amount

        def op():
            note = f"§aYour {econ_obj} was {'increased' if delta>0 else 'decreased'} by {abs(amount)}."
            return self.plugin.apply_or_queue_score_delta(player, econ_obj, delta, note)

        ok = await self._run_on_server_thread(op)
        await self.bot.audit(f"**{interaction.user}** pay {action.value} `{amount}` for **{player}** on **{econ_obj}**")
        await interaction.followup.send("✅ Queued/applied." if ok else "⚠️ Failed.", ephemeral=True)

    # -------- Queue Management --------
    @app_commands.command(name="view_queues", description="View pending operations for offline players.")
    @admin_only()
    async def view_queues(self, interaction: discord.Interaction):
        await self.safe_defer(interaction, ephemeral=True)

        def get_queue_info():
            score_queue = dict(self.plugin._score_ops)
            command_queue = dict(self.plugin._command_ops)
            return score_queue, command_queue

        score_ops, command_ops = await self._run_on_server_thread(get_queue_info)

        embed = discord.Embed(title="📋 Offline Player Queues", color=0x3498DB)

        if score_ops:
            score_lines = []
            for player, ops in score_ops.items():
                score_lines.append(f"**{player}**: {len(ops)} score operations")
            embed.add_field(name="💰 Score Operations", value="\n".join(score_lines[:10]), inline=False)
            if len(score_lines) > 10:
                embed.add_field(name="", value=f"... and {len(score_lines) - 10} more players", inline=False)
        else:
            embed.add_field(name="💰 Score Operations", value="None pending", inline=False)

        if command_ops:
            command_lines = []
            for player, ops in command_ops.items():
                command_lines.append(f"**{player}**: {len(ops)} commands")
            embed.add_field(name="⚙️ Command Operations", value="\n".join(command_lines[:10]), inline=False)
            if len(command_lines) > 10:
                embed.add_field(name="", value=f"... and {len(command_lines) - 10} more players", inline=False)
        else:
            embed.add_field(name="⚙️ Command Operations", value="None pending", inline=False)

        total_players = len(set(score_ops.keys()) | set(command_ops.keys()))
        embed.set_footer(text=f"Total players with pending operations: {total_players}")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="clear_player_queue", description="Clear all pending operations for a specific player.")
    @admin_only()
    @app_commands.describe(player="The player name to clear operations for")
    async def clear_player_queue(self, interaction: discord.Interaction, player: str):
        await self.safe_defer(interaction, ephemeral=True)

        def clear_queues():
            key = player.lower()
            score_ops = self.plugin._score_ops.pop(key, [])
            command_ops = self.plugin._command_ops.pop(key, [])
            return len(score_ops), len(command_ops)

        score_count, command_count = await self._run_on_server_thread(clear_queues)
        total = score_count + command_count

        if total > 0:
            await self.bot.audit(f"**{interaction.user}** cleared {total} pending operations for **{player}** ({score_count} score, {command_count} command)")
            await interaction.followup.send(f"✅ Cleared {total} pending operations for **{player}** ({score_count} score, {command_count} command).", ephemeral=True)
        else:
            await interaction.followup.send(f"ℹ️ No pending operations found for **{player}**.", ephemeral=True)

    @app_commands.command(name="view_player_queue", description="View detailed pending operations for a specific player.")
    @admin_only()
    @app_commands.describe(player="The player name to view operations for")
    async def view_player_queue(self, interaction: discord.Interaction, player: str):
        await self.safe_defer(interaction, ephemeral=True)

        def get_player_queue():
            key = player.lower()
            score_ops = self.plugin._score_ops.get(key, [])
            command_ops = self.plugin._command_ops.get(key, [])
            return score_ops, command_ops

        score_ops, command_ops = await self._run_on_server_thread(get_player_queue)

        if not score_ops and not command_ops:
            await interaction.followup.send(f"ℹ️ No pending operations found for **{player}**.", ephemeral=True)
            return

        embed = discord.Embed(title=f"📋 Pending Operations for {player}", color=0x3498DB)

        if score_ops:
            score_lines = []
            for objective, delta, notify in score_ops:
                action = "add" if delta > 0 else "remove"
                score_lines.append(f"• {action} {abs(delta)} to `{objective}`")
                if notify:
                    score_lines.append(f"  └ Notify: {notify[:50]}{'...' if len(notify) > 50 else ''}")
            embed.add_field(name=f"💰 Score Operations ({len(score_ops)})", value="\n".join(score_lines), inline=False)

        if command_ops:
            command_lines = []
            for command, notify in command_ops:
                command_lines.append(f"• `{command[:60]}{'...' if len(command) > 60 else ''}`")
                if notify:
                    command_lines.append(f"  └ Notify: {notify[:50]}{'...' if len(notify) > 50 else ''}")
            embed.add_field(name=f"⚙️ Command Operations ({len(command_ops)})", value="\n".join(command_lines), inline=False)

        embed.set_footer(text="These operations will execute when the player joins the server")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # -------- Grief Monitoring Commands Removed --------
    # Grief monitoring still posts to Discord channels but commands have been removed
    # to reduce server lag from command processing

    # -------- grief monitoring toggle commands --------
    @app_commands.command(name="grief_toggle", description="Toggle grief monitoring features on/off")
    @admin_only()
    @app_commands.choices(feature=[
        app_commands.Choice(name="all", value="all"),
        app_commands.Choice(name="block_break", value="block_break"),
        app_commands.Choice(name="block_place", value="block_place"),
        app_commands.Choice(name="container_access", value="container_access"),
    ])
    @app_commands.choices(state=[
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="off", value="off"),
    ])
    @app_commands.describe(
        feature="Which grief monitoring feature to toggle",
        state="Turn the feature on or off"
    )
    async def grief_toggle(self, interaction: discord.Interaction, feature: app_commands.Choice[str], state: app_commands.Choice[str]):
        await self.safe_defer(interaction, ephemeral=False)

        enabled = state.value == "on"
        feature_name = feature.value

        def toggle_feature():
            try:
                if feature_name == "all":
                    self.plugin.config.features.grief_monitoring = enabled
                    result = f"All grief monitoring {'enabled' if enabled else 'disabled'}"
                elif feature_name == "block_break":
                    self.plugin.config.grief_monitoring.track_block_break = enabled
                    result = f"Block break tracking {'enabled' if enabled else 'disabled'}"
                elif feature_name == "block_place":
                    self.plugin.config.grief_monitoring.track_block_place = enabled
                    result = f"Block place tracking {'enabled' if enabled else 'disabled'}"
                elif feature_name == "container_access":
                    self.plugin.config.grief_monitoring.track_container_access = enabled
                    result = f"Container access tracking {'enabled' if enabled else 'disabled'}"
                else:
                    return {"success": False, "error": "Unknown feature"}

                # Get current status for display
                current_status = {
                    "grief_monitoring": self.plugin.config.features.grief_monitoring,
                    "block_break": self.plugin.config.grief_monitoring.track_block_break,
                    "block_place": self.plugin.config.grief_monitoring.track_block_place,
                    "container_access": self.plugin.config.grief_monitoring.track_container_access,
                }

                return {"success": True, "message": result, "current": current_status}
            except Exception as e:
                return {"success": False, "error": str(e)}

        result = await self._run_on_server_thread(toggle_feature)

        if result["success"]:
            # Create embed showing what changed
            embed = discord.Embed(
                title="⚙️ Grief Monitoring Updated",
                description=result["message"],
                color=0x2ecc71 if enabled else 0xe74c3c,
                timestamp=discord.utils.utcnow()
            )

            # Show current grief monitoring status
            current = result["current"]
            grief_status = "✅ Enabled" if current["grief_monitoring"] else "❌ Disabled"
            embed.add_field(name="Grief Monitoring", value=grief_status, inline=True)

            if current["grief_monitoring"]:
                features = []
                if current["block_break"]:
                    features.append("✅ Block Break")
                else:
                    features.append("❌ Block Break")

                if current["block_place"]:
                    features.append("✅ Block Place")
                else:
                    features.append("❌ Block Place")

                if current["container_access"]:
                    features.append("✅ Container Access")
                else:
                    features.append("❌ Container Access")

                embed.add_field(
                    name="Active Features",
                    value="\n".join(features),
                    inline=True
                )

            embed.set_footer(text="Changes are in memory only. Update config.toml to persist.")

            await self.bot.audit(
                f"**{interaction.user}** toggled grief monitoring: {result['message']}"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                f"❌ Failed to toggle grief monitoring: {result['error']}",
                ephemeral=True
            )

    @app_commands.command(name="grief_status", description="Show current grief monitoring status and settings")
    @admin_only()
    async def grief_status(self, interaction: discord.Interaction):
        await self.safe_defer(interaction, ephemeral=True)

        def get_status():
            try:
                if not hasattr(self.plugin, 'grief_tracker'):
                    return {"success": False, "error": "Grief tracker not initialized"}

                status = {
                    "enabled": self.plugin.config.features.grief_monitoring,
                    "track_block_break": self.plugin.config.grief_monitoring.track_block_break,
                    "track_block_place": self.plugin.config.grief_monitoring.track_block_place,
                    "track_container_access": self.plugin.config.grief_monitoring.track_container_access,
                    "retention_days": self.plugin.config.grief_monitoring.retention_days,
                    "event_count": len(self.plugin.grief_tracker.events),
                    "monitored_blocks": self.plugin.config.grief_monitoring.monitored_blocks,
                    "grief_place_blocks": self.plugin.config.grief_monitoring.grief_place_blocks,
                    "monitored_containers": self.plugin.config.grief_monitoring.monitored_containers,
                }
                return {"success": True, "status": status}
            except Exception as e:
                return {"success": False, "error": str(e)}

        result = await self._run_on_server_thread(get_status)

        if result["success"]:
            status = result["status"]
            embed = discord.Embed(
                title="🛡️ Grief Monitoring Status",
                color=0x2ecc71 if status["enabled"] else 0x95a5a6,
                timestamp=discord.utils.utcnow()
            )

            # Main status
            main_status = "✅ Enabled" if status["enabled"] else "❌ Disabled"
            embed.add_field(name="Status", value=main_status, inline=True)
            embed.add_field(name="Events Stored", value=f"{status['event_count']:,}", inline=True)
            embed.add_field(name="Retention", value=f"{status['retention_days']} days", inline=True)

            if status["enabled"]:
                # Tracking features
                features = []
                if status["track_block_break"]:
                    features.append("✅ Block Break")
                if status["track_block_place"]:
                    features.append("✅ Block Place (grief blocks only)")
                if status["track_container_access"]:
                    features.append("✅ Container Access")

                if features:
                    embed.add_field(name="Active Tracking", value="\n".join(features), inline=False)

                # Monitored items summary
                grief_blocks_count = len(status["grief_place_blocks"])
                containers_count = len(status["monitored_containers"])

                embed.add_field(name="Grief Blocks Monitored", value=f"{grief_blocks_count} types", inline=True)
                embed.add_field(name="Containers Monitored", value=f"{containers_count} types", inline=True)
            else:
                embed.add_field(
                    name="Note",
                    value="Grief monitoring is disabled. Use `/grief_toggle` to enable features.",
                    inline=False
                )

            embed.set_footer(text="Use /grief_toggle to change settings • Use /config_reload to reload from file")
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Failed to get grief status: {result['error']}", ephemeral=True)

    # -------- config reload --------
    @app_commands.command(name="config_reload", description="Reload the plugin configuration from config.toml")
    @admin_only()
    async def config_reload(self, interaction: discord.Interaction):
        await self.safe_defer(interaction, ephemeral=False)

        def reload_config():
            try:
                # Store old config for comparison
                old_grief_enabled = self.plugin.config.features.grief_monitoring
                old_block_break = self.plugin.config.grief_monitoring.track_block_break
                old_block_place = self.plugin.config.grief_monitoring.track_block_place
                old_container = self.plugin.config.grief_monitoring.track_container_access

                # Reload the config from file
                from ..config_schema import BridgeConfig
                self.plugin.config = BridgeConfig.load(self.plugin.config_path)

                # Return comparison info
                return {
                    "success": True,
                    "changes": {
                        "grief_monitoring": old_grief_enabled != self.plugin.config.features.grief_monitoring,
                        "block_break": old_block_break != self.plugin.config.grief_monitoring.track_block_break,
                        "block_place": old_block_place != self.plugin.config.grief_monitoring.track_block_place,
                        "container_access": old_container != self.plugin.config.grief_monitoring.track_container_access,
                    },
                    "current": {
                        "grief_monitoring": self.plugin.config.features.grief_monitoring,
                        "block_break": self.plugin.config.grief_monitoring.track_block_break,
                        "block_place": self.plugin.config.grief_monitoring.track_block_place,
                        "container_access": self.plugin.config.grief_monitoring.track_container_access,
                    }
                }
            except Exception as e:
                self.plugin.logger.error(f"Failed to reload config: {e}")
                return {"success": False, "error": str(e)}

        result = await self._run_on_server_thread(reload_config)

        if result["success"]:
            embed = discord.Embed(
                title="🔄 Configuration Reloaded",
                description="Plugin configuration has been reloaded from config.toml",
                color=0x2ecc71
            )

            # Show current grief monitoring status
            current = result["current"]
            grief_status = "✅ Enabled" if current["grief_monitoring"] else "❌ Disabled"
            embed.add_field(name="Grief Monitoring", value=grief_status, inline=True)

            if current["grief_monitoring"]:
                features = []
                if current["block_break"]:
                    features.append("Block Break")
                if current["block_place"]:
                    features.append("Block Place")
                if current["container_access"]:
                    features.append("Container Access")

                if features:
                    embed.add_field(name="Active Features", value="\n".join(f"✅ {f}" for f in features), inline=True)
                else:
                    embed.add_field(name="Active Features", value="❌ None", inline=True)

            # Show what changed
            changes = result["changes"]
            changed_items = [k for k, v in changes.items() if v]
            if changed_items:
                embed.add_field(
                    name="Changes Detected",
                    value="\n".join(f"🔄 {item.replace('_', ' ').title()}" for item in changed_items),
                    inline=False
                )
            else:
                embed.add_field(name="Changes", value="No changes detected", inline=False)

            await self.bot.audit(f"**{interaction.user}** reloaded plugin configuration")
            await interaction.followup.send(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Configuration Reload Failed",
                description=f"Failed to reload config: {result['error']}",
                color=0xe74c3c
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="grief_status", description="Show current grief monitoring status and settings")
    @admin_only()
    async def grief_status(self, interaction: discord.Interaction):
        await self.safe_defer(interaction, ephemeral=True)

        def get_status():
            try:
                return {
                    "success": True,
                    "main_enabled": self.plugin.config.features.grief_monitoring,
                    "block_break": self.plugin.config.grief_monitoring.track_block_break,
                    "block_place": self.plugin.config.grief_monitoring.track_block_place,
                    "container_access": self.plugin.config.grief_monitoring.track_container_access,
                    "event_cooldown": self.plugin.config.grief_monitoring.event_cooldown,
                    "monitored_containers": len(self.plugin.config.grief_monitoring.monitored_containers),
                    "monitored_blocks": len(self.plugin.config.grief_monitoring.monitored_blocks),
                }
            except Exception as e:
                self.plugin.logger.error(f"Failed to get grief status: {e}")
                return {"success": False, "error": str(e)}

        result = await self._run_on_server_thread(get_status)

        if result["success"]:
            main_status = "✅ Enabled" if result["main_enabled"] else "❌ Disabled"
            color = 0x2ecc71 if result["main_enabled"] else 0xe74c3c

            embed = discord.Embed(
                title="🛡️ Grief Monitoring Status",
                description=f"**Main Status:** {main_status}",
                color=color
            )

            if result["main_enabled"]:
                # Show individual feature status
                features = []
                if result["block_break"]:
                    features.append("✅ Block Break Monitoring")
                else:
                    features.append("❌ Block Break Monitoring")

                if result["block_place"]:
                    features.append("✅ Block Place Monitoring")
                else:
                    features.append("❌ Block Place Monitoring")

                if result["container_access"]:
                    features.append("✅ Container Access Monitoring")
                else:
                    features.append("❌ Container Access Monitoring")

                embed.add_field(name="Features", value="\n".join(features), inline=False)

                # Show settings
                settings = [
                    f"Event Cooldown: {result['event_cooldown']}s",
                    f"Monitored Containers: {result['monitored_containers']} types",
                    f"Monitored Blocks: {result['monitored_blocks']} types" if result['monitored_blocks'] > 0 else "Monitored Blocks: All types"
                ]
                embed.add_field(name="Settings", value="\n".join(settings), inline=False)
            else:
                embed.add_field(
                    name="Note",
                    value="Grief monitoring is disabled. Use `/grief_toggle` to enable features.",
                    inline=False
                )

            embed.set_footer(text="Use /grief_toggle to change settings • Use /config_reload to reload from file")
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Failed to get grief status: {result['error']}", ephemeral=True)
