import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict


@dataclass
class DiscordActivityEntry:
    """Single Discord activity event"""
    user_id: str
    username: str
    event_type: str  # "join", "leave", "message", "voice_join", "voice_leave"
    timestamp: float
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MinecraftActivityEntry:
    """Single Minecraft activity event"""
    player_name: str
    player_uuid: str
    event_type: str  # "join", "leave"
    timestamp: float
    world: Optional[str] = None
    coordinates: Optional[str] = None


@dataclass
class ActivityStats:
    """Activity statistics for a time period"""
    total_events: int = 0
    unique_users: int = 0
    joins: int = 0
    leaves: int = 0
    messages: int = 0
    voice_activity: int = 0
    most_active_users: List[Dict[str, Any]] = field(default_factory=list)
    daily_breakdown: Dict[str, int] = field(default_factory=dict)
    all_users: List[Dict[str, Any]] = field(default_factory=list)  # All users with activity data
    inactive_users: List[Dict[str, Any]] = field(default_factory=list)  # Users with no recent activity


@dataclass
class AdminLinkEntry:
    """Admin-created link between Discord and Minecraft accounts"""
    discord_id: str
    discord_username: str
    minecraft_uuid: str
    minecraft_username: str
    linked_by: str  # Admin who created the link
    linked_at: float  # Timestamp
    notes: str = ""


