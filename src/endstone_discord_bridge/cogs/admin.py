
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

    # -------- Grief Monitoring --------
    @app_commands.command(name="grief_stats", description="View grief monitoring statistics")
    @admin_only()
    @app_commands.describe(
        time_range="Time range to analyze"
    )
    async def grief_stats(
        self,
        interaction: discord.Interaction,
        time_range: str = "7d"
    ):
        await self.safe_defer(interaction, ephemeral=True)

        try:
            if not hasattr(self.plugin, 'grief_tracker'):
                await interaction.followup.send(
                    "❌ Grief monitoring is not enabled or not available.",
                    ephemeral=True
                )
                return

            # Parse time range
            hours, days = self._parse_time_range(time_range)
            stats = self.plugin.grief_tracker.get_stats(hours=hours, days=days)

            embed = discord.Embed(
                title=f"🛡️ Grief Monitoring Stats ({stats['time_range']})",
                color=0xe74c3c,
                timestamp=discord.utils.utcnow()
            )

            # Overview stats
            embed.add_field(
                name="📊 Overview",
                value=f"**Total Events:** {stats['total_events']:,}\n"
                      f"**Block Breaks:** {stats['block_breaks']:,}\n"
                      f"**Block Places:** {stats['block_places']:,}\n"
                      f"**Container Access:** {stats['container_accesses']:,}\n"
                      f"**Unique Players:** {stats['unique_players']}",
                inline=True
            )

            # Most broken blocks
            if stats['most_broken_blocks']:
                broken_list = []
                for item in stats['most_broken_blocks'][:5]:
                    broken_list.append(f"**{item['block_type']}:** {item['count']}")

                embed.add_field(
                    name="🔨 Most Broken Blocks",
                    value="\n".join(broken_list),
                    inline=True
                )

            # Most placed blocks
            if stats['most_placed_blocks']:
                placed_list = []
                for item in stats['most_placed_blocks'][:5]:
                    placed_list.append(f"**{item['block_type']}:** {item['count']}")

                embed.add_field(
                    name="🧱 Most Placed Blocks",
                    value="\n".join(placed_list),
                    inline=True
                )

            # Most accessed containers
            if stats['most_accessed_containers']:
                container_list = []
                for item in stats['most_accessed_containers'][:5]:
                    container_list.append(f"**{item['block_type']}:** {item['count']}")

                embed.add_field(
                    name="📦 Most Accessed Containers",
                    value="\n".join(container_list),
                    inline=True
                )

            embed.set_footer(text="Use /grief_player to view specific player activity")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            self.plugin.logger.error(f"Error generating grief stats: {e}")
            await interaction.followup.send(
                "❌ Failed to generate grief statistics. Check server logs for details.",
                ephemeral=True
            )

    @grief_stats.autocomplete('time_range')
    async def grief_stats_time_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return [
            # Hours (1-12)
            app_commands.Choice(name="1 hour", value="1h"),
            app_commands.Choice(name="2 hours", value="2h"),
            app_commands.Choice(name="3 hours", value="3h"),
            app_commands.Choice(name="4 hours", value="4h"),
            app_commands.Choice(name="5 hours", value="5h"),
            app_commands.Choice(name="6 hours", value="6h"),
            app_commands.Choice(name="7 hours", value="7h"),
            app_commands.Choice(name="8 hours", value="8h"),
            app_commands.Choice(name="9 hours", value="9h"),
            app_commands.Choice(name="10 hours", value="10h"),
            app_commands.Choice(name="11 hours", value="11h"),
            app_commands.Choice(name="12 hours", value="12h"),
            # Days (1-6)
            app_commands.Choice(name="1 day", value="1d"),
            app_commands.Choice(name="2 days", value="2d"),
            app_commands.Choice(name="3 days", value="3d"),
            app_commands.Choice(name="4 days", value="4d"),
            app_commands.Choice(name="5 days", value="5d"),
            app_commands.Choice(name="6 days", value="6d"),
            # Weeks
            app_commands.Choice(name="7 days (1 week)", value="7d"),
            app_commands.Choice(name="14 days (2 weeks)", value="14d"),
            app_commands.Choice(name="30 days (1 month)", value="30d"),
        ]

    @app_commands.command(name="grief_player", description="View grief activity for a specific player")
    @admin_only()
    @app_commands.describe(
        player="Player name to investigate",
        time_range="Time range to analyze",
        event_type="Type of events to show (optional)"
    )
    async def grief_player(
        self,
        interaction: discord.Interaction,
        player: str,
        time_range: str = "7d",
        event_type: Optional[str] = None
    ):
        await self.safe_defer(interaction, ephemeral=True)

        try:
            if not hasattr(self.plugin, 'grief_tracker'):
                await interaction.followup.send(
                    "❌ Grief monitoring is not enabled or not available.",
                    ephemeral=True
                )
                return

            # Find player UUID
            def find_player_uuid():
                # Try to find online player first
                online_player = self.plugin._online_player_obj(player)
                if online_player:
                    return str(online_player.unique_id)

                # Try to find in linked accounts
                link = self.plugin.linked.get_by_minecraft_name(player)
                if link:
                    return link.minecraft_uuid

                # Try to find in activity tracker
                for entry in self.plugin.activity_tracker.minecraft_activity:
                    if entry.player_name.lower() == player.lower():
                        return entry.player_uuid

                return None

            player_uuid = await self._run_on_server_thread(find_player_uuid)

            if not player_uuid:
                await interaction.followup.send(
                    f"❌ Could not find UUID for player '{player}'. Make sure the name is correct.",
                    ephemeral=True
                )
                return

            # Parse time range and get events for player
            hours, days = self._parse_time_range(time_range)
            event_filter = event_type if event_type else None
            events = self.plugin.grief_tracker.get_events_by_player(player_uuid, event_filter, hours=hours, days=days)

            # Format time range for display
            if hours:
                time_display = f"{hours} hour{'s' if hours != 1 else ''}"
            else:
                time_display = f"{days} day{'s' if days != 1 else ''}"

            if not events:
                await interaction.followup.send(
                    f"❌ No grief events found for **{player}** in the last {time_display}.",
                    ephemeral=True
                )
                return

            # Create embed
            embed = discord.Embed(
                title=f"🔍 Grief Activity: {player}",
                description=f"Found {len(events)} events in the last {time_display}",
                color=0xe74c3c,
                timestamp=discord.utils.utcnow()
            )

            # Count events by type
            break_count = sum(1 for e in events if e.event_type == "block_break")
            place_count = sum(1 for e in events if e.event_type == "block_place")
            container_count = sum(1 for e in events if e.event_type == "container_access")

            embed.add_field(
                name="📊 Event Summary",
                value=f"🔨 **Block Breaks:** {break_count}\n"
                      f"🧱 **Block Places:** {place_count}\n"
                      f"📦 **Container Access:** {container_count}",
                inline=True
            )

            # Show recent events (last 10)
            recent_events = sorted(events, key=lambda x: x.timestamp, reverse=True)[:10]
            event_lines = []

            for event in recent_events:
                timestamp = discord.utils.format_dt(
                    discord.utils.utcfromtimestamp(event.timestamp),
                    style='R'
                )

                if event.event_type == "block_break":
                    icon = "🔨"
                elif event.event_type == "block_place":
                    icon = "🧱"
                else:
                    icon = "📦"

                location = f"({event.location['x']}, {event.location['y']}, {event.location['z']})"
                event_lines.append(f"{icon} **{event.block_type}** at {location} {timestamp}")

            embed.add_field(
                name="🕐 Recent Events",
                value="\n".join(event_lines),
                inline=False
            )

            embed.set_footer(text=f"Player UUID: {player_uuid}")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            self.plugin.logger.error(f"Error generating grief player report: {e}")
            await interaction.followup.send(
                "❌ Failed to generate grief player report. Check server logs for details.",
                ephemeral=True
            )

    @grief_player.autocomplete('time_range')
    async def grief_player_time_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return [
            # Hours (1-12)
            app_commands.Choice(name="1 hour", value="1h"),
            app_commands.Choice(name="2 hours", value="2h"),
            app_commands.Choice(name="3 hours", value="3h"),
            app_commands.Choice(name="4 hours", value="4h"),
            app_commands.Choice(name="5 hours", value="5h"),
            app_commands.Choice(name="6 hours", value="6h"),
            app_commands.Choice(name="7 hours", value="7h"),
            app_commands.Choice(name="8 hours", value="8h"),
            app_commands.Choice(name="9 hours", value="9h"),
            app_commands.Choice(name="10 hours", value="10h"),
            app_commands.Choice(name="11 hours", value="11h"),
            app_commands.Choice(name="12 hours", value="12h"),
            # Days (1-6)
            app_commands.Choice(name="1 day", value="1d"),
            app_commands.Choice(name="2 days", value="2d"),
            app_commands.Choice(name="3 days", value="3d"),
            app_commands.Choice(name="4 days", value="4d"),
            app_commands.Choice(name="5 days", value="5d"),
            app_commands.Choice(name="6 days", value="6d"),
            # Weeks
            app_commands.Choice(name="7 days (1 week)", value="7d"),
            app_commands.Choice(name="14 days (2 weeks)", value="14d"),
            app_commands.Choice(name="30 days (1 month)", value="30d"),
        ]

    @grief_player.autocomplete('event_type')
    async def grief_player_event_type_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name="All Events", value=""),
            app_commands.Choice(name="Block Breaks", value="block_break"),
            app_commands.Choice(name="Block Places", value="block_place"),
            app_commands.Choice(name="Container Access", value="container_access"),
        ]

    @app_commands.command(name="grief_location", description="View grief activity near a specific location")
    @admin_only()
    @app_commands.describe(
        x="X coordinate",
        y="Y coordinate",
        z="Z coordinate",
        radius="Search radius (default: 5)",
        time_range="Time range to analyze"
    )
    async def grief_location(
        self,
        interaction: discord.Interaction,
        x: int,
        y: int,
        z: int,
        radius: int = 5,
        time_range: str = "7d"
    ):
        await self.safe_defer(interaction, ephemeral=True)

        try:
            if not hasattr(self.plugin, 'grief_tracker'):
                await interaction.followup.send(
                    "❌ Grief monitoring is not enabled or not available.",
                    ephemeral=True
                )
                return

            # Parse time range and get events
            hours, days = self._parse_time_range(time_range)
            location = {"x": x, "y": y, "z": z}
            events = self.plugin.grief_tracker.get_events_by_location(location, radius, hours=hours, days=days)

            # Format time range for display
            if hours:
                time_display = f"{hours} hour{'s' if hours != 1 else ''}"
            else:
                time_display = f"{days} day{'s' if days != 1 else ''}"

            if not events:
                await interaction.followup.send(
                    f"❌ No grief events found near ({x}, {y}, {z}) within {radius} blocks in the last {time_display}.",
                    ephemeral=True
                )
                return

            # Create embed
            embed = discord.Embed(
                title=f"🗺️ Grief Activity Near ({x}, {y}, {z})",
                description=f"Found {len(events)} events within {radius} blocks in the last {time_display}",
                color=0xe74c3c,
                timestamp=discord.utils.utcnow()
            )

            # Count events by type and player
            break_count = sum(1 for e in events if e.event_type == "block_break")
            place_count = sum(1 for e in events if e.event_type == "block_place")
            container_count = sum(1 for e in events if e.event_type == "container_access")

            unique_players = set(e.player_name for e in events)

            embed.add_field(
                name="📊 Summary",
                value=f"🔨 **Block Breaks:** {break_count}\n"
                      f"🧱 **Block Places:** {place_count}\n"
                      f"📦 **Container Access:** {container_count}\n"
                      f"👥 **Unique Players:** {len(unique_players)}",
                inline=True
            )

            # Show events (limit to 15 most recent)
            recent_events = events[:15]
            event_lines = []

            for event in recent_events:
                timestamp = discord.utils.format_dt(
                    discord.utils.utcfromtimestamp(event.timestamp),
                    style='R'
                )

                if event.event_type == "block_break":
                    icon = "🔨"
                elif event.event_type == "block_place":
                    icon = "🧱"
                else:
                    icon = "📦"

                event_location = f"({event.location['x']}, {event.location['y']}, {event.location['z']})"
                distance = max(
                    abs(event.location['x'] - x),
                    abs(event.location['y'] - y),
                    abs(event.location['z'] - z)
                )

                event_lines.append(
                    f"{icon} **{event.player_name}** {event.block_type} at {event_location} "
                    f"({distance}b away) {timestamp}"
                )

            embed.add_field(
                name=f"🕐 Recent Events ({len(recent_events)}/{len(events)})",
                value="\n".join(event_lines),
                inline=False
            )

            if len(events) > 15:
                embed.add_field(
                    name="ℹ️ Note",
                    value=f"Showing {len(recent_events)} most recent events out of {len(events)} total.",
                    inline=False
                )

            embed.set_footer(text=f"Search radius: {radius} blocks")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            self.plugin.logger.error(f"Error generating grief location report: {e}")
            await interaction.followup.send(
                "❌ Failed to generate grief location report. Check server logs for details.",
                ephemeral=True
            )

    @grief_location.autocomplete('time_range')
    async def grief_location_time_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return [
            # Hours (1-12)
            app_commands.Choice(name="1 hour", value="1h"),
            app_commands.Choice(name="2 hours", value="2h"),
            app_commands.Choice(name="3 hours", value="3h"),
            app_commands.Choice(name="4 hours", value="4h"),
            app_commands.Choice(name="5 hours", value="5h"),
            app_commands.Choice(name="6 hours", value="6h"),
            app_commands.Choice(name="7 hours", value="7h"),
            app_commands.Choice(name="8 hours", value="8h"),
            app_commands.Choice(name="9 hours", value="9h"),
            app_commands.Choice(name="10 hours", value="10h"),
            app_commands.Choice(name="11 hours", value="11h"),
            app_commands.Choice(name="12 hours", value="12h"),
            # Days (1-6)
            app_commands.Choice(name="1 day", value="1d"),
            app_commands.Choice(name="2 days", value="2d"),
            app_commands.Choice(name="3 days", value="3d"),
            app_commands.Choice(name="4 days", value="4d"),
            app_commands.Choice(name="5 days", value="5d"),
            app_commands.Choice(name="6 days", value="6d"),
            # Weeks
            app_commands.Choice(name="7 days (1 week)", value="7d"),
            app_commands.Choice(name="14 days (2 weeks)", value="14d"),
            app_commands.Choice(name="30 days (1 month)", value="30d"),
        ]

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

        def update_config():
            try:
                if feature_name == "all":
                    # Toggle main grief monitoring and all sub-features
                    self.plugin.config.features.grief_monitoring = enabled
                    self.plugin.config.grief_monitoring.track_block_break = enabled
                    self.plugin.config.grief_monitoring.track_block_place = enabled
                    self.plugin.config.grief_monitoring.track_container_access = enabled
                    return "all grief monitoring features"
                elif feature_name == "block_break":
                    self.plugin.config.grief_monitoring.track_block_break = enabled
                    return "block break monitoring"
                elif feature_name == "block_place":
                    self.plugin.config.grief_monitoring.track_block_place = enabled
                    return "block place monitoring"
                elif feature_name == "container_access":
                    self.plugin.config.grief_monitoring.track_container_access = enabled
                    return "container access monitoring"
                return None
            except Exception as e:
                self.plugin.logger.error(f"Failed to update grief monitoring config: {e}")
                return None

        result = await self._run_on_server_thread(update_config)

        if result:
            # Save the config changes
            def save_config():
                try:
                    self.plugin.config.save(self.plugin.config_path)
                    return True
                except Exception as e:
                    self.plugin.logger.error(f"Failed to save config: {e}")
                    return False

            saved = await self._run_on_server_thread(save_config)

            if saved:
                status = "enabled" if enabled else "disabled"
                embed = discord.Embed(
                    title="🛡️ Grief Monitoring Updated",
                    description=f"**{result.title()}** has been **{status}**",
                    color=0x2ecc71 if enabled else 0xe74c3c
                )
                embed.add_field(name="Status", value=status.title(), inline=True)
                embed.add_field(name="Feature", value=result.title(), inline=True)

                await self.bot.audit(f"**{interaction.user}** {status} {result}")
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("⚠️ Failed to save config changes.", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Failed to update grief monitoring settings.", ephemeral=True)

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
