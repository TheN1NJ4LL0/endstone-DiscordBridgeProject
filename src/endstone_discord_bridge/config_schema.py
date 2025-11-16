
import tomllib, json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class DiscordSection:
    token: str = ""
    guild_id: int = 0
    admin_role_ids: list[int] = field(default_factory=lambda: [0])
    dev_guild_id: int = 0
    webhook_url: str = ""
    webhook_avatar_template: str = "https://minotar.net/avatar/{name}.png"


@dataclass
class FeaturesSection:
    relay_edits: bool = True
    relay_deletes: bool = True
    command_spy: bool = False
    advancements: bool = False
    nick_sync: bool = True
    webhook_mode: bool = False
    list_dm_default: bool = True
    activity_tracking: bool = True
    grief_monitoring: bool = False


@dataclass
class PresenceSection:
    type: str = "playing"  # playing|listening|watching|competing|custom
    template: str = "Playing with {online} players"


@dataclass
class AnnouncementsSection:
    enabled: bool = False
    time_h: int = 12
    time_m: int = 0
    message: str = "High-noon event starts now!"


@dataclass
class ChannelsSection:
    relay: int = 0
    global_: int = 0  # stored as global_ in Python, written as 'global' in TOML
    staff: int = 0
    audit: int = 0                 # NEW: dedicated audit channel
    heartbeat: int = 0
    trade: int = 0
    welcome: int = 0      # NEW
    leave: int = 0        # NEW
    grief_block_break: int = 0  # NEW: grief monitoring - block breaks
    grief_block_place: int = 0  # NEW: grief monitoring - block places
    grief_container: int = 0    # NEW: grief monitoring - container access

    def to_names(self) -> dict[str, int]:
        return {
            "relay": self.relay,
            "global": self.global_,
            "staff": self.staff,
            "audit": self.audit,
            "heartbeat": self.heartbeat,
            "trade": self.trade,
            "welcome": self.welcome,  # NEW
            "leave": self.leave,  # NEW
            "grief_block_break": self.grief_block_break,  # NEW
            "grief_block_place": self.grief_block_place,  # NEW
            "grief_container": self.grief_container,      # NEW
        }


@dataclass
class RoutingSection:
    join: str = "global"
    quit: str = "global"
    death: str = "global"
    command_spy: str = "staff"
    advancements: str = "global"
    announcements: str = "relay"
    audit_log: str = "audit"   # default now points to dedicated audit channel
    chat_staff_prefix: str = "[STAFF]"
    chat_trade_prefix: str = "[trade]"


@dataclass
class LinkingSection:
    # TTL only; pending/links kept for back-compat and optional in-file use
    code_ttl_minutes: int = 10
    pending: dict[str, dict[str, Any]] = field(default_factory=dict)  # uuid -> {code, expires, name}
    links: dict[str, str] = field(default_factory=dict)               # uuid -> discord_id


@dataclass
class EconomySection:
    scoreboard_objective: str = "Money"


@dataclass
class ActivitySection:
    enabled: bool = True
    cleanup_days: int = 90  # Days to keep activity data before cleanup
    track_messages: bool = True
    track_voice: bool = True
    track_member_events: bool = True


@dataclass
class GriefMonitoringSection:
    track_block_break: bool = True
    track_block_place: bool = True
    track_container_access: bool = True
    retention_days: int = 30
    monitored_blocks: list[str] = field(default_factory=list)
    # Grief blocks to monitor for placement (empty = monitor all)
    grief_place_blocks: list[str] = field(default_factory=lambda: [
        "minecraft:lava",
        "minecraft:water",
        "minecraft:fire",
        "minecraft:soul_fire",
        "minecraft:tnt",
        "minecraft:end_crystal",
        "minecraft:obsidian",
        "minecraft:cobweb",
        "minecraft:soul_sand",
        "minecraft:soul_soil",
        "minecraft:bedrock",
        "minecraft:barrier",
        "minecraft:structure_block",
        "minecraft:command_block",
        "minecraft:chain_command_block",
        "minecraft:repeating_command_block"
    ])
    monitored_containers: list[str] = field(default_factory=lambda: [
        "minecraft:chest",
        "minecraft:trapped_chest",
        "minecraft:ender_chest",
        "minecraft:shulker_box",
        "minecraft:barrel",
        "minecraft:hopper",
        "minecraft:dropper",
        "minecraft:dispenser"
    ])
    event_cooldown: int = 1


