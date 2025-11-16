import discord
from discord import app_commands
from typing import Literal
import io

from ..util import MinecraftCogBase, admin_only


class ActivityCommands(MinecraftCogBase):
    """Commands for viewing Discord and Minecraft activity statistics"""

    @app_commands.command(name="activity", description="View activity statistics for Discord or Minecraft")
    @admin_only()
    @app_commands.describe(
        platform="Choose Discord or Minecraft activity",
        days="Number of days to analyze (7, 14, or 30)"
    )
    async def activity(
        self, 
        interaction: discord.Interaction, 
        platform: Literal["discord", "minecraft"], 
        days: Literal[7, 14, 30]
    ):
        await self.safe_defer(interaction, ephemeral=True)
        
        try:
            activity_tracker = self.plugin.activity_tracker
            
            if platform == "discord":
                stats = activity_tracker.get_discord_stats(days)
                embed = self._create_discord_stats_embed(stats, days)
            else:  # minecraft
                stats = activity_tracker.get_minecraft_stats(days)
                embed = self._create_minecraft_stats_embed(stats, days)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            self.plugin.logger.error(f"Error generating activity stats: {e}")
            await interaction.followup.send(
                "❌ Failed to generate activity statistics. Check server logs for details.", 
                ephemeral=True
            )

    def _create_discord_stats_embed(self, stats, days: int) -> discord.Embed:
        """Create an embed for Discord activity statistics"""
        embed = discord.Embed(
            title=f"📊 Discord Activity ({days} days)",
            color=0x5865F2,
            timestamp=discord.utils.utcnow()
        )
        
        # Overview
        embed.add_field(
            name="📈 Overview",
            value=f"**Total Events:** {stats.total_events:,}\n"
                  f"**Unique Users:** {stats.unique_users:,}\n"
                  f"**Average Events/Day:** {stats.total_events / days:.1f}",
            inline=True
        )
        
        # Event breakdown
        embed.add_field(
            name="🔢 Event Types",
            value=f"**Joins:** {stats.joins:,}\n"
                  f"**Leaves:** {stats.leaves:,}\n"
                  f"**Messages:** {stats.messages:,}\n"
                  f"**Voice Activity:** {stats.voice_activity:,}",
            inline=True
        )
        
        # Most active users with linked account info
        if stats.most_active_users:
            top_users = []
            for i, user in enumerate(stats.most_active_users[:5], 1):
                username = user['username']
                count = user['count']
                is_linked = user.get('is_linked', False)
                minecraft_name = user.get('minecraft_username')

                if is_linked and minecraft_name:
                    display_name = f"{username} 🔗 {minecraft_name}"
                else:
                    display_name = username

                top_users.append(f"{i}. **{display_name}** - {count:,} events")

            embed.add_field(
                name="👑 Most Active Users",
                value="\n".join(top_users) if top_users else "No activity",
                inline=False
            )
        
        # Daily activity chart (simplified)
        if stats.daily_breakdown:
            daily_summary = []
            sorted_days = sorted(stats.daily_breakdown.items(), reverse=True)
            for date, count in sorted_days[:7]:  # Show last 7 days
                daily_summary.append(f"**{date}:** {count:,}")
            
            embed.add_field(
                name="📅 Recent Daily Activity",
                value="\n".join(daily_summary) if daily_summary else "No recent activity",
                inline=False
            )
        
        embed.set_footer(text="Activity data is automatically cleaned up after 90 days")
        return embed

    def _create_minecraft_stats_embed(self, stats, days: int) -> discord.Embed:
        """Create an embed for Minecraft activity statistics"""
        embed = discord.Embed(
            title=f"⛏️ Minecraft Activity ({days} days)",
            color=0x00AA00,
            timestamp=discord.utils.utcnow()
        )
        
        # Overview
        embed.add_field(
            name="📈 Overview",
            value=f"**Total Events:** {stats.total_events:,}\n"
                  f"**Unique Players:** {stats.unique_users:,}\n"
                  f"**Average Events/Day:** {stats.total_events / days:.1f}",
            inline=True
        )
        
        # Event breakdown
        embed.add_field(
            name="🔢 Event Types",
            value=f"**Joins:** {stats.joins:,}\n"
                  f"**Leaves:** {stats.leaves:,}\n"
                  f"**Sessions:** {min(stats.joins, stats.leaves):,}",
            inline=True
        )
        
        # Calculate average session time if we have both joins and leaves
        if stats.joins > 0 and stats.leaves > 0:
            # This is a simplified calculation - for accurate session time,
            # we'd need to match joins with leaves per player
            avg_session_indicator = "📊 Session Data Available"
        else:
            avg_session_indicator = "📊 Limited Session Data"
        
        embed.add_field(
            name="⏱️ Session Info",
            value=avg_session_indicator,
            inline=True
        )
        
        # Most active players with linked account info
        if stats.most_active_users:
            top_players = []
            for i, player in enumerate(stats.most_active_users[:5], 1):
                username = player['username']
                count = player['count']
                is_linked = player.get('is_linked', False)
                discord_name = player.get('discord_username')

                if is_linked and discord_name:
                    display_name = f"{username} 🔗 {discord_name}"
                else:
                    display_name = username

                top_players.append(f"{i}. **{display_name}** - {count:,} events")

            embed.add_field(
                name="👑 Most Active Players",
                value="\n".join(top_players) if top_players else "No activity",
                inline=False
            )
        
        # Daily activity chart (simplified)
        if stats.daily_breakdown:
            daily_summary = []
            sorted_days = sorted(stats.daily_breakdown.items(), reverse=True)
            for date, count in sorted_days[:7]:  # Show last 7 days
                daily_summary.append(f"**{date}:** {count:,}")
            
            embed.add_field(
                name="📅 Recent Daily Activity",
                value="\n".join(daily_summary) if daily_summary else "No recent activity",
                inline=False
            )
        
        embed.set_footer(text="Activity data is automatically cleaned up after 90 days")
        return embed

    @app_commands.command(name="activity_export", description="Export raw activity data (admin only)")
    @admin_only()
    @app_commands.describe(
        platform="Choose Discord or Minecraft activity",
        days="Number of days to export (7, 14, or 30)"
    )
    async def activity_export(
        self, 
        interaction: discord.Interaction, 
        platform: Literal["discord", "minecraft"], 
        days: Literal[7, 14, 30]
    ):
        await self.safe_defer(interaction, ephemeral=True)
        
        try:
            activity_tracker = self.plugin.activity_tracker
            
            if platform == "discord":
                stats = activity_tracker.get_discord_stats(days)
                filename = f"discord_activity_{days}d.txt"
                content = self._format_discord_export(stats, days)
            else:  # minecraft
                stats = activity_tracker.get_minecraft_stats(days)
                filename = f"minecraft_activity_{days}d.txt"
                content = self._format_minecraft_export(stats, days)
            
            # Create a text file with the data
            file_content = content.encode('utf-8')
            file = discord.File(
                fp=io.BytesIO(file_content),
                filename=filename
            )
            
            await interaction.followup.send(
                f"📄 Activity export for {platform} ({days} days):",
                file=file,
                ephemeral=True
            )
            
        except Exception as e:
            self.plugin.logger.error(f"Error exporting activity data: {e}")
            await interaction.followup.send(
                "❌ Failed to export activity data. Check server logs for details.", 
                ephemeral=True
            )

    def _format_discord_export(self, stats, days: int) -> str:
        """Format Discord activity data for export"""
        lines = [
            f"Discord Activity Report ({days} days)",
            f"Generated: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "=" * 50,
            "",
            "OVERVIEW:",
            f"Total Events: {stats.total_events:,}",
            f"Unique Users: {stats.unique_users:,}",
            f"Average Events/Day: {stats.total_events / days:.1f}",
            "",
            "EVENT BREAKDOWN:",
            f"Joins: {stats.joins:,}",
            f"Leaves: {stats.leaves:,}",
            f"Messages: {stats.messages:,}",
            f"Voice Activity: {stats.voice_activity:,}",
            "",
            "TOP USERS:",
        ]
        
        for i, user in enumerate(stats.most_active_users[:10], 1):
            lines.append(f"{i:2d}. {user['username']} - {user['count']:,} events")
        
        lines.extend(["", "DAILY BREAKDOWN:"])
        for date, count in sorted(stats.daily_breakdown.items(), reverse=True):
            lines.append(f"{date}: {count:,} events")
        
        return "\n".join(lines)

    def _format_minecraft_export(self, stats, days: int) -> str:
        """Format Minecraft activity data for export"""
        lines = [
            f"Minecraft Activity Report ({days} days)",
            f"Generated: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "=" * 50,
            "",
            "OVERVIEW:",
            f"Total Events: {stats.total_events:,}",
            f"Unique Players: {stats.unique_users:,}",
            f"Average Events/Day: {stats.total_events / days:.1f}",
            "",
            "EVENT BREAKDOWN:",
            f"Joins: {stats.joins:,}",
            f"Leaves: {stats.leaves:,}",
            f"Completed Sessions: {min(stats.joins, stats.leaves):,}",
            "",
            "TOP PLAYERS:",
        ]
        
        for i, player in enumerate(stats.most_active_users[:10], 1):
            lines.append(f"{i:2d}. {player['username']} - {player['count']:,} events")
        
        lines.extend(["", "DAILY BREAKDOWN:"])
        for date, count in sorted(stats.daily_breakdown.items(), reverse=True):
            lines.append(f"{date}: {count:,} events")
        
        return "\n".join(lines)

    @app_commands.command(name="members", description="View comprehensive member list with activity data")
    @admin_only()
    @app_commands.describe(
        days="Number of days to analyze for recent activity (7, 14, or 30)",
        show_inactive="Whether to show inactive members (default: False)"
    )
    async def members(
        self,
        interaction: discord.Interaction,
        days: Literal[7, 14, 30] = 30,
        show_inactive: bool = False
    ):
        await self.safe_defer(interaction, ephemeral=True)

        try:
            activity_tracker = self.plugin.activity_tracker
            member_data = activity_tracker.get_comprehensive_member_list(days)

            if show_inactive:
                embed = self._create_inactive_members_embed(member_data, days)
            else:
                embed = self._create_active_members_embed(member_data, days)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            self.plugin.logger.error(f"Error generating member list: {e}")
            await interaction.followup.send(
                "❌ Failed to generate member list. Check server logs for details.",
                ephemeral=True
            )

    @app_commands.command(name="link_accounts", description="Link a Discord user to a Minecraft player")
    @admin_only()
    @app_commands.describe(
        discord_user="Discord user to link",
        minecraft_username="Minecraft username to link",
        notes="Optional notes about this link"
    )
    async def link_accounts(
        self,
        interaction: discord.Interaction,
        discord_user: discord.Member,
        minecraft_username: str,
        notes: str = ""
    ):
        await self.safe_defer(interaction, ephemeral=True)

        try:
            activity_tracker = self.plugin.activity_tracker

            # Try to find the Minecraft UUID from recent activity
            minecraft_uuid = None
            for entry in activity_tracker.minecraft_activity:
                if entry.player_name.lower() == minecraft_username.lower():
                    minecraft_uuid = entry.player_uuid
                    break

            if not minecraft_uuid:
                await interaction.followup.send(
                    f"❌ Could not find Minecraft player '{minecraft_username}' in recent activity. "
                    "Make sure they have joined the server recently.",
                    ephemeral=True
                )
                return

            success = activity_tracker.add_admin_link(
                discord_id=str(discord_user.id),
                discord_username=discord_user.display_name,
                minecraft_uuid=minecraft_uuid,
                minecraft_username=minecraft_username,
                linked_by=str(interaction.user.id),
                notes=notes
            )

            if success:
                await interaction.followup.send(
                    f"✅ Successfully linked **{discord_user.display_name}** to **{minecraft_username}**",
                    ephemeral=True
                )
                await self.bot.audit(f"**{interaction.user}** linked Discord user **{discord_user.display_name}** to Minecraft player **{minecraft_username}**")
            else:
                await interaction.followup.send(
                    f"❌ Failed to create link. One of these accounts may already be linked.",
                    ephemeral=True
                )

        except Exception as e:
            self.plugin.logger.error(f"Error linking accounts: {e}")
            await interaction.followup.send(
                "❌ Failed to link accounts. Check server logs for details.",
                ephemeral=True
            )

    @app_commands.command(name="unlink_accounts", description="Remove a link between Discord and Minecraft accounts")
    @admin_only()
    @app_commands.describe(
        discord_user="Discord user to unlink (optional if minecraft_username provided)",
        minecraft_username="Minecraft username to unlink (optional if discord_user provided)"
    )
    async def unlink_accounts(
        self,
        interaction: discord.Interaction,
        discord_user: discord.Member = None,
        minecraft_username: str = None
    ):
        await self.safe_defer(interaction, ephemeral=True)

        if not discord_user and not minecraft_username:
            await interaction.followup.send(
                "❌ You must provide either a Discord user or Minecraft username to unlink.",
                ephemeral=True
            )
            return

        try:
            activity_tracker = self.plugin.activity_tracker

            success = False
            if discord_user:
                success = activity_tracker.remove_admin_link(discord_id=str(discord_user.id))
            elif minecraft_username:
                # Find UUID for the username
                minecraft_uuid = None
                for entry in activity_tracker.minecraft_activity:
                    if entry.player_name.lower() == minecraft_username.lower():
                        minecraft_uuid = entry.player_uuid
                        break
                if minecraft_uuid:
                    success = activity_tracker.remove_admin_link(minecraft_uuid=minecraft_uuid)

            if success:
                target = discord_user.display_name if discord_user else minecraft_username
                await interaction.followup.send(
                    f"✅ Successfully unlinked **{target}**",
                    ephemeral=True
                )
                await self.bot.audit(f"**{interaction.user}** unlinked **{target}**")
            else:
                await interaction.followup.send(
                    f"❌ No link found for the specified account.",
                    ephemeral=True
                )

        except Exception as e:
            self.plugin.logger.error(f"Error unlinking accounts: {e}")
            await interaction.followup.send(
                "❌ Failed to unlink accounts. Check server logs for details.",
                ephemeral=True
            )

    @app_commands.command(name="linked_accounts", description="View all linked accounts")
    @admin_only()
    async def linked_accounts(self, interaction: discord.Interaction):
        await self.safe_defer(interaction, ephemeral=True)

        try:
            activity_tracker = self.plugin.activity_tracker
            links = activity_tracker.get_all_admin_links()

            if not links:
                await interaction.followup.send("📝 No linked accounts found.", ephemeral=True)
                return

            embed = discord.Embed(
                title="🔗 Linked Accounts",
                color=0x00AA00,
                timestamp=discord.utils.utcnow()
            )

            link_list = []
            for i, link in enumerate(links[:20], 1):  # Limit to 20 to avoid embed limits
                link_list.append(
                    f"{i}. **{link.discord_username}** ↔ **{link.minecraft_username}**"
                )

            embed.add_field(
                name=f"📊 Links ({len(links)} total)",
                value="\n".join(link_list) if link_list else "None",
                inline=False
            )

            if len(links) > 20:
                embed.add_field(
                    name="ℹ️ Note",
                    value=f"Showing first 20 of {len(links)} total links",
                    inline=False
                )

            embed.set_footer(text="Use /unlink_accounts to remove links")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            self.plugin.logger.error(f"Error viewing linked accounts: {e}")
            await interaction.followup.send(
                "❌ Failed to view linked accounts. Check server logs for details.",
                ephemeral=True
            )

    def _create_active_members_embed(self, member_data: dict, days: int) -> discord.Embed:
        """Create an embed for active members"""
        embed = discord.Embed(
            title=f"👥 Active Members ({days} days)",
            color=0x00AA00,
            timestamp=discord.utils.utcnow()
        )

        # Overview
        embed.add_field(
            name="📊 Overview",
            value=f"**Total Members:** {member_data['total_members']:,}\n"
                  f"**Active:** {member_data['active_count']:,}\n"
                  f"**Inactive:** {member_data['inactive_count']:,}\n"
                  f"**Linked Accounts:** {member_data['linked_count']:,}",
            inline=True
        )

        # Platform breakdown
        embed.add_field(
            name="🎮 Platform Breakdown",
            value=f"**Discord Only:** {member_data['discord_only']:,}\n"
                  f"**Minecraft Only:** {member_data['minecraft_only']:,}\n"
                  f"**Both Platforms:** {member_data['linked_count']:,}",
            inline=True
        )

        # Most active members
        active_members = member_data['active_members'][:10]  # Top 10
        if active_members:
            member_list = []
            for i, member in enumerate(active_members, 1):
                name = member['discord_username'] or member['minecraft_username'] or 'Unknown'
                total_events = member['discord_events_recent'] + member['minecraft_events_recent']
                days_ago = member['days_since_last_activity']

                status = "🔗" if member['is_linked'] else ("💬" if member['discord_username'] else "⛏️")
                member_list.append(f"{i}. {status} **{name}** - {total_events} events ({days_ago}d ago)")

            embed.add_field(
                name="🏆 Most Active Members",
                value="\n".join(member_list),
                inline=False
            )

        embed.add_field(
            name="ℹ️ Legend",
            value="🔗 Linked Account | 💬 Discord Only | ⛏️ Minecraft Only",
            inline=False
        )

        embed.set_footer(text=f"Use '/members {days} true' to see inactive members")
        return embed

    def _create_inactive_members_embed(self, member_data: dict, days: int) -> discord.Embed:
        """Create an embed for inactive members"""
        embed = discord.Embed(
            title=f"😴 Inactive Members (>{days} days)",
            color=0xFF6B6B,
            timestamp=discord.utils.utcnow()
        )

        # Overview
        embed.add_field(
            name="📊 Overview",
            value=f"**Total Inactive:** {member_data['inactive_count']:,}\n"
                  f"**Total Members:** {member_data['total_members']:,}\n"
                  f"**Inactive Rate:** {(member_data['inactive_count'] / max(member_data['total_members'], 1) * 100):.1f}%",
            inline=True
        )

        # Inactive members (sorted by last activity)
        inactive_members = member_data['inactive_members'][:15]  # Top 15 most recently inactive
        if inactive_members:
            member_list = []
            for i, member in enumerate(inactive_members, 1):
                name = member['discord_username'] or member['minecraft_username'] or 'Unknown'
                days_ago = member['days_since_last_activity']
                total_events = member['total_discord_events'] + member['total_minecraft_events']

                status = "🔗" if member['is_linked'] else ("💬" if member['discord_username'] else "⛏️")
                member_list.append(f"{i}. {status} **{name}** - {days_ago}d ago ({total_events} total events)")

            embed.add_field(
                name="😴 Inactive Members (Most Recent First)",
                value="\n".join(member_list),
                inline=False
            )

        if member_data['inactive_count'] > 15:
            embed.add_field(
                name="📝 Note",
                value=f"Showing 15 of {member_data['inactive_count']} inactive members",
                inline=False
            )

        embed.add_field(
            name="ℹ️ Legend",
            value="🔗 Linked Account | 💬 Discord Only | ⛏️ Minecraft Only",
            inline=False
        )

        embed.set_footer(text="Consider removing members inactive for 60+ days")
        return embed

    @app_commands.command(name="inactive_members", description="List members inactive for a specific number of days")
    @admin_only()
    @app_commands.describe(
        min_days="Minimum days of inactivity to include (default: 30)",
        platform="Filter by platform (optional)"
    )
    async def inactive_members(
        self,
        interaction: discord.Interaction,
        min_days: int = 30,
        platform: Literal["discord", "minecraft", "both"] = "both"
    ):
        await self.safe_defer(interaction, ephemeral=True)

        if min_days < 1 or min_days > 365:
            await interaction.followup.send(
                "❌ Days must be between 1 and 365.",
                ephemeral=True
            )
            return

        try:
            activity_tracker = self.plugin.activity_tracker
            member_data = activity_tracker.get_comprehensive_member_list(90)  # Look at 90 days of data

            # Filter inactive members by criteria
            filtered_inactive = []
            for member in member_data['inactive_members']:
                if member['days_since_last_activity'] >= min_days:
                    # Apply platform filter
                    if platform == "discord" and not member['discord_username']:
                        continue
                    elif platform == "minecraft" and not member['minecraft_username']:
                        continue
                    filtered_inactive.append(member)

            embed = self._create_filtered_inactive_embed(filtered_inactive, min_days, platform)
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            self.plugin.logger.error(f"Error listing inactive members: {e}")
            await interaction.followup.send(
                "❌ Failed to list inactive members. Check server logs for details.",
                ephemeral=True
            )

    @app_commands.command(name="export_inactive", description="Export list of inactive members for bulk management")
    @admin_only()
    @app_commands.describe(
        min_days="Minimum days of inactivity to include",
        format_type="Export format"
    )
    async def export_inactive(
        self,
        interaction: discord.Interaction,
        min_days: int = 60,
        format_type: Literal["discord_ids", "minecraft_names", "detailed"] = "detailed"
    ):
        await self.safe_defer(interaction, ephemeral=True)

        try:
            activity_tracker = self.plugin.activity_tracker
            member_data = activity_tracker.get_comprehensive_member_list(90)

            # Filter inactive members
            filtered_inactive = [
                member for member in member_data['inactive_members']
                if member['days_since_last_activity'] >= min_days
            ]

            if not filtered_inactive:
                await interaction.followup.send(
                    f"📝 No members found inactive for {min_days}+ days.",
                    ephemeral=True
                )
                return

            # Generate export content based on format
            if format_type == "discord_ids":
                content = self._format_discord_ids_export(filtered_inactive, min_days)
                filename = f"inactive_discord_ids_{min_days}d.txt"
            elif format_type == "minecraft_names":
                content = self._format_minecraft_names_export(filtered_inactive, min_days)
                filename = f"inactive_minecraft_{min_days}d.txt"
            else:  # detailed
                content = self._format_detailed_inactive_export(filtered_inactive, min_days)
                filename = f"inactive_members_detailed_{min_days}d.txt"

            # Create file
            file_content = content.encode('utf-8')
            file = discord.File(
                fp=io.BytesIO(file_content),
                filename=filename
            )

            await interaction.followup.send(
                f"📄 Inactive members export ({len(filtered_inactive)} members, {min_days}+ days):",
                file=file,
                ephemeral=True
            )

        except Exception as e:
            self.plugin.logger.error(f"Error exporting inactive members: {e}")
            await interaction.followup.send(
                "❌ Failed to export inactive members. Check server logs for details.",
                ephemeral=True
            )

    def _create_filtered_inactive_embed(self, inactive_members: list, min_days: int, platform: str) -> discord.Embed:
        """Create embed for filtered inactive members"""
        embed = discord.Embed(
            title=f"😴 Inactive Members ({min_days}+ days)",
            color=0xFF6B6B,
            timestamp=discord.utils.utcnow()
        )

        embed.add_field(
            name="📊 Filter Results",
            value=f"**Found:** {len(inactive_members)} members\n"
                  f"**Min Inactivity:** {min_days} days\n"
                  f"**Platform Filter:** {platform.title()}",
            inline=True
        )

        if inactive_members:
            member_list = []
            for i, member in enumerate(inactive_members[:15], 1):  # Show top 15
                name = member['discord_username'] or member['minecraft_username'] or 'Unknown'
                days_ago = member['days_since_last_activity']
                total_events = member['total_discord_events'] + member['total_minecraft_events']

                status = "🔗" if member['is_linked'] else ("💬" if member['discord_username'] else "⛏️")
                member_list.append(f"{i}. {status} **{name}** - {days_ago}d ago ({total_events} events)")

            embed.add_field(
                name="😴 Inactive Members",
                value="\n".join(member_list),
                inline=False
            )

            if len(inactive_members) > 15:
                embed.add_field(
                    name="📝 Note",
                    value=f"Showing 15 of {len(inactive_members)} inactive members. Use /export_inactive for full list.",
                    inline=False
                )
        else:
            embed.add_field(
                name="✅ No Results",
                value="No members found matching the criteria.",
                inline=False
            )

        embed.set_footer(text="Use /export_inactive for bulk management options")
        return embed

    def _format_discord_ids_export(self, inactive_members: list, min_days: int) -> str:
        """Format Discord IDs for bulk operations"""
        lines = [
            f"Discord IDs - Inactive Members ({min_days}+ days)",
            f"Generated: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Total: {len(inactive_members)} members",
            "=" * 50,
            "",
            "# Discord User IDs (one per line):",
            "# Use these for bulk Discord operations",
            ""
        ]

        for member in inactive_members:
            if member['discord_id']:
                lines.append(member['discord_id'])

        return "\n".join(lines)

    def _format_minecraft_names_export(self, inactive_members: list, min_days: int) -> str:
        """Format Minecraft usernames for bulk operations"""
        lines = [
            f"Minecraft Usernames - Inactive Members ({min_days}+ days)",
            f"Generated: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Total: {len(inactive_members)} members",
            "=" * 50,
            "",
            "# Minecraft Usernames (one per line):",
            "# Use these for bulk Minecraft operations",
            ""
        ]

        for member in inactive_members:
            if member['minecraft_username']:
                lines.append(member['minecraft_username'])

        return "\n".join(lines)

    def _format_detailed_inactive_export(self, inactive_members: list, min_days: int) -> str:
        """Format detailed inactive member information"""
        lines = [
            f"Detailed Inactive Members Report ({min_days}+ days)",
            f"Generated: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Total: {len(inactive_members)} members",
            "=" * 80,
            "",
            f"{'#':<3} {'Discord Username':<20} {'Minecraft Username':<20} {'Days Inactive':<15} {'Total Events':<15} {'Linked':<8}",
            "-" * 80,
        ]

        for i, member in enumerate(inactive_members, 1):
            discord_name = member['discord_username'] or 'N/A'
            minecraft_name = member['minecraft_username'] or 'N/A'
            days_inactive = member['days_since_last_activity']
            total_events = member['total_discord_events'] + member['total_minecraft_events']
            is_linked = 'Yes' if member['is_linked'] else 'No'

            lines.append(
                f"{i:<3} {discord_name[:19]:<20} {minecraft_name[:19]:<20} {days_inactive:<15} {total_events:<15} {is_linked:<8}"
            )

        lines.extend([
            "",
            "=" * 80,
            "SUMMARY:",
            f"- Total inactive members: {len(inactive_members)}",
            f"- Minimum inactivity threshold: {min_days} days",
            f"- Discord-only accounts: {sum(1 for m in inactive_members if m['discord_username'] and not m['minecraft_username'])}",
            f"- Minecraft-only accounts: {sum(1 for m in inactive_members if m['minecraft_username'] and not m['discord_username'])}",
            f"- Linked accounts: {sum(1 for m in inactive_members if m['is_linked'])}",
            "",
            "RECOMMENDATIONS:",
            "- Consider removing members inactive for 60+ days",
            "- Review linked accounts before removal",
            "- Check with other admins before bulk operations"
        ])

        return "\n".join(lines)

    @app_commands.command(name="unified_activity", description="View unified activity report showing linked accounts together")
    @admin_only()
    @app_commands.describe(
        days="Number of days to analyze (7, 14, or 30)"
    )
    async def unified_activity(
        self,
        interaction: discord.Interaction,
        days: Literal[7, 14, 30]
    ):
        await self.safe_defer(interaction, ephemeral=True)

        try:
            activity_tracker = self.plugin.activity_tracker

            # Get both Discord and Minecraft stats
            discord_stats = activity_tracker.get_discord_stats(days)
            minecraft_stats = activity_tracker.get_minecraft_stats(days)

            # Get comprehensive member data
            member_data = activity_tracker.get_comprehensive_member_list(days)

            embed = self._create_unified_activity_embed(discord_stats, minecraft_stats, member_data, days)
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            self.plugin.logger.error(f"Error generating unified activity report: {e}")
            await interaction.followup.send(
                "❌ Failed to generate unified activity report. Check server logs for details.",
                ephemeral=True
            )

    def _create_unified_activity_embed(self, discord_stats, minecraft_stats, member_data: dict, days: int) -> discord.Embed:
        """Create a unified activity report embed"""
        embed = discord.Embed(
            title=f"🌐 Unified Activity Report ({days} days)",
            color=0x9B59B6,
            timestamp=discord.utils.utcnow()
        )

        # Cross-platform overview
        total_events = discord_stats.total_events + minecraft_stats.total_events

        embed.add_field(
            name="🌍 Cross-Platform Overview",
            value=f"**Total Events:** {total_events:,}\n"
                  f"**Discord Events:** {discord_stats.total_events:,}\n"
                  f"**Minecraft Events:** {minecraft_stats.total_events:,}\n"
                  f"**Linked Accounts:** {member_data['linked_count']:,}",
            inline=True
        )

        # Platform breakdown
        embed.add_field(
            name="👥 Member Distribution",
            value=f"**Total Members:** {member_data['total_members']:,}\n"
                  f"**Discord Only:** {member_data['discord_only']:,}\n"
                  f"**Minecraft Only:** {member_data['minecraft_only']:,}\n"
                  f"**Both Platforms:** {member_data['linked_count']:,}",
            inline=True
        )

        # Activity rates
        discord_rate = discord_stats.total_events / days if days > 0 else 0
        minecraft_rate = minecraft_stats.total_events / days if days > 0 else 0

        embed.add_field(
            name="📊 Daily Activity Rates",
            value=f"**Discord:** {discord_rate:.1f}/day\n"
                  f"**Minecraft:** {minecraft_rate:.1f}/day\n"
                  f"**Combined:** {(discord_rate + minecraft_rate):.1f}/day",
            inline=True
        )

        # Most active linked accounts
        linked_activity = []
        for member in member_data['active_members'][:10]:
            if member['is_linked']:
                discord_events = member['discord_events_recent']
                minecraft_events = member['minecraft_events_recent']
                total_events = discord_events + minecraft_events

                if total_events > 0:
                    linked_activity.append({
                        'discord_name': member['discord_username'],
                        'minecraft_name': member['minecraft_username'],
                        'discord_events': discord_events,
                        'minecraft_events': minecraft_events,
                        'total_events': total_events
                    })

        if linked_activity:
            linked_activity.sort(key=lambda x: x['total_events'], reverse=True)
            linked_list = []
            for i, account in enumerate(linked_activity[:5], 1):
                discord_name = account['discord_name'] or 'N/A'
                minecraft_name = account['minecraft_name'] or 'N/A'
                d_events = account['discord_events']
                m_events = account['minecraft_events']
                total = account['total_events']

                linked_list.append(
                    f"{i}. **{discord_name}** ↔ **{minecraft_name}**\n"
                    f"   💬 {d_events} | ⛏️ {m_events} | 📊 {total} total"
                )

            embed.add_field(
                name="🔗 Most Active Linked Accounts",
                value="\n".join(linked_list),
                inline=False
            )

        # Engagement insights
        engagement_insights = []
        if member_data['linked_count'] > 0:
            link_rate = (member_data['linked_count'] / member_data['total_members']) * 100
            engagement_insights.append(f"**Account Linking Rate:** {link_rate:.1f}%")

        if discord_stats.total_events > 0 and minecraft_stats.total_events > 0:
            discord_ratio = (discord_stats.total_events / total_events) * 100
            minecraft_ratio = (minecraft_stats.total_events / total_events) * 100
            engagement_insights.extend([
                f"**Discord Activity:** {discord_ratio:.1f}%",
                f"**Minecraft Activity:** {minecraft_ratio:.1f}%"
            ])

        if engagement_insights:
            embed.add_field(
                name="📈 Engagement Insights",
                value="\n".join(engagement_insights),
                inline=False
            )

        embed.add_field(
            name="ℹ️ Legend",
            value="💬 Discord Events | ⛏️ Minecraft Events | 🔗 Linked Account",
            inline=False
        )

        embed.set_footer(text="Use /link_accounts to link more Discord and Minecraft accounts")
        return embed

    @app_commands.command(name="daily_activity", description="View detailed daily activity breakdown for all players")
    @admin_only()
    @app_commands.describe(
        days="Number of days to analyze (7, 14, or 30)",
        show_details="Show individual player details (may send multiple messages)"
    )
    async def daily_activity(
        self,
        interaction: discord.Interaction,
        days: Literal[7, 14, 30] = 14,
        show_details: bool = True
    ):
        await self.safe_defer(interaction, ephemeral=True)

        try:
            activity_tracker = self.plugin.activity_tracker
            daily_data = activity_tracker.get_detailed_daily_activity(days)

            # Send overview first
            overview_embed = self._create_daily_overview_embed(daily_data, days)
            await interaction.followup.send(embed=overview_embed, ephemeral=True)

            if show_details:
                # Send detailed breakdowns (may be multiple messages)
                detail_embeds = self._create_daily_detail_embeds(daily_data, days)

                for i, embed in enumerate(detail_embeds):
                    if i == 0:
                        continue  # Skip first as we already sent overview
                    await interaction.followup.send(embed=embed, ephemeral=True)

                if len(detail_embeds) > 1:
                    await interaction.followup.send(
                        f"📊 Daily activity breakdown complete ({len(detail_embeds)} messages sent)",
                        ephemeral=True
                    )

        except Exception as e:
            self.plugin.logger.error(f"Error generating daily activity: {e}")
            await interaction.followup.send(
                "❌ Failed to generate daily activity report. Check server logs for details.",
                ephemeral=True
            )

    @app_commands.command(name="player_activity", description="View detailed activity for a specific player")
    @admin_only()
    @app_commands.describe(
        player_name="Player name (Discord username or Minecraft name)",
        days="Number of days to analyze (7, 14, or 30)"
    )
    async def player_activity(
        self,
        interaction: discord.Interaction,
        player_name: str,
        days: Literal[7, 14, 30] = 14
    ):
        await self.safe_defer(interaction, ephemeral=True)

        try:
            activity_tracker = self.plugin.activity_tracker
            daily_data = activity_tracker.get_detailed_daily_activity(days)

            # Find player in data
            player_data = self._find_player_in_daily_data(daily_data, player_name)

            if not player_data:
                await interaction.followup.send(
                    f"❌ No activity found for player '{player_name}' in the last {days} days.",
                    ephemeral=True
                )
                return

            embed = self._create_player_activity_embed(player_data, player_name, days)
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            self.plugin.logger.error(f"Error generating player activity: {e}")
            await interaction.followup.send(
                "❌ Failed to generate player activity report. Check server logs for details.",
                ephemeral=True
            )

    def _create_daily_overview_embed(self, daily_data, days):
        """Create overview embed for daily activity"""
        embed = discord.Embed(
            title=f"📅 Daily Activity Overview ({days} days)",
            color=0x3498DB,
            timestamp=discord.utils.utcnow()
        )

        # Calculate totals
        total_discord_events = sum(day['total_discord_events'] for day in daily_data.values())
        total_minecraft_events = sum(day['total_minecraft_events'] for day in daily_data.values())
        total_events = total_discord_events + total_minecraft_events

        # Get unique users across all days
        all_discord_users = set()
        all_minecraft_players = set()

        for day_data in daily_data.values():
            all_discord_users.update(day_data['discord_users'].keys())
            all_minecraft_players.update(day_data['minecraft_players'].keys())

        # Overview stats
        embed.add_field(
            name="📊 Total Activity",
            value=f"**Total Events:** {total_events:,}\n"
                  f"**Discord Events:** {total_discord_events:,}\n"
                  f"**Minecraft Events:** {total_minecraft_events:,}",
            inline=True
        )

        embed.add_field(
            name="👥 Unique Users",
            value=f"**Discord Users:** {len(all_discord_users)}\n"
                  f"**Minecraft Players:** {len(all_minecraft_players)}\n"
                  f"**Total Unique:** {len(all_discord_users | all_minecraft_players)}",
            inline=True
        )

        # Daily averages
        avg_discord = total_discord_events / days if days > 0 else 0
        avg_minecraft = total_minecraft_events / days if days > 0 else 0

        embed.add_field(
            name="📈 Daily Averages",
            value=f"**Discord:** {avg_discord:.1f} events/day\n"
                  f"**Minecraft:** {avg_minecraft:.1f} events/day\n"
                  f"**Combined:** {(avg_discord + avg_minecraft):.1f} events/day",
            inline=True
        )

        return embed

    def _create_daily_detail_embeds(self, daily_data, days):
        """Create detailed daily breakdown embeds (may be multiple)"""
        embeds = []

        # Sort days by date (most recent first)
        sorted_days = sorted(daily_data.items(), reverse=True)

        # Group days into embeds (max 5 days per embed to avoid Discord limits)
        days_per_embed = 5
        for i in range(0, len(sorted_days), days_per_embed):
            embed = discord.Embed(
                title=f"📅 Daily Activity Details (Days {i+1}-{min(i+days_per_embed, len(sorted_days))})",
                color=0x2ECC71,
                timestamp=discord.utils.utcnow()
            )

            day_chunk = sorted_days[i:i+days_per_embed]

            for date, day_data in day_chunk:
                discord_events = day_data['total_discord_events']
                minecraft_events = day_data['total_minecraft_events']
                discord_users = day_data['unique_discord_users']
                minecraft_players = day_data['unique_minecraft_players']

                # Get most active users for this day
                top_discord = sorted(
                    day_data['discord_users'].items(),
                    key=lambda x: x[1]['events'],
                    reverse=True
                )[:3]

                top_minecraft = sorted(
                    day_data['minecraft_players'].items(),
                    key=lambda x: x[1]['events'],
                    reverse=True
                )[:3]

                day_summary = [
                    f"**Events:** 💬 {discord_events} | ⛏️ {minecraft_events}",
                    f"**Users:** 💬 {discord_users} | ⛏️ {minecraft_players}"
                ]

                if top_discord:
                    discord_top = ", ".join([f"{user[1]['username']} ({user[1]['events']})" for user in top_discord])
                    day_summary.append(f"**Top Discord:** {discord_top}")

                if top_minecraft:
                    minecraft_top = ", ".join([f"{user[1]['username']} ({user[1]['events']})" for user in top_minecraft])
                    day_summary.append(f"**Top Minecraft:** {minecraft_top}")

                embed.add_field(
                    name=f"📅 {date}",
                    value="\n".join(day_summary),
                    inline=False
                )

            embeds.append(embed)

        return embeds

    def _find_player_in_daily_data(self, daily_data, player_name):
        """Find a player's activity data across all days"""
        player_name_lower = player_name.lower()
        player_activity = {
            'discord_data': {},
            'minecraft_data': {},
            'found_discord': False,
            'found_minecraft': False,
            'discord_username': None,
            'minecraft_username': None
        }

        for date, day_data in daily_data.items():
            # Search Discord users
            for user_id, user_data in day_data['discord_users'].items():
                if user_data['username'].lower() == player_name_lower:
                    player_activity['discord_data'][date] = user_data
                    player_activity['found_discord'] = True
                    player_activity['discord_username'] = user_data['username']

            # Search Minecraft players
            for player_uuid, player_data in day_data['minecraft_players'].items():
                if player_data['username'].lower() == player_name_lower:
                    player_activity['minecraft_data'][date] = player_data
                    player_activity['found_minecraft'] = True
                    player_activity['minecraft_username'] = player_data['username']

        if not player_activity['found_discord'] and not player_activity['found_minecraft']:
            return None

        return player_activity

    def _create_player_activity_embed(self, player_data, player_name, days):
        """Create detailed activity embed for a specific player"""
        embed = discord.Embed(
            title=f"👤 Player Activity: {player_name}",
            color=0x9B59B6,
            timestamp=discord.utils.utcnow()
        )

        # Player info
        platforms = []
        if player_data['found_discord']:
            platforms.append(f"💬 Discord: {player_data['discord_username']}")
        if player_data['found_minecraft']:
            platforms.append(f"⛏️ Minecraft: {player_data['minecraft_username']}")

        embed.add_field(
            name="🔍 Found On",
            value="\n".join(platforms),
            inline=False
        )

        # Calculate totals
        total_discord_events = sum(day['events'] for day in player_data['discord_data'].values())
        total_minecraft_events = sum(day['events'] for day in player_data['minecraft_data'].values())

        # Discord activity breakdown
        if player_data['found_discord']:
            discord_messages = sum(day['messages'] for day in player_data['discord_data'].values())
            discord_joins = sum(day['joins'] for day in player_data['discord_data'].values())
            discord_voice = sum(day['voice_activity'] for day in player_data['discord_data'].values())

            embed.add_field(
                name="💬 Discord Activity",
                value=f"**Total Events:** {total_discord_events}\n"
                      f"**Messages:** {discord_messages}\n"
                      f"**Joins/Leaves:** {discord_joins}\n"
                      f"**Voice Activity:** {discord_voice}",
                inline=True
            )

        # Minecraft activity breakdown
        if player_data['found_minecraft']:
            minecraft_joins = sum(day['joins'] for day in player_data['minecraft_data'].values())
            minecraft_leaves = sum(day['leaves'] for day in player_data['minecraft_data'].values())

            embed.add_field(
                name="⛏️ Minecraft Activity",
                value=f"**Total Events:** {total_minecraft_events}\n"
                      f"**Joins:** {minecraft_joins}\n"
                      f"**Leaves:** {minecraft_leaves}\n"
                      f"**Sessions:** {minecraft_joins}",
                inline=True
            )

        # Daily breakdown (last 7 days)
        daily_breakdown = []
        sorted_dates = sorted(set(list(player_data['discord_data'].keys()) + list(player_data['minecraft_data'].keys())), reverse=True)

        for date in sorted_dates[:7]:  # Show last 7 days
            discord_events = player_data['discord_data'].get(date, {}).get('events', 0)
            minecraft_events = player_data['minecraft_data'].get(date, {}).get('events', 0)
            total_day = discord_events + minecraft_events

            if total_day > 0:
                daily_breakdown.append(f"**{date}:** {total_day} events (💬{discord_events} ⛏️{minecraft_events})")

        if daily_breakdown:
            embed.add_field(
                name="📅 Recent Daily Activity",
                value="\n".join(daily_breakdown),
                inline=False
            )

        # Activity summary
        total_events = total_discord_events + total_minecraft_events
        active_days = len(set(list(player_data['discord_data'].keys()) + list(player_data['minecraft_data'].keys())))
        avg_events_per_day = total_events / active_days if active_days > 0 else 0

        embed.add_field(
            name="📊 Summary",
            value=f"**Total Events:** {total_events}\n"
                  f"**Active Days:** {active_days}/{days}\n"
                  f"**Avg Events/Day:** {avg_events_per_day:.1f}",
            inline=True
        )

        embed.set_footer(text=f"Activity data for the last {days} days")
        return embed

    @app_commands.command(name="all_players_activity", description="View activity for ALL players on Discord, Minecraft, or both")
    @admin_only()
    @app_commands.describe(
        platform="Choose which platform(s) to show activity for",
        days="Number of days to analyze (7, 14, or 30)",
        sort_by="How to sort the player list"
    )
    async def all_players_activity(
        self,
        interaction: discord.Interaction,
        platform: Literal["discord", "minecraft", "both"] = "both",
        days: Literal[7, 14, 30] = 14,
        sort_by: Literal["activity", "name", "last_seen"] = "activity"
    ):
        await self.safe_defer(interaction, ephemeral=True)

        try:
            activity_tracker = self.plugin.activity_tracker
            daily_data = activity_tracker.get_detailed_daily_activity(days)

            # Collect all players from the daily data
            all_players = self._collect_all_players_from_daily_data(daily_data, platform, days)

            if not all_players:
                await interaction.followup.send(
                    f"❌ No players found with activity on {platform} in the last {days} days.",
                    ephemeral=True
                )
                return

            # Sort players based on criteria
            sorted_players = self._sort_players(all_players, sort_by)

            # Create embeds (multiple messages due to player count)
            embeds = self._create_all_players_embeds(sorted_players, platform, days, sort_by)

            # Send all embeds
            for i, embed in enumerate(embeds):
                await interaction.followup.send(embed=embed, ephemeral=True)

            # Send summary message
            total_players = len(sorted_players)
            total_messages = len(embeds)
            await interaction.followup.send(
                f"📊 **All Players Activity Report Complete**\n"
                f"**Platform:** {platform.title()}\n"
                f"**Period:** {days} days\n"
                f"**Total Players:** {total_players}\n"
                f"**Messages Sent:** {total_messages}",
                ephemeral=True
            )

        except Exception as e:
            self.plugin.logger.error(f"Error generating all players activity: {e}")
            await interaction.followup.send(
                "❌ Failed to generate all players activity report. Check server logs for details.",
                ephemeral=True
            )

    def _collect_all_players_from_daily_data(self, daily_data, platform, days):
        """Collect all players from daily data with their activity stats"""
        all_players = {}

        for date, day_data in daily_data.items():
            # Process Discord users if requested
            if platform in ["discord", "both"]:
                for user_id, user_data in day_data['discord_users'].items():
                    if user_id not in all_players:
                        all_players[user_id] = {
                            'id': user_id,
                            'discord_username': user_data['username'],
                            'minecraft_username': None,
                            'platform': 'discord',
                            'total_events': 0,
                            'discord_events': 0,
                            'minecraft_events': 0,
                            'discord_messages': 0,
                            'discord_joins': 0,
                            'discord_voice': 0,
                            'minecraft_joins': 0,
                            'minecraft_leaves': 0,
                            'last_activity_date': date,
                            'active_days': set(),
                            'daily_breakdown': {}
                        }

                    player = all_players[user_id]
                    player['discord_username'] = user_data['username']  # Update to latest
                    player['discord_events'] += user_data['events']
                    player['total_events'] += user_data['events']
                    player['discord_messages'] += user_data['messages']
                    player['discord_joins'] += user_data['joins']
                    player['discord_voice'] += user_data['voice_activity']
                    player['active_days'].add(date)
                    player['daily_breakdown'][date] = {
                        'discord': user_data['events'],
                        'minecraft': 0
                    }

                    # Update last activity date
                    if date > player['last_activity_date']:
                        player['last_activity_date'] = date

            # Process Minecraft players if requested
            if platform in ["minecraft", "both"]:
                for player_uuid, player_data in day_data['minecraft_players'].items():
                    # For minecraft-only view, use UUID as key
                    # For both view, try to find if this player is linked to a Discord account
                    player_key = player_uuid

                    if platform == "both":
                        # Check if this Minecraft player is linked to a Discord account
                        activity_tracker = self.plugin.activity_tracker
                        link = activity_tracker.get_admin_link_by_minecraft(player_uuid)
                        if link:
                            player_key = link.discord_id  # Use Discord ID as primary key for linked accounts

                    if player_key not in all_players:
                        all_players[player_key] = {
                            'id': player_key,
                            'discord_username': None,
                            'minecraft_username': player_data['username'],
                            'platform': 'minecraft',
                            'total_events': 0,
                            'discord_events': 0,
                            'minecraft_events': 0,
                            'discord_messages': 0,
                            'discord_joins': 0,
                            'discord_voice': 0,
                            'minecraft_joins': 0,
                            'minecraft_leaves': 0,
                            'last_activity_date': date,
                            'active_days': set(),
                            'daily_breakdown': {}
                        }

                        # If this is a linked account, update Discord info
                        if platform == "both" and player_key != player_uuid:
                            activity_tracker = self.plugin.activity_tracker
                            link = activity_tracker.get_admin_link_by_minecraft(player_uuid)
                            if link:
                                all_players[player_key]['discord_username'] = link.discord_username
                                all_players[player_key]['platform'] = 'both'

                    player = all_players[player_key]
                    player['minecraft_username'] = player_data['username']  # Update to latest
                    player['minecraft_events'] += player_data['events']
                    player['total_events'] += player_data['events']
                    player['minecraft_joins'] += player_data['joins']
                    player['minecraft_leaves'] += player_data['leaves']
                    player['active_days'].add(date)

                    if date not in player['daily_breakdown']:
                        player['daily_breakdown'][date] = {'discord': 0, 'minecraft': 0}
                    player['daily_breakdown'][date]['minecraft'] += player_data['events']

                    # Update last activity date
                    if date > player['last_activity_date']:
                        player['last_activity_date'] = date

                    # Update platform if this player has both Discord and Minecraft activity
                    if player['discord_events'] > 0 and player['minecraft_events'] > 0:
                        player['platform'] = 'both'

        # Convert active_days set to count
        for player in all_players.values():
            player['active_days_count'] = len(player['active_days'])
            del player['active_days']  # Remove set for JSON compatibility

        return list(all_players.values())

    def _sort_players(self, players, sort_by):
        """Sort players based on the specified criteria"""
        if sort_by == "activity":
            return sorted(players, key=lambda x: x['total_events'], reverse=True)
        elif sort_by == "name":
            return sorted(players, key=lambda x: (x['discord_username'] or x['minecraft_username'] or 'Unknown').lower())
        elif sort_by == "last_seen":
            return sorted(players, key=lambda x: x['last_activity_date'], reverse=True)
        else:
            return players

    def _create_all_players_embeds(self, players, platform, days, sort_by):
        """Create embeds for all players activity (multiple embeds due to player count)"""
        embeds = []
        players_per_embed = 15  # Limit to avoid Discord embed limits

        total_players = len(players)
        total_embeds = (total_players + players_per_embed - 1) // players_per_embed

        for i in range(0, total_players, players_per_embed):
            embed_players = players[i:i + players_per_embed]
            embed_num = (i // players_per_embed) + 1

            embed = discord.Embed(
                title=f"👥 All Players Activity - {platform.title()} ({days} days)",
                description=f"**Page {embed_num}/{total_embeds}** | Sorted by: {sort_by.replace('_', ' ').title()}",
                color=0x3498DB,
                timestamp=discord.utils.utcnow()
            )

            # Add summary for first embed
            if embed_num == 1:
                total_events = sum(p['total_events'] for p in players)
                avg_events = total_events / len(players) if players else 0
                most_active = players[0] if players else None

                summary_lines = [
                    f"**Total Players:** {total_players}",
                    f"**Total Events:** {total_events:,}",
                    f"**Average Events/Player:** {avg_events:.1f}"
                ]

                if most_active:
                    most_active_name = most_active['discord_username'] or most_active['minecraft_username'] or 'Unknown'
                    summary_lines.append(f"**Most Active:** {most_active_name} ({most_active['total_events']} events)")

                embed.add_field(
                    name="📊 Summary",
                    value="\n".join(summary_lines),
                    inline=False
                )

            # Add players to this embed
            player_lines = []
            for j, player in enumerate(embed_players, 1):
                rank = i + j
                discord_name = player['discord_username'] or 'N/A'
                minecraft_name = player['minecraft_username'] or 'N/A'

                # Determine display name and platform icon
                if player['platform'] == 'both':
                    display_name = f"{discord_name} ↔ {minecraft_name}"
                    icon = "🔗"
                elif player['platform'] == 'discord':
                    display_name = discord_name
                    icon = "💬"
                else:  # minecraft
                    display_name = minecraft_name
                    icon = "⛏️"

                # Activity breakdown
                activity_parts = []
                if platform in ["discord", "both"] and player['discord_events'] > 0:
                    activity_parts.append(f"💬{player['discord_events']}")
                if platform in ["minecraft", "both"] and player['minecraft_events'] > 0:
                    activity_parts.append(f"⛏️{player['minecraft_events']}")

                activity_str = " | ".join(activity_parts) if activity_parts else "No activity"

                player_lines.append(
                    f"{rank}. {icon} **{display_name}**\n"
                    f"    📊 {player['total_events']} total | {activity_str} | 📅 {player['active_days_count']}d"
                )

            embed.add_field(
                name=f"👥 Players {i+1}-{min(i+players_per_embed, total_players)}",
                value="\n".join(player_lines),
                inline=False
            )

            # Add legend
            if platform == "both":
                legend = "🔗 Linked Account | 💬 Discord Only | ⛏️ Minecraft Only"
            elif platform == "discord":
                legend = "💬 Discord Activity | 📊 Total Events | 📅 Active Days"
            else:  # minecraft
                legend = "⛏️ Minecraft Activity | 📊 Total Events | 📅 Active Days"

            embed.add_field(
                name="ℹ️ Legend",
                value=legend,
                inline=False
            )

            embed.set_footer(text=f"Page {embed_num}/{total_embeds} • {total_players} total players")
            embeds.append(embed)

        return embeds