class ActivityTracker:
    """Tracks and stores Discord and Minecraft activity data"""

    def __init__(self, data_folder: Path, config=None):
        self.data_folder = data_folder
        self.discord_file = data_folder / "discord.json"
        self.minecraft_file = data_folder / "server.json"
        self.admin_links_file = data_folder / "admin_links.json"
        self.config = config

        # In-memory storage (loaded from files)
        self.discord_activity: List[DiscordActivityEntry] = []
        self.minecraft_activity: List[MinecraftActivityEntry] = []
        self.admin_links: List[AdminLinkEntry] = []

        # Load existing data
        self.load_data()
    
    def load_data(self):
        """Load activity data from JSON files"""
        try:
            if self.discord_file.exists():
                with open(self.discord_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.discord_activity = [
                        DiscordActivityEntry(**entry) for entry in data.get('activity', [])
                    ]
        except Exception as e:
            print(f"Error loading Discord activity data: {e}")
            self.discord_activity = []

        try:
            if self.minecraft_file.exists():
                with open(self.minecraft_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.minecraft_activity = [
                        MinecraftActivityEntry(**entry) for entry in data.get('activity', [])
                    ]
        except Exception as e:
            print(f"Error loading Minecraft activity data: {e}")
            self.minecraft_activity = []

        try:
            if self.admin_links_file.exists():
                with open(self.admin_links_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.admin_links = [
                        AdminLinkEntry(**entry) for entry in data.get('links', [])
                    ]
        except Exception as e:
            print(f"Error loading admin links data: {e}")
            self.admin_links = []
    
    def save_data(self):
        """Save activity data to JSON files"""
        try:
            # Save Discord activity
            discord_data = {
                'last_updated': time.time(),
                'activity': [asdict(entry) for entry in self.discord_activity]
            }
            with open(self.discord_file, 'w', encoding='utf-8') as f:
                json.dump(discord_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving Discord activity data: {e}")

        try:
            # Save Minecraft activity
            minecraft_data = {
                'last_updated': time.time(),
                'activity': [asdict(entry) for entry in self.minecraft_activity]
            }
            with open(self.minecraft_file, 'w', encoding='utf-8') as f:
                json.dump(minecraft_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving Minecraft activity data: {e}")

        try:
            # Save admin links
            links_data = {
                'last_updated': time.time(),
                'links': [asdict(entry) for entry in self.admin_links]
            }
            with open(self.admin_links_file, 'w', encoding='utf-8') as f:
                json.dump(links_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving admin links data: {e}")
    
    def add_discord_activity(self, user_id: str, username: str, event_type: str, 
                           channel_id: Optional[str] = None, channel_name: Optional[str] = None,
                           additional_data: Optional[Dict[str, Any]] = None):
        """Add a Discord activity entry"""
        entry = DiscordActivityEntry(
            user_id=str(user_id),
            username=username,
            event_type=event_type,
            timestamp=time.time(),
            channel_id=str(channel_id) if channel_id else None,
            channel_name=channel_name,
            additional_data=additional_data or {}
        )
        self.discord_activity.append(entry)
        self._cleanup_old_entries()
        self.save_data()
    
    def add_minecraft_activity(self, player_name: str, player_uuid: str, event_type: str,
                             world: Optional[str] = None, coordinates: Optional[str] = None):
        """Add a Minecraft activity entry"""
        entry = MinecraftActivityEntry(
            player_name=player_name,
            player_uuid=str(player_uuid),
            event_type=event_type,
            timestamp=time.time(),
            world=world,
            coordinates=coordinates
        )
        self.minecraft_activity.append(entry)
        self._cleanup_old_entries()
        self.save_data()
    
    def _cleanup_old_entries(self, max_days: Optional[int] = None):
        """Remove entries older than max_days to prevent file bloat"""
        if max_days is None:
            max_days = getattr(getattr(self.config, 'activity', None), 'cleanup_days', 90) if self.config else 90
        cutoff_time = time.time() - (max_days * 24 * 60 * 60)
        
        self.discord_activity = [
            entry for entry in self.discord_activity 
            if entry.timestamp > cutoff_time
        ]
        
        self.minecraft_activity = [
            entry for entry in self.minecraft_activity 
            if entry.timestamp > cutoff_time
        ]
    
    def get_discord_stats(self, days: int) -> ActivityStats:
        """Get Discord activity statistics for the specified number of days"""
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        recent_activity = [
            entry for entry in self.discord_activity 
            if entry.timestamp > cutoff_time
        ]
        
        return self._calculate_discord_stats(recent_activity, days)
    
    def get_minecraft_stats(self, days: int) -> ActivityStats:
        """Get Minecraft activity statistics for the specified number of days"""
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        recent_activity = [
            entry for entry in self.minecraft_activity 
            if entry.timestamp > cutoff_time
        ]
        
        return self._calculate_minecraft_stats(recent_activity, days)
    
    def _calculate_discord_stats(self, activity: List[DiscordActivityEntry], days: int) -> ActivityStats:
        """Calculate statistics for Discord activity"""
        stats = ActivityStats()
        stats.total_events = len(activity)
        
        if not activity:
            return stats
        
        # Count unique users
        unique_users = set(entry.user_id for entry in activity)
        stats.unique_users = len(unique_users)
        
        # Count event types
        for entry in activity:
            if entry.event_type == "join":
                stats.joins += 1
            elif entry.event_type == "leave":
                stats.leaves += 1
            elif entry.event_type == "message":
                stats.messages += 1
            elif entry.event_type in ["voice_join", "voice_leave"]:
                stats.voice_activity += 1
        
        # Calculate most active users
        user_activity = {}
        for entry in activity:
            user_activity[entry.user_id] = user_activity.get(entry.user_id, 0) + 1
        
        # Enhanced most active users with linked account info
        enhanced_users = []
        for user_id, count in sorted(user_activity.items(), key=lambda x: x[1], reverse=True)[:10]:
            username = self._get_latest_username(user_id, activity)
            link = self.get_admin_link_by_discord(user_id)
            user_data = {
                "user_id": user_id,
                "username": username,
                "count": count,
                "is_linked": link is not None,
                "minecraft_username": link.minecraft_username if link else None
            }
            enhanced_users.append(user_data)

        stats.most_active_users = enhanced_users
        
        # Daily breakdown
        stats.daily_breakdown = self._get_daily_breakdown(activity, days)
        
        return stats
    
    def _calculate_minecraft_stats(self, activity: List[MinecraftActivityEntry], days: int) -> ActivityStats:
        """Calculate statistics for Minecraft activity"""
        stats = ActivityStats()
        stats.total_events = len(activity)
        
        if not activity:
            return stats
        
        # Count unique players
        unique_players = set(entry.player_uuid for entry in activity)
        stats.unique_users = len(unique_players)
        
        # Count event types
        for entry in activity:
            if entry.event_type == "join":
                stats.joins += 1
            elif entry.event_type == "leave":
                stats.leaves += 1
        
        # Calculate most active players
        player_activity = {}
        for entry in activity:
            player_activity[entry.player_uuid] = player_activity.get(entry.player_uuid, 0) + 1
        
        # Enhanced most active players with linked account info
        enhanced_players = []
        for player_uuid, count in sorted(player_activity.items(), key=lambda x: x[1], reverse=True)[:10]:
            username = self._get_latest_player_name(player_uuid, activity)
            link = self.get_admin_link_by_minecraft(player_uuid)
            player_data = {
                "user_id": player_uuid,
                "username": username,
                "count": count,
                "is_linked": link is not None,
                "discord_username": link.discord_username if link else None
            }
            enhanced_players.append(player_data)

        stats.most_active_users = enhanced_players
        
        # Daily breakdown
        stats.daily_breakdown = self._get_daily_breakdown(activity, days)
        
        return stats
    
    def _get_latest_username(self, user_id: str, activity: List[DiscordActivityEntry]) -> str:
        """Get the most recent username for a Discord user"""
        for entry in reversed(activity):
            if entry.user_id == user_id:
                return entry.username
        return "Unknown"
    
    def _get_latest_player_name(self, player_uuid: str, activity: List[MinecraftActivityEntry]) -> str:
        """Get the most recent player name for a Minecraft player"""
        for entry in reversed(activity):
            if entry.player_uuid == player_uuid:
                return entry.player_name
        return "Unknown"
    
    def _get_daily_breakdown(self, activity: List, days: int) -> Dict[str, int]:
        """Get daily breakdown of activity"""
        daily_counts = {}
        
        # Initialize all days with 0
        for i in range(days):
            date = datetime.now(timezone.utc) - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            daily_counts[date_str] = 0
        
        # Count activity per day
        for entry in activity:
            entry_date = datetime.fromtimestamp(entry.timestamp, timezone.utc)
            date_str = entry_date.strftime("%Y-%m-%d")
            if date_str in daily_counts:
                daily_counts[date_str] += 1
        
        return daily_counts

    # Admin linking methods
    def add_admin_link(self, discord_id: str, discord_username: str, minecraft_uuid: str,
                      minecraft_username: str, linked_by: str, notes: str = "") -> bool:
        """Add an admin-created link between Discord and Minecraft accounts"""
        # Check if link already exists
        for link in self.admin_links:
            if link.discord_id == str(discord_id) or link.minecraft_uuid == str(minecraft_uuid):
                return False  # Link already exists

        link = AdminLinkEntry(
            discord_id=str(discord_id),
            discord_username=discord_username,
            minecraft_uuid=str(minecraft_uuid),
            minecraft_username=minecraft_username,
            linked_by=linked_by,
            linked_at=time.time(),
            notes=notes
        )
        self.admin_links.append(link)
        self.save_data()
        return True

    def remove_admin_link(self, discord_id: str = None, minecraft_uuid: str = None) -> bool:
        """Remove an admin link by Discord ID or Minecraft UUID"""
        for i, link in enumerate(self.admin_links):
            if (discord_id and link.discord_id == str(discord_id)) or \
               (minecraft_uuid and link.minecraft_uuid == str(minecraft_uuid)):
                self.admin_links.pop(i)
                self.save_data()
                return True
        return False

    def get_admin_link_by_discord(self, discord_id: str) -> Optional[AdminLinkEntry]:
        """Get admin link by Discord ID"""
        for link in self.admin_links:
            if link.discord_id == str(discord_id):
                return link
        return None

    def get_admin_link_by_minecraft(self, minecraft_uuid: str) -> Optional[AdminLinkEntry]:
        """Get admin link by Minecraft UUID"""
        for link in self.admin_links:
            if link.minecraft_uuid == str(minecraft_uuid):
                return link
        return None

    def get_all_admin_links(self) -> List[AdminLinkEntry]:
        """Get all admin links"""
        return self.admin_links.copy()

    def get_comprehensive_member_list(self, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive list of all members with activity data"""
        cutoff_time = time.time() - (days * 24 * 60 * 60)

        # Get recent activity
        recent_discord = [e for e in self.discord_activity if e.timestamp > cutoff_time]
        recent_minecraft = [e for e in self.minecraft_activity if e.timestamp > cutoff_time]

        # Track all users
        all_members = {}

        # Process Discord activity
        for entry in self.discord_activity:
            user_id = entry.user_id
            if user_id not in all_members:
                all_members[user_id] = {
                    'discord_id': user_id,
                    'discord_username': entry.username,
                    'minecraft_uuid': None,
                    'minecraft_username': None,
                    'last_discord_activity': entry.timestamp,
                    'last_minecraft_activity': None,
                    'discord_events_recent': 0,
                    'minecraft_events_recent': 0,
                    'total_discord_events': 0,
                    'total_minecraft_events': 0,
                    'is_linked': False,
                    'link_type': None,
                    'days_since_last_activity': 0
                }
            else:
                all_members[user_id]['last_discord_activity'] = max(
                    all_members[user_id]['last_discord_activity'], entry.timestamp
                )
                all_members[user_id]['discord_username'] = entry.username  # Update to latest

            all_members[user_id]['total_discord_events'] += 1
            if entry.timestamp > cutoff_time:
                all_members[user_id]['discord_events_recent'] += 1

        # Process Minecraft activity
        for entry in self.minecraft_activity:
            uuid = entry.player_uuid
            # Find if this player is linked via admin links
            linked_discord = None
            for link in self.admin_links:
                if link.minecraft_uuid == uuid:
                    linked_discord = link.discord_id
                    break

            if linked_discord and linked_discord in all_members:
                # Update existing Discord member with Minecraft data
                member = all_members[linked_discord]
                member['minecraft_uuid'] = uuid
                member['minecraft_username'] = entry.player_name
                member['is_linked'] = True
                member['link_type'] = 'admin'
                if member['last_minecraft_activity'] is None:
                    member['last_minecraft_activity'] = entry.timestamp
                else:
                    member['last_minecraft_activity'] = max(
                        member['last_minecraft_activity'], entry.timestamp
                    )
                member['total_minecraft_events'] += 1
                if entry.timestamp > cutoff_time:
                    member['minecraft_events_recent'] += 1
            else:
                # Create new entry for Minecraft-only player
                member_key = f"mc_{uuid}"
                if member_key not in all_members:
                    all_members[member_key] = {
                        'discord_id': None,
                        'discord_username': None,
                        'minecraft_uuid': uuid,
                        'minecraft_username': entry.player_name,
                        'last_discord_activity': None,
                        'last_minecraft_activity': entry.timestamp,
                        'discord_events_recent': 0,
                        'minecraft_events_recent': 0,
                        'total_discord_events': 0,
                        'total_minecraft_events': 0,
                        'is_linked': False,
                        'link_type': None,
                        'days_since_last_activity': 0
                    }
                else:
                    all_members[member_key]['last_minecraft_activity'] = max(
                        all_members[member_key]['last_minecraft_activity'], entry.timestamp
                    )
                    all_members[member_key]['minecraft_username'] = entry.player_name

                all_members[member_key]['total_minecraft_events'] += 1
                if entry.timestamp > cutoff_time:
                    all_members[member_key]['minecraft_events_recent'] += 1

        # Calculate days since last activity and categorize
        current_time = time.time()
        active_members = []
        inactive_members = []

        for member in all_members.values():
            last_activity = max(
                member['last_discord_activity'] or 0,
                member['last_minecraft_activity'] or 0
            )
            member['days_since_last_activity'] = int((current_time - last_activity) / (24 * 60 * 60))

            if member['days_since_last_activity'] <= days:
                active_members.append(member)
            else:
                inactive_members.append(member)

        # Sort by last activity (most recent first)
        active_members.sort(key=lambda x: max(x['last_discord_activity'] or 0, x['last_minecraft_activity'] or 0), reverse=True)
        inactive_members.sort(key=lambda x: max(x['last_discord_activity'] or 0, x['last_minecraft_activity'] or 0), reverse=True)

        return {
            'active_members': active_members,
            'inactive_members': inactive_members,
            'total_members': len(all_members),
            'active_count': len(active_members),
            'inactive_count': len(inactive_members),
            'linked_count': sum(1 for m in all_members.values() if m['is_linked']),
            'discord_only': sum(1 for m in all_members.values() if m['discord_id'] and not m['minecraft_uuid']),
            'minecraft_only': sum(1 for m in all_members.values() if m['minecraft_uuid'] and not m['discord_id']),
            'analysis_period_days': days
        }

    def get_detailed_daily_activity(self, days: int = 30) -> Dict[str, Any]:
        """Get detailed daily activity breakdown for all players"""
        cutoff_time = time.time() - (days * 24 * 60 * 60)

        # Get recent activity
        recent_discord = [e for e in self.discord_activity if e.timestamp > cutoff_time]
        recent_minecraft = [e for e in self.minecraft_activity if e.timestamp > cutoff_time]

        # Initialize daily data structure
        daily_data = {}
        for i in range(days):
            date = datetime.now(timezone.utc) - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            daily_data[date_str] = {
                'discord_users': {},
                'minecraft_players': {},
                'total_discord_events': 0,
                'total_minecraft_events': 0,
                'unique_discord_users': set(),
                'unique_minecraft_players': set()
            }

        # Process Discord activity
        for entry in recent_discord:
            entry_date = datetime.fromtimestamp(entry.timestamp, timezone.utc)
            date_str = entry_date.strftime("%Y-%m-%d")

            if date_str in daily_data:
                user_id = entry.user_id
                username = entry.username

                if user_id not in daily_data[date_str]['discord_users']:
                    daily_data[date_str]['discord_users'][user_id] = {
                        'username': username,
                        'events': 0,
                        'joins': 0,
                        'leaves': 0,
                        'messages': 0,
                        'voice_activity': 0
                    }

                daily_data[date_str]['discord_users'][user_id]['events'] += 1
                daily_data[date_str]['discord_users'][user_id]['username'] = username  # Update to latest
                daily_data[date_str]['total_discord_events'] += 1
                daily_data[date_str]['unique_discord_users'].add(user_id)

                # Count event types
                if entry.event_type == "join":
                    daily_data[date_str]['discord_users'][user_id]['joins'] += 1
                elif entry.event_type == "leave":
                    daily_data[date_str]['discord_users'][user_id]['leaves'] += 1
                elif entry.event_type == "message":
                    daily_data[date_str]['discord_users'][user_id]['messages'] += 1
                elif entry.event_type in ["voice_join", "voice_leave"]:
                    daily_data[date_str]['discord_users'][user_id]['voice_activity'] += 1

        # Process Minecraft activity
        for entry in recent_minecraft:
            entry_date = datetime.fromtimestamp(entry.timestamp, timezone.utc)
            date_str = entry_date.strftime("%Y-%m-%d")

            if date_str in daily_data:
                player_uuid = entry.player_uuid
                player_name = entry.player_name

                if player_uuid not in daily_data[date_str]['minecraft_players']:
                    daily_data[date_str]['minecraft_players'][player_uuid] = {
                        'username': player_name,
                        'events': 0,
                        'joins': 0,
                        'leaves': 0,
                        'sessions': 0
                    }

                daily_data[date_str]['minecraft_players'][player_uuid]['events'] += 1
                daily_data[date_str]['minecraft_players'][player_uuid]['username'] = player_name  # Update to latest
                daily_data[date_str]['total_minecraft_events'] += 1
                daily_data[date_str]['unique_minecraft_players'].add(player_uuid)

                # Count event types
                if entry.event_type == "join":
                    daily_data[date_str]['minecraft_players'][player_uuid]['joins'] += 1
                elif entry.event_type == "leave":
                    daily_data[date_str]['minecraft_players'][player_uuid]['leaves'] += 1

        # Convert sets to counts for JSON serialization
        for date_data in daily_data.values():
            date_data['unique_discord_users'] = len(date_data['unique_discord_users'])
            date_data['unique_minecraft_players'] = len(date_data['unique_minecraft_players'])

        return daily_data
