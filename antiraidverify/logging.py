"""Structured logging to guild log channels."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord

from .constants import (
    COLOR_ADMIN,
    COLOR_ERROR,
    COLOR_SUCCESS,
    COLOR_SUSPICIOUS,
    COLOR_TIMEOUT,
)
from .models import GuildSettings, PendingVerification, ScoreResult

if TYPE_CHECKING:
    from .storage import Storage

log = logging.getLogger("red.antiraidverify")


class EventLogger:
    """Send audit embeds to configured log channels."""

    def __init__(self, storage: "Storage") -> None:
        self.storage = storage

    async def _get_log_channel(
        self, guild: discord.Guild, settings: GuildSettings
    ) -> Optional[discord.TextChannel]:
        if not settings.log_channel_id:
            return None
        channel = guild.get_channel(settings.log_channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel
        return None

    async def log_suspicious_join(
        self,
        guild: discord.Guild,
        member: discord.Member,
        score: ScoreResult,
        mass_join: bool = False,
    ) -> None:
        settings = await self.storage.get_guild_settings(guild.id)
        embed = discord.Embed(
            title="Suspicious Join Detected",
            color=COLOR_SUSPICIOUS,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
        embed.add_field(name="Score", value=str(score.total), inline=True)
        embed.add_field(name="Account Age", value=f"{score.account_age_days} days", inline=True)
        if score.factors:
            factors_text = "\n".join(f"+{pts} {name}" for name, pts in score.factors.items())
            embed.add_field(name="Factors", value=factors_text, inline=False)
        if mass_join:
            embed.add_field(
                name="Mass Join Alert",
                value="High join rate detected in this server.",
                inline=False,
            )
        embed.set_footer(text="AntiRaidVerify")
        await self._send(guild, settings, embed, f"Suspicious join: {member} score={score.total}")

    async def log_verification_success(
        self,
        guild: discord.Guild,
        member: discord.Member,
        pending: Optional[PendingVerification],
        manual: bool = False,
        moderator: Optional[discord.Member] = None,
    ) -> None:
        settings = await self.storage.get_guild_settings(guild.id)
        embed = discord.Embed(
            title="Verification Successful" if not manual else "Manual Verification",
            color=COLOR_SUCCESS if not manual else COLOR_ADMIN,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
        if pending:
            duration = discord.utils.utcnow().timestamp() - pending.joined_at
            embed.add_field(
                name="Time in Quarantine",
                value=f"{duration / 3600:.1f} hours",
                inline=True,
            )
            embed.add_field(name="Score", value=str(pending.score), inline=True)
        if manual and moderator:
            embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        embed.set_footer(text="AntiRaidVerify")
        await self._send(guild, settings, embed, f"Verified: {member}")

    async def log_timeout_action(
        self,
        guild: discord.Guild,
        member: discord.Member,
        action: str,
        reason: str,
    ) -> None:
        settings = await self.storage.get_guild_settings(guild.id)
        embed = discord.Embed(
            title=f"Verification Timeout — {action.title()}",
            color=COLOR_TIMEOUT,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
        embed.add_field(name="Action", value=action, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text="AntiRaidVerify")
        await self._send(guild, settings, embed, f"Timeout {action}: {member}")

    async def log_manual_quarantine(
        self,
        guild: discord.Guild,
        member: discord.Member,
        moderator: discord.Member,
    ) -> None:
        settings = await self.storage.get_guild_settings(guild.id)
        embed = discord.Embed(
            title="Manual Quarantine",
            color=COLOR_ADMIN,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
        embed.add_field(name="Moderator", value=moderator.mention, inline=True)
        embed.set_footer(text="AntiRaidVerify")
        await self._send(guild, settings, embed, f"Manual quarantine: {member} by {moderator}")

    async def log_error(
        self,
        guild: Optional[discord.Guild],
        context: str,
        error: Exception,
    ) -> None:
        embed = discord.Embed(
            title="Error",
            color=COLOR_ERROR,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Context", value=context, inline=False)
        embed.add_field(name="Error", value=f"`{type(error).__name__}: {error}`", inline=False)
        embed.set_footer(text="AntiRaidVerify")
        log.error("%s: %s", context, error, exc_info=error)
        if guild is not None:
            settings = await self.storage.get_guild_settings(guild.id)
            await self._send(guild, settings, embed, f"Error: {context} — {error}")

    async def _send(
        self,
        guild: discord.Guild,
        settings: GuildSettings,
        embed: discord.Embed,
        fallback_message: str,
    ) -> None:
        channel = await self._get_log_channel(guild, settings)
        if channel is None:
            log.info("[%s] %s", guild.id, fallback_message)
            return
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as exc:
            log.warning("Failed to send log embed in guild %s: %s", guild.id, exc)