@dataclass
class LangSection:
    join: str = "➡️ {name} joined the server."
    quit: str = "⬅️ {name} left the server."
    death: str = "{message}"


@dataclass
class BridgeConfig:
    discord: DiscordSection = field(default_factory=DiscordSection)
    features: FeaturesSection = field(default_factory=FeaturesSection)
    presence: PresenceSection = field(default_factory=PresenceSection)
    announcements: AnnouncementsSection = field(default_factory=AnnouncementsSection)
    channels: ChannelsSection = field(default_factory=ChannelsSection)
    routing: RoutingSection = field(default_factory=RoutingSection)
    linking: LinkingSection = field(default_factory=LinkingSection)
    economy: EconomySection = field(default_factory=EconomySection)
    activity: ActivitySection = field(default_factory=ActivitySection)
    grief_monitoring: GriefMonitoringSection = field(default_factory=GriefMonitoringSection)
    lang: LangSection = field(default_factory=LangSection)

    @staticmethod
    def load(path: Path) -> "BridgeConfig":
        if not path.exists():
            cfg = BridgeConfig()
            cfg.save(path)
            return cfg

        raw = path.read_text(encoding="utf-8")
        data = tomllib.loads(raw)

        def as_section(section_cls, key):
            src = dict(data.get(key, {}))
            # map TOML 'channels.global' -> dataclass 'global_'
            if key == "channels" and "global" in src and "global_" not in src:
                src["global_"] = src.pop("global")
            return section_cls(**{**asdict(section_cls()), **src})

        cfg = BridgeConfig(
            discord=as_section(DiscordSection, "discord"),
            features=as_section(FeaturesSection, "features"),
            presence=as_section(PresenceSection, "presence"),
            announcements=as_section(AnnouncementsSection, "announcements"),
            channels=as_section(ChannelsSection, "channels"),
            routing=as_section(RoutingSection, "routing"),
            linking=as_section(LinkingSection, "linking"),
            economy=as_section(EconomySection, "economy"),
            activity=as_section(ActivitySection, "activity"),
            grief_monitoring=as_section(GriefMonitoringSection, "grief_monitoring"),
            lang=as_section(LangSection, "lang"),
        )
        return cfg

    def save(self, path: Path):
        # Minimal TOML writer (no external deps)
        def _quote(s: str) -> str:
            return json.dumps(s)

        def _val(v) -> str:
            if isinstance(v, bool):
                return "true" if v else "false"
            if isinstance(v, int):
                return str(v)
            if isinstance(v, float):
                return ("%f" % v).rstrip("0").rstrip(".")
            if isinstance(v, str):
                return _quote(v)
            if isinstance(v, list):
                return "[" + ", ".join(_val(x) for x in v) + "]"
            if isinstance(v, dict):
                items = []
                for k, vv in v.items():
                    items.append(f"{k} = {_val(vv)}")
                return "{" + ", ".join(items) + "}"
            return _quote(str(v))

        data = asdict(self)
        # map dataclass 'channels.global_' -> TOML 'channels.global'
        if "channels" in data and isinstance(data["channels"], dict):
            ch = data["channels"]
            if "global_" in ch:
                ch["global"] = ch.pop("global_")

        lines: list[str] = []
        for section, content in data.items():
            if not isinstance(content, dict):
                continue
            lines.append(f"[{section}]")
            for k, v in content.items():
                lines.append(f"{k} = {_val(v)}")
            lines.append("")
        out = "\n".join(lines).rstrip() + "\n"

        tmp = path.with_suffix(".tmp")
        tmp.write_text(out, encoding="utf-8")
        tmp.replace(path)
