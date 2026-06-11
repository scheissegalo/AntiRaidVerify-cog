"""Role-based quarantine management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord

from .models import GuildSettings

if TYPE_CHECKING:
    from .logging import EventLogger
    from .storage import Storage


class SetupError(Exception):
    """Raised when guild configuration is invalid for quarantine operations."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class QuarantineManager:
    """Assign and remove quarantine roles with hierarchy checks."""

    def __init__(self, storage: "Storage", event_logger: "EventLogger") -> None:
        self.storage = storage
        self.event_logger = event_logger

    def validate_settings(self, guild: discord.Guild, settings: GuildSettings) -> list[str]:
        """Return a list of setup issues; empty list means OK."""
        issues: list[str] = []
        if not settings.verification_channel_id:
            issues.append("Verification channel is not set.")
        if not settings.unverified_role_id:
            issues.append("Unverified role is not set.")
        if not settings.verified_role_id:
            issues.append("Verified role is not set (recommended).")

        me = guild.me
        if me is None:
            issues.append("Bot member not found in guild.")
            return issues

        for role_id, label in (
            (settings.unverified_role_id, "Unverified"),
            (settings.verified_role_id, "Verified"),
        ):
            if not role_id:
                continue
            role = guild.get_role(role_id)
            if role is None:
                issues.append(f"{label} role (ID {role_id}) no longer exists.")
            elif role >= me.top_role:
                issues.append(f"Bot role must be above {label} role.")

        if settings.verification_channel_id:
            channel = guild.get_channel(settings.verification_channel_id)
            if channel is None:
                issues.append("Verification channel no longer exists.")
            elif isinstance(channel, discord.TextChannel):
                perms = channel.permissions_for(me)
                if not perms.send_messages or not perms.embed_links:
                    issues.append("Bot lacks Send Messages/Embed Links in verification channel.")

        if not me.guild_permissions.manage_roles:
            issues.append("Bot lacks Manage Roles permission.")

        return issues

    def get_role(self, guild: discord.Guild, role_id: Optional[int]) -> Optional[discord.Role]:
        if role_id is None:
            return None
        return guild.get_role(role_id)

    async def apply_quarantine(
        self, member: discord.Member, settings: GuildSettings
    ) -> None:
        issues = self.validate_settings(member.guild, settings)
        if issues:
            raise SetupError("; ".join(issues))

        unverified = self.get_role(member.guild, settings.unverified_role_id)
        if unverified is None:
            raise SetupError("Unverified role not found.")

        if unverified in member.roles:
            return

        try:
            await member.add_roles(unverified, reason="AntiRaidVerify: suspicious join quarantine")
        except discord.Forbidden as exc:
            raise SetupError(f"Cannot assign unverified role: {exc}") from exc

    async def release_quarantine(
        self, member: discord.Member, settings: GuildSettings
    ) -> None:
        unverified = self.get_role(member.guild, settings.unverified_role_id)
        verified = self.get_role(member.guild, settings.verified_role_id)

        roles_to_remove = []
        roles_to_add = []

        if unverified and unverified in member.roles:
            roles_to_remove.append(unverified)
        if verified and verified not in member.roles:
            roles_to_add.append(verified)

        try:
            if roles_to_remove:
                await member.remove_roles(
                    *roles_to_remove,
                    reason="AntiRaidVerify: verification complete",
                )
            if roles_to_add:
                await member.add_roles(
                    *roles_to_add,
                    reason="AntiRaidVerify: verification complete",
                )
        except discord.Forbidden as exc:
            raise SetupError(f"Cannot update roles on verify: {exc}") from exc

    def get_verification_channel(
        self, guild: discord.Guild, settings: GuildSettings
    ) -> Optional[discord.TextChannel]:
        if not settings.verification_channel_id:
            return None
        channel = guild.get_channel(settings.verification_channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel
        return None

    def member_has_whitelist_role(
        self, member: discord.Member, settings: GuildSettings
    ) -> bool:
        whitelist_ids = set(settings.whitelist_role_ids)
        if not whitelist_ids:
            return False
        return any(role.id in whitelist_ids for role in member.roles)
