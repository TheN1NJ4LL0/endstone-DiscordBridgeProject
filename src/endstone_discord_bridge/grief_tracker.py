import time
import threading
import asyncio
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from collections import deque

try:
    import discord
except ImportError:
    discord = None


@dataclass
class GriefEvent:
    """Represents a grief monitoring event"""
    timestamp: float
    player_uuid: str
    player_name: str
    event_type: str  # "block_break", "block_place", "container_access"
    block_type: str
    location: Dict[str, Any]  # {"x": int, "y": int, "z": int, "world": str}
    additional_data: Dict[str, Any] = None  # Extra data like container contents, tool used, etc.

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GriefEvent':
        """Create from dictionary"""
        return cls(**data)


class GriefTracker:
    """Tracks and manages grief monitoring events"""

    def __init__(self, plugin):
        self.plugin = plugin
        self.config = plugin.config.grief_monitoring
        self.lock = threading.Lock()

        # In-memory storage for recent events (for cooldown checking)
        self.recent_events = {}

        # In-memory storage for searchable events (last 48 hours, max 10000 events)
        # Using deque for efficient append/pop operations
        self.stored_events: deque = deque(maxlen=10000)

        # Start cleanup thread
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        """Start background thread to clean up old events"""
        def cleanup_loop():
            while True:
                try:
                    time.sleep(3600)  # Run every hour
                    self.cleanup_old_events()
                except Exception as e:
                    self.plugin.logger.error(f"Error during grief event cleanup: {e}")

        cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        cleanup_thread.start()

    def _should_track_event(self, event: GriefEvent, store_event: bool = True) -> bool:
        """Check if event should be tracked based on cooldown and configuration

        Args:
            event: The grief event to check
            store_event: If True, check if event should be stored. If False, only check if it should be sent to Discord.
        """
        # Check if grief monitoring is enabled
        if not self.plugin.config.features.grief_monitoring:
            return False

        # Check specific event type settings
        if event.event_type == "block_break" and not self.config.track_block_break:
            return False
        if event.event_type == "block_place" and not self.config.track_block_place:
            return False
        if event.event_type == "container_access" and not self.config.track_container_access:
            return False

        # For block breaks: check monitored_blocks filter (empty = monitor all)
        if event.event_type == "block_break":
            if self.config.monitored_blocks and event.block_type not in self.config.monitored_blocks:
                return False

        # For block places: check grief_place_blocks filter (only store/notify grief blocks)
        if event.event_type == "block_place":
            if self.config.grief_place_blocks and event.block_type not in self.config.grief_place_blocks:
                return False

        # Check container type for container access events
        if event.event_type == "container_access":
            if event.block_type not in self.config.monitored_containers:
                return False

        # Check cooldown to prevent spam
        event_key = f"{event.player_uuid}:{event.event_type}:{event.block_type}:{event.location['x']}:{event.location['y']}:{event.location['z']}"
        current_time = time.time()

        if event_key in self.recent_events:
            last_time = self.recent_events[event_key]
            if current_time - last_time < self.config.event_cooldown:
                return False

        self.recent_events[event_key] = current_time
        return True

    def track_block_break(self, player_uuid: str, player_name: str, block_type: str,
                          location: Dict[str, Any], tool_used: str = None) -> bool:
        """Track a block break event"""
        event = GriefEvent(
            timestamp=time.time(),
            player_uuid=player_uuid,
            player_name=player_name,
            event_type="block_break",
            block_type=block_type,
            location=location,
            additional_data={"tool_used": tool_used} if tool_used else {}
        )

        if not self._should_track_event(event):
            return False

        # Store event in memory for searching
        with self.lock:
            self.stored_events.append(event)

        # Send to Discord
        self._send_discord_notification(event, "grief_block_break")
        return True

    def track_block_place(self, player_uuid: str, player_name: str, block_type: str,
                          location: Dict[str, Any], item_used: str = None) -> bool:
        """Track a block place event"""
        event = GriefEvent(
            timestamp=time.time(),
            player_uuid=player_uuid,
            player_name=player_name,
            event_type="block_place",
            block_type=block_type,
            location=location,
            additional_data={"item_used": item_used} if item_used else {}
        )

        if not self._should_track_event(event):
            return False

        # Store event in memory for searching
        with self.lock:
            self.stored_events.append(event)

        # Send to Discord
        self._send_discord_notification(event, "grief_block_place")
        return True

    def track_container_access(self, player_uuid: str, player_name: str, container_type: str,
                               location: Dict[str, Any], action: str = "open") -> bool:
        """Track a container access event"""
        event = GriefEvent(
            timestamp=time.time(),
            player_uuid=player_uuid,
            player_name=player_name,
            event_type="container_access",
            block_type=container_type,
            location=location,
            additional_data={"action": action}
        )

        if not self._should_track_event(event):
            return False

        # Store event in memory for searching
        with self.lock:
            self.stored_events.append(event)

        # Send to Discord
        self._send_discord_notification(event, "grief_container")
        return True

    def _send_discord_notification(self, event: GriefEvent, channel_key: str):
        """Send grief notification to Discord"""
        try:
            # Get the appropriate channel
            channel_id = getattr(self.plugin.config.channels, channel_key, None)
            if not channel_id:
                return

            # Format the notification message
            timestamp_str = datetime.fromtimestamp(event.timestamp, timezone.utc).strftime("%H:%M:%S")
            location_str = f"({event.location['x']}, {event.location['y']}, {event.location['z']})"
            world_str = event.location.get('world', 'unknown')

            # Create embed based on event type
            if event.event_type == "block_break":
                title = "🔨 Block Broken"
                color = 0xe74c3c  # Red
                description = f"**{event.player_name}** broke **{event.block_type}**"
            elif event.event_type == "block_place":
                title = "🧱 Block Placed"
                color = 0x2ecc71  # Green
                description = f"**{event.player_name}** placed **{event.block_type}**"
            else:  # container_access
                title = "📦 Container Accessed"
                color = 0xf39c12  # Orange
                action = event.additional_data.get('action', 'accessed')
                description = f"**{event.player_name}** {action} **{event.block_type}**"

            embed_data = {
                "title": title,
                "description": description,
                "color": color,
                "timestamp": datetime.fromtimestamp(event.timestamp, timezone.utc).isoformat(),
                "fields": [
                    {
                        "name": "📍 Location",
                        "value": f"{location_str} in {world_str}",
                        "inline": True
                    },
                    {
                        "name": "🕐 Time",
                        "value": timestamp_str,
                        "inline": True
                    }
                ]
            }

            # Add additional data if available
            if event.additional_data:
                for key, value in event.additional_data.items():
                    if value:
                        embed_data["fields"].append({
                            "name": key.replace('_', ' ').title(),
                            "value": str(value),
                            "inline": True
                        })

            # Send to Discord channel
            self._queue_discord_message(channel_key, embed_data)

        except Exception as e:
            self.plugin.logger.error(f"Failed to send grief notification: {e}")

    def _queue_discord_message(self, channel_key: str, embed_data: Dict[str, Any]):
        """Send grief notification to Discord channel using the plugin's message system"""

        async def send_with_retry():
            max_retries = 3
            retry_delay = 1.0

            for attempt in range(max_retries):
                try:
                    # Wait for bot to be ready if it isn't already
                    if self.plugin.bot and self.plugin.bot.loop and not self.plugin.bot.loop.is_closed():
                        await self.plugin.bot.wait_until_ready()

                        # Resolve the channel using the bot's routing system
                        ch = await self.plugin.bot._resolve_named_channel(channel_key)
                        if ch:
                            # Convert embed_data dict to discord.Embed
                            if discord:
                                embed = discord.Embed(
                                    title=embed_data.get("title", ""),
                                    description=embed_data.get("description", ""),
                                    color=embed_data.get("color", 0xe74c3c)
                                )

                            # Add fields if present
                            for field in embed_data.get("fields", []):
                                embed.add_field(
                                    name=field["name"],
                                    value=field["value"],
                                    inline=field.get("inline", False)
                                )

                            # Set timestamp if present
                            if "timestamp" in embed_data:
                                embed.timestamp = discord.utils.utcnow()

                            await ch.send(embed=embed)
                            # Console logging removed - notifications visible in Discord
                            return
                        else:
                            raise Exception(f"Could not resolve channel: {channel_key}")
                    else:
                        raise Exception("Bot not ready or loop closed")

                except Exception as e:
                    # Only log final failure to reduce console clutter
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                    else:
                        self.plugin.logger.error(f"Failed to send grief notification after {max_retries} attempts: {e}")

        # Queue the message send
        if self.plugin.bot and self.plugin.bot.loop and not self.plugin.bot.loop.is_closed():
            import asyncio
            asyncio.run_coroutine_threadsafe(send_with_retry(), self.plugin.bot.loop)
        else:
            # Only log if bot is completely unavailable (rare case)
            pass

    def get_events_by_player(self, player_uuid: str, event_type: Optional[str] = None, hours: Optional[int] = None, days: Optional[int] = None) -> List[GriefEvent]:
        """Get events for a specific player, optionally filtered by event type

        Args:
            player_uuid: Player's UUID
            event_type: Optional filter for event type
            hours: Time range in hours (takes precedence over days)
            days: Time range in days (used if hours not specified)
        """
        # Calculate cutoff time based on hours or days
        if hours is not None:
            cutoff_time = time.time() - (hours * 3600)
        elif days is not None:
            cutoff_time = time.time() - (days * 24 * 3600)
        else:
            cutoff_time = time.time() - (7 * 24 * 3600)  # Default 7 days

        with self.lock:
            events = [
                e for e in self.stored_events
                if e.player_uuid == player_uuid and e.timestamp >= cutoff_time
            ]

        # Filter by event type if specified
        if event_type:
            events = [e for e in events if e.event_type == event_type]

        # Sort by timestamp, most recent first
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events

    def get_events_by_location(self, location: Dict[str, Any], radius: int, hours: Optional[int] = None, days: Optional[int] = None) -> List[GriefEvent]:
        """Get events near a specific location within a given radius

        Args:
            location: Dict with x, y, z coordinates
            radius: Search radius in blocks
            hours: Time range in hours (takes precedence over days)
            days: Time range in days (used if hours not specified)
        """
        # Calculate cutoff time based on hours or days
        if hours is not None:
            cutoff_time = time.time() - (hours * 3600)
        elif days is not None:
            cutoff_time = time.time() - (days * 24 * 3600)
        else:
            cutoff_time = time.time() - (7 * 24 * 3600)  # Default 7 days

        x, y, z = location['x'], location['y'], location['z']

        with self.lock:
            events = [
                e for e in self.stored_events
                if e.timestamp >= cutoff_time and
                abs(e.location['x'] - x) <= radius and
                abs(e.location['y'] - y) <= radius and
                abs(e.location['z'] - z) <= radius
            ]

        # Sort by timestamp, most recent first
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events

    def get_stats(self, hours: Optional[int] = None, days: Optional[int] = None) -> Dict[str, Any]:
        """Get detailed statistics for grief events

        Args:
            hours: Time range in hours (takes precedence over days)
            days: Time range in days (used if hours not specified)
        """
        # Calculate cutoff time based on hours or days
        if hours is not None:
            cutoff_time = time.time() - (hours * 3600)
            time_label = f"{hours} hour{'s' if hours != 1 else ''}"
        elif days is not None:
            cutoff_time = time.time() - (days * 24 * 3600)
            time_label = f"{days} day{'s' if days != 1 else ''}"
        else:
            cutoff_time = time.time() - (7 * 24 * 3600)
            time_label = "7 days"

        with self.lock:
            recent_events = [e for e in self.stored_events if e.timestamp >= cutoff_time]

        # Count by type
        break_count = sum(1 for e in recent_events if e.event_type == "block_break")
        place_count = sum(1 for e in recent_events if e.event_type == "block_place")
        container_count = sum(1 for e in recent_events if e.event_type == "container_access")

        # Count by player
        player_counts = {}
        for event in recent_events:
            player_counts[event.player_name] = player_counts.get(event.player_name, 0) + 1

        # Count most broken blocks
        broken_blocks = {}
        for event in recent_events:
            if event.event_type == "block_break":
                broken_blocks[event.block_type] = broken_blocks.get(event.block_type, 0) + 1
        most_broken = [{"block_type": k, "count": v} for k, v in sorted(broken_blocks.items(), key=lambda x: x[1], reverse=True)]

        # Count most placed blocks
        placed_blocks = {}
        for event in recent_events:
            if event.event_type == "block_place":
                placed_blocks[event.block_type] = placed_blocks.get(event.block_type, 0) + 1
        most_placed = [{"block_type": k, "count": v} for k, v in sorted(placed_blocks.items(), key=lambda x: x[1], reverse=True)]

        # Count most accessed containers
        accessed_containers = {}
        for event in recent_events:
            if event.event_type == "container_access":
                accessed_containers[event.block_type] = accessed_containers.get(event.block_type, 0) + 1
        most_accessed = [{"block_type": k, "count": v} for k, v in sorted(accessed_containers.items(), key=lambda x: x[1], reverse=True)]

        return {
            "total_events": len(recent_events),
            "block_breaks": break_count,
            "block_places": place_count,
            "container_accesses": container_count,
            "unique_players": len(player_counts),
            "most_broken_blocks": most_broken,
            "most_placed_blocks": most_placed,
            "most_accessed_containers": most_accessed,
            "time_range": time_label
        }

    def cleanup_old_events(self):
        """Clean up old events from memory"""
        # Clean up recent events cache - keep only last hour for cooldown
        current_time = time.time()
        self.recent_events = {k: v for k, v in self.recent_events.items() if current_time - v < 3600}

        # Clean up stored events - keep based on retention_days config (default 30 days)
        retention_seconds = self.config.retention_days * 24 * 3600
        cutoff_time = current_time - retention_seconds
        with self.lock:
            # Convert deque to list, filter, and recreate deque
            filtered = [e for e in self.stored_events if e.timestamp >= cutoff_time]
            self.stored_events.clear()
            self.stored_events.extend(filtered)
