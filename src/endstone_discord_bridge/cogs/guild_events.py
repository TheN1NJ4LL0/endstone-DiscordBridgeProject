from __future__ import annotations

import discord
from discord.ext import commands


class GuildEvents(commands.Cog):
    """Posts rich embeds when members join/leave the Discord guild."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # We assume DiscordBot sets self.plugin to the Endstone plugin instance
        self.plugin = getattr(bot, "plugin", None)

    # Helper: restrict to the configured primary guild if set
    def _is_primary_guild(self, guild: discord.Guild | None) -> bool:
        if guild is None:
            return False
        cfg = getattr(self.plugin, "config", None)
        if not cfg:
            return True
        gid = int(getattr(cfg.discord, "guild_id", 0) or 0)
        return gid == 0 or guild.id == gid

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not self._is_primary_guild(member.guild):
            return

        # Track Discord member join activity
        if (self.plugin and hasattr(self.plugin, 'activity_tracker') and
            self.plugin.config.activity.enabled and self.plugin.config.activity.track_member_events):
            self.plugin.activity_tracker.add_discord_activity(
                user_id=str(member.id),
                username=member.display_name,
                event_type="join",
                additional_data={
                    "account_created": member.created_at.isoformat(),
                    "joined_at": member.joined_at.isoformat() if member.joined_at else None
                }
            )

        # Resolve target channel by name "welcome" from [channels]
        ch = await self.bot._resolve_named_channel("welcome")  # provided by DiscordBot
        if not ch:
            return

        # Build nice welcome embed
        embed = discord.Embed(
            title="👋 New Member",
            description=f"{member.mention} joined the server.",
            color=0x3BA55C,  # green
        )
        try:
            embed.set_thumbnail(url=member.display_avatar.url)
        except Exception:
            pass
        embed.add_field(name="User", value=f"{member} (`{member.id}`)", inline=False)
        if member.created_at:
            embed.add_field(
                name="Account Created",
                value=discord.utils.format_dt(member.created_at, style="R"),
                inline=True,
            )
        if member.guild and member.guild.member_count is not None:
            embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        embed.timestamp = discord.utils.utcnow()

        try:
            await ch.send(embed=embed)  # type: ignore[arg-type]
        except Exception:
            # Never crash the bridge on Discord API hiccups
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Note: member may be a cached Member; if not cached, discord.py still passes a Member-ish object
        guild = member.guild if hasattr(member, "guild") else None
        if not self._is_primary_guild(guild):
            return

        # Track Discord member leave activity
        if (self.plugin and hasattr(self.plugin, 'activity_tracker') and
            self.plugin.config.activity.enabled and self.plugin.config.activity.track_member_events):
            self.plugin.activity_tracker.add_discord_activity(
                user_id=str(member.id),
                username=getattr(member, 'display_name', getattr(member, 'name', 'Unknown')),
                event_type="leave",
                additional_data={
                    "account_created": member.created_at.isoformat() if hasattr(member, 'created_at') else None
                }
            )

        ch = await self.bot._resolve_named_channel("leave")
        if not ch:
            return

        embed = discord.Embed(
            title="🚪 Member Left",
            description=f"**{getattr(member, 'name', 'A user')}** has left the server.",
            color=0xED4245,  # red
        )
        # We may not always have an avatar here, but try
        try:
            embed.set_thumbnail(url=member.display_avatar.url)
        except Exception:
            pass

        tag = f"{getattr(member, 'name', 'unknown')}#{getattr(member, 'discriminator', '0000')}"
        uid = getattr(member, "id", None)
        embed.add_field(name="User", value=f"{tag}" + (f" (`{uid}`)" if uid else ""), inline=False)

        if guild and guild.member_count is not None:
            embed.add_field(name="Member Count", value=str(guild.member_count), inline=True)

        embed.timestamp = discord.utils.utcnow()

        try:
            await ch.send(embed=embed)  # type: ignore[arg-type]
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Track voice activity for activity monitoring"""
        if not self._is_primary_guild(member.guild):
            return

        if (not self.plugin or not hasattr(self.plugin, 'activity_tracker') or
            not self.plugin.config.activity.enabled or not self.plugin.config.activity.track_voice):
            return

        # Track voice joins
        if before.channel is None and after.channel is not None:
            self.plugin.activity_tracker.add_discord_activity(
                user_id=str(member.id),
                username=member.display_name,
                event_type="voice_join",
                channel_id=str(after.channel.id),
                channel_name=after.channel.name,
                additional_data={
                    "channel_type": str(after.channel.type),
                    "member_count": len(after.channel.members) if after.channel else 0
                }
            )

        # Track voice leaves
        elif before.channel is not None and after.channel is None:
            self.plugin.activity_tracker.add_discord_activity(
                user_id=str(member.id),
                username=member.display_name,
                event_type="voice_leave",
                channel_id=str(before.channel.id),
                channel_name=before.channel.name,
                additional_data={
                    "channel_type": str(before.channel.type),
                    "member_count": len(before.channel.members) if before.channel else 0
                }
            )
