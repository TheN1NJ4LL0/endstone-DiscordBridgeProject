
import asyncio
import string
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, List, Tuple as Tup
from urllib.parse import quote

import discord  # embeds

from endstone.plugin import Plugin
from endstone.command import Command, CommandSender
from endstone.event import (
    event_handler,
    PlayerChatEvent,
    PlayerJoinEvent,
    PlayerQuitEvent,
    PlayerDeathEvent,
    PlayerCommandEvent,
    BlockBreakEvent,
    BlockPlaceEvent,
    PlayerInteractEvent,
)
from endstone import Player

from .config_schema import BridgeConfig
from .linked_store import LinkedStore
from .bot import DiscordBot
from .util import SyncRunner, translate_component
from .activity_tracker import ActivityTracker
from .grief_tracker import GriefTracker


class DiscordBridgePlugin(Plugin):
    api_version = "0.10"

    @property
    def config(self) -> BridgeConfig:  # type: ignore[override]
        return self._cfg

    commands = {
        "link": {
            "description": "Generate a code to link your Discord account (/verify in Discord).",
            "usages": ["/link"],
            "permissions": ["endstone_discord_bridge.link"],
        }
    }

    permissions = {
        "endstone_discord_bridge.link": {
            "description": "Allow players to use /link to link Discord.",
            "default": True,
        }
    }

    # ---------- lifecycle ----------
    def on_load(self) -> None:
        self.data_folder.mkdir(parents=True, exist_ok=True)

    def on_enable(self) -> None:
        cfg_path = self.data_folder / "config.toml"
        self._cfg = BridgeConfig.load(cfg_path)

        # Linked store
        self.linked_path = self.data_folder / "linked.toml"
        self.linked: LinkedStore = LinkedStore.load(self.linked_path)

        migrated_links = False
        link_cfg = getattr(self._cfg, "linking", None)
        if link_cfg is not None:
            cfg_pending = getattr(link_cfg, "pending", None)
            cfg_links = getattr(link_cfg, "links", None)
            if isinstance(cfg_pending, dict) and cfg_pending:
                self.linked.pending.update(cfg_pending)
                try: cfg_pending.clear()
                except Exception: pass
                migrated_links = True
            if isinstance(cfg_links, dict) and cfg_links:
                self.linked.links.update(cfg_links)
                try: cfg_links.clear()
                except Exception: pass
                migrated_links = True
        if migrated_links:
            self.save_linked()
            try: self._cfg.save(cfg_path)
            except Exception: pass

        # soft-mute store
        self._muted: set[str] = set()

        # offline-safe scoreboard queue: name_lower -> list[(objective, delta, notify)]
        self._score_ops: Dict[str, List[Tup[str, int, str]]] = {}

        # offline-safe command queue: name_lower -> list[(command, notify_msg)]
        self._command_ops: Dict[str, List[Tup[str, str]]] = {}

        # Activity tracker
        self.activity_tracker = ActivityTracker(self.data_folder, self.config)

        # Grief tracker
        self.grief_tracker = GriefTracker(self)

        self.sync = SyncRunner(self.server, self)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.bot_thread: Optional[threading.Thread] = None
        self.bot: Optional[DiscordBot] = None

        self.start_bot_thread()
        self.register_events(self)
        self.logger.info("Discord bridge enabled.")
        self._relay("🟢 **Server started**")

    def on_disable(self) -> None:
        self.logger.info("Shutting down Discord bridge…")
        # Removed shutdown message to Discord as it hangs during server shutdown
        try:
            if self.bot and self.bot.loop and self.bot.loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(self.bot.close(), self.bot.loop)
                try: fut.result(timeout=10)
                except Exception: pass
            if self.loop and self.loop.is_running():
                self.loop.call_soon_threadsafe(self.loop.stop)
            if self.bot_thread and self.bot_thread.is_alive():
                self.bot_thread.join(timeout=5)
        except Exception:
            pass
        self.bot = None

    # ---------- threading / bot ----------
    def start_bot_thread(self) -> None:
        if self.bot_thread and self.bot_thread.is_alive():
            return
        if not self.config.discord.token:
            self.logger.error("No Discord token configured. Set [discord].token in config.toml.")
            return

        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.loop = loop
            bot = DiscordBot(self, self.config)
            self.bot = bot
            loop.create_task(bot.start(self.config.discord.token))
            loop.run_forever()

        self.bot_thread = threading.Thread(target=run, name="DiscordBotThread", daemon=True)
        self.bot_thread.start()

    # ---------- config & store I/O ----------
    def save_linked(self) -> None:
        try:
            self.linked.save(self.linked_path)
        except Exception as e:
            self.logger.error(f"Failed saving linked store: {e}")

    def _relay(self, text: str) -> None:
        """Send a simple message to the relay channel with retry logic"""
        self._queue_simple_message(text, "relay", "system")

    # ---------- helpers ----------
    def _generate_link_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        import random
        return "".join(random.choice(alphabet) for _ in range(6))

    def lookup_name_by_uuid(self, uuid: str) -> Optional[str]:
        try:
            p = self.server.get_player(uuid)
            return p.name if p else None
        except Exception:
            return None

    def _world_and_coords(self, player) -> Tuple[Optional[str], Optional[str]]:
        try:
            lvl = getattr(player, "level", None) or getattr(getattr(player, "location", None), "level", None)
            world = getattr(lvl, "name", None) or getattr(lvl, "level_name", None)
        except Exception:
            world = None
        try:
            loc = getattr(player, "location", None)
            x = int(round(getattr(loc, "x", 0)))
            y = int(round(getattr(loc, "y", 0)))
            z = int(round(getattr(loc, "z", 0)))
            coords = f"{x}, {y}, {z}"
        except Exception:
            coords = None
        return world, coords

    def _minotar(self, name: str) -> str:
        # URL-encode the name to handle spaces and special characters
        encoded_name = quote(name, safe='')
        return (self.config.discord.webhook_avatar_template or "").format(name=encoded_name)

    def _online_player_obj(self, name: str) -> Optional[Player]:
        n = name.lower()
        for p in self.server.online_players:
            if p.name.lower() == n:
                return p
        return None

    # ---- offline-safe scoreboard mutator (main thread only) ----
    def apply_or_queue_score_delta(self, player_name: str, objective: str, delta: int, notify_msg: str) -> bool:
        player = self._online_player_obj(player_name)
        cs = self.server.command_sender
        if player is not None:
            ok = True
            if delta > 0:
                ok = self.server.dispatch_command(cs, f"scoreboard players add {player_name} {objective} {delta}")
            elif delta < 0:
                ok = self.server.dispatch_command(cs, f"scoreboard players remove {player_name} {objective} {abs(delta)}")
            if ok:
                try:
                    player.send_message(notify_msg)
                except Exception:
                    pass
            return ok
        key = player_name.lower()
        self._score_ops.setdefault(key, []).append((objective, delta, notify_msg))
        return True

    def apply_or_queue_command(self, player_name: str, command: str, notify_msg: str = "") -> bool:
        """Queue a command to be executed when the player comes online, or execute immediately if online"""
        player = self._online_player_obj(player_name)
        cs = self.server.command_sender
        if player is not None:
            # Player is online, execute immediately
            ok = self.server.dispatch_command(cs, command)
            if ok and notify_msg:
                try:
                    player.send_message(notify_msg)
                except Exception:
                    pass
            return ok
        # Player is offline, queue the command
        key = player_name.lower()
        self._command_ops.setdefault(key, []).append((command, notify_msg))
        return True

    def _flush_score_ops_for(self, player: Player):
        key = player.name.lower()
        ops = self._score_ops.pop(key, [])
        if not ops:
            return
        cs = self.server.command_sender
        for objective, delta, notify in ops:
            ok = True
            if delta > 0:
                ok = self.server.dispatch_command(cs, f"scoreboard players add {player.name} {objective} {delta}")
            elif delta < 0:
                ok = self.server.dispatch_command(cs, f"scoreboard players remove {player.name} {objective} {abs(delta)}")
            if ok:
                try:
                    player.send_message(notify)
                except Exception:
                    pass

    def _flush_command_ops_for(self, player: Player):
        """Execute all queued commands for a player when they join"""
        key = player.name.lower()
        ops = self._command_ops.pop(key, [])
        if not ops:
            return
        cs = self.server.command_sender
        for command, notify in ops:
            ok = self.server.dispatch_command(cs, command)
            if ok and notify:
                try:
                    player.send_message(notify)
                except Exception:
                    pass

    # ---------- /link ----------
    def on_command(self, sender: CommandSender, command: Command, args: list[str]) -> bool:
        if command.name != "link":
            return False
        if isinstance(sender, Player):
            code = self._generate_link_code()
            uuid = str(sender.unique_id)
            now = datetime.now(timezone.utc)
            exp = now + timedelta(minutes=self.config.linking.code_ttl_minutes)
            self.linked.pending[uuid] = {"code": code, "expires": exp.timestamp(), "name": sender.name}
            self.save_linked()
            sender.send_message(
                f"§aDiscord Link Code: §e{code}§r — Use in Discord: /verify {code} "
                f"(expires in {self.config.linking.code_ttl_minutes}m)"
            )
        else:
            sender.send_message("Run this command in-game.")
        return True

    # ---------- Events (MC → Discord embeds) ----------
    @event_handler
    def on_player_chat(self, event: PlayerChatEvent):
        if getattr(self, "_muted", None) and event.player and event.player.name.lower() in self._muted:
            try:
                event.cancel()
            except Exception:
                try:
                    event.is_cancelled = True
                except Exception:
                    pass
            try:
                event.player.send_message(" §7You are currently muted.§r")
            except Exception:
                pass
            return
        msg = translate_component(self.server, event.message)
        name = event.player.name

        # Filter out SuperEnchants commands (anything starting with -op) from Discord relay
        if msg.strip().startswith("-op"):
            return

        route = "relay"
        pref_staff = self.config.routing.chat_staff_prefix
        pref_trade = self.config.routing.chat_trade_prefix
        if pref_staff and msg.startswith(pref_staff):
            route = "staff"; msg = msg[len(pref_staff):].lstrip()
        elif pref_trade and msg.startswith(pref_trade):
            route = "trade"; msg = msg[len(pref_trade):].lstrip()

        # Always attempt to send, even if bot isn't ready yet - queue it up
        self._queue_discord_message(name, msg, route, "chat")

    @event_handler
    def on_player_join(self, event: PlayerJoinEvent):
        name = event.player.name
        text = self.config.lang.join.format(name=name)
        world, coords = self._world_and_coords(event.player)

        # Track activity
        self.activity_tracker.add_minecraft_activity(
            player_name=name,
            player_uuid=str(event.player.unique_id),
            event_type="join",
            world=world,
            coordinates=coords
        )

        # Always attempt to send join messages, even if bot isn't ready yet
        self._queue_join_leave_message(name, text, world, coords, "join", 0x3BA55C)
        self._flush_score_ops_for(event.player)
        self._flush_command_ops_for(event.player)

    @event_handler
    def on_player_quit(self, event: PlayerQuitEvent):
        name = event.player.name
        text = self.config.lang.quit.format(name=name)
        world, coords = self._world_and_coords(event.player)

        # Track activity
        self.activity_tracker.add_minecraft_activity(
            player_name=name,
            player_uuid=str(event.player.unique_id),
            event_type="leave",
            world=world,
            coordinates=coords
        )

        # Always attempt to send quit messages, even if bot isn't ready yet
        self._queue_join_leave_message(name, text, world, coords, "quit", 0xF59E0B)

    @event_handler
    def on_player_death(self, event: PlayerDeathEvent):
        localized = translate_component(self.server, event.death_message)
        text = self.config.lang.death.format(message=localized)
        name = getattr(getattr(event, "player", None), "name", "Player")
        try:
            world, coords = self._world_and_coords(event.player)  # type: ignore
        except Exception:
            world, coords = None, None

        # Always attempt to send death messages, even if bot isn't ready yet
        self._queue_join_leave_message(name, text, world, coords, "death", 0xED4245)

    @event_handler
    def on_player_command(self, event: PlayerCommandEvent):
        if not self.config.features.command_spy:
            return

        # Always attempt to send command spy messages, even if bot isn't ready yet
        self._queue_simple_message(f"🕵️ {event.player.name}: `{event.command}`", "command_spy", "command_spy")

    @event_handler
    def on_block_break(self, event: BlockBreakEvent):
        """Handle block break events for grief monitoring"""
        if not self.config.features.grief_monitoring:
            return

        try:
            player = event.player
            block = event.block

            # Get exact block coordinates
            location = {
                "x": block.x,
                "y": block.y,
                "z": block.z,
                "world": block.dimension.name if hasattr(block.dimension, 'name') else "unknown"
            }

            # Get block type - this might need adjustment based on actual Endstone API
            block_type = getattr(block, 'type', 'unknown_block')
            if hasattr(block_type, 'name'):
                block_type = block_type.name
            else:
                block_type = str(block_type)

            # Get tool used if available
            tool_used = None
            if hasattr(player, 'inventory') and hasattr(player.inventory, 'item_in_hand'):
                item = player.inventory.item_in_hand
                if item and hasattr(item, 'type'):
                    tool_used = getattr(item.type, 'name', str(item.type))

            # Console logging removed - grief notifications go to Discord only

            # Track the event
            self.grief_tracker.track_block_break(
                player_uuid=str(player.unique_id),
                player_name=player.name,
                block_type=block_type,
                location=location,
                tool_used=tool_used
            )

        except Exception as e:
            self.logger.error(f"Error tracking block break event: {e}")

    @event_handler
    def on_block_place(self, event: BlockPlaceEvent):
        """Handle block place events for grief monitoring"""
        if not self.config.features.grief_monitoring:
            return

        try:
            player = event.player

            # Get block type from the block_placed_state (this is the correct way!)
            block_type = "unknown_block"
            location = {"x": 0, "y": 0, "z": 0, "world": "unknown"}

            # Use block_placed_state to get the block that was actually placed
            if hasattr(event, 'block_placed_state') and event.block_placed_state:
                placed_block = event.block_placed_state
                block_type = placed_block.type  # This is the actual block type placed

                # Get exact coordinates from the placed block
                location = {
                    "x": placed_block.x,
                    "y": placed_block.y,
                    "z": placed_block.z,
                    "world": placed_block.dimension.name if hasattr(placed_block.dimension, 'name') else "unknown"
                }

            # Fallback: try to get from the block property
            elif hasattr(event, 'block') and event.block:
                block = event.block
                block_type = block.type
                location = {
                    "x": block.x,
                    "y": block.y,
                    "z": block.z,
                    "world": block.dimension.name if hasattr(block.dimension, 'name') else "unknown"
                }

            # Get item used from player's inventory
            item_used = None
            if hasattr(player, 'inventory') and hasattr(player.inventory, 'item_in_hand'):
                item = player.inventory.item_in_hand
                if item and hasattr(item, 'type'):
                    item_used = getattr(item.type, 'name', str(item.type))

            # Get item used if not already set
            if not item_used and hasattr(player, 'inventory') and hasattr(player.inventory, 'item_in_hand'):
                item = player.inventory.item_in_hand
                if item and hasattr(item, 'type'):
                    item_used = getattr(item.type, 'name', str(item.type))

            # Console logging removed - grief notifications go to Discord only

            # Track the event
            self.grief_tracker.track_block_place(
                player_uuid=str(player.unique_id),
                player_name=player.name,
                block_type=block_type,
                location=location,
                item_used=item_used
            )

        except Exception as e:
            self.logger.error(f"Error tracking block place event: {e}")

    @event_handler
    def on_player_interact(self, event: PlayerInteractEvent):
        """Handle player interaction events for container access monitoring"""
        if not self.config.features.grief_monitoring:
            return

        try:
            # Check if this event has a block (container interaction)
            if not event.has_block:
                return

            # Get action type - only process right-click actions for containers
            action_type = event.action

            # Only process RIGHT_CLICK_BLOCK actions (opening containers)
            # Check if this is a right-click action using string comparison for now
            action_str = str(action_type).upper()
            if 'RIGHT_CLICK_BLOCK' not in action_str and 'RIGHT_CLICK' not in action_str:
                return

            # Get the clicked block
            block = event.block
            if not block:
                return

            # Get block type
            block_type = block.type

            # Check if this is a monitored container type
            container_types = self.config.grief_monitoring.monitored_containers
            is_container = (block_type in container_types or
                          f"minecraft:{block_type}" in container_types or
                          block_type.replace("minecraft:", "") in [c.replace("minecraft:", "") for c in container_types])

            if not is_container:
                return

            player = event.player

            # Get exact block coordinates
            location = {
                "x": block.x,
                "y": block.y,
                "z": block.z,
                "world": block.dimension.name if hasattr(block.dimension, 'name') else "unknown"
            }

            # Determine action type
            action = "opened"
            if action_type == "right_click_block":
                action = "right-clicked"
            elif action_type == "interact":
                action = "interacted with"

            # Console logging removed - grief notifications go to Discord only

            # Track the event
            self.grief_tracker.track_container_access(
                player_uuid=str(player.unique_id),
                player_name=player.name,
                container_type=block_type,
                location=location,
                action=action
            )

        except Exception as e:
            self.logger.error(f"Error tracking container access event: {e}")

    def _queue_discord_message(self, name: str, msg: str, route: str, msg_type: str = "chat"):
        """Queue a message to be sent to Discord with retry logic"""
        async def send_with_retry():
            max_retries = 3
            retry_delay = 1.0

            for attempt in range(max_retries):
                try:
                    # Wait for bot to be ready if it isn't already
                    if self.bot and self.bot.loop and not self.bot.loop.is_closed():
                        await self.bot.wait_until_ready()

                        avatar = self._minotar(name)
                        description = f"**{name}**\n{msg}"
                        embed = discord.Embed(description=description, color=0x57F287)
                        embed.set_author(name=name, icon_url=avatar)

                        success = False

                        # Try webhook mode first if enabled
                        if self.config.features.webhook_mode and self.config.discord.webhook_url:
                            try:
                                success = await self.bot.send_via_webhook(username=name, text=None, avatar_url=avatar, embed=embed)
                                if success:
                                    self.logger.debug(f"Chat message sent via webhook: {name}: {msg[:50]}...")
                                    return
                                else:
                                    self.logger.warning(f"Webhook send failed for {name}, falling back to channel")
                            except Exception as e:
                                self.logger.warning(f"Webhook send error for {name}: {e}, falling back to channel")

                        # Fallback to channel send
                        if not success:
                            ch = await self.bot._resolve_named_channel(route)
                            if ch:
                                await ch.send(embed=embed)
                                self.logger.debug(f"Chat message sent to channel {route}: {name}: {msg[:50]}...")
                                return
                            else:
                                raise Exception(f"Could not resolve channel: {route}")
                    else:
                        raise Exception("Bot not ready or loop closed")

                except Exception as e:
                    self.logger.warning(f"Attempt {attempt + 1}/{max_retries} failed to send {msg_type} message for {name}: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                    else:
                        self.logger.error(f"Failed to send {msg_type} message for {name} after {max_retries} attempts: {msg[:100]}...")

        # Queue the message send
        if self.bot and self.bot.loop and not self.bot.loop.is_closed():
            asyncio.run_coroutine_threadsafe(send_with_retry(), self.bot.loop)
        else:
            self.logger.warning(f"Cannot queue {msg_type} message for {name} - bot not available: {msg[:50]}...")

    def _queue_join_leave_message(self, name: str, text: str, world: Optional[str], coords: Optional[str], event_type: str, color: int):
        """Queue a join/leave message to be sent to Discord with retry logic"""
        async def send_with_retry():
            max_retries = 3
            retry_delay = 1.0

            for attempt in range(max_retries):
                try:
                    # Wait for bot to be ready if it isn't already
                    if self.bot and self.bot.loop and not self.bot.loop.is_closed():
                        await self.bot.wait_until_ready()

                        avatar = self._minotar(name)

                        # Send to rich channel (join/quit specific)
                        try:
                            ch_rich = await self.bot.route_named(event_type)
                            if ch_rich:
                                embed = discord.Embed(description=text, color=color)
                                embed.set_author(name=name, icon_url=avatar)
                                if world:  embed.add_field(name="🌍 World",  value=f"`{world}`", inline=True)
                                if coords: embed.add_field(name="📍 Coords", value=f"`{coords}`", inline=True)
                                embed.timestamp = discord.utils.utcnow()
                                await ch_rich.send(embed=embed)
                                self.logger.debug(f"{event_type.capitalize()} message sent to {event_type} channel: {name}")
                        except Exception as e:
                            self.logger.warning(f"Failed to send {event_type} message to rich channel for {name}: {e}")

                        # Send minimal version to relay channel
                        try:
                            ch_relay = await self.bot._resolve_named_channel("relay")
                            if ch_relay:
                                embed_min = discord.Embed(description=text, color=color)
                                embed_min.set_author(name=name, icon_url=avatar)
                                embed_min.timestamp = discord.utils.utcnow()
                                await ch_relay.send(embed=embed_min)
                                self.logger.debug(f"{event_type.capitalize()} message sent to relay channel: {name}")
                        except Exception as e:
                            self.logger.warning(f"Failed to send {event_type} message to relay channel for {name}: {e}")

                        return  # Success
                    else:
                        raise Exception("Bot not ready or loop closed")

                except Exception as e:
                    self.logger.warning(f"Attempt {attempt + 1}/{max_retries} failed to send {event_type} message for {name}: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                    else:
                        self.logger.error(f"Failed to send {event_type} message for {name} after {max_retries} attempts")

        # Queue the message send
        if self.bot and self.bot.loop and not self.bot.loop.is_closed():
            asyncio.run_coroutine_threadsafe(send_with_retry(), self.bot.loop)
        else:
            self.logger.warning(f"Cannot queue {event_type} message for {name} - bot not available")

    def _queue_simple_message(self, message: str, route: str, msg_type: str):
        """Queue a simple text message to be sent to Discord with retry logic"""
        async def send_with_retry():
            max_retries = 3
            retry_delay = 1.0

            for attempt in range(max_retries):
                try:
                    # Wait for bot to be ready if it isn't already
                    if self.bot and self.bot.loop and not self.bot.loop.is_closed():
                        await self.bot.wait_until_ready()

                        ch = await self.bot.route_named(route)
                        if ch:
                            await ch.send(message)
                            self.logger.debug(f"{msg_type.capitalize()} message sent to {route}: {message[:50]}...")
                            return
                        else:
                            raise Exception(f"Could not resolve channel: {route}")
                    else:
                        raise Exception("Bot not ready or loop closed")

                except Exception as e:
                    self.logger.warning(f"Attempt {attempt + 1}/{max_retries} failed to send {msg_type} message: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                    else:
                        self.logger.error(f"Failed to send {msg_type} message after {max_retries} attempts: {message[:100]}...")

        # Queue the message send
        if self.bot and self.bot.loop and not self.bot.loop.is_closed():
            asyncio.run_coroutine_threadsafe(send_with_retry(), self.bot.loop)
        else:
            self.logger.warning(f"Cannot queue {msg_type} message - bot not available: {message[:50]}...")
