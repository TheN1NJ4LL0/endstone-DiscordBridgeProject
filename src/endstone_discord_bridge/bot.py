
import asyncio
from datetime import datetime, timedelta
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

from .config_schema import BridgeConfig
from .cogs.guild_events import GuildEvents

PRESENCE_MAP = {
    "playing":   discord.ActivityType.playing,
    "listening": discord.ActivityType.listening,
    "watching":  discord.ActivityType.watching,
    "competing": discord.ActivityType.competing,
    "custom":    discord.ActivityType.custom,
}


class DiscordBot(commands.Bot):
    def __init__(self, plugin, config: BridgeConfig):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="/", intents=intents)
        self.plugin = plugin
        self.plugin_config = config
        self.logger = plugin.logger

        self._presence_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._announce_task: Optional[asyncio.Task] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._heartbeat_msg_id: Optional[int] = None

    # ---------------- helpers ----------------
    async def _ensure_http(self):
        if not self._session:
            self._session = aiohttp.ClientSession()

    async def _resolve_named_channel(self, name: str):
        ch_id = (self.plugin_config.channels.to_names().get(name) or 0)
        if not ch_id:
            return None
        ch = self.get_channel(int(ch_id))
        if ch is None:
            try:
                ch = await self.fetch_channel(int(ch_id))  # type: ignore
            except Exception as e:
                self.logger.error(f"Cannot fetch channel {name} ({ch_id}): {e}")
                return None
        return ch  # type: ignore

    async def route_named(self, route_name: str):
        target_name = getattr(self.plugin_config.routing, route_name)
        return await self._resolve_named_channel(target_name)

    def _is_primary_guild(self, guild: discord.Guild) -> bool:
        """Check if this is the configured primary guild"""
        if guild is None:
            return False
        gid = int(self.plugin_config.discord.guild_id or 0)
        return gid == 0 or guild.id == gid

    # ---------------- presence / heartbeat / announcements ----------------
    async def _presence_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                p = self.plugin_config.presence

                def stats():
                    s = self.plugin.server
                    return len(list(s.online_players)), getattr(s, "current_tps", None), getattr(s, "current_mspt", None)

                online, tps, mspt = await self.plugin.sync.run(stats)

                template = (p.template or "").replace("{players}", "{online}")
                try:
                    text = template.format(online=online, tps=tps, mspt=mspt)
                except Exception:
                    text = f"{online} online"

                activity = discord.Activity(type=PRESENCE_MAP.get(p.type, discord.ActivityType.playing), name=text)
                await self.change_presence(activity=activity)
            except Exception as e:
                self.logger.error(f"presence loop: {e}")
            await asyncio.sleep(60)

    async def _heartbeat_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                ch = await self._resolve_named_channel("heartbeat")
                if ch:
                    def collect():
                        s = self.plugin.server
                        tps = getattr(s, "current_tps", None)
                        mspt = getattr(s, "current_mspt", None)
                        players = [p.name for p in s.online_players]
                        return tps, mspt, players

                    tps, mspt, players = await self.plugin.sync.run(collect)
                    desc = [f"**Status:** Online"]
                    if tps is not None and mspt is not None:
                        desc.append(f"**TPS:** {tps:.2f} | **MSPT:** {mspt:.2f} ms")
                    desc.append(f"**Players ({len(players)}):** {', '.join(players) or 'None'}")
                    embed = discord.Embed(title="Server Heartbeat", description="\n".join(desc), color=0x5865F2)

                    if self._heartbeat_msg_id:
                        try:
                            msg = await ch.fetch_message(self._heartbeat_msg_id)  # type: ignore
                            await msg.edit(embed=embed)
                        except Exception:
                            m = await ch.send(embed=embed)  # type: ignore
                            self._heartbeat_msg_id = m.id
                    else:
                        m = await ch.send(embed=embed)  # type: ignore
                        self._heartbeat_msg_id = m.id
            except Exception as e:
                self.logger.error(f"heartbeat loop: {e}")
            await asyncio.sleep(3600)

    async def _announcements_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                ann = self.plugin_config.announcements
                if not ann.enabled:
                    await asyncio.sleep(300)
                    continue
                now = datetime.now()
                run_at = now.replace(hour=ann.time_h, minute=ann.time_m, second=0, microsecond=0)
                if run_at <= now:
                    run_at += timedelta(days=1)
                await asyncio.sleep((run_at - now).total_seconds())
                ch = await self.route_named("announcements")
                if ch:
                    await ch.send(ann.message)  # type: ignore
            except Exception as e:
                self.logger.error(f"announcements loop: {e}")
            await asyncio.sleep(10)

    # ---------------- audit helper ----------------
    async def audit(self, text: str):
        ch = await self.route_named("audit_log")
        if ch:
            try:
                await ch.send(embed=discord.Embed(title="Audit", description=text, color=0x2B2D31))  # type: ignore
            except Exception as e:
                self.logger.error(f"audit send failed: {e}")

    # ---------------- Discord lifecycle ----------------
    async def setup_hook(self) -> None:
        from .cogs.public import AccountLinkCommands
        from .cogs.status import ServerStatusCommands
        from .cogs.admin import AdminCommands
        from .cogs.activity import ActivityCommands

        await self.add_cog(AccountLinkCommands(self))
        await self.add_cog(ServerStatusCommands(self))
        await self.add_cog(AdminCommands(self))
        await self.add_cog(ActivityCommands(self))
        await self.add_cog(GuildEvents(self))
        
        try:
            if self.plugin_config.discord.dev_guild_id:
                g = discord.Object(id=int(self.plugin_config.discord.dev_guild_id))
                # copy globals so dev guild sees updates instantly
                self.tree.copy_global_to(guild=g)
                synced = await self.tree.sync(guild=g)
                self.logger.info(f"Synced {len(synced)} commands to Dev Guild {g.id}.")
            else:
                synced = await self.tree.sync()
                self.logger.info(f"Synced {len(synced)} commands globally (propagation may take time).")
        except Exception as e:
            self.logger.error(f"Failed to sync application commands: {e}")

        self._presence_task = asyncio.create_task(self._presence_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._announce_task = asyncio.create_task(self._announcements_loop())

    async def on_ready(self):
        self.logger.info(f"Discord bot logged in as {self.user}")

    async def close(self):
        try:
            if self._session:
                await self._session.close()
        finally:
            await super().close()

    # ---------------- Discord -> MC relay ----------------
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # Track Discord message activity (for all channels, not just relay)
        if (message.guild and self._is_primary_guild(message.guild) and
            self.plugin_config.activity.enabled and self.plugin_config.activity.track_messages):
            self.plugin.activity_tracker.add_discord_activity(
                user_id=str(message.author.id),
                username=message.author.display_name,
                event_type="message",
                channel_id=str(message.channel.id),
                channel_name=getattr(message.channel, 'name', 'Unknown'),
                additional_data={"message_length": len(message.content or "")}
            )

        relay_id = self.plugin_config.channels.relay
        if message.channel.id != int(relay_id):
            return
        content = (message.content or "").strip()
        if not content:
            return

        # Find linked MC name for dual display
        def linked_mc_name():
            for uuid, did in self.plugin.linked.links.items():
                if did == str(message.author.id):
                    try:
                        p = self.plugin.server.get_player(uuid)
                        return p.name if p else None
                    except Exception:
                        return None
            return None

        mc_name = await self.plugin.sync.run(linked_mc_name)
        label = f"§9Discord§r:{message.author.display_name}"
        if mc_name:
            label += f" ↔ {mc_name}"

        def send_to_mc():
            try:
                self.plugin.server.broadcast_message(f"<{label}> {content}")
                self.logger.debug(f"Discord message relayed to server: {message.author.display_name}: {content[:50]}...")
            except Exception as e:
                self.logger.error(f"Failed to relay Discord message to server: {e}")
        self.plugin.sync.run_fire_and_forget(send_to_mc)

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not self.plugin_config.features.relay_edits:
            return
        if before.author.bot or before.channel.id != int(self.plugin_config.channels.relay):
            return
        def send():
            try:
                self.plugin.server.broadcast_message(f"[edit] <§9Discord§r:{before.author.display_name}> {after.content}")
                self.logger.debug(f"Discord edit relayed to server: {before.author.display_name}")
            except Exception as e:
                self.logger.error(f"Failed to relay Discord edit to server: {e}")
        self.plugin.sync.run_fire_and_forget(send)

    async def on_message_delete(self, message: discord.Message):
        if not self.plugin_config.features.relay_deletes:
            return
        if message.author.bot or message.channel.id != int(self.plugin_config.channels.relay):
            return
        def send():
            try:
                self.plugin.server.broadcast_message(f"[delete] <§9Discord§r:{message.author.display_name}> (message removed)")
                self.logger.debug(f"Discord delete relayed to server: {message.author.display_name}")
            except Exception as e:
                self.logger.error(f"Failed to relay Discord delete to server: {e}")
        self.plugin.sync.run_fire_and_forget(send)

    # ---------------- webhook (optional embeds for MC->Discord) ----------------
    async def send_via_webhook(
        self,
        username: str,
        text: Optional[str] = None,
        avatar_url: Optional[str] = None,
        embed: Optional[discord.Embed] = None,
    ):
        await self._ensure_http()
        url = self.plugin_config.discord.webhook_url
        if not url:
            return False
        try:
            payload = {"username": username}
            if avatar_url:
                payload["avatar_url"] = avatar_url
            if embed is not None:
                payload["embeds"] = [embed.to_dict()]  # type: ignore
            else:
                payload["content"] = text or ""
            async with self._session.post(url, json=payload) as resp:
                return resp.status in (200, 204)
        except Exception as e:
            self.logger.error(f"webhook send failed: {e}")
            return False
