"""Background timeout enforcement for unverified members."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING

import discord

from .constants import TIMEOUT_POLL_INTERVAL_SECONDS
from .models import GuildSettings

if TYPE_CHECKING:
    from .antiraidverify import AntiRaidVerify

log = logging.getLogger("red.antiraidverify.timeout")


class TimeoutManager:
    """Periodically enforce verification timeouts."""

    def __init__(self, cog: "AntiRaidVerify") -> None:
        self.cog = cog
        self._task: asyncio.Task | None = None

    async def run(self) -> None:
        await self.cog.bot.wait_until_ready()
        while True:
            try:
                await self._process_expired()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("Timeout loop error: %s", exc, exc_info=exc)
            await asyncio.sleep(TIMEOUT_POLL_INTERVAL_SECONDS)

    async def _process_expired(self) -> None:
        import time

        now = time.time()
        pending_list = await self.cog.storage.get_all_pending()
        for pending in pending_list:
            if pending.expires_at > now:
                continue
            guild = self.cog.bot.get_guild(pending.guild_id)
            if guild is None:
                await self.cog.storage.clear_pending(pending.guild_id, pending.user_id)
                continue
            settings = await self.cog.storage.get_guild_settings(guild.id)
            member = guild.get_member(pending.user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(pending.user_id)
                except discord.NotFound:
                    await self._cleanup(guild, pending, settings)
                    continue

            await self._enforce_timeout(guild, member, pending, settings)

    async def _enforce_timeout(
        self,
        guild: discord.Guild,
        member: discord.Member,
        pending,
        settings: GuildSettings,
    ) -> None:
        reason = "AntiRaidVerify: verification timeout"
        action = settings.timeout_action

        try:
            if action == "ban":
                until = None
                if settings.ban_duration_hours > 0:
                    until = discord.utils.utcnow() + timedelta(hours=settings.ban_duration_hours)
                await guild.ban(
                    member,
                    reason=reason,
                    delete_message_seconds=86400,
                    until=until,
                )
            else:
                await member.kick(reason=reason)
        except discord.Forbidden:
            await self.cog.event_logger.log_error(
                guild, f"timeout {action}", Exception("Missing kick/ban permissions")
            )
        except discord.HTTPException as exc:
            await self.cog.event_logger.log_error(guild, f"timeout {action}", exc)
        else:
            await self.cog.event_logger.log_timeout_action(
                guild, member, action, reason
            )

        await self._cleanup(guild, pending, settings)

    async def _cleanup(self, guild, pending, settings: GuildSettings) -> None:
        await self.cog.verification.cleanup_message(guild, pending, settings)
        await self.cog.storage.clear_pending(pending.guild_id, pending.user_id)
