
import asyncio
from concurrent.futures import Future
from typing import Any, Callable

import discord
from discord import app_commands
from discord.ext import commands


class SyncRunner:
    """Run callables on the Endstone main thread and await their result from asyncio."""
    def __init__(self, server, plugin):
        self.server = server
        self.plugin = plugin

    async def run(self, func: Callable[[], Any], timeout: float | None = 15.0) -> Any:
        fut: Future = Future()

        def _wrap():
            try:
                fut.set_result(func())
            except Exception as e:
                fut.set_exception(e)

        self.server.scheduler.run_task(self.plugin, _wrap, delay=0)
        loop = asyncio.get_running_loop()
        return await asyncio.wrap_future(fut, loop=loop)

    def run_fire_and_forget(self, func: Callable[[], Any]) -> None:
        self.server.scheduler.run_task(self.plugin, func, delay=0)


def admin_only(permission_msg: str = "❌ You need an admin role or Server Admin to use this."):
    """Slash command check: allow Discord admins or members with configured admin_role_ids."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure(permission_msg)
        if interaction.user.guild_permissions.administrator:
            return True
        bot = interaction.client  # our DiscordBot
        allowed_ids = set(getattr(getattr(bot, "plugin_config", None), "discord", None).admin_role_ids or [])
        if any(r.id in allowed_ids for r in interaction.user.roles):
            return True
        raise app_commands.CheckFailure(permission_msg)

    def decorator(func):
        return app_commands.check(predicate)(func)

    return decorator


class MinecraftCogBase(commands.Cog):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.plugin = bot.plugin  # type: ignore[attr-defined]
        self.server = self.plugin.server
        self.sync = SyncRunner(self.server, self.plugin)

    async def _run_on_server_thread(self, func: Callable[[], Any]) -> Any:
        return await self.sync.run(func)

    async def safe_defer(self, interaction: discord.Interaction, ephemeral: bool = True):
        try:
            await interaction.response.defer(ephemeral=ephemeral)
        except Exception:
            pass


def translate_component(server, component) -> str:
    try:
        lang = getattr(server, "language", None)
        if lang and component is not None:
            return lang.translate(component)
    except Exception:
        pass
    return str(component)
